# Void Fissure Telegram Subscriptions — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Подписываться на разрывы Бездны (Void Fissures) по фильтру {эра, тип миссии, Steel Path, Void Storm} и получать уведомление в Telegram, когда в worldstate появляется подходящий разрыв.

**Architecture:** Новый async-`FissurePoller` (близнец `AuctionPoller`) в lifespan backend-а тянет разрывы из warframestat.us, матчит против подписок в SQLite и шлёт уведомления через Telegram Bot API; `TelegramBot` long-poll'ит `getUpdates` и регистрирует получателей по `/start`. Frontend — новая страница `Fissures` (управление подписками + живой список + панель Telegram), живой список через 30-сек polling (без Centrifugo).

**Tech Stack:** Python 3.12 / FastAPI / aiosqlite / httpx / pytest + pytest-asyncio + pytest-httpx; SolidJS / @tanstack/solid-query / Tailwind.

**Спека:** `docs/superpowers/specs/2026-06-21-void-fissure-telegram-subscriptions-design.md`

---

## File Structure

**Backend — новый подпакет `src/alecaframe_api/fissures/`:**
- `__init__.py` — пустой маркер пакета.
- `models.py` — `Fissure`, `Subscription`, `parse_fissure()`, `_planet_from_node()`, `PLATFORM_MAP`.
- `matcher.py` — чистая `matches(fissure, sub) -> bool`.
- `client.py` — `FissureClient` (httpx + TTL-кэш) + `FissureClientError`.
- `telegram.py` — `TelegramClient` (send/getUpdates) + `TelegramBot` (long-poll, `/start`).
- `poller.py` — `FissurePoller` + `format_message()`.
- `dependencies.py` — singleton `fissure_client` + `FissureClientDep`.
- `router.py` — REST под `/fissures`.

**Backend — правки существующих:**
- `src/alecaframe_api/config.py` — 3 новых поля settings.
- `src/alecaframe_api/db/schema.sql` — 3 таблицы.
- `src/alecaframe_api/db/repo.py` — методы подписок/чатов/журнала.
- `src/alecaframe_api/schemas.py` — Pydantic-модели ответов.
- `src/alecaframe_api/main.py` — wiring в lifespan + `include_router`.
- `.env.example`, `docker-compose.yml` — `TG_API_KEY`.

**Frontend:**
- `frontend/src/routes/Fissures.tsx` — новая страница.
- `frontend/src/api/types.ts`, `frontend/src/api/queries.ts` — типы + fetchers/keys.
- `frontend/src/main.tsx`, `frontend/src/components/Layout.tsx` — роут + навигация.
- `frontend/src/i18n/dict/en.ts`, `frontend/src/i18n/dict/ru.ts` — строки.

**Tests:** `tests/fixtures/wfm_fissures_sample.json` + `tests/test_fissures_{models,matcher,client,telegram,poller,repo,router}.py` + правка `tests/test_config.py` (или новый).

---

## Task 1: Config — settings для Telegram и источника разрывов

**Files:**
- Modify: `src/alecaframe_api/config.py`
- Test: `tests/test_fissures_config.py`

- [ ] **Step 1: Failing test**

Create `tests/test_fissures_config.py`:

```python
from __future__ import annotations


def test_tg_api_key_reads_unprefixed_env(monkeypatch) -> None:
    monkeypatch.setenv("TG_API_KEY", "12345:secret")
    from alecaframe_api.config import Settings
    s = Settings()
    assert s.tg_api_key == "12345:secret"


def test_fissure_defaults() -> None:
    from alecaframe_api.config import Settings
    s = Settings()
    assert s.fissure_poll_interval_seconds == 60
    assert s.fissure_source_base_url == "https://api.warframestat.us"
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_fissures_config.py -v`
Expected: FAIL (`AttributeError: 'Settings' object has no attribute 'tg_api_key'`).

- [ ] **Step 3: Implement**

In `src/alecaframe_api/config.py`, add these fields inside `class Settings` after the `wfm_rate_limit_per_second` field:

```python
    # void fissures + telegram
    tg_api_key: str | None = Field(default=None, validation_alias="TG_API_KEY")
    fissure_poll_interval_seconds: int = 60
    fissure_source_base_url: str = "https://api.warframestat.us"
```

(`Field` is already imported. `validation_alias` makes the env var exactly `TG_API_KEY`, bypassing the `ALECA_` prefix — same trick already used by `aleca_data_home`.)

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_fissures_config.py -v`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add src/alecaframe_api/config.py tests/test_fissures_config.py
git commit -m "feat(fissures): add TG_API_KEY + fissure source settings"
```

---

## Task 2: DB schema + Repo methods

**Files:**
- Modify: `src/alecaframe_api/db/schema.sql`
- Modify: `src/alecaframe_api/db/repo.py`
- Test: `tests/test_fissures_repo.py`

- [ ] **Step 1: Failing test**

Create `tests/test_fissures_repo.py`:

```python
from __future__ import annotations

import pytest

from alecaframe_api.db.repo import Repo


@pytest.fixture
async def repo(tmp_path):
    r = Repo(db_path=tmp_path / "t.db")
    await r.connect()
    yield r
    await r.close()


async def test_subscription_crud(repo: Repo) -> None:
    sub_id = await repo.add_fissure_subscription(
        era="Axi", mission_type=None, is_hard=True, is_storm=None, ts=100,
    )
    assert isinstance(sub_id, int)
    rows = await repo.list_fissure_subscriptions()
    assert len(rows) == 1
    assert rows[0]["era"] == "Axi"
    assert rows[0]["mission_type"] is None
    assert rows[0]["is_hard"] == 1
    assert rows[0]["is_storm"] is None
    assert rows[0]["enabled"] == 1
    assert await repo.remove_fissure_subscription(sub_id) is True
    assert await repo.remove_fissure_subscription(sub_id) is False
    assert await repo.list_fissure_subscriptions() == []


async def test_enabled_only_filter(repo: Repo) -> None:
    await repo.add_fissure_subscription(era="Lith", mission_type=None, is_hard=None, is_storm=None, ts=1)
    rows = await repo.list_fissure_subscriptions(enabled_only=True)
    assert len(rows) == 1


async def test_register_telegram_chat_idempotent(repo: Repo) -> None:
    await repo.register_telegram_chat(chat_id=555, username="alice", ts=10)
    await repo.register_telegram_chat(chat_id=555, username="alice2", ts=20)
    chats = await repo.list_telegram_chats()
    assert len(chats) == 1
    assert chats[0]["chat_id"] == 555
    assert chats[0]["username"] == "alice2"  # username updated, row not duplicated


async def test_notification_dedup_and_prune(repo: Repo) -> None:
    assert await repo.record_fissure_notification(subscription_id=1, fissure_id="f1", ts=100) is True
    assert await repo.record_fissure_notification(subscription_id=1, fissure_id="f1", ts=200) is False
    assert await repo.record_fissure_notification(subscription_id=1, fissure_id="f2", ts=100) is True
    pruned = await repo.prune_fissure_notifications(older_than=150)
    assert pruned == 2  # f1@100 and f2@100 removed; none left below 150
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_fissures_repo.py -v`
Expected: FAIL (`AttributeError: 'Repo' object has no attribute 'add_fissure_subscription'`).

- [ ] **Step 3a: Implement schema**

Append to `src/alecaframe_api/db/schema.sql`:

```sql

-- Void Fissure subscriptions + Telegram chats + notification dedup ledger.

CREATE TABLE IF NOT EXISTS fissure_subscription (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  era          TEXT,            -- NULL = any
  mission_type TEXT,            -- NULL = any
  is_hard      INTEGER,         -- 0 | 1 | NULL(any)
  is_storm     INTEGER,         -- 0 | 1 | NULL(any)
  enabled      INTEGER NOT NULL DEFAULT 1,
  created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_chat (
  chat_id       INTEGER PRIMARY KEY,
  username      TEXT,
  registered_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fissure_notification (
  subscription_id INTEGER NOT NULL,
  fissure_id      TEXT NOT NULL,
  notified_at     INTEGER NOT NULL,
  PRIMARY KEY (subscription_id, fissure_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_fissure_notif_at ON fissure_notification(notified_at);
```

- [ ] **Step 3b: Implement repo methods**

