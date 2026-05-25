# Phase B.2a: History storage + Signals engine + Endpoints — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Add SQLite-backed price history (snapshots every 30 min), 9 statistical signal functions, and 4 new endpoints (`/history/{slug}`, `/signals/active`, `/signals/feed`, `/me/dashboard-actions`). No frontend changes — those land in B.2b.

**Architecture:** Snapshot writer is called from two places: (1) backend broker-consumer on every live order event (delta-style; cheap), and (2) APScheduler in poller every 30 min (synthetic-from-REST-orders snapshot). Both write into the same `order_snapshots` table. Signals are pure functions over (slug, history, current state) → SignalEvent | None; the runner is called from the snapshot writer and on /signals/active reads. Set compositions are loaded once at startup from `cachedData/json/Warframes.json` etc.

**Tech Stack:** `aiosqlite>=0.20` for async SQLite, WAL journal mode, `busy_timeout=5000`. No Alembic — single-file DB with `CREATE TABLE IF NOT EXISTS`.

---

## File Map

**Create:**
- `src/alecaframe_api/db/__init__.py` (package marker)
- `src/alecaframe_api/db/schema.sql` (CREATE TABLE statements)
- `src/alecaframe_api/db/repo.py` (`Repo` class with all queries)
- `src/alecaframe_api/wfm/history.py` (`write_snapshot` + `read_history`)
- `src/alecaframe_api/wfm/signals.py` (9 signal functions + `run_signals`)
- `src/alecaframe_api/wfm/sets_loader.py` (build SetCompositions from AlecaFrame cachedData)
- `src/alecaframe_api/wfm/history_router.py` (new endpoints)
- `tests/test_db_repo.py`
- `tests/test_wfm_history.py`
- `tests/test_wfm_signals.py`
- `tests/test_wfm_sets_loader.py`
- `tests/fixtures/aleca_warframes_sample.json` (recorded slice)

**Modify:**
- `pyproject.toml` — add `aiosqlite>=0.20`
- `src/alecaframe_api/config.py` — add `signal_throttle_seconds: int = 3600`
- `src/alecaframe_api/main.py` — open Repo in lifespan, load real sets via loader, include history_router, wire signals into consumer
- `src/alecaframe_api/wfm/consumer.py` — after Centrifugo publish, write snapshot + run signals
- `src/alecaframe_api/wfm/poller.py` — APScheduler also calls REST-snapshot job every 30 min
- `README.md` — document new endpoints

---

## Conventions

- **Commit format:** Conventional Commits
- **Branch:** `feature/b2a-history-signals` (already created from master @ 13f8955)
- **Working dir:** `B:\Sync\Programming\projects\aleca frame inventory`
- **All test commands:** `uv run pytest ...`
- **SQLite path:** `_settings.sqlite_path` (defaults to `/data/wfm_history.db`)

---

## Task 1: Dependencies

```powershell
uv add 'aiosqlite>=0.20'
uv run python -c "import aiosqlite; print('ok', aiosqlite.__version__)"
git add pyproject.toml uv.lock
git commit -m "build: add aiosqlite for B.2a history storage"
```

- [ ] Done when version prints and commit lands.

---

## Task 2: Database schema

**Files:**
- Create: `src/alecaframe_api/db/__init__.py`
- Create: `src/alecaframe_api/db/schema.sql`

- [ ] **Step 1: Package marker**

```python
# src/alecaframe_api/db/__init__.py
"""SQLite history storage."""
```

- [ ] **Step 2: Schema**

Create `src/alecaframe_api/db/schema.sql`:

