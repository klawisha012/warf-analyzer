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
        self, *, slug: str, ts: int, side: str, online_only: int,
        count_orders: int, min_price: int | None,
        p10: int | None, p25: int | None, median: int | None,
        p75: int | None, p90: int | None, max_price: int | None,
        volume_qty: int, top5: list[int],
    ) -> None:
        conn = self._require_conn()
        await conn.execute(
            """INSERT OR REPLACE INTO order_snapshots
               (slug, ts, side, online_only, count_orders, min_price,
                p10, p25, median, p75, p90, max_price, volume_qty, top5_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, ts, side, online_only, count_orders, min_price,
             p10, p25, median, p75, p90, max_price, volume_qty,
             json.dumps(top5)),
        )
        await conn.commit()

    async def history(
        self, *, slug: str, side: str, online_only: int,
        since_ts: int, until_ts: int | None = None, limit: int = 5000,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        if until_ts is None:
            sql = ("SELECT * FROM order_snapshots "
                   "WHERE slug=? AND side=? AND online_only=? AND ts >= ? "
                   "ORDER BY ts DESC LIMIT ?")
            args = (slug, side, online_only, since_ts, limit)
        else:
            sql = ("SELECT * FROM order_snapshots "
                   "WHERE slug=? AND side=? AND online_only=? AND ts BETWEEN ? AND ? "
                   "ORDER BY ts DESC LIMIT ?")
            args = (slug, side, online_only, since_ts, until_ts, limit)
        async with conn.execute(sql, args) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(zip(cols, row))
            try:
                d["top5"] = json.loads(d.pop("top5_json") or "[]")
            except Exception:
                d["top5"] = []
            out.append(d)
        return out

    # ----------------------------------------------------------- signals

    async def insert_signal_event(
        self, ts: int, slug: str, signal_type: str,
        payload: dict, dedup_key: str,
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
        self, *, types: list[str] | None = None,
        slug: str | None = None, limit: int = 50, since_ts: int = 0,
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
            d = dict(zip(cols, row))
            raw = d.pop("payload_json") or "{}"
            try:
                d["payload"] = json.loads(raw)
            except json.JSONDecodeError as e:
                log.warning("bad payload_json id=%s: %s", d.get("id"), e)
                d["payload"] = {}
            out.append(d)
        return out

    # ----------------------------------------------------------- sets

    async def upsert_set_composition(self, set_slug: str, part_slug: str, qty: int) -> None:
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