Append these methods to `class Repo` in `src/alecaframe_api/db/repo.py` (after `recent_gone_riven_auctions`):

```python
    # ----------------------------------------------------------- fissures

    async def add_fissure_subscription(
        self, *, era: str | None, mission_type: str | None,
        is_hard: bool | None, is_storm: bool | None, ts: int,
    ) -> int:
        conn = self._require_conn()
        cur = await conn.execute(
            """INSERT INTO fissure_subscription
               (era, mission_type, is_hard, is_storm, enabled, created_at)
               VALUES (?, ?, ?, ?, 1, ?)""",
            (era, mission_type,
             None if is_hard is None else int(is_hard),
             None if is_storm is None else int(is_storm),
             ts),
        )
        await conn.commit()
        return int(cur.lastrowid)

    async def list_fissure_subscriptions(
        self, *, enabled_only: bool = False,
    ) -> list[dict[str, Any]]:
        conn = self._require_conn()
        sql = ("SELECT id, era, mission_type, is_hard, is_storm, enabled, created_at "
               "FROM fissure_subscription")
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at DESC"
        async with conn.execute(sql) as cursor:
            cols = [c[0] for c in cursor.description]
            rows = await cursor.fetchall()
        return [dict(zip(cols, r)) for r in rows]

    async def remove_fissure_subscription(self, sub_id: int) -> bool:
        conn = self._require_conn()
        cur = await conn.execute(
            "DELETE FROM fissure_subscription WHERE id = ?", (sub_id,),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0

    async def register_telegram_chat(
        self, *, chat_id: int, username: str | None, ts: int,
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
        return [dict(zip(cols, r)) for r in rows]

    async def record_fissure_notification(
        self, *, subscription_id: int, fissure_id: str, ts: int,
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
            "DELETE FROM fissure_notification WHERE notified_at < ?", (older_than,),
        )
        await conn.commit()
        return cur.rowcount or 0
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_fissures_repo.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/alecaframe_api/db/schema.sql src/alecaframe_api/db/repo.py tests/test_fissures_repo.py
git commit -m "feat(fissures): add subscription, telegram_chat, notification tables + repo methods"
```

---

## Task 3: Fixture + models (parse_fissure)

**Files:**
- Create: `tests/fixtures/wfm_fissures_sample.json`
- Create: `src/alecaframe_api/fissures/__init__.py` (empty)
- Create: `src/alecaframe_api/fissures/models.py`
- Test: `tests/test_fissures_models.py`

- [ ] **Step 1: Create fixture**

Create `tests/fixtures/wfm_fissures_sample.json` (3 real objects: normal / Steel Path / Void Storm):

```json
[
  {
    "id": "6a37c4e71242731bf68ce5b2",
    "activation": "2026-06-21T11:03:03.054Z",
    "expiry": "2026-06-21T12:55:09.638Z",
    "node": "Tuvul Commons (Zariman)",
    "missionType": "Void Cascade",
    "enemy": "Crossfire",
    "tier": "Omnia",
    "tierNum": 6,
    "isStorm": false,
    "isHard": false
  },
  {
    "id": "6a37c2cad201d87c508ce5b1",
    "activation": "2026-06-21T10:54:02.850Z",
    "expiry": "2026-06-21T12:42:01.145Z",
    "node": "Proteus (Neptune)",
    "missionType": "Defense",
    "enemy": "Corpus",
    "tier": "Neo",
    "tierNum": 3,
    "isStorm": false,
    "isHard": true
  },
  {
    "id": "6a37bf830c9a9f02258ce5b1",
    "activation": "2026-06-21T11:20:03.351Z",
    "expiry": "2026-06-21T12:50:03.351Z",
    "node": "Bendar Cluster (Earth)",
    "missionType": "Skirmish",
    "enemy": "Grineer",
    "tier": "Lith",
    "tierNum": 1,
    "isStorm": true,
    "isHard": false
  }
]
```

- [ ] **Step 2: Failing test**

Create `tests/test_fissures_models.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

from alecaframe_api.fissures.models import parse_fissure, _planet_from_node


def _load() -> list[dict]:
    p = Path(__file__).parent / "fixtures" / "wfm_fissures_sample.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_parse_normal_storm_hard() -> None:
    raw = _load()
    normal = parse_fissure(raw[0])
    assert normal is not None
    assert normal.era == "Omnia"
    assert normal.mission_type == "Void Cascade"
    assert normal.is_hard is False and normal.is_storm is False
    assert normal.planet == "Zariman"

    hard = parse_fissure(raw[1])
    assert hard.is_hard is True and hard.is_storm is False
    assert hard.planet == "Neptune"

    storm = parse_fissure(raw[2])
    assert storm.is_storm is True and storm.is_hard is False
    assert storm.era == "Lith"
    assert storm.planet == "Earth"


def test_parse_skips_incomplete() -> None:
    assert parse_fissure({"id": "x", "tier": "Lith"}) is None  # no missionType
    assert parse_fissure({"tier": "Lith", "missionType": "Survival"}) is None  # no id


def test_planet_helper() -> None:
    assert _planet_from_node("Proteus (Neptune)") == "Neptune"
    assert _planet_from_node("NoParens") is None
    assert _planet_from_node(None) is None
```

- [ ] **Step 3: Run, verify fail**

Run: `uv run pytest tests/test_fissures_models.py -v`
Expected: FAIL (`ModuleNotFoundError: alecaframe_api.fissures.models`).

- [ ] **Step 4: Implement**

Create empty `src/alecaframe_api/fissures/__init__.py`.

Create `src/alecaframe_api/fissures/models.py`:

```python
"""Domain model for Void Fissures + parsing of warframestat.us payloads."""
from __future__ import annotations

from dataclasses import dataclass

# Map our settings Platform literal to warframestat.us path segments.
PLATFORM_MAP: dict[str, str] = {"pc": "pc", "xbox": "xb1", "ps4": "ps4", "switch": "swi"}


@dataclass(frozen=True)
class Fissure:
    id: str
    era: str            # warframestat.us `tier`: Lith/Meso/Neo/Axi/Requiem/Omnia
    mission_type: str
    node: str
    planet: str | None
    enemy: str | None
    is_hard: bool       # Steel Path
    is_storm: bool      # Void Storm (Railjack)
    activation: str | None
    expiry: str | None


@dataclass(frozen=True)
class Subscription:
    id: int
    era: str | None          # None = any
    mission_type: str | None # None = any
    is_hard: bool | None     # None = any
    is_storm: bool | None    # None = any
    enabled: bool
    created_at: int


def _planet_from_node(node: str | None) -> str | None:
    """`"Proteus (Neptune)"` -> `"Neptune"`. None if no parenthesised tail."""
    if not node:
        return None
    lo = node.rfind("(")
    hi = node.rfind(")")
    if lo != -1 and hi != -1 and hi > lo:
        return node[lo + 1 : hi].strip() or None
    return None


def parse_fissure(raw: dict) -> Fissure | None:
    """Normalise one warframestat.us fissure object. Returns None if the
    minimal identifying fields (id, tier, missionType) are missing."""
    fid = raw.get("id")
    era = raw.get("tier")
    mission_type = raw.get("missionType")
    if not fid or not era or not mission_type:
        return None
    node = raw.get("node") or ""
    return Fissure(
        id=str(fid),
        era=str(era),
        mission_type=str(mission_type),
        node=node,
        planet=_planet_from_node(node),
        enemy=raw.get("enemy"),
        is_hard=bool(raw.get("isHard")),
        is_storm=bool(raw.get("isStorm")),
        activation=raw.get("activation"),
        expiry=raw.get("expiry"),
    )
```

- [ ] **Step 5: Run, verify pass**

Run: `uv run pytest tests/test_fissures_models.py -v`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add tests/fixtures/wfm_fissures_sample.json src/alecaframe_api/fissures/__init__.py src/alecaframe_api/fissures/models.py tests/test_fissures_models.py
git commit -m "feat(fissures): Fissure/Subscription models + warframestat.us parser"
```

---

## Task 4: Matcher

**Files:**
- Create: `src/alecaframe_api/fissures/matcher.py`
- Test: `tests/test_fissures_matcher.py`

- [ ] **Step 1: Failing test**

Create `tests/test_fissures_matcher.py`:

```python
from __future__ import annotations