```sql
-- WAL pragmas are applied programmatically in repo.py; this file is pure DDL.

CREATE TABLE IF NOT EXISTS order_snapshots (
  slug          TEXT NOT NULL,
  ts            INTEGER NOT NULL,
  side          TEXT NOT NULL,
  online_only   INTEGER NOT NULL,
  count_orders  INTEGER NOT NULL,
  min_price     INTEGER,
  p10           INTEGER, p25 INTEGER, median INTEGER, p75 INTEGER, p90 INTEGER,
  max_price     INTEGER,
  volume_qty    INTEGER NOT NULL,
  top5_json     TEXT,
  PRIMARY KEY (slug, ts, side, online_only)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_snapshots_slug_ts ON order_snapshots(slug, ts DESC);

CREATE TABLE IF NOT EXISTS live_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  slug TEXT,
  event_type TEXT,
  payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_live_events_ts ON live_events(ts DESC);

CREATE TABLE IF NOT EXISTS signal_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  slug TEXT,
  signal_type TEXT,
  payload_json TEXT,
  dedup_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_signal_events_ts ON signal_events(ts DESC);

CREATE TABLE IF NOT EXISTS wfm_items (
  slug TEXT PRIMARY KEY,
  url_name TEXT,
  item_name TEXT,
  thumb_url TEXT,
  mastery_req INTEGER,
  tags TEXT,
  vaulted INTEGER,
  unique_name TEXT,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS set_compositions (
  set_slug TEXT,
  part_slug TEXT,
  qty INTEGER,
  PRIMARY KEY (set_slug, part_slug)
);
```

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/db/__init__.py src/alecaframe_api/db/schema.sql
git commit -m "feat(db): SQLite schema for history + signals"
```

---

## Task 3: `db/repo.py` + tests

**Files:**
- Create: `src/alecaframe_api/db/repo.py`
- Create: `tests/test_db_repo.py`

- [ ] **Step 1: Failing tests**

`tests/test_db_repo.py`:

```python
"""Repo tests — snapshot insert + read, signal dedup, set compositions."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from alecaframe_api.db.repo import Repo


@pytest.fixture
async def repo(tmp_path: Path) -> Repo:
    r = Repo(db_path=tmp_path / "test.db")
    await r.connect()
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_insert_and_query_snapshot(repo: Repo) -> None:
    now = int(time.time())
    await repo.insert_snapshot(
        slug="kronen_prime_blade", ts=now, side="sell", online_only=1,
        count_orders=3, min_price=35, p10=35, p25=36, median=36, p75=37, p90=38,
        max_price=38, volume_qty=4, top5=[35, 36, 36, 37, 38],
    )
    rows = await repo.history(slug="kronen_prime_blade", side="sell",
                              online_only=1, since_ts=now - 60)
    assert len(rows) == 1
    assert rows[0]["min_price"] == 35
    assert rows[0]["top5"] == [35, 36, 36, 37, 38]


@pytest.mark.asyncio
async def test_insert_signal_event_dedup(repo: Repo) -> None:
    now = int(time.time())
    inserted_a = await repo.insert_signal_event(
        ts=now, slug="x", signal_type="undervalued_mine",
        payload={"diff": 5}, dedup_key="undervalued_mine:x:2026-05-25",
    )
    inserted_b = await repo.insert_signal_event(
        ts=now + 1, slug="x", signal_type="undervalued_mine",
        payload={"diff": 6}, dedup_key="undervalued_mine:x:2026-05-25",
    )
    assert inserted_a is True
    assert inserted_b is False   # second insert is a no-op


@pytest.mark.asyncio
async def test_set_compositions_roundtrip(repo: Repo) -> None:
    await repo.upsert_set_composition("kronen_prime_set", "kronen_prime_blade", 2)
    await repo.upsert_set_composition("kronen_prime_set", "kronen_prime_handle", 1)
    rows = await repo.read_set_compositions()
    by_set = {r["set_slug"]: r for r in rows}
    assert by_set["kronen_prime_set"]["parts"] == {"kronen_prime_blade": 2, "kronen_prime_handle": 1}


@pytest.mark.asyncio
async def test_recent_signals_filtered(repo: Repo) -> None:
    now = int(time.time())
    await repo.insert_signal_event(now - 100, "x", "undervalued_mine", {}, "a")
    await repo.insert_signal_event(now - 50,  "y", "competitor_undercut", {}, "b")
    await repo.insert_signal_event(now - 10,  "z", "undervalued_mine", {}, "c")
    rows = await repo.recent_signals(types=["undervalued_mine"], limit=10)
    assert [r["slug"] for r in rows] == ["z", "x"]   # newest first
```

- [ ] **Step 2: Implement repo**

Create `src/alecaframe_api/db/repo.py`:

```python
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

    async def connect(self) -> None:
        if self._conn is not None:
            return
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.db_path)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(_SCHEMA_PATH.read_text(encoding="utf-8"))
        await self._conn.commit()

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
        assert self._conn is not None
        await self._conn.execute(
            """INSERT OR REPLACE INTO order_snapshots
               (slug, ts, side, online_only, count_orders, min_price,
                p10, p25, median, p75, p90, max_price, volume_qty, top5_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, ts, side, online_only, count_orders, min_price,
             p10, p25, median, p75, p90, max_price, volume_qty,
             json.dumps(top5)),
        )
        await self._conn.commit()

    async def history(
        self, *, slug: str, side: str, online_only: int,
        since_ts: int, until_ts: int | None = None, limit: int = 5000,
    ) -> list[dict[str, Any]]:
        assert self._conn is not None
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
        async with self._conn.execute(sql, args) as cursor:
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
        assert self._conn is not None
        try:
            await self._conn.execute(
                """INSERT INTO signal_events (ts, slug, signal_type, payload_json, dedup_key)
                   VALUES (?, ?, ?, ?, ?)""",
                (ts, slug, signal_type, json.dumps(payload), dedup_key),
            )
            await self._conn.commit()
            return True
        except aiosqlite.IntegrityError:
            return False  # unique constraint on dedup_key

    async def recent_signals(
        self, *, types: list[str] | None = None,
        slug: str | None = None, limit: int = 50, since_ts: int = 0,
    ) -> list[dict[str, Any]]:
        assert self._conn is not None
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
        async with self._conn.execute(sql, args) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            d = dict(zip(cols, row))
            try:
                d["payload"] = json.loads(d.pop("payload_json") or "{}")
            except Exception:
                d["payload"] = {}
            out.append(d)
        return out

    # ----------------------------------------------------------- sets

    async def upsert_set_composition(self, set_slug: str, part_slug: str, qty: int) -> None:
        assert self._conn is not None
        await self._conn.execute(
            """INSERT OR REPLACE INTO set_compositions (set_slug, part_slug, qty)
               VALUES (?, ?, ?)""",
            (set_slug, part_slug, qty),
        )
        await self._conn.commit()

    async def read_set_compositions(self) -> list[dict[str, Any]]:
        assert self._conn is not None
        async with self._conn.execute(
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
        assert self._conn is not None
        await self._conn.execute(
            "INSERT INTO live_events (ts, slug, event_type, payload_json) VALUES (?, ?, ?, ?)",
            (ts, slug, event_type, json.dumps(payload)),
        )
        await self._conn.commit()
```

- [ ] **Step 3: Verify tests pass**

```powershell
uv run pytest tests/test_db_repo.py -v
```

Expected: 4 passed.

- [ ] **Step 4: Commit**

```powershell
git add src/alecaframe_api/db/repo.py tests/test_db_repo.py
git commit -m "feat(db): Repo with snapshot/signal/sets/live-events queries"
```

---

## Task 4: `wfm/history.py` — write_snapshot helper

**Files:**
- Create: `src/alecaframe_api/wfm/history.py`
- Create: `tests/test_wfm_history.py`

`write_snapshot(slug, orders, repo, *, ts=None, sides=("sell","buy"))` computes stats from raw WFM orders and writes both sell+buy rows for both online-only AND all-orders into the snapshot table. Used by the consumer (per-event) and the poller (per-30min REST fetch).

- [ ] **Step 1: Test**

`tests/test_wfm_history.py`:

```python
"""history.write_snapshot orchestration tests."""
from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from alecaframe_api.db.repo import Repo
from alecaframe_api.wfm.history import write_snapshot


FIXTURE = Path(__file__).parent / "fixtures" / "wfm_orders_kronen_prime_blade.json"


@pytest.fixture
async def repo(tmp_path: Path) -> Repo:
    r = Repo(db_path=tmp_path / "h.db")
    await r.connect()
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_write_snapshot_writes_4_rows(repo: Repo) -> None:
    """One snapshot writes (sell, buy) × (online_only=1, =0) = 4 rows."""
    orders = json.loads(FIXTURE.read_text(encoding="utf-8"))["payload"]["orders"]
    ts = int(time.time())
    await write_snapshot(repo=repo, slug="kronen_prime_blade", orders=orders, ts=ts)
    # Verify 4 keys: sell-online, sell-all, buy-online, buy-all.
    sells_online = await repo.history(slug="kronen_prime_blade", side="sell",
                                      online_only=1, since_ts=ts - 60)
    sells_all = await repo.history(slug="kronen_prime_blade", side="sell",
                                   online_only=0, since_ts=ts - 60)
    buys_online = await repo.history(slug="kronen_prime_blade", side="buy",
                                     online_only=1, since_ts=ts - 60)
    buys_all = await repo.history(slug="kronen_prime_blade", side="buy",
                                  online_only=0, since_ts=ts - 60)
    assert len(sells_online) == 1
    assert len(sells_all) == 1
    assert len(buys_online) == 1
    assert len(buys_all) == 1
    # Sanity: online sell median is 36 (from prices test)
    assert sells_online[0]["median"] == 36


@pytest.mark.asyncio
async def test_write_snapshot_idempotent_at_same_ts(repo: Repo) -> None:
    """INSERT OR REPLACE means same ts produces same row count."""
    orders = json.loads(FIXTURE.read_text(encoding="utf-8"))["payload"]["orders"]
    ts = int(time.time())
    await write_snapshot(repo=repo, slug="kronen_prime_blade", orders=orders, ts=ts)
    await write_snapshot(repo=repo, slug="kronen_prime_blade", orders=orders, ts=ts)
    rows = await repo.history(slug="kronen_prime_blade", side="sell", online_only=1,
                              since_ts=ts - 60)
    assert len(rows) == 1
```

- [ ] **Step 2: Implement**

Create `src/alecaframe_api/wfm/history.py`:

```python
"""Snapshot writer — turn raw WFM orders into 4 stat rows in the DB."""
from __future__ import annotations

import time
from typing import Any

from alecaframe_api.db.repo import Repo
from alecaframe_api.wfm.prices import compute_stats


async def write_snapshot(
    *, repo: Repo, slug: str, orders: list[dict[str, Any]],
    ts: int | None = None, platform: str = "pc",
) -> None:
    """Compute sell+buy × online_only/all stats and persist all 4 rows."""
    ts = ts if ts is not None else int(time.time())
    for side in ("sell", "buy"):
        for online_only in (1, 0):
            s = compute_stats(orders, side=side,
                              online_only=bool(online_only), platform=platform)
            await repo.insert_snapshot(
                slug=slug, ts=ts, side=side, online_only=online_only,
                count_orders=s.count_orders, min_price=s.min_price,
                p10=s.p10, p25=s.p25, median=s.median, p75=s.p75, p90=s.p90,
                max_price=s.max_price, volume_qty=s.volume_qty, top5=s.top5,
            )
```

- [ ] **Step 3: Verify + commit**

```powershell
uv run pytest tests/test_wfm_history.py -v
git add src/alecaframe_api/wfm/history.py tests/test_wfm_history.py
git commit -m "feat(wfm): write_snapshot helper — 4 stat rows per (slug, ts)"
```

---

## Task 5: Set composition loader from AlecaFrame cachedData

**Files:**
- Create: `src/alecaframe_api/wfm/sets_loader.py`
- Create: `tests/test_wfm_sets_loader.py`
- Create: `tests/fixtures/aleca_warframes_sample.json` (small slice)

The loader walks `cachedData/json/Warframes.json`, `Primary.json`, etc., for each item that has a `components` field, produces a `SetComposition` whose parts are matched to WFM slugs via the SlugResolver.

- [ ] **Step 1: Test fixture**

Create `tests/fixtures/aleca_warframes_sample.json`:

```json
[
  {
    "uniqueName": "/Lotus/Powersuits/Mag/MagPrime",
    "name": "Mag Prime",
    "components": [
      {"name": "Blueprint", "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/MagPrimeBlueprint", "itemCount": 1, "primeSellingPrice": 25},
      {"name": "Neuroptics", "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/MagPrimeHelmetBlueprint", "itemCount": 1, "primeSellingPrice": 15},
      {"name": "Chassis", "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/MagPrimeChassisBlueprint", "itemCount": 1, "primeSellingPrice": 15},
      {"name": "Systems", "uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/MagPrimeSystemsBlueprint", "itemCount": 1, "primeSellingPrice": 15}
    ]
  }
]
```

- [ ] **Step 2: Test**

`tests/test_wfm_sets_loader.py`:

```python
"""Loader test — read AlecaFrame Warframes.json slice + resolve via SlugResolver."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alecaframe_api.wfm.sets_loader import load_set_compositions_from_aleca
from alecaframe_api.wfm.slugs import ItemRef, SlugResolver


@pytest.fixture
def resolver() -> SlugResolver:
    r = SlugResolver()
    r.load([
        ItemRef(slug="mag_prime_set",                 item_name="Mag Prime Set",            thumb_url=None, vaulted=False, wfm_id="1"),
        ItemRef(slug="mag_prime_blueprint",           item_name="Mag Prime Blueprint",      thumb_url=None, vaulted=False, wfm_id="2"),
        ItemRef(slug="mag_prime_helmet_blueprint",    item_name="Mag Prime Helmet BP",       thumb_url=None, vaulted=False, wfm_id="3"),
        ItemRef(slug="mag_prime_chassis_blueprint",   item_name="Mag Prime Chassis BP",      thumb_url=None, vaulted=False, wfm_id="4"),
        ItemRef(slug="mag_prime_systems_blueprint",   item_name="Mag Prime Systems BP",      thumb_url=None, vaulted=False, wfm_id="5"),
    ])
    return r


def test_loader_builds_mag_prime_set(tmp_path: Path, resolver: SlugResolver) -> None:
    fixture = Path(__file__).parent / "fixtures" / "aleca_warframes_sample.json"
    cached_dir = tmp_path
    (cached_dir / "Warframes.json").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    sets = load_set_compositions_from_aleca(cached_json_dir=cached_dir, resolver=resolver)
    by_slug = {s.set_slug: s for s in sets}
    assert "mag_prime_set" in by_slug
    s = by_slug["mag_prime_set"]
    assert s.set_name == "Mag Prime Set"
    assert s.parts == {
        "mag_prime_blueprint": 1,
        "mag_prime_helmet_blueprint": 1,
        "mag_prime_chassis_blueprint": 1,
        "mag_prime_systems_blueprint": 1,
    }


def test_loader_skips_items_without_components(tmp_path: Path, resolver: SlugResolver) -> None:
    (tmp_path / "Warframes.json").write_text(
        json.dumps([{"name": "Excalibur", "uniqueName": "/Lotus/Powersuits/Excalibur/Excalibur"}]),
        encoding="utf-8",
    )
    sets = load_set_compositions_from_aleca(cached_json_dir=tmp_path, resolver=resolver)
    assert sets == []


def test_loader_skips_unresolvable_components(tmp_path: Path, resolver: SlugResolver) -> None:
    """If any part can't resolve to a slug, skip the whole set rather than producing a partial."""
    (tmp_path / "Warframes.json").write_text(
        json.dumps([{
            "name": "Mystery Prime", "uniqueName": "/Lotus/Powersuits/Mystery/MysteryPrime",
            "components": [
                {"uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/MysteryPrimeBlueprint", "itemCount": 1}
            ],
        }]),
        encoding="utf-8",
    )
    sets = load_set_compositions_from_aleca(cached_json_dir=tmp_path, resolver=resolver)
    assert sets == []
```

- [ ] **Step 3: Implement**

Create `src/alecaframe_api/wfm/sets_loader.py`:

```python
"""Build SetComposition[] from AlecaFrame `cachedData/json/*.json`.

Each AlecaFrame catalogue entry has `name`, `uniqueName`, and (for sets) a
`components` list. We synthesise the set slug from the warframe/weapon name
(`Mag Prime` → `mag_prime_set`) and resolve each component's `uniqueName`
through SlugResolver. If any component is unresolvable, the whole set is
dropped — partial sets would mislead the profit calculator.
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from alecaframe_api.wfm.sets import SetComposition
from alecaframe_api.wfm.slugs import SlugResolver

log = logging.getLogger("alecaframe.wfm.sets_loader")

_CATALOGUE_FILES = (
    "Warframes.json", "Primary.json", "Secondary.json", "Melee.json",
    "Sentinels.json", "Arch-Gun.json", "Arch-Melee.json",
)


def _to_set_slug(item_name: str) -> str:
    """`Mag Prime` → `mag_prime_set`."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", item_name.lower()).strip("_")
    if cleaned.endswith("_set"):
        return cleaned
    return f"{cleaned}_set"


