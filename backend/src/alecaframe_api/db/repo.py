"""Async SQLite repository — all queries live here."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

log = logging.getLogger("alecaframe.db.repo")
_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


async def _try_add_column(
    conn: aiosqlite.Connection, table: str, column_decl: str
) -> None:
    """ALTER TABLE … ADD COLUMN that's safe to re-run. Used for tiny schema
    bumps so we don't need a full migration system. The expected failure on
    a re-run is `duplicate column name` — anything else is re-raised."""
    try:
        await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column_decl}")
    except aiosqlite.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise


@dataclass
class Repo:
    db_path: Path
    _conn: aiosqlite.Connection | None = field(default=None, init=False, repr=False)

    def _require_conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Repo.connect() has not been awaited")
        return self._conn

    async def connect(self) -> None:
        if self._conn is not None:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await aiosqlite.connect(self.db_path)
        try:
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            await conn.execute("PRAGMA foreign_keys=ON")
            await conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
            # Idempotent column adds for existing DBs (schema.sql `CREATE
            # TABLE IF NOT EXISTS` is a no-op when the table is already
            # there, so new columns wouldn't appear without an explicit
            # ALTER). Each add is wrapped — "duplicate column name" is the
            # expected error on already-migrated DBs and is swallowed.
            await _try_add_column(conn, "riven_auction", "owner_status TEXT")
            await _try_add_column(conn, "fissure_subscription", "planet TEXT")
            await _try_add_column(conn, "fissure_subscription", "node TEXT")
            await conn.commit()
        except Exception:
            await conn.close()
            raise
        self._conn = conn

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    # ----------------------------------------------------------- snapshots

    async def insert_snapshot(
        self,
        *,
        slug: str,
        ts: int,
        side: str,
        online_only: int,
        count_orders: int,
        min_price: int | None,
        p10: int | None,
        p25: int | None,
        median: int | None,
        p75: int | None,
        p90: int | None,
        max_price: int | None,
        volume_qty: int,
        top5: list[int],
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO order_snapshots
               (slug, ts, side, online_only, count_orders, min_price,
                p10, p25, median, p75, p90, max_price, volume_qty, top5_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                slug,
                ts,
                side,
                online_only,
                count_orders,
                min_price,
                p10,
                p25,
                median,
                p75,
                p90,
                max_price,
                volume_qty,
                json.dumps(top5),
            ),
        )
        await conn.commit()

    async def history(
        self,
        *,
        slug: str,
        side: str,
        online_only: int,
        since_ts: int,
        until_ts: int | None = None,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        if until_ts is None:
            sql = (
                "SELECT * FROM order_snapshots "
                "WHERE slug=? AND side=? AND online_only=? AND ts >= ? "
                "ORDER BY ts DESC LIMIT ?"
            )
            args = (slug, side, online_only, since_ts, limit)
        else:
            sql = (
                "SELECT * FROM order_snapshots "
                "WHERE slug=? AND side=? AND online_only=? AND ts BETWEEN ? AND ? "
                "ORDER BY ts DESC LIMIT ?"
            )
            args = (slug, side, online_only, since_ts, until_ts, limit)
        async with conn.execute(sql, args) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(zip(cols, row, strict=False))
            try:
                d["top5"] = json.loads(d.pop("top5_json") or "[]")
            except Exception:
                d["top5"] = []
            out.append(d)
        return out

    # ----------------------------------------------------------- signals

    async def insert_signal_event(
        self,
        ts: int,
        slug: str,
        signal_type: str,
        payload: dict,
        dedup_key: str,
    ) -> bool:
        """Returns True if newly inserted, False if dedup'd."""
        conn = self._require_conn()
        try:
            await conn.execute(
                """INSERT INTO signal_events (ts, slug, signal_type, payload_json, dedup_key)
                   VALUES (?, ?, ?, ?, ?)""",
                (ts, slug, signal_type, json.dumps(payload), dedup_key),
            )
            await conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False  # unique constraint on dedup_key

    async def recent_signals(
        self,
        *,
        types: list[str] | None = None,
        slug: str | None = None,
        limit: int = 50,
        since_ts: int = 0,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        clauses = ["ts >= ?"]
        args: list[Any] = [since_ts]
        if types:
            placeholders = ",".join("?" * len(types))
            clauses.append(f"signal_type IN ({placeholders})")
            args.extend(types)
        if slug:
            clauses.append("slug = ?")
            args.append(slug)
        where = " AND ".join(clauses)
        sql = f"SELECT * FROM signal_events WHERE {where} ORDER BY ts DESC LIMIT ?"
        args.append(limit)
        async with conn.execute(sql, args) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(zip(cols, row, strict=False))
            raw = d.pop("payload_json") or "{}"
            try:
                d["payload"] = json.loads(raw)
            except json.JSONDecodeError as e:
                log.warning("bad payload_json id=%s: %s", d.get("id"), e)
                d["payload"] = {}
            out.append(d)
        return out

    # ----------------------------------------------------------- sets

    async def upsert_set_composition(
        self, set_slug: str, part_slug: str, qty: int
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO set_compositions (set_slug, part_slug, qty)
               VALUES (?, ?, ?)""",
            (set_slug, part_slug, qty),
        )
        await conn.commit()

    async def read_set_compositions(self) -> list[dict[str, Any]]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT set_slug, part_slug, qty FROM set_compositions"
        ) as cursor:
            rows = await cursor.fetchall()
        grouped: dict[str, dict[str, int]] = {}
        for set_slug, part_slug, qty in rows:
            grouped.setdefault(set_slug, {})[part_slug] = qty
        return [{"set_slug": s, "parts": p} for s, p in grouped.items()]

    # ----------------------------------------------------------- base stats

    async def upsert_base_stats(self, rows: list[dict[str, Any]]) -> int:
        """Bulk upsert reference base stats keyed by unique_name. Each row:
        {unique_name, category, name, mastery_req, disposition, stats(dict), source}.
        Returns the number of rows written."""
        if not rows:
            return 0
        import time

        now = int(time.time())
        conn = self._require_conn()
        await conn.executemany(
            """INSERT INTO item_base_stats
                 (unique_name, category, name, mastery_req, disposition, stats_json, source, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(unique_name) DO UPDATE SET
                 category=excluded.category, name=excluded.name,
                 mastery_req=excluded.mastery_req, disposition=excluded.disposition,
                 stats_json=excluded.stats_json, source=excluded.source,
                 updated_at=excluded.updated_at""",
            [
                (
                    r["unique_name"],
                    r.get("category"),
                    r.get("name"),
                    r.get("mastery_req"),
                    r.get("disposition"),
                    json.dumps(r.get("stats") or {}, ensure_ascii=False),
                    r.get("source") or "wfcd",
                    now,
                )
                for r in rows
            ],
        )
        await conn.commit()
        return len(rows)

    async def count_base_stats(self) -> int:
        conn = self._require_conn()
        async with conn.execute("SELECT COUNT(*) FROM item_base_stats") as cur:
            row = await cur.fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _base_stats_row(d: dict[str, Any]) -> dict[str, Any]:
        try:
            d["stats"] = json.loads(d.pop("stats_json") or "{}")
        except Exception:
            d["stats"] = {}
        return d

    async def get_base_stats(self, unique_name: str) -> dict[str, Any] | None:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT * FROM item_base_stats WHERE unique_name = ?",
            (unique_name,),
        ) as cursor:
            cols = [c[0] for c in cursor.description]
            row = await cursor.fetchone()
        return self._base_stats_row(dict(zip(cols, row, strict=False))) if row else None

    async def list_base_stats(
        self,
        *,
        category: str | None = None,
        limit: int = 2000,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        if category:
            sql = (
                "SELECT * FROM item_base_stats WHERE category = ? ORDER BY name LIMIT ?"
            )
            args: tuple[Any, ...] = (category, limit)
        else:
            sql = "SELECT * FROM item_base_stats ORDER BY name LIMIT ?"
            args = (limit,)
        async with conn.execute(sql, args) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        return [self._base_stats_row(dict(zip(cols, r, strict=False))) for r in rows]

    async def weapon_base_stats_index(self) -> dict[str, dict[str, Any]]:
        """`{normalized lowercased name: row}` for the riven name-join.

        WFM riven slugs don't map to WFCD `uniqueName` deterministically, so
        the scorer joins by display name (see `riven_scoring.resolve_weapon`).
        """
        rows = await self.list_base_stats(limit=10000)
        return {(r.get("name") or "").strip().lower(): r for r in rows if r.get("name")}

    # ----------------------------------------------------------- live events

    async def append_live_event(
        self, ts: int, slug: str | None, event_type: str, payload: dict
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            "INSERT INTO live_events (ts, slug, event_type, payload_json) VALUES (?, ?, ?, ?)",
            (ts, slug, event_type, json.dumps(payload)),
        )
        await conn.commit()

    # ----------------------------------------------------------- rivens

    async def add_riven_watch(
        self,
        weapon_slug: str,
        *,
        ts: int,
        notes: str | None = None,
    ) -> None:
        """Add a weapon to the riven watchlist; idempotent (re-adding leaves
        the row alone — we use INSERT OR IGNORE so the original `added_at`
        timestamp is preserved)."""
        conn = self._require_conn()
        await conn.execute(
            """INSERT OR IGNORE INTO riven_watchlist (weapon_slug, added_at, notes)
               VALUES (?, ?, ?)""",
            (weapon_slug, ts, notes),
        )
        await conn.commit()

    async def list_riven_watch(self) -> list[dict[str, Any]]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT weapon_slug, added_at, notes FROM riven_watchlist ORDER BY added_at DESC"
        ) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        return [dict(zip(cols, r, strict=False)) for r in rows]

    async def remove_riven_watch(self, weapon_slug: str) -> bool:
        conn = self._require_conn()
        cur = await conn.execute(
            "DELETE FROM riven_watchlist WHERE weapon_slug = ?",
            (weapon_slug,),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0

    async def write_riven_snapshot(
        self,
        *,
        weapon_slug: str,
        ts: int,
        tier: str,
        count: int,
        min_price: int | None,
        p25: int | None,
        median: int | None,
        p75: int | None,
        max_price: int | None,
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO riven_snapshot
               (weapon_slug, ts, tier, count, min_price, p25, median, p75, max_price)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (weapon_slug, ts, tier, count, min_price, p25, median, p75, max_price),
        )
        await conn.commit()

    async def riven_snapshot_history(
        self,
        *,
        weapon_slug: str,
        tier: str,
        since_ts: int,
        limit: int = 5000,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        async with conn.execute(
            """SELECT * FROM riven_snapshot
               WHERE weapon_slug=? AND tier=? AND ts >= ?
               ORDER BY ts DESC LIMIT ?""",
            (weapon_slug, tier, since_ts, limit),
        ) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        return [dict(zip(cols, r, strict=False)) for r in rows]

    async def upsert_riven_auction(
        self,
        *,
        auction_id: str,
        weapon_slug: str,
        seen_at: int,
        buyout_price: int | None,
        starting_price: int | None,
        top_bid: int | None,
        re_rolls: int | None,
        mod_rank: int | None,
        polarity: str | None,
        attributes: list[dict[str, Any]],
        owner_name: str | None,
        owner_status: str | None,
        tier: str,
    ) -> None:
        """Insert a new active auction or update an existing one's last_seen +
        mutable fields (price/tier/owner_status). Preserves first_seen on update."""
        conn = self._require_conn()
        attrs_json = json.dumps(attributes)
        await conn.execute(
            """INSERT INTO riven_auction (
                 auction_id, weapon_slug, first_seen, last_seen,
                 buyout_price, starting_price, top_bid,
                 re_rolls, mod_rank, polarity, attributes_json,
                 owner_name, owner_status, tier, status, gone_at
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', NULL)
               ON CONFLICT(auction_id) DO UPDATE SET
                 last_seen      = excluded.last_seen,
                 buyout_price   = excluded.buyout_price,
                 starting_price = excluded.starting_price,
                 top_bid        = excluded.top_bid,
                 owner_status   = excluded.owner_status,
                 tier           = excluded.tier,
                 status         = 'active',
                 gone_at        = NULL""",
            (
                auction_id,
                weapon_slug,
                seen_at,
                seen_at,
                buyout_price,
                starting_price,
                top_bid,
                re_rolls,
                mod_rank,
                polarity,
                attrs_json,
                owner_name,
                owner_status,
                tier,
            ),
        )
        await conn.commit()

    async def mark_riven_auctions_gone(
        self,
        *,
        weapon_slug: str,
        seen_ids: set[str],
        at: int,
    ) -> int:
        """Flip any currently-active auction for `weapon_slug` to 'gone' if
        it isn't present in `seen_ids`. Returns the number of rows flipped."""
        conn = self._require_conn()
        if not seen_ids:
            cur = await conn.execute(
                """UPDATE riven_auction SET status='gone', gone_at=?
                   WHERE weapon_slug=? AND status='active'""",
                (at, weapon_slug),
            )
        else:
            placeholders = ",".join("?" * len(seen_ids))
            cur = await conn.execute(
                f"""UPDATE riven_auction SET status='gone', gone_at=?
                    WHERE weapon_slug=? AND status='active'
                      AND auction_id NOT IN ({placeholders})""",
                (at, weapon_slug, *seen_ids),
            )
        await conn.commit()
        return cur.rowcount or 0

    async def active_riven_auctions(self, weapon_slug: str) -> list[dict[str, Any]]:
        conn = self._require_conn()
        async with conn.execute(
            """SELECT * FROM riven_auction
               WHERE weapon_slug=? AND status='active'
               ORDER BY buyout_price ASC""",
            (weapon_slug,),
        ) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(zip(cols, r, strict=False))
            try:
                d["attributes"] = json.loads(d.pop("attributes_json") or "[]")
            except Exception:
                d["attributes"] = []
            out.append(d)
        return out

    async def recent_gone_riven_auctions(
        self,
        weapon_slug: str,
        *,
        since_ts: int,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Auctions that disappeared (likely sold) since `since_ts`. Useful
        for inferring real sale prices vs listing prices."""
        conn = self._require_conn()
        async with conn.execute(
            """SELECT * FROM riven_auction
               WHERE weapon_slug=? AND status='gone' AND gone_at >= ?
               ORDER BY gone_at DESC LIMIT ?""",
            (weapon_slug, since_ts, limit),
        ) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            d = dict(zip(cols, r, strict=False))
            try:
                d["attributes"] = json.loads(d.pop("attributes_json") or "[]")
            except Exception:
                d["attributes"] = []
            out.append(d)
        return out

    # ----------------------------------------------------------- fissures

    async def add_fissure_subscription(
        self,
        *,
        era: str | None,
        mission_type: str | None,
        planet: str | None = None,
        node: str | None = None,
        is_hard: bool | None,
        is_storm: bool | None,
        ts: int,
    ) -> int:
        conn = self._require_conn()
        cur = await conn.execute(
            """INSERT INTO fissure_subscription
               (era, mission_type, planet, node, is_hard, is_storm, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (
                era,
                mission_type,
                planet,
                node,
                None if is_hard is None else int(is_hard),
                None if is_storm is None else int(is_storm),
                ts,
            ),
        )
        await conn.commit()
        return int(cur.lastrowid)

    async def list_fissure_subscriptions(
        self,
        *,
        enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        sql = (
            "SELECT id, era, mission_type, planet, node, is_hard, is_storm, enabled, created_at "
            "FROM fissure_subscription"
        )
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at DESC"
        async with conn.execute(sql) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        return [dict(zip(cols, r, strict=False)) for r in rows]

    async def remove_fissure_subscription(self, sub_id: int) -> bool:
        conn = self._require_conn()
        cur = await conn.execute(
            "DELETE FROM fissure_subscription WHERE id = ?",
            (sub_id,),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0

    async def register_telegram_chat(
        self,
        *,
        chat_id: int,
        username: str | None,
        ts: int,
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            """INSERT INTO telegram_chat (chat_id, username, registered_at)
               VALUES (?, ?, ?)
               ON CONFLICT(chat_id) DO UPDATE SET username = excluded.username""",
            (chat_id, username, ts),
        )
        await conn.commit()

    async def list_telegram_chats(self) -> list[dict[str, Any]]:
        conn = self._require_conn()
        async with conn.execute(
            "SELECT chat_id, username, registered_at FROM telegram_chat "
            "ORDER BY registered_at ASC"
        ) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        return [dict(zip(cols, r, strict=False)) for r in rows]

    async def record_fissure_notification(
        self,
        *,
        subscription_id: int,
        fissure_id: str,
        ts: int,
    ) -> bool:
        """INSERT OR IGNORE into the dedup ledger. Returns True if newly
        inserted (first time we've seen this sub×fissure pair), False if it
        was already there."""
        conn = self._require_conn()
        cur = await conn.execute(
            """INSERT OR IGNORE INTO fissure_notification
               (subscription_id, fissure_id, notified_at) VALUES (?, ?, ?)""",
            (subscription_id, fissure_id, ts),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0

    async def prune_fissure_notifications(self, *, older_than: int) -> int:
        conn = self._require_conn()
        cur = await conn.execute(
            "DELETE FROM fissure_notification WHERE notified_at < ?",
            (older_than,),
        )
        await conn.commit()
        return cur.rowcount or 0