from alecaframe_api.fissures.matcher import matches
from alecaframe_api.fissures.models import Fissure, Subscription


def _fissure(**over) -> Fissure:
    base = dict(
        id="f1", era="Axi", mission_type="Survival", node="Xini (Eris)",
        planet="Eris", enemy="Infested", is_hard=False, is_storm=False,
        activation=None, expiry=None,
    )
    base.update(over)
    return Fissure(**base)


def _sub(**over) -> Subscription:
    base = dict(id=1, era=None, mission_type=None, is_hard=None,
                is_storm=None, enabled=True, created_at=0)
    base.update(over)
    return Subscription(**base)


def test_empty_subscription_matches_everything() -> None:
    assert matches(_fissure(), _sub()) is True


def test_era_filter() -> None:
    assert matches(_fissure(era="Axi"), _sub(era="Axi")) is True
    assert matches(_fissure(era="Axi"), _sub(era="Lith")) is False


def test_mission_filter() -> None:
    assert matches(_fissure(mission_type="Survival"), _sub(mission_type="Survival")) is True
    assert matches(_fissure(mission_type="Survival"), _sub(mission_type="Capture")) is False


def test_steel_path_and_storm_filters() -> None:
    assert matches(_fissure(is_hard=True), _sub(is_hard=True)) is True
    assert matches(_fissure(is_hard=False), _sub(is_hard=True)) is False
    assert matches(_fissure(is_storm=True), _sub(is_storm=True)) is True
    assert matches(_fissure(is_storm=False), _sub(is_storm=True)) is False


def test_combined_filter_all_must_match() -> None:
    f = _fissure(era="Axi", mission_type="Survival", is_hard=False, is_storm=False)
    assert matches(f, _sub(era="Axi", mission_type="Survival", is_hard=False, is_storm=False)) is True
    assert matches(f, _sub(era="Axi", mission_type="Defense")) is False
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_fissures_matcher.py -v`
Expected: FAIL (`ModuleNotFoundError: alecaframe_api.fissures.matcher`).

- [ ] **Step 3: Implement**

Create `src/alecaframe_api/fissures/matcher.py`:

```python
"""Pure predicate: does a live fissure satisfy a subscription filter?

A `None` field on the subscription means "any" for that axis. A fissure
matches iff every *specified* (non-None) axis is equal."""
from __future__ import annotations

from alecaframe_api.fissures.models import Fissure, Subscription


def matches(fissure: Fissure, sub: Subscription) -> bool:
    if sub.era is not None and fissure.era != sub.era:
        return False
    if sub.mission_type is not None and fissure.mission_type != sub.mission_type:
        return False
    if sub.is_hard is not None and fissure.is_hard != sub.is_hard:
        return False
    if sub.is_storm is not None and fissure.is_storm != sub.is_storm:
        return False
    return True
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_fissures_matcher.py -v`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add src/alecaframe_api/fissures/matcher.py tests/test_fissures_matcher.py
git commit -m "feat(fissures): subscription matcher predicate"
```

---

## Task 5: FissureClient (httpx + TTL cache)

**Files:**
- Create: `src/alecaframe_api/fissures/client.py`
- Test: `tests/test_fissures_client.py`

- [ ] **Step 1: Failing test**

Create `tests/test_fissures_client.py`:

```python
from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.fissures.client import FissureClient, FissureClientError


def _fixture() -> list[dict]:
    p = Path(__file__).parent / "fixtures" / "wfm_fissures_sample.json"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_get_fissures_parses(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://wf.test/pc/fissures", method="GET", json=_fixture(),
    )
    c = FissureClient(base_url="https://wf.test", platform="pc")
    out = await c.get_fissures(now=1000.0)
    assert len(out) == 3
    assert {f.era for f in out} == {"Omnia", "Neo", "Lith"}


@pytest.mark.asyncio
async def test_get_fissures_uses_ttl_cache(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://wf.test/pc/fissures", method="GET", json=_fixture(),
    )
    c = FissureClient(base_url="https://wf.test", platform="pc", cache_ttl=30.0)
    await c.get_fissures(now=1000.0)
    await c.get_fissures(now=1010.0)  # within TTL -> served from cache
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_platform_maps_to_warframestat_segment(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://wf.test/xb1/fissures", method="GET", json=[])
    c = FissureClient(base_url="https://wf.test", platform="xbox")
    await c.get_fissures(now=1.0)
    assert str(httpx_mock.get_request().url).endswith("/xb1/fissures")


@pytest.mark.asyncio
async def test_raises_on_5xx(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://wf.test/pc/fissures", method="GET", status_code=502)
    c = FissureClient(base_url="https://wf.test", platform="pc")
    with pytest.raises(FissureClientError):
        await c.get_fissures(now=1.0)
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_fissures_client.py -v`
Expected: FAIL (`ModuleNotFoundError: alecaframe_api.fissures.client`).

- [ ] **Step 3: Implement**

Create `src/alecaframe_api/fissures/client.py`:

```python
"""HTTP client for warframestat.us /fissures with a small in-process TTL cache
shared by the poller and the HTTP route (so a page load doesn't re-hit the
upstream more than once per `cache_ttl`)."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

import httpx

from alecaframe_api.fissures.models import Fissure, parse_fissure, PLATFORM_MAP

log = logging.getLogger("alecaframe.fissures.client")
_UA = "alecaframe-api fissure-poller"


class FissureClientError(RuntimeError):
    pass


@dataclass
class FissureClient:
    base_url: str = "https://api.warframestat.us"
    platform: str = "pc"
    timeout: float = 10.0
    cache_ttl: float = 30.0
    _cache: tuple[float, list[Fissure]] | None = field(default=None, init=False, repr=False)

    def _url(self) -> str:
        seg = PLATFORM_MAP.get(self.platform, "pc")
        return f"{self.base_url.rstrip('/')}/{seg}/fissures"

    async def get_fissures(self, *, now: float | None = None, fresh: bool = False) -> list[Fissure]:
        t = now if now is not None else time.time()
        if not fresh and self._cache is not None and (t - self._cache[0]) < self.cache_ttl:
            return self._cache[1]
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                resp = await c.get(self._url(), headers={"User-Agent": _UA, "Accept": "application/json"})
        except httpx.HTTPError as e:
            raise FissureClientError(f"fissures fetch failed: {e}") from e
        if resp.status_code >= 400:
            raise FissureClientError(f"fissures fetch status {resp.status_code}")
        try:
            data = resp.json()
        except ValueError as e:
            raise FissureClientError(f"fissures bad json: {e}") from e
        if not isinstance(data, list):
            raise FissureClientError("fissures payload is not a list")
        out: list[Fissure] = []
        for raw in data:
            if isinstance(raw, dict):
                f = parse_fissure(raw)
                if f is not None:
                    out.append(f)
        self._cache = (t, out)
        return out
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_fissures_client.py -v`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/alecaframe_api/fissures/client.py tests/test_fissures_client.py
git commit -m "feat(fissures): warframestat.us client with TTL cache"
```

---

## Task 6: Telegram client + bot (/start registration)

**Files:**
- Create: `src/alecaframe_api/fissures/telegram.py`
- Test: `tests/test_fissures_telegram.py`

- [ ] **Step 1: Failing test**

Create `tests/test_fissures_telegram.py`:

```python
from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.telegram import TelegramClient, TelegramBot


@pytest.fixture
async def repo(tmp_path):
    r = Repo(db_path=tmp_path / "t.db")
    await r.connect()
    yield r
    await r.close()


@pytest.mark.asyncio
async def test_send_message_hits_correct_url(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://tg.test/botTOKEN/sendMessage", method="POST", json={"ok": True},
    )
    c = TelegramClient(token="TOKEN", base_url="https://tg.test")
    ok = await c.send_message(555, "hi")
    assert ok is True
    req = httpx_mock.get_request()
    import json as _j
    body = _j.loads(req.content)
    assert body == {"chat_id": 555, "text": "hi"}


class _CapturingClient:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> bool:
        self.sent.append((chat_id, text))
        return True