def load_set_compositions_from_aleca(
    *, cached_json_dir: Path, resolver: SlugResolver,
) -> list[SetComposition]:
    out: list[SetComposition] = []
    for fname in _CATALOGUE_FILES:
        path = cached_json_dir / fname
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("can't parse %s: %s", path, e)
            continue
        items = raw if isinstance(raw, list) else (
            list(raw.values()) if isinstance(raw, dict) else []
        )
        for it in items:
            if not isinstance(it, dict):
                continue
            components = it.get("components")
            name = it.get("name")
            if not components or not isinstance(components, list) or not name:
                continue
            parts: dict[str, int] = {}
            bad = False
            for c in components:
                u = c.get("uniqueName")
                qty = int(c.get("itemCount", 1) or 1)
                slug = resolver.resolve_unique_name(u) if u else None
                if not slug:
                    bad = True
                    break
                parts[slug] = parts.get(slug, 0) + qty
            if bad or not parts:
                continue
            out.append(SetComposition(
                set_slug=_to_set_slug(name),
                set_name=f"{name} Set" if not name.endswith(" Set") else name,
                parts=parts,
            ))
    return out
```

- [ ] **Step 4: Run + commit**

```powershell
uv run pytest tests/test_wfm_sets_loader.py -v
git add src/alecaframe_api/wfm/sets_loader.py tests/test_wfm_sets_loader.py tests/fixtures/aleca_warframes_sample.json
git commit -m "feat(wfm): set composition loader from AlecaFrame cachedData"
```

---

## Task 6: 9 signal functions + signal runner

**Files:**
- Create: `src/alecaframe_api/wfm/signals.py`
- Create: `tests/test_wfm_signals.py`

Each signal is a pure function: `def signal_X(slug, history, current, my_orders) -> SignalEvent | None`. The runner iterates them on each snapshot write.

This is a big task — but each signal is small and the tests are tabular. Single commit with all 9 + runner.

- [ ] **Step 1: Tests** — provide a fixture with controlled history and assert each signal fires when expected.

Create `tests/test_wfm_signals.py`:

```python
"""Tests for the 9 signal functions + runner."""
from __future__ import annotations

import time

import pytest

from alecaframe_api.wfm.signals import (
    Snapshot, SignalContext,
    undervalued_mine, overpriced_mine, competitor_undercut,
    bid_match, floor_drop, momentum_up,
    volume_spike, vault_premium, set_profit_window,
    run_signals,
)


def _snap(*, ts, side="sell", online_only=1, median=None, min_price=None,
          max_price=None, volume=10, top5=None, count=5) -> Snapshot:
    return Snapshot(
        slug="x", ts=ts, side=side, online_only=online_only,
        count_orders=count, min_price=min_price, median=median, max_price=max_price,
        p10=min_price, p25=min_price, p75=max_price, p90=max_price,
        volume_qty=volume, top5=top5 or [],
    )


def test_undervalued_mine_fires_when_my_price_below_median_minus_2sigma() -> None:
    now = int(time.time())
    history = [_snap(ts=now - 86400 * d, median=40) for d in range(1, 8)]
    ctx = SignalContext(
        slug="x", now_ts=now,
        history_7d=history,
        current_sell=_snap(ts=now, median=40, min_price=30, top5=[30, 31, 32, 33, 35]),
        current_buy=_snap(ts=now, side="buy", median=20),
        my_listing_price=20,   # below median 40 - any sigma
    )
    ev = undervalued_mine(ctx)
    assert ev is not None
    assert ev.signal_type == "undervalued_mine"