@pytest.mark.asyncio
async def test_handle_updates_registers_on_start(repo: Repo) -> None:
    fake = _CapturingClient()
    bot = TelegramBot(client=fake, repo=repo)
    updates = [{
        "update_id": 10,
        "message": {"text": "/start", "chat": {"id": 777, "username": "bob"}},
    }]
    await bot.handle_updates(updates, now=123)
    chats = await repo.list_telegram_chats()
    assert len(chats) == 1 and chats[0]["chat_id"] == 777
    assert fake.sent and fake.sent[0][0] == 777   # welcome message sent
    assert bot._offset == 11                       # offset advanced past update_id


@pytest.mark.asyncio
async def test_handle_updates_ignores_non_start(repo: Repo) -> None:
    fake = _CapturingClient()
    bot = TelegramBot(client=fake, repo=repo)
    await bot.handle_updates(
        [{"update_id": 1, "message": {"text": "hello", "chat": {"id": 1}}}], now=1,
    )
    assert await repo.list_telegram_chats() == []
    assert fake.sent == []
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_fissures_telegram.py -v`
Expected: FAIL (`ModuleNotFoundError: alecaframe_api.fissures.telegram`).

- [ ] **Step 3: Implement**

Create `src/alecaframe_api/fissures/telegram.py`:

```python
"""Telegram Bot API: outbound sendMessage + inbound long-poll getUpdates.

Webhook is intentionally NOT used — the app runs locally without a public
HTTPS endpoint, so long-poll is the only viable inbound channel."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

import httpx

from alecaframe_api.db.repo import Repo

log = logging.getLogger("alecaframe.fissures.telegram")

WELCOME_TEXT = "✅ Подписка активна. Сюда будут приходить уведомления о разрывах Бездны."


class TelegramError(RuntimeError):
    pass


@dataclass
class TelegramClient:
    token: str
    base_url: str = "https://api.telegram.org"
    timeout: float = 30.0

    def _url(self, method: str) -> str:
        return f"{self.base_url.rstrip('/')}/bot{self.token}/{method}"

    async def send_message(self, chat_id: int, text: str) -> bool:
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as c:
                resp = await c.post(self._url("sendMessage"), json={"chat_id": chat_id, "text": text})
        except httpx.HTTPError as e:
            log.warning("telegram sendMessage failed: %s", e)
            return False
        if resp.status_code >= 400:
            log.warning("telegram sendMessage status %d: %s", resp.status_code, resp.text[:200])
            return False
        return True

    async def get_updates(self, *, offset: int | None = None, timeout: int = 25) -> list[dict]:
        params: dict = {"timeout": timeout}
        if offset is not None:
            params["offset"] = offset
        # client timeout must outlast the server-side long-poll window.
        async with httpx.AsyncClient(timeout=timeout + 10) as c:
            resp = await c.get(self._url("getUpdates"), params=params)
        if resp.status_code >= 400:
            raise TelegramError(f"getUpdates status {resp.status_code}")
        data = resp.json()
        if not data.get("ok"):
            raise TelegramError(f"getUpdates not ok: {str(data)[:200]}")
        return data.get("result") or []


@dataclass
class TelegramBot:
    client: TelegramClient
    repo: Repo
    poll_timeout: int = 25
    _offset: int | None = field(default=None, init=False)

    async def handle_updates(self, updates: list[dict], *, now: int) -> None:
        for u in updates:
            uid = u.get("update_id")
            if isinstance(uid, int):
                self._offset = max(self._offset or 0, uid + 1)
            msg = u.get("message") or u.get("edited_message") or {}
            text = (msg.get("text") or "").strip()
            chat = msg.get("chat") or {}
            chat_id = chat.get("id")
            if chat_id is None or not text:
                continue
            # first token, stripped of any @botname suffix
            if text.split()[0].split("@")[0] == "/start":
                username = chat.get("username") or chat.get("first_name")
                await self.repo.register_telegram_chat(chat_id=int(chat_id), username=username, ts=now)
                await self.client.send_message(int(chat_id), WELCOME_TEXT)

    async def run(self) -> None:
        log.info("telegram bot starting (long-poll)")
        while True:
            try:
                updates = await self.client.get_updates(offset=self._offset, timeout=self.poll_timeout)
                await self.handle_updates(updates, now=int(time.time()))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("telegram poll failed: %s", e)
                await asyncio.sleep(5)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_fissures_telegram.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/alecaframe_api/fissures/telegram.py tests/test_fissures_telegram.py
git commit -m "feat(fissures): telegram client + long-poll bot with /start registration"
```

---

## Task 7: FissurePoller

**Files:**
- Create: `src/alecaframe_api/fissures/poller.py`
- Test: `tests/test_fissures_poller.py`

- [ ] **Step 1: Failing test**

Create `tests/test_fissures_poller.py`:

```python
from __future__ import annotations

import pytest

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.models import Fissure
from alecaframe_api.fissures.poller import FissurePoller, format_message


@pytest.fixture
async def repo(tmp_path):
    r = Repo(db_path=tmp_path / "t.db")
    await r.connect()
    yield r
    await r.close()


def _f(fid: str, era: str, mt: str = "Survival", hard=False, storm=False) -> Fissure:
    return Fissure(id=fid, era=era, mission_type=mt, node="X (Eris)", planet="Eris",
                   enemy="Infested", is_hard=hard, is_storm=storm, activation=None, expiry=None)


class _FakeClient:
    def __init__(self, fissures: list[Fissure]) -> None:
        self.fissures = fissures

    async def get_fissures(self, *, now=None, fresh=False) -> list[Fissure]:
        return self.fissures


class _FakeTelegram:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id: int, text: str) -> bool:
        self.sent.append((chat_id, text))
        return True


@pytest.mark.asyncio
async def test_notify_then_dedup_then_new(repo: Repo) -> None:
    await repo.add_fissure_subscription(era="Axi", mission_type=None, is_hard=None, is_storm=None, ts=1)
    await repo.register_telegram_chat(chat_id=555, username=None, ts=1)
    client = _FakeClient([_f("a1", "Axi"), _f("l1", "Lith")])
    tg = _FakeTelegram()
    poller = FissurePoller(repo=repo, client=client, telegram=tg)

    await poller.tick(now=1000)
    assert len(tg.sent) == 1 and tg.sent[0][0] == 555  # only the Axi one matched

    await poller.tick(now=1001)
    assert len(tg.sent) == 1  # dedup: same fissure not re-sent

    client.fissures.append(_f("a2", "Axi"))
    await poller.tick(now=1002)
    assert len(tg.sent) == 2  # new Axi fissure fires once


@pytest.mark.asyncio
async def test_no_subscriptions_is_noop(repo: Repo) -> None:
    client = _FakeClient([_f("a1", "Axi")])
    tg = _FakeTelegram()
    poller = FissurePoller(repo=repo, client=client, telegram=tg)
    await poller.tick(now=1)
    assert tg.sent == []


def test_format_message_includes_axes() -> None:
    msg = format_message(_f("a1", "Axi", mt="Survival", hard=True))
    assert "Axi" in msg and "Survival" in msg
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_fissures_poller.py -v`
Expected: FAIL (`ModuleNotFoundError: alecaframe_api.fissures.poller`).

- [ ] **Step 3: Implement**

Create `src/alecaframe_api/fissures/poller.py`:

```python
"""FissurePoller — periodic match of live fissures against subscriptions.

Per tick:
1. Fetch live fissures (errors logged, tick never aborts).
2. Read enabled subscriptions; if none, just prune the ledger and return.
3. For each subscription × matching fissure not yet in the dedup ledger:
   record it, then (if Telegram is on) broadcast to every registered chat.
4. Prune ledger entries older than NOTIFICATION_TTL_S."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.client import FissureClient, FissureClientError
from alecaframe_api.fissures.matcher import matches
from alecaframe_api.fissures.models import Fissure, Subscription
from alecaframe_api.fissures.telegram import TelegramClient

log = logging.getLogger("alecaframe.fissures.poller")

DEFAULT_POLL_INTERVAL_S = 60.0
NOTIFICATION_TTL_S = 3 * 3600


def format_message(f: Fissure) -> str:
    track: list[str] = []
    if f.is_hard:
        track.append("Стальной путь")
    if f.is_storm:
        track.append("Void Storm")
    line2 = f"{f.era} · {f.mission_type}"
    if track:
        line2 += " · " + ", ".join(track)
    bits = ["🌀 Новый разрыв Бездны", line2]
    if f.node:
        bits.append(f.node)
    return "\n".join(bits)