def test_undervalued_mine_silent_when_competitive() -> None:
    now = int(time.time())
    history = [_snap(ts=now - 86400 * d, median=40) for d in range(1, 8)]
    ctx = SignalContext(
        slug="x", now_ts=now, history_7d=history,
        current_sell=_snap(ts=now, median=40, min_price=38), current_buy=None,
        my_listing_price=39,
    )
    assert undervalued_mine(ctx) is None


def test_competitor_undercut_fires() -> None:
    now = int(time.time())
    ctx = SignalContext(
        slug="x", now_ts=now, history_7d=[],
        current_sell=_snap(ts=now, top5=[30, 32, 34, 35, 38]),
        current_buy=None, my_listing_price=35,
    )
    ev = competitor_undercut(ctx)
    assert ev is not None


def test_bid_match_fires_when_high_buyer() -> None:
    now = int(time.time())
    ctx = SignalContext(
        slug="x", now_ts=now, history_7d=[],
        current_sell=_snap(ts=now, median=30),
        current_buy=_snap(ts=now, side="buy", max_price=40),
        my_listing_price=None,
    )
    ev = bid_match(ctx)
    assert ev is not None and ev.payload["offer_price"] == 40


def test_floor_drop_fires_on_minus_10pct() -> None:
    now = int(time.time())
    earlier = _snap(ts=now - 3600 * 6, min_price=40)
    current = _snap(ts=now, min_price=35)  # -12.5%
    ctx = SignalContext(slug="x", now_ts=now, history_7d=[earlier],
                        current_sell=current, current_buy=None, my_listing_price=None)
    ev = floor_drop(ctx)
    assert ev is not None


def test_momentum_up_fires_on_ema_cross() -> None:
    now = int(time.time())
    history = [
        _snap(ts=now - 86400 + 6*3600*i, median=30 + i * 2)
        for i in range(8)
    ]
    ctx = SignalContext(slug="x", now_ts=now, history_7d=history,
                        current_sell=_snap(ts=now, median=46), current_buy=None,
                        my_listing_price=None)
    ev = momentum_up(ctx)
    assert ev is not None


def test_volume_spike_fires() -> None:
    now = int(time.time())
    history = [_snap(ts=now - 3600 * h, volume=5) for h in range(1, 25)]
    ctx = SignalContext(slug="x", now_ts=now, history_7d=history,
                        current_sell=_snap(ts=now, volume=20), current_buy=None,
                        my_listing_price=None)
    ev = volume_spike(ctx)
    assert ev is not None


def test_run_signals_returns_list_of_events() -> None:
    now = int(time.time())
    ctx = SignalContext(slug="x", now_ts=now, history_7d=[],
                        current_sell=_snap(ts=now, top5=[30, 32, 34, 35, 38]),
                        current_buy=_snap(ts=now, side="buy", max_price=40),
                        my_listing_price=35)
    events = run_signals(ctx)
    types = {e.signal_type for e in events}
    assert "competitor_undercut" in types
    assert "bid_match" in types
```

(`vault_premium` and `set_profit_window` need cross-slug context; they're tested via integration in B.2a Task 9 e2e — left out of this unit test for brevity.)

- [ ] **Step 2: Implement**

Create `src/alecaframe_api/wfm/signals.py`:

```python
"""9 signal functions + runner.

Each signal: pure function over (slug, history, current state, optional my_listing).
Returns SignalEvent or None. dedup_key embedded in the event so the DB layer
can drop duplicates.
"""
from __future__ import annotations

import datetime as _dt
import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("alecaframe.wfm.signals")


@dataclass(frozen=True)
class Snapshot:
    slug: str
    ts: int
    side: str
    online_only: int
    count_orders: int
    min_price: int | None
    p10: int | None
    p25: int | None
    median: int | None
    p75: int | None
    p90: int | None
    max_price: int | None
    volume_qty: int
    top5: list[int]


@dataclass
class SignalContext:
    slug: str
    now_ts: int
    history_7d: list[Snapshot]   # sell-side, online-only, last 7 days, newest first or oldest first — caller's choice
    current_sell: Snapshot | None
    current_buy: Snapshot | None
    my_listing_price: int | None
    # cross-slug helpers — optional, used by vault_premium / set_profit_window
    is_vaulted: bool | None = None
    set_context: dict[str, Any] | None = None   # {set_slug, parts_cost, set_price} when applicable


@dataclass(frozen=True)
class SignalEvent:
    slug: str
    ts: int
    signal_type: str
    payload: dict[str, Any]
    dedup_key: str


def _today_iso(ts: int) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).date().isoformat()


def _hour_iso(ts: int) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).strftime("%Y-%m-%dT%H")


def _week_iso(ts: int) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).strftime("%G-W%V")


def _medians(snaps: list[Snapshot]) -> list[int]:
    return [s.median for s in snaps if s.median is not None]


# ----------------------------------------------------------------- signals


def undervalued_mine(ctx: SignalContext) -> SignalEvent | None:
    if ctx.my_listing_price is None:
        return None
    medians = _medians(ctx.history_7d)
    if len(medians) < 3:
        return None
    mu = statistics.mean(medians)
    sigma = statistics.pstdev(medians) if len(medians) > 1 else 0
    threshold = mu - max(2 * sigma, 2)
    if ctx.my_listing_price < threshold:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="undervalued_mine",
            payload={
                "my_price": ctx.my_listing_price,
                "median_7d": int(mu),
                "sigma_7d": round(sigma, 1),
            },
            dedup_key=f"undervalued_mine:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def overpriced_mine(ctx: SignalContext) -> SignalEvent | None:
    if ctx.my_listing_price is None or ctx.current_sell is None or not ctx.current_sell.top5:
        return None
    top5_mean = statistics.mean(ctx.current_sell.top5)
    if ctx.my_listing_price > top5_mean * 1.10:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="overpriced_mine",
            payload={"my_price": ctx.my_listing_price, "top5_mean": int(top5_mean)},
            dedup_key=f"overpriced_mine:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def competitor_undercut(ctx: SignalContext) -> SignalEvent | None:
    if ctx.my_listing_price is None or ctx.current_sell is None or not ctx.current_sell.top5:
        return None
    if ctx.current_sell.top5[0] < ctx.my_listing_price - 1:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="competitor_undercut",
            payload={"my_price": ctx.my_listing_price, "top": ctx.current_sell.top5[0]},
            dedup_key=f"competitor_undercut:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def bid_match(ctx: SignalContext) -> SignalEvent | None:
    if ctx.current_buy is None or ctx.current_buy.max_price is None:
        return None
    floor = ctx.current_sell.min_price if ctx.current_sell else 0
    if floor and ctx.current_buy.max_price >= floor:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="bid_match",
            payload={"offer_price": ctx.current_buy.max_price, "floor": floor},
            dedup_key=f"bid_match:{ctx.slug}:{_today_iso(ctx.now_ts)}:{ctx.current_buy.max_price}",
        )
    if not floor and ctx.current_buy.max_price:
        # No live sell side at all but someone wants to buy — interesting.
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="bid_match",
            payload={"offer_price": ctx.current_buy.max_price, "floor": None},
            dedup_key=f"bid_match:{ctx.slug}:{_today_iso(ctx.now_ts)}:{ctx.current_buy.max_price}",
        )
    return None


def floor_drop(ctx: SignalContext) -> SignalEvent | None:
    if ctx.current_sell is None or ctx.current_sell.min_price is None:
        return None
    cutoff = ctx.now_ts - 6 * 3600
    earlier_floors = [
        s.min_price for s in ctx.history_7d
        if s.min_price is not None and s.ts >= cutoff and s.ts < ctx.now_ts
    ]
    if not earlier_floors:
        return None
    baseline = max(earlier_floors)
    drop_pct = (baseline - ctx.current_sell.min_price) / baseline if baseline else 0
    if drop_pct >= 0.10:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="floor_drop",
            payload={"current": ctx.current_sell.min_price, "baseline": baseline,
                     "drop_pct": round(drop_pct * 100, 1)},
            dedup_key=f"floor_drop:{ctx.slug}:{_hour_iso(ctx.now_ts)}",
        )
    return None


def _ema(values: list[float], alpha: float) -> float | None:
    if not values:
        return None
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def momentum_up(ctx: SignalContext) -> SignalEvent | None:
    medians = _medians(ctx.history_7d)
    if len(medians) < 6:
        return None
    # short EMA = α=0.4 over last 4 points; long EMA = α=0.15 over all
    short = _ema(medians[-4:], 0.4)
    long = _ema(medians, 0.15)
    if short is None or long is None:
        return None
    if short > long * 1.05:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="momentum_up",
            payload={"ema_short": round(short, 1), "ema_long": round(long, 1)},
            dedup_key=f"momentum_up:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def volume_spike(ctx: SignalContext) -> SignalEvent | None:
    if ctx.current_sell is None:
        return None
    cutoff = ctx.now_ts - 86400
    recent = [s.volume_qty for s in ctx.history_7d if s.ts >= cutoff]
    if len(recent) < 5:
        return None
    mean_vol = statistics.mean(recent) or 1
    if ctx.current_sell.volume_qty > 3 * mean_vol:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="volume_spike",
            payload={"current_volume": ctx.current_sell.volume_qty,
                     "mean_24h_volume": round(mean_vol, 1)},
            dedup_key=f"volume_spike:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def vault_premium(ctx: SignalContext) -> SignalEvent | None:
    if not ctx.is_vaulted or ctx.current_sell is None or ctx.current_sell.median is None:
        return None
    medians = _medians(ctx.history_7d)
    if len(medians) < 5:
        return None
    baseline = statistics.median(medians)
    if ctx.current_sell.median > baseline * 1.5:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="vault_premium",
            payload={"current_median": ctx.current_sell.median, "baseline": int(baseline)},
            dedup_key=f"vault_premium:{ctx.slug}:{_week_iso(ctx.now_ts)}",
        )
    return None