def _row_to_sub(r: dict) -> Subscription:
    def _b(v) -> bool | None:
        return None if v is None else bool(v)
    return Subscription(
        id=int(r["id"]), era=r["era"], mission_type=r["mission_type"],
        is_hard=_b(r["is_hard"]), is_storm=_b(r["is_storm"]),
        enabled=bool(r["enabled"]), created_at=int(r["created_at"]),
    )


@dataclass
class FissurePoller:
    repo: Repo
    client: FissureClient
    telegram: TelegramClient | None = None
    poll_interval: float = DEFAULT_POLL_INTERVAL_S

    async def tick(self, *, now: int | None = None) -> None:
        t = now if now is not None else int(time.time())
        try:
            fissures = await self.client.get_fissures()
        except FissureClientError as e:
            log.warning("fissure fetch failed: %s; skipping tick", e)
            return
        subs_raw = await self.repo.list_fissure_subscriptions(enabled_only=True)
        if not subs_raw:
            await self.repo.prune_fissure_notifications(older_than=t - NOTIFICATION_TTL_S)
            return
        subs = [_row_to_sub(r) for r in subs_raw]
        chats = await self.repo.list_telegram_chats()
        for sub in subs:
            for f in fissures:
                if not matches(f, sub):
                    continue
                newly = await self.repo.record_fissure_notification(
                    subscription_id=sub.id, fissure_id=f.id, ts=t,
                )
                if not newly:
                    continue
                if self.telegram is not None and chats:
                    text = format_message(f)
                    for chat in chats:
                        await self.telegram.send_message(int(chat["chat_id"]), text)
        await self.repo.prune_fissure_notifications(older_than=t - NOTIFICATION_TTL_S)

    async def run(self) -> None:
        log.info("fissure poller starting; interval=%.1fs", self.poll_interval)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("fissure poller tick failed: %s", e)
            await asyncio.sleep(self.poll_interval)
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_fissures_poller.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/alecaframe_api/fissures/poller.py tests/test_fissures_poller.py
git commit -m "feat(fissures): poller matching live fissures to subscriptions with dedup"
```

---

## Task 8: Pydantic schemas

**Files:**
- Modify: `src/alecaframe_api/schemas.py`

- [ ] **Step 1: Implement** (no standalone test — exercised by Task 9's router tests)

Append to `src/alecaframe_api/schemas.py`:

```python
# ----- void fissures -------------------------------------------------------


class FissureRow(BaseModel):
    id: str
    era: str
    mission_type: str
    node: str
    planet: str | None = None
    enemy: str | None = None
    is_hard: bool
    is_storm: bool
    expiry: str | None = None
    eta_seconds: int | None = None


class FissuresResponse(BaseModel):
    total: int
    items: list[FissureRow]


class FissureMetaResponse(BaseModel):
    eras: list[str]
    mission_types: list[str]


class FissureSubscriptionRow(BaseModel):
    id: int
    era: str | None = None
    mission_type: str | None = None
    is_hard: bool | None = None
    is_storm: bool | None = None
    enabled: bool = True
    created_at: int


class FissureSubscriptionsResponse(BaseModel):
    total: int
    items: list[FissureSubscriptionRow]


class FissureSubscriptionCreate(BaseModel):
    era: str | None = None
    mission_type: str | None = None
    is_hard: bool | None = None
    is_storm: bool | None = None


class TelegramChatRow(BaseModel):
    chat_id: int
    username: str | None = None
    registered_at: int


class TelegramChatsResponse(BaseModel):
    bot_enabled: bool
    total: int
    items: list[TelegramChatRow]
```

- [ ] **Step 2: Verify import**

Run: `uv run python -c "import alecaframe_api.schemas as s; print(s.FissuresResponse, s.TelegramChatsResponse)"`
Expected: prints the two classes, no error.

- [ ] **Step 3: Commit**

```bash
git add src/alecaframe_api/schemas.py
git commit -m "feat(fissures): response schemas"
```

---

## Task 9: Dependencies + Router

**Files:**
- Create: `src/alecaframe_api/fissures/dependencies.py`
- Create: `src/alecaframe_api/fissures/router.py`
- Test: `tests/test_fissures_router.py`

- [ ] **Step 1: Failing test**

Create `tests/test_fissures_router.py`:

```python
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.models import Fissure
from alecaframe_api.fissures.router import router
from alecaframe_api.fissures.dependencies import get_fissure_client
from alecaframe_api.wfm.dependencies import get_repo


class _FakeClient:
    async def get_fissures(self, *, now=None, fresh=False) -> list[Fissure]:
        return [Fissure(id="a1", era="Axi", mission_type="Survival", node="X (Eris)",
                        planet="Eris", enemy="Infested", is_hard=False, is_storm=False,
                        activation=None, expiry=None)]


@pytest.fixture
async def client(tmp_path):
    repo = Repo(db_path=tmp_path / "t.db")
    await repo.connect()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_fissure_client] = lambda: _FakeClient()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    await repo.close()


@pytest.mark.asyncio
async def test_live_fissures(client: httpx.AsyncClient) -> None:
    r = await client.get("/fissures")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["items"][0]["era"] == "Axi"


@pytest.mark.asyncio
async def test_meta_includes_eras_and_live_mission(client: httpx.AsyncClient) -> None:
    r = await client.get("/fissures/meta")
    assert r.status_code == 200
    body = r.json()
    assert "Axi" in body["eras"]
    assert "Survival" in body["mission_types"]