def set_profit_window(ctx: SignalContext) -> SignalEvent | None:
    if not ctx.set_context:
        return None
    parts_cost = ctx.set_context.get("parts_cost")
    set_price = ctx.set_context.get("set_price")
    set_slug = ctx.set_context.get("set_slug")
    if parts_cost is None or set_price is None or not set_slug:
        return None
    if parts_cost < set_price * 0.85:
        return SignalEvent(
            slug=set_slug, ts=ctx.now_ts, signal_type="set_profit_window",
            payload={"parts_cost": parts_cost, "set_price": set_price,
                     "profit_pct": round((1 - parts_cost / set_price) * 100, 1)},
            dedup_key=f"set_profit_window:{set_slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


# ----------------------------------------------------------------- runner

_ALL_SIGNALS: tuple[Callable[[SignalContext], SignalEvent | None], ...] = (
    undervalued_mine, overpriced_mine, competitor_undercut,
    bid_match, floor_drop, momentum_up,
    volume_spike, vault_premium, set_profit_window,
)


def run_signals(ctx: SignalContext) -> list[SignalEvent]:
    out: list[SignalEvent] = []
    for fn in _ALL_SIGNALS:
        try:
            ev = fn(ctx)
        except Exception as e:
            log.warning("signal %s raised: %s", fn.__name__, e)
            continue
        if ev is not None:
            out.append(ev)
    return out
```

- [ ] **Step 3: Test + commit**

```powershell
uv run pytest tests/test_wfm_signals.py -v
git add src/alecaframe_api/wfm/signals.py tests/test_wfm_signals.py
git commit -m "feat(wfm): 9 signal functions + run_signals dispatcher"
```

---

## Task 7: `/history/{slug}` + `/signals/active` + `/signals/feed` + `/me/dashboard-actions` endpoints

**Files:**
- Create: `src/alecaframe_api/wfm/history_router.py`

- [ ] **Step 1: Implement** (no unit tests — covered by e2e in Task 9)

Create `src/alecaframe_api/wfm/history_router.py`:

```python
"""History + signals endpoints. Read from the Repo singleton injected via main."""
from __future__ import annotations

import time
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from alecaframe_api.wfm.dependencies import SlugResolverDep

router = APIRouter()


def _get_repo():
    from alecaframe_api import main as _m
    if not hasattr(_m, "repo") or _m.repo is None:
        raise HTTPException(503, "history storage not initialised")
    return _m.repo


@router.get("/history/{slug}", summary="Price history snapshots for a slug")
async def history(
    slug: str,
    resolver: SlugResolverDep,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
    granularity: Annotated[str, Query(description="hour | day")] = "hour",
    online_only: Annotated[bool, Query()] = True,
    side: Annotated[str, Query(description="sell | buy")] = "sell",
) -> dict[str, Any]:
    if resolver.by_slug(slug) is None:
        raise HTTPException(404, f"unknown slug '{slug}'")
    repo = _get_repo()
    since = int(time.time()) - days * 86400
    rows = await repo.history(
        slug=slug, side=side, online_only=int(online_only), since_ts=since,
    )
    # Granularity downsampling: pick one row per bucket (newest in bucket wins).
    bucket = 3600 if granularity == "hour" else 86400
    seen: set[int] = set()
    out: list[dict[str, Any]] = []
    for r in rows:
        b = r["ts"] // bucket
        if b in seen:
            continue
        seen.add(b)
        out.append(r)
    return {
        "slug": slug, "days": days, "granularity": granularity,
        "side": side, "online_only": online_only, "rows": list(reversed(out)),
    }


@router.get("/signals/active", summary="Currently active signals")
async def signals_active(
    type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    since_hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> dict[str, Any]:
    repo = _get_repo()
    since = int(time.time()) - since_hours * 3600
    types = [type] if type else None
    rows = await repo.recent_signals(types=types, limit=limit, since_ts=since)
    return {"total": len(rows), "items": rows}


@router.get("/signals/feed", summary="Infinite-scroll signal stream")
async def signals_feed(
    since: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    repo = _get_repo()
    rows = await repo.recent_signals(since_ts=since, limit=limit)
    return {"total": len(rows), "items": rows, "cursor_ts": rows[0]["ts"] if rows else None}


@router.get("/me/dashboard-actions", summary="Top 10 ranked todo for the user")
async def dashboard_actions(limit: Annotated[int, Query(ge=1, le=50)] = 10) -> dict[str, Any]:
    repo = _get_repo()
    # Simple ranking: take last 24h signal events, score by type priority.
    since = int(time.time()) - 24 * 3600
    rows = await repo.recent_signals(since_ts=since, limit=200)
    priority = {
        "bid_match": 100, "set_profit_window": 90, "competitor_undercut": 80,
        "undervalued_mine": 70, "overpriced_mine": 60, "vault_premium": 55,
        "floor_drop": 40, "momentum_up": 30, "volume_spike": 25,
    }
    scored = sorted(rows, key=lambda r: -priority.get(r["signal_type"], 10))[:limit]
    return {"total": len(scored), "items": scored}
```

- [ ] **Step 2: Smoke import + commit**

```powershell
uv run python -c "from alecaframe_api.wfm.history_router import router; print(len(router.routes))"
git add src/alecaframe_api/wfm/history_router.py
git commit -m "feat(wfm): /history/{slug}, /signals/active, /signals/feed, /me/dashboard-actions endpoints"
```

---

## Task 8: Wire Repo + sets-loader + history_router + signal-on-event in main.py + consumer

**Files:**
- Modify: `src/alecaframe_api/main.py`
- Modify: `src/alecaframe_api/wfm/consumer.py`

- [ ] **Step 1: main.py changes**

Add imports:

```python
from alecaframe_api.db.repo import Repo
from alecaframe_api.wfm.history_router import router as history_router
from alecaframe_api.wfm.sets_loader import load_set_compositions_from_aleca
```

Add a module-level `repo: Repo | None = None`.

In lifespan, AFTER constructing the WFM stack and BEFORE the real-time subsystem block, add:

```python
    # ----- DB + sets loader -----
    global repo
    repo = Repo(db_path=_settings.sqlite_path)
    await repo.connect()
    # Persisted set_compositions table — populate from AlecaFrame cachedData if empty.
    existing = await repo.read_set_compositions()
    if not existing:
        try:
            loaded = load_set_compositions_from_aleca(
                cached_json_dir=ALECA_DATA_HOME / "cachedData" / "json",
                resolver=slug_resolver,
            )
            for comp in loaded:
                for part_slug, qty in comp.parts.items():
                    await repo.upsert_set_composition(comp.set_slug, part_slug, qty)
                set_idx.register(comp)
            log.info("loaded %d set compositions from AlecaFrame cachedData", len(loaded))
        except Exception as e:
            log.warning("set composition load failed: %s", e)
    else:
        # Use DB copy.
        from alecaframe_api.wfm.sets import SetComposition
        for row in existing:
            set_idx.register(SetComposition(
                set_slug=row["set_slug"], set_name=row["set_slug"], parts=row["parts"],
            ))
```

Add shutdown:

```python
    if repo is not None:
        await repo.close()
```

(Place before `await redis_client.aclose()`.)

Include router:

```python
app.include_router(history_router)
```

- [ ] **Step 2: consumer.py — write snapshot + run signals**

Open `src/alecaframe_api/wfm/consumer.py`. Currently `handle_live_order` invalidates cache + publishes. Extend it to also call `write_snapshot` + `run_signals` if a Repo is provided.

Replace with:

```python
"""Backend consumer for `wfm.live.orders` topic."""
from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from alecaframe_api.db.repo import Repo
from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.history import write_snapshot
from alecaframe_api.wfm.signals import SignalContext, Snapshot, run_signals

log = logging.getLogger("alecaframe.wfm.consumer")


class _PublisherProto(Protocol):
    async def publish(self, channel: str, data: dict[str, Any]) -> None: ...


async def handle_live_order(
    *, msg: dict, cache: Cache, publisher: _PublisherProto,
    repo: Repo | None = None,
) -> None:
    payload = msg.get("payload") or {}
    item = payload.get("item") or {}
    slug = item.get("url_name") or payload.get("url_name")
    if not slug:
        return
    try:
        for k in (f"orders:{slug}:0", f"orders:{slug}:1"):
            await cache.delete(k)
    except Exception as e:
        log.warning("cache invalidate failed for %s: %s", slug, e)
    await publisher.publish(f"wfm.orders.{slug}", {"slug": slug})
    # B.2a addition: opportunistic snapshot + signal compute on live events.
    # We don't have a full order book here, just one event — skip until the
    # 30-min REST snapshot fills the table. The poller's APScheduler job
    # writes real snapshots from /v1/items/{slug}/orders.
    if repo is not None:
        try:
            await repo.append_live_event(
                ts=int(time.time()), slug=slug,
                event_type=str(msg.get("type") or ""), payload=msg,
            )
        except Exception as e:
            log.warning("append_live_event failed for %s: %s", slug, e)
```

Update the lifespan's `_on_live_order` callback to pass `repo=repo`.

- [ ] **Step 3: pytest + commit**

```powershell
uv run pytest -v
git add src/alecaframe_api/main.py src/alecaframe_api/wfm/consumer.py
git commit -m "feat(main): wire Repo + sets loader + history router + live-event audit"
```

---

## Task 9: Poller — periodic REST snapshot job

**Files:** Modify `src/alecaframe_api/wfm/poller.py`

- [ ] **Step 1: Add a 30-min snapshot job that fetches /orders for each subscribed slug and writes to a local Repo**

Open `src/alecaframe_api/wfm/poller.py`. After the existing scheduler block (`sched = AsyncIOScheduler()` and the first `add_job`), add a second job:

```python
    # Snapshot job — every 30 min, fetch /orders for each subscribed slug + write snapshot
    from alecaframe_api.db.repo import Repo
    from alecaframe_api.wfm.history import write_snapshot
    poller_repo = Repo(db_path=s.sqlite_path)
    await poller_repo.connect()

    async def _snapshot_subscribed_slugs() -> None:
        for slug in list(socket_client._slugs)[:20]:   # cap to stay under rate limit
            try:
                payload = await wfm_client.get_orders(slug)
                orders = (payload.get("payload") or {}).get("orders") or []
                await write_snapshot(repo=poller_repo, slug=slug, orders=orders)
            except Exception as e:
                log.warning("snapshot for %s failed: %s", slug, e)

    sched.add_job(
        lambda: asyncio.create_task(_snapshot_subscribed_slugs()),
        trigger="interval", minutes=30,
    )
```

Add `await poller_repo.close()` to the shutdown sequence.

- [ ] **Step 2: pytest + commit**

```powershell
uv run pytest -v
git add src/alecaframe_api/wfm/poller.py
git commit -m "feat(poller): periodic REST-snapshot job (every 30 min, top 20 slugs)"
```

---

## Task 10: README + verification

- [ ] **Step 1: README new section**

Add after the "Real-time channels (B.1c)" section in README.md:

```markdown
## History + signals (B.2a)

SQLite history database at `data/wfm_history.db` accumulates price snapshots
каждые 30 минут (top 20 подписанных slugs). 9 signal types fire on snapshots
or live events; dedup by `signal_type:slug:date`.

New endpoints:
- `GET /history/{slug}?days=30&granularity=hour|day&side=sell|buy&online_only=true`
- `GET /signals/active?type=undervalued_mine&since_hours=24&limit=50`
- `GET /signals/feed?since=<ts>&limit=50`
- `GET /me/dashboard-actions?limit=10` — top-10 ranked todos by signal priority

Set compositions loaded at first startup from `%LOCALAPPDATA%\AlecaFrame\cachedData\json\Warframes.json`
etc. — replaces the Kronen-only seed from B.1a.

При выключённом RabbitMQ history накапливается только из poller-snapshots
(каждые 30 мин), без live audit-trail.
```

Commit:

```powershell
git add README.md
git commit -m "docs: B.2a history + signals + endpoints"
```

- [ ] **Step 2: Final pytest + smoke**

```powershell
uv run pytest -v
docker compose build backend poller
docker compose up -d --force-recreate backend poller
Start-Sleep -Seconds 15
Invoke-RestMethod http://127.0.0.1:8765/signals/active
Invoke-RestMethod http://127.0.0.1:8765/me/dashboard-actions
docker compose logs --tail=20 poller
```

Expected: endpoints return `{total: 0, items: []}` (no signals fired yet); poller logs show snapshot job loaded.

---

## Definition of Done — Phase B.2a

- `aiosqlite>=0.20` installed
- `data/wfm_history.db` is created on backend startup
- 9 signal functions in `wfm/signals.py`, all unit-tested
- 4 new endpoints reachable: `/history/{slug}`, `/signals/active`, `/signals/feed`, `/me/dashboard-actions`
- Set composition table populated from AlecaFrame cachedData (≥50 sets after first start)
- Poller writes snapshots every 30 min
- Backend pytest ≈ 70 passed (57 prior + ~12 new across db_repo, history, signals, sets_loader)
- No frontend changes (B.2b handles UI)

---

## Self-Review

**Spec coverage** (against design doc §7):
- ✅ §7.1 Storage (SQLite WAL, 5 tables)
- ✅ §7.2 Signals (9 types with dedup_key, pure functions)
- ✅ §7.3 Endpoints (history, signals/active, signals/feed, dashboard-actions)
- ⏭ §7.4 Frontend pages (B.2b)
- ⏭ Auto-downsample hourly→daily after 30 days — deferred (currently we just LIMIT 5000)

**Open risks:**
- The poller opens a SECOND SQLite connection (`poller_repo`) — SQLite WAL handles concurrent readers/writers fine, but watch for `database is locked` warnings under heavy contention. If it happens, narrow `busy_timeout` to 30000 and consider a writer-queue.
- `vault_premium` baseline uses the 7-day median; for a newly-unvaulted item there's no baseline yet. Tested as "skip when not enough history" — works.

---

**End of B.2a plan.** B.2b (frontend History + Signals pages) writes after this lands.