@pytest.mark.asyncio
async def test_subscription_crud(client: httpx.AsyncClient) -> None:
    r = await client.post("/fissures/subscriptions", json={"era": "Axi", "is_hard": True})
    assert r.status_code == 201
    body = r.json()
    assert body["total"] == 1
    sub_id = body["items"][0]["id"]
    assert body["items"][0]["era"] == "Axi"
    assert body["items"][0]["is_hard"] is True

    r = await client.delete(f"/fissures/subscriptions/{sub_id}")
    assert r.status_code == 200
    r = await client.get("/fissures/subscriptions")
    assert r.json()["total"] == 0

    r = await client.delete(f"/fissures/subscriptions/{sub_id}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run, verify fail**

Run: `uv run pytest tests/test_fissures_router.py -v`
Expected: FAIL (`ModuleNotFoundError: alecaframe_api.fissures.router`).

- [ ] **Step 3a: Implement dependencies**

Create `src/alecaframe_api/fissures/dependencies.py`:

```python
"""DI singleton for the fissures router, populated by main.py lifespan."""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from alecaframe_api.fissures.client import FissureClient

fissure_client: FissureClient | None = None


def get_fissure_client() -> FissureClient:
    if fissure_client is None:
        raise RuntimeError("FissureClient not initialised; main.py lifespan must set it")
    return fissure_client


FissureClientDep = Annotated[FissureClient, Depends(get_fissure_client)]
```

- [ ] **Step 3b: Implement router**

Create `src/alecaframe_api/fissures/router.py`:

```python
"""HTTP surface for Void Fissure subscriptions + Telegram registration."""
from __future__ import annotations

import logging
import time
from datetime import datetime

from fastapi import APIRouter, HTTPException, status

from alecaframe_api.fissures.client import FissureClientError
from alecaframe_api.fissures.dependencies import FissureClientDep
from alecaframe_api.fissures.models import Fissure
from alecaframe_api.schemas import (
    FissureMetaResponse, FissureRow, FissuresResponse,
    FissureSubscriptionCreate, FissureSubscriptionRow, FissureSubscriptionsResponse,
    TelegramChatRow, TelegramChatsResponse,
)
from alecaframe_api.wfm.dependencies import RepoDep

log = logging.getLogger("alecaframe.fissures.router")

router = APIRouter(prefix="/fissures", tags=["fissures"])

ERAS = ["Lith", "Meso", "Neo", "Axi", "Requiem", "Omnia"]
KNOWN_MISSION_TYPES = [
    "Alchemy", "Assault", "Capture", "Defection", "Defense", "Disruption",
    "Excavation", "Extermination", "Hijack", "Interception", "Mobile Defense",
    "Orphix", "Rescue", "Sabotage", "Skirmish", "Spy", "Survival",
    "Void Cascade", "Void Flood", "Volatile",
]


def _eta_seconds(expiry: str | None, now: float) -> int | None:
    if not expiry:
        return None
    try:
        dt = datetime.fromisoformat(expiry.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0, int(dt.timestamp() - now))


def _to_row(f: Fissure, now: float) -> FissureRow:
    return FissureRow(
        id=f.id, era=f.era, mission_type=f.mission_type, node=f.node,
        planet=f.planet, enemy=f.enemy, is_hard=f.is_hard, is_storm=f.is_storm,
        expiry=f.expiry, eta_seconds=_eta_seconds(f.expiry, now),
    )


def _norm_sub(r: dict) -> dict:
    def _b(v) -> bool | None:
        return None if v is None else bool(v)
    return {
        "id": r["id"], "era": r["era"], "mission_type": r["mission_type"],
        "is_hard": _b(r["is_hard"]), "is_storm": _b(r["is_storm"]),
        "enabled": bool(r["enabled"]), "created_at": r["created_at"],
    }


@router.get("", response_model=FissuresResponse, summary="Current active Void Fissures")
async def list_fissures(client: FissureClientDep) -> FissuresResponse:
    try:
        fissures = await client.get_fissures()
    except FissureClientError as e:
        raise HTTPException(503, str(e)) from e
    now = time.time()
    rows = [_to_row(f, now) for f in fissures]
    rows.sort(key=lambda r: (r.is_storm, r.is_hard, r.era, r.mission_type))
    return FissuresResponse(total=len(rows), items=rows)


@router.get("/meta", response_model=FissureMetaResponse,
            summary="All possible fissure axes (eras + mission types)")
async def fissures_meta(client: FissureClientDep) -> FissureMetaResponse:
    live: set[str] = set()
    try:
        for f in await client.get_fissures():
            live.add(f.mission_type)
    except FissureClientError:
        pass
    return FissureMetaResponse(
        eras=ERAS, mission_types=sorted(set(KNOWN_MISSION_TYPES) | live),
    )


@router.get("/subscriptions", response_model=FissureSubscriptionsResponse)
async def list_subscriptions(repo: RepoDep) -> FissureSubscriptionsResponse:
    rows = await repo.list_fissure_subscriptions()
    items = [FissureSubscriptionRow(**_norm_sub(r)) for r in rows]
    return FissureSubscriptionsResponse(total=len(items), items=items)


@router.post("/subscriptions", response_model=FissureSubscriptionsResponse,
             status_code=status.HTTP_201_CREATED)
async def add_subscription(req: FissureSubscriptionCreate, repo: RepoDep) -> FissureSubscriptionsResponse:
    await repo.add_fissure_subscription(
        era=req.era or None, mission_type=req.mission_type or None,
        is_hard=req.is_hard, is_storm=req.is_storm, ts=int(time.time()),
    )
    rows = await repo.list_fissure_subscriptions()
    items = [FissureSubscriptionRow(**_norm_sub(r)) for r in rows]
    return FissureSubscriptionsResponse(total=len(items), items=items)


@router.delete("/subscriptions/{sub_id}")
async def remove_subscription(sub_id: int, repo: RepoDep) -> dict:
    if not await repo.remove_fissure_subscription(sub_id):
        raise HTTPException(404, f"subscription {sub_id} not found")
    return {"removed": sub_id}


@router.get("/telegram/chats", response_model=TelegramChatsResponse)
async def telegram_chats(repo: RepoDep) -> TelegramChatsResponse:
    from alecaframe_api.config import get_settings  # noqa: PLC0415
    rows = await repo.list_telegram_chats()
    items = [TelegramChatRow(**r) for r in rows]
    return TelegramChatsResponse(
        bot_enabled=bool(get_settings().tg_api_key), total=len(items), items=items,
    )


@router.post("/telegram/test")
async def telegram_test(repo: RepoDep) -> dict:
    from alecaframe_api.main import telegram_client  # noqa: PLC0415
    if telegram_client is None:
        raise HTTPException(503, "telegram disabled (TG_API_KEY not set)")
    chats = await repo.list_telegram_chats()
    sent = 0
    for chat in chats:
        if await telegram_client.send_message(int(chat["chat_id"]), "🔔 Тест: уведомления о разрывах работают."):
            sent += 1
    return {"sent": sent, "chats": len(chats)}
```

- [ ] **Step 4: Run, verify pass**

Run: `uv run pytest tests/test_fissures_router.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add src/alecaframe_api/fissures/dependencies.py src/alecaframe_api/fissures/router.py tests/test_fissures_router.py
git commit -m "feat(fissures): REST router (live, meta, subscriptions, telegram)"
```

---

## Task 10: Wire into main.py lifespan

**Files:**
- Modify: `src/alecaframe_api/main.py`

- [ ] **Step 1: Add imports**

In `src/alecaframe_api/main.py`, after the line `from .wfm.rivens_router import router as rivens_router`, add:

```python
from .fissures.client import FissureClient
from .fissures.poller import FissurePoller
from .fissures.telegram import TelegramClient, TelegramBot
from .fissures import dependencies as fissures_deps
from .fissures.router import router as fissures_router
```

- [ ] **Step 2: Add module globals**

After the line `auction_poller: AuctionPoller | None = None`, add:

```python
telegram_client: TelegramClient | None = None
fissure_poller: FissurePoller | None = None
```

- [ ] **Step 3: Start subsystem in lifespan**

In `lifespan`, right after the `auction_poller_task = asyncio.create_task(auction_poller.run())` line, insert:

```python

    # ----- Void Fissure subsystem -----
    global telegram_client, fissure_poller
    fissures_deps.fissure_client = FissureClient(
        base_url=_settings.fissure_source_base_url,
        platform=_settings.wfm_platform,
    )
    if _settings.tg_api_key:
        telegram_client = TelegramClient(token=_settings.tg_api_key)
    fissure_poller = FissurePoller(
        repo=repo, client=fissures_deps.fissure_client,
        telegram=telegram_client,
        poll_interval=float(_settings.fissure_poll_interval_seconds),
    )
    fissure_poller_task = asyncio.create_task(fissure_poller.run())
    telegram_bot_task: asyncio.Task | None = None
    if telegram_client is not None:
        telegram_bot = TelegramBot(client=telegram_client, repo=repo)
        telegram_bot_task = asyncio.create_task(telegram_bot.run())
    else:
        log.info("TG_API_KEY not set; telegram subsystem disabled")
```

- [ ] **Step 4: Cancel tasks on shutdown**

In the shutdown section (after `yield`), replace this block:

```python
    # Shutdown
    price_poller_task.cancel()
    auction_poller_task.cancel()
    for task in (price_poller_task, auction_poller_task):
```

with:

```python
    # Shutdown
    price_poller_task.cancel()
    auction_poller_task.cancel()
    fissure_poller_task.cancel()
    if telegram_bot_task is not None:
        telegram_bot_task.cancel()
    for task in (price_poller_task, auction_poller_task, fissure_poller_task, telegram_bot_task):
        if task is None:
            continue
```

(Note: the original loop body `try: await task / except ...:` stays as-is below the `for` header; just ensure the `if task is None: continue` guard is the first line inside the loop.)

- [ ] **Step 5: Include router**

After the line `app.include_router(rivens_router)`, add:

```python
app.include_router(fissures_router)
```

- [ ] **Step 6: Verify app imports + full suite green**

Run: `uv run python -c "import alecaframe_api.main as m; assert any(getattr(r,'path','').startswith('/fissures') for r in m.app.routes)"`
Expected: no error (the `/fissures` routes are registered).

Run: `uv run pytest -q`
Expected: all tests pass (existing + new fissures tests).

- [ ] **Step 7: Commit**

```bash
git add src/alecaframe_api/main.py
git commit -m "feat(fissures): start poller + telegram bot in lifespan, mount router"
```

---

## Task 11: Env + docker-compose

**Files:**
- Modify: `.env.example`
- Modify: `docker-compose.yml`

- [ ] **Step 1: .env.example**

Append to `.env.example`:

```bash

# Telegram bot for Void Fissure notifications (token from @BotFather).
# Leave empty to disable the Telegram subsystem (poller still runs; the
# Fissures page still shows live fissures, just no Telegram messages).
TG_API_KEY=
```

- [ ] **Step 2: docker-compose.yml**

In `docker-compose.yml`, add this line to the `x-backend-env: &backend-env` anchor block (e.g. after `ALECA_LOG_LEVEL: ...`):

```yaml
  TG_API_KEY: ${TG_API_KEY:-}
```

(The anchor is merged into both `backend` and `poller`; the fissure subsystem runs in `backend`, which is what needs it.)

- [ ] **Step 3: Verify compose parses**

Run: `docker compose config >/dev/null && echo OK`
Expected: `OK` (no YAML error). If `docker` is unavailable in the dev shell, skip with a note.

- [ ] **Step 4: Commit**

```bash
git add .env.example docker-compose.yml
git commit -m "chore(fissures): expose TG_API_KEY to backend container"
```

---

## Task 12: Frontend types

**Files:**
- Modify: `frontend/src/api/types.ts`

- [ ] **Step 1: Implement**

Append to `frontend/src/api/types.ts`:

```typescript
// ----- void fissures -------------------------------------------------------

export type FissureRow = {
  id: string;
  era: string;
  mission_type: string;
  node: string;
  planet: string | null;
  enemy: string | null;
  is_hard: boolean;
  is_storm: boolean;
  expiry: string | null;
  eta_seconds: number | null;
};

export type FissuresResponse = { total: number; items: FissureRow[] };

export type FissureMetaResponse = { eras: string[]; mission_types: string[] };

export type FissureSubscriptionRow = {
  id: number;
  era: string | null;
  mission_type: string | null;
  is_hard: boolean | null;
  is_storm: boolean | null;
  enabled: boolean;
  created_at: number;
};

export type FissureSubscriptionsResponse = { total: number; items: FissureSubscriptionRow[] };

export type FissureSubscriptionCreate = {
  era: string | null;
  mission_type: string | null;
  is_hard: boolean | null;
  is_storm: boolean | null;
};

export type TelegramChatRow = { chat_id: number; username: string | null; registered_at: number };

export type TelegramChatsResponse = { bot_enabled: boolean; total: number; items: TelegramChatRow[] };
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "feat(fissures): frontend types"
```

---

## Task 13: Frontend queries (keys + fetchers)

**Files:**
- Modify: `frontend/src/api/queries.ts`

- [ ] **Step 1: Implement**

In `frontend/src/api/queries.ts`:

a) Ensure the new types are imported (extend the existing `import type { ... } from "./types"` block):

```typescript
  FissuresResponse,
  FissureMetaResponse,
  FissureSubscriptionsResponse,
  FissureSubscriptionCreate,
  TelegramChatsResponse,
```

b) Add to the `keys` object:

```typescript
  fissuresLive:  () => ["fissures", "live"] as const,
  fissuresMeta:  () => ["fissures", "meta"] as const,
  fissuresSubs:  () => ["fissures", "subs"] as const,
  fissuresChats: () => ["fissures", "chats"] as const,
```

c) Add to the `fetchers` object:

```typescript
  fissuresLive: () => api<FissuresResponse>("/fissures"),
  fissuresMeta: () => api<FissureMetaResponse>("/fissures/meta"),
  fissuresSubsList: () => api<FissureSubscriptionsResponse>("/fissures/subscriptions"),
  fissuresSubAdd: (body: FissureSubscriptionCreate) =>
    api<FissureSubscriptionsResponse>("/fissures/subscriptions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  fissuresSubRemove: (id: number) =>
    api<{ removed: number }>(`/fissures/subscriptions/${id}`, { method: "DELETE" }),
  fissuresChats: () => api<TelegramChatsResponse>("/fissures/telegram/chats"),
  fissuresTest: () => api<{ sent: number; chats: number }>("/fissures/telegram/test", { method: "POST" }),
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/queries.ts
git commit -m "feat(fissures): frontend query keys + fetchers"
```

---

## Task 14: Frontend page (Fissures.tsx)

**Files:**
- Create: `frontend/src/routes/Fissures.tsx`

- [ ] **Step 1: Implement**

Create `frontend/src/routes/Fissures.tsx`:

```tsx
import { For, Show, createSignal } from "solid-js";
import { createQuery, useQueryClient } from "@tanstack/solid-query";
import Card from "../components/Card";
import Badge from "../components/Badge";
import EmptyState from "../components/EmptyState";
import { fetchers, keys } from "../api/queries";
import { t } from "../i18n";

// tri-state <select> value -> nullable bool: "" any, "yes" true, "no" false.
function triToBool(v: string): boolean | null {
  if (v === "yes") return true;
  if (v === "no") return false;
  return null;
}

function fmtEta(sec: number | null | undefined): string {
  if (sec == null) return "";
  const m = Math.floor(sec / 60);
  if (m < 60) return `${m}m`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

const selectClass =
  "w-full px-2 py-1 text-sm rounded-md bg-slate-900 border border-slate-800 text-slate-100";

export default function Fissures() {
  const qc = useQueryClient();

  const live = createQuery(() => ({
    queryKey: keys.fissuresLive(),
    queryFn: fetchers.fissuresLive,
    refetchInterval: 30_000,
  }));
  const meta = createQuery(() => ({
    queryKey: keys.fissuresMeta(),
    queryFn: fetchers.fissuresMeta,
    staleTime: 60 * 60 * 1000,
  }));
  const subs = createQuery(() => ({
    queryKey: keys.fissuresSubs(),
    queryFn: fetchers.fissuresSubsList,
    refetchInterval: 30_000,
  }));
  const chats = createQuery(() => ({
    queryKey: keys.fissuresChats(),
    queryFn: fetchers.fissuresChats,
    refetchInterval: 30_000,
  }));

  const [era, setEra] = createSignal("");
  const [mission, setMission] = createSignal("");
  const [hard, setHard] = createSignal("");
  const [storm, setStorm] = createSignal("");

  async function addSub() {
    await fetchers.fissuresSubAdd({
      era: era() || null,
      mission_type: mission() || null,
      is_hard: triToBool(hard()),
      is_storm: triToBool(storm()),
    });
    setEra(""); setMission(""); setHard(""); setStorm("");
    await qc.invalidateQueries({ queryKey: keys.fissuresSubs() });
  }

  async function removeSub(id: number) {
    await fetchers.fissuresSubRemove(id);
    await qc.invalidateQueries({ queryKey: keys.fissuresSubs() });
  }

  async function sendTest() {
    await fetchers.fissuresTest();
    await qc.invalidateQueries({ queryKey: keys.fissuresChats() });
  }

  return (
    <div class="space-y-4">
      <header class="flex items-center gap-3">
        <h1 class="text-2xl font-bold">{t("fissures.title")}</h1>
      </header>

      <div class="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4">
        <div class="space-y-4">
          <Card title={t("fissures.subscriptions")}>
            <div class="space-y-2">
              <label class="block text-xs text-slate-400">{t("fissures.era")}</label>
              <select value={era()} onChange={(e) => setEra(e.currentTarget.value)} class={selectClass}>
                <option value="">{t("fissures.any")}</option>
                <For each={meta.data?.eras ?? []}>{(x) => <option value={x}>{x}</option>}</For>
              </select>

              <label class="block text-xs text-slate-400">{t("fissures.mission")}</label>
              <select value={mission()} onChange={(e) => setMission(e.currentTarget.value)} class={selectClass}>
                <option value="">{t("fissures.any")}</option>
                <For each={meta.data?.mission_types ?? []}>{(x) => <option value={x}>{x}</option>}</For>
              </select>

              <label class="block text-xs text-slate-400">{t("fissures.steelPath")}</label>
              <select value={hard()} onChange={(e) => setHard(e.currentTarget.value)} class={selectClass}>
                <option value="">{t("fissures.any")}</option>
                <option value="yes">{t("fissures.yes")}</option>
                <option value="no">{t("fissures.no")}</option>
              </select>

              <label class="block text-xs text-slate-400">{t("fissures.voidStorm")}</label>
              <select value={storm()} onChange={(e) => setStorm(e.currentTarget.value)} class={selectClass}>
                <option value="">{t("fissures.any")}</option>
                <option value="yes">{t("fissures.yes")}</option>
                <option value="no">{t("fissures.no")}</option>
              </select>

              <button
                type="button"
                onClick={addSub}
                class="w-full mt-2 px-2 py-1.5 text-sm rounded-md bg-sky-600 hover:bg-sky-500 text-white"
              >
                {t("fissures.addSub")}
              </button>
            </div>

            <div class="mt-4">
              <Show
                when={(subs.data?.items ?? []).length > 0}
                fallback={<div class="text-sm text-slate-500">{t("fissures.subsEmpty")}</div>}
              >
                <ul class="space-y-1">
                  <For each={subs.data?.items ?? []}>
                    {(s) => (
                      <li class="flex items-center justify-between gap-2 px-2 py-1 rounded bg-slate-900/50 text-sm">
                        <span class="flex flex-wrap gap-1 items-center">
                          <Badge variant="info">{s.era ?? t("fissures.any")}</Badge>
                          <Badge>{s.mission_type ?? t("fissures.any")}</Badge>
                          <Show when={s.is_hard === true}><Badge variant="warn">SP</Badge></Show>
                          <Show when={s.is_storm === true}><Badge variant="vaulted">Storm</Badge></Show>
                        </span>
                        <button
                          type="button"
                          onClick={() => removeSub(s.id)}
                          class="text-slate-500 hover:text-rose-400 px-1"
                        >
                          ×
                        </button>
                      </li>
                    )}
                  </For>
                </ul>
              </Show>
            </div>
          </Card>

          <Card title={t("fissures.telegram")}>
            <Show
              when={chats.data?.bot_enabled}
              fallback={<div class="text-sm text-amber-300">{t("fissures.botDisabled")}</div>}
            >
              <p class="text-sm text-slate-400">{t("fissures.startHint")}</p>
              <div class="mt-2">
                <Show
                  when={(chats.data?.items ?? []).length > 0}
                  fallback={<div class="text-sm text-slate-500">{t("fissures.noChats")}</div>}
                >
                  <ul class="space-y-1">
                    <For each={chats.data?.items ?? []}>
                      {(c) => (
                        <li class="text-sm text-slate-300">{c.username ? `@${c.username}` : c.chat_id}</li>
                      )}
                    </For>
                  </ul>
                </Show>
              </div>
              <button
                type="button"
                onClick={sendTest}
                class="w-full mt-3 px-2 py-1.5 text-sm rounded-md bg-slate-700 hover:bg-slate-600 text-white"
              >
                {t("fissures.sendTest")}
              </button>
            </Show>
          </Card>
        </div>

        <Card title={t("fissures.live")}>
          <Show
            when={(live.data?.items ?? []).length > 0}
            fallback={<EmptyState title={t("fissures.liveEmpty")} hint="" />}
          >
            <ul class="space-y-1">
              <For each={live.data?.items ?? []}>
                {(f) => (
                  <li class="flex items-center justify-between gap-2 px-2 py-1.5 rounded bg-slate-900/40 text-sm">
                    <span class="flex flex-wrap items-center gap-1.5">
                      <Badge variant="info">{f.era}</Badge>
                      <span class="text-slate-100">{f.mission_type}</span>
                      <span class="text-slate-500">· {f.node}</span>
                      <Show when={f.is_hard}><Badge variant="warn">SP</Badge></Show>
                      <Show when={f.is_storm}><Badge variant="vaulted">Storm</Badge></Show>
                    </span>
                    <span class="text-xs text-slate-500 font-mono">{fmtEta(f.eta_seconds)}</span>
                  </li>
                )}
              </For>
            </ul>
          </Show>
        </Card>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/routes/Fissures.tsx
git commit -m "feat(fissures): Fissures page (subscriptions, live list, telegram panel)"
```

---

## Task 15: Route + nav + i18n

**Files:**
- Modify: `frontend/src/main.tsx`
- Modify: `frontend/src/components/Layout.tsx`
- Modify: `frontend/src/i18n/dict/en.ts`
- Modify: `frontend/src/i18n/dict/ru.ts`

- [ ] **Step 1: Route in main.tsx**

In `frontend/src/main.tsx`, next to the other `lazy(() => import("./routes/..."))` lines add:

```typescript
const Fissures = lazy(() => import("./routes/Fissures"));
```

and next to the other `<Route .../>` lines add:

```tsx
<Route path="/fissures" component={Fissures} />
```

- [ ] **Step 2: Nav in Layout.tsx**

In `frontend/src/components/Layout.tsx`, add to the `NAV` array (after the `/rivens` entry):

```typescript
  { href: "/fissures",    key: "nav.fissures"   },
```

- [ ] **Step 3: en.ts strings**

In `frontend/src/i18n/dict/en.ts`: add `fissures: "Fissures",` to the `nav` object, and add this section as a sibling of `rivens`:

```typescript
  fissures: {
    title: "Void Fissures",
    subscriptions: "Subscriptions",
    era: "Relic era",
    mission: "Mission type",
    steelPath: "Steel Path",
    voidStorm: "Void Storm",
    any: "Any",
    yes: "Yes",
    no: "No",
    addSub: "Subscribe",
    subsEmpty: "No subscriptions yet",
    telegram: "Telegram",
    botDisabled: "Telegram bot is off (TG_API_KEY not set)",
    startHint: "Message the bot /start to receive notifications.",
    noChats: "No one registered yet — send the bot /start.",
    sendTest: "Send test message",
    live: "Active fissures",
    liveEmpty: "No active fissures right now",
  },
```

- [ ] **Step 4: ru.ts strings**

In `frontend/src/i18n/dict/ru.ts`: add `fissures: "Разрывы",` to the `nav` object, and add this section as a sibling of `rivens`:

```typescript
  fissures: {
    title: "Разрывы Бездны",
    subscriptions: "Подписки",
    era: "Эра реликвии",
    mission: "Тип миссии",
    steelPath: "Стальной путь",
    voidStorm: "Void Storm",
    any: "Любое",
    yes: "Да",
    no: "Нет",
    addSub: "Подписаться",
    subsEmpty: "Подписок пока нет",
    telegram: "Telegram",
    botDisabled: "Бот Telegram выключен (TG_API_KEY не задан)",
    startHint: "Напиши боту /start, чтобы получать уведомления.",
    noChats: "Пока никто не зарегистрирован — напиши боту /start.",
    sendTest: "Отправить тест",
    live: "Активные разрывы",
    liveEmpty: "Сейчас активных разрывов нет",
  },
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/main.tsx frontend/src/components/Layout.tsx frontend/src/i18n/dict/en.ts frontend/src/i18n/dict/ru.ts
git commit -m "feat(fissures): route, nav link, i18n strings (en/ru)"
```

---

## Task 16: Frontend build verification

**Files:** none (verification only)

- [ ] **Step 1: Typecheck + build**

Run: `cd frontend && npm run build`
Expected: build succeeds, no TypeScript errors. If type errors surface, fix them in the relevant file (most likely a missing type import in `queries.ts` or a key typo in i18n) and re-run.

- [ ] **Step 2: Commit (only if fixes were needed)**

```bash
git add -A frontend
git commit -m "fix(fissures): resolve frontend build issues"
```

---

## Final verification

- [ ] **Backend suite green:** `uv run pytest -q` → all pass.
- [ ] **App mounts routes:** `/fissures`, `/fissures/meta`, `/fissures/subscriptions`, `/fissures/telegram/chats` present in `app.routes`.
- [ ] **Manual smoke (optional, needs stack + real bot token):**
  1. Put a real token in `.env` as `TG_API_KEY=...`, `docker compose up -d`.
  2. Message the bot `/start` → expect the welcome reply; the chat appears under `GET /fissures/telegram/chats`.
  3. `POST /fissures/subscriptions {"era":"Lith"}`; within ~1 min of a Lith fissure being live, expect a Telegram message.
  4. `POST /fissures/telegram/test` → expect the test message in Telegram.

---

## .gitignore note

Перед финальным коммитом убедиться, что в репозиторий не попадают артефакты: `scratch/`, `scripts/research_*.txt`, `scripts/probe_dll_output.json` (если они не нужны). Эта фича новых артефактов не порождает (только тестовая фикстура `tests/fixtures/wfm_fissures_sample.json`, которая коммитится намеренно).
