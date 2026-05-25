# Phase B.1a: WFM REST Client + on-demand endpoints — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a rate-limited, Redis-cached, asyncio-native WFM REST client and expose backend endpoints under `/wfm/*` (proxy-style) and `/me/*` (your-inventory-merged-with-market) so that any caller — curl, the existing SolidJS skeleton, or B.1b's new pages — can read warframe.market data live.

**Architecture:** A single `WFMClient` class owns every HTTP call to `api.warframe.market`. It pulls the JWT from `decrypt-agent`, applies a Redis-shared 3-req/s token bucket, and caches every response in Redis with per-endpoint TTLs. Slug resolution (DE `uniqueName` ↔ WFM slug) is bootstrapped at first call by hitting `/v1/items` once and stashing the mapping in Redis for 24h. Set-profit and `wtb-matches` are pure functions over inventory + order books.

**Tech Stack:** Python 3.13 + FastAPI + httpx (async) + redis.asyncio + aiolimiter + pydantic + pytest-httpx + pytest-asyncio.

---

## File Map

**Create:**
- `src/alecaframe_api/infra/__init__.py` — package marker
- `src/alecaframe_api/infra/cache.py` — Redis async-client wrapper (`Cache` class)
- `src/alecaframe_api/wfm/slugs.py` — `SlugResolver` + uniqueName→slug heuristics
- `src/alecaframe_api/wfm/client.py` — `WFMClient` (REST methods + rate-limit + cache)
- `src/alecaframe_api/wfm/prices.py` — `compute_stats(orders, online_only)` aggregator
- `src/alecaframe_api/wfm/sets.py` — `SetIndex` + `compute_set_profits(inventory, prices)`
- `src/alecaframe_api/wfm/router.py` — `APIRouter` for `/wfm/*`, `/me/*`
- `src/alecaframe_api/wfm/dependencies.py` — FastAPI `Depends()` providers (`get_wfm_client`, `get_slug_resolver`)
- `tests/test_infra_cache.py`
- `tests/test_wfm_slugs.py`
- `tests/test_wfm_client.py`
- `tests/test_wfm_prices.py`
- `tests/test_wfm_sets.py`
- `tests/fixtures/wfm_items_sample.json` — recorded `/v1/items` slice (≈15 prime parts + a few mods)
- `tests/fixtures/wfm_orders_kronen_prime_blade.json` — recorded `/v1/items/.../orders`

**Modify:**
- `pyproject.toml` — add `aiolimiter>=1.2`, `redis>=5.2`; bump `httpx>=0.28` (already in main from B.0); confirm `pytest-httpx>=0.36` and `fakeredis>=2.26` in dev
- `src/alecaframe_api/config.py` — add `wfm_base_url` field with default `https://api.warframe.market/v1`
- `src/alecaframe_api/main.py` — `app.include_router(wfm_router)`; create `WFMClient` + `SlugResolver` in lifespan; expose via dependency providers
- `src/alecaframe_api/schemas.py` — extend with `OrderRow`, `OrderBookStats`, `OrderBookResponse`, `PricedItemEntry`, `PricedItemListResponse`, `SetProfitRow`, `SetProfitResponse`, `WtbMatchRow`, `WtbMatchResponse`, `RelistNudgeRow`, `RelistNudgeResponse`
- `README.md` — add B.1a endpoints to the "Endpoints" section

**Out of scope (deferred to B.1b/B.1c):**
- Any frontend page or new component
- RabbitMQ / WebSocket / Centrifugo wiring
- Signals / forecasts / history persistence

---

## Conventions

- **Commit format:** Conventional Commits.
- **Branch:** `feature/b1a-wfm-rest` (already created from `master` @ `ab4edea`).
- **All test commands:** `uv run pytest ...` from project root.
- **Working directory:** `B:\Sync\Programming\projects\aleca frame inventory`.
- **Real-WFM-API calls in tests:** forbidden. All HTTP is mocked with `pytest-httpx`. All Redis is faked with `fakeredis`.

---

## Task 1: Add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add runtime deps**

Run:
```powershell
uv add 'aiolimiter>=1.2' 'redis>=5.2'
```

Expected: deps added, `uv.lock` updated.

- [ ] **Step 2: Add dev deps**

Run:
```powershell
uv add --dev 'fakeredis>=2.26'
```

Expected: dev dep added.

- [ ] **Step 3: Confirm**

```powershell
uv run python -c "import aiolimiter, redis.asyncio, fakeredis; print('ok', aiolimiter.__version__, redis.__version__, fakeredis.__version__)"
```

Expected: `ok 1.x.x 5.x.x 2.x.x` — versions print, no ImportError.

- [ ] **Step 4: Commit**

```powershell
git add pyproject.toml uv.lock
git commit -m "build: add aiolimiter, redis, fakeredis deps for WFM client"
```

---

## Task 2: Settings extension

**Files:**
- Modify: `src/alecaframe_api/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_config.py` (after the existing two tests):

```python


def test_wfm_base_url_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ALECA_WFM_BASE_URL", raising=False)
    s = reload_settings()
    assert s.wfm_base_url == "https://api.warframe.market/v1"


def test_wfm_base_url_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALECA_WFM_BASE_URL", "https://mock.wfm.test/v1")
    s = reload_settings()
    assert s.wfm_base_url == "https://mock.wfm.test/v1"
```

- [ ] **Step 2: Verify the new tests fail**

```powershell
uv run pytest tests/test_config.py -v
```

Expected: 2 new tests fail with `AttributeError: 'Settings' object has no attribute 'wfm_base_url'`. The 2 existing tests still pass.

- [ ] **Step 3: Add the field**

In `src/alecaframe_api/config.py`, find the `# warframe.market specifics` section and add `wfm_base_url` before `wfm_platform`:

```python
    # warframe.market specifics
    wfm_base_url: str = "https://api.warframe.market/v1"
    wfm_platform: Platform = "pc"
    wfm_language: str = "en"
    wfm_rate_limit_per_second: int = 3
```

- [ ] **Step 4: Verify all config tests pass**

```powershell
uv run pytest tests/test_config.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/config.py tests/test_config.py
git commit -m "feat(config): add wfm_base_url setting"
```

---

## Task 3: `infra/cache.py` — Redis async wrapper

**Files:**
- Create: `src/alecaframe_api/infra/__init__.py`
- Create: `src/alecaframe_api/infra/cache.py`
- Create: `tests/test_infra_cache.py`

- [ ] **Step 1: Package marker**

Create `src/alecaframe_api/infra/__init__.py`:

```python
"""Cross-cutting infrastructure: cache, broker, push.

Modules in this package own one external system each and expose a small
async-friendly facade for the rest of the codebase.
"""
```

- [ ] **Step 2: Failing tests first**

Create `tests/test_infra_cache.py`:

```python
"""Tests for the Redis cache wrapper."""
from __future__ import annotations

import pytest

from alecaframe_api.infra.cache import Cache


@pytest.fixture
async def cache() -> Cache:
    """fakeredis-backed Cache instance, isolated per test."""
    import fakeredis.aioredis
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = Cache(client=client, key_prefix="test")
    yield c
    await client.aclose()


@pytest.mark.asyncio
async def test_set_then_get_json_roundtrip(cache: Cache) -> None:
    await cache.set_json("foo", {"a": 1, "b": [2, 3]}, ttl_seconds=60)
    got = await cache.get_json("foo")
    assert got == {"a": 1, "b": [2, 3]}


@pytest.mark.asyncio
async def test_get_json_missing_returns_none(cache: Cache) -> None:
    got = await cache.get_json("nope")
    assert got is None


@pytest.mark.asyncio
async def test_delete(cache: Cache) -> None:
    await cache.set_json("k", {"x": 1}, ttl_seconds=60)
    await cache.delete("k")
    assert await cache.get_json("k") is None


@pytest.mark.asyncio
async def test_key_prefix_isolation() -> None:
    """Two caches with different prefixes must not see each other's keys."""
    import fakeredis.aioredis
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a = Cache(client=client, key_prefix="a")
    b = Cache(client=client, key_prefix="b")
    await a.set_json("k", {"who": "a"}, ttl_seconds=60)
    assert await b.get_json("k") is None
    assert (await a.get_json("k")) == {"who": "a"}
    await client.aclose()


@pytest.mark.asyncio
async def test_ttl_is_applied(cache: Cache) -> None:
    """The wrapper sets EXPIRE — verify TTL is non-negative on a fresh key."""
    await cache.set_json("ttlcheck", {"k": 1}, ttl_seconds=60)
    # fakeredis exposes the underlying client; check ttl > 0
    ttl = await cache.ttl_seconds("ttlcheck")
    assert ttl is not None and 0 < ttl <= 60


@pytest.mark.asyncio
async def test_get_or_set_calls_loader_on_miss(cache: Cache) -> None:
    calls = {"n": 0}

    async def loader() -> dict:
        calls["n"] += 1
        return {"computed": True}

    first = await cache.get_or_set_json("lazy", ttl_seconds=60, loader=loader)
    second = await cache.get_or_set_json("lazy", ttl_seconds=60, loader=loader)
    assert first == {"computed": True}
    assert second == {"computed": True}
    assert calls["n"] == 1  # loader called once, second hit was cached
```

- [ ] **Step 3: Run, verify all six fail**

```powershell
uv run pytest tests/test_infra_cache.py -v
```

Expected: 6 errors / fails — `ModuleNotFoundError: No module named 'alecaframe_api.infra.cache'`.

- [ ] **Step 4: Implement `cache.py`**

Create `src/alecaframe_api/infra/cache.py`:

```python
"""Async Redis cache wrapper.

Thin convenience layer on top of `redis.asyncio.Redis` so callers don't
sprinkle JSON-serialisation boilerplate everywhere. Every key is prefixed
to isolate logical namespaces (e.g. `wfm` vs `signals`).

Designed for `dict[str, Any]` payloads — anything else, use the client directly.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Protocol


class _RedisLike(Protocol):
    """Just the redis.asyncio.Redis methods we touch."""
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ex: int | None = None) -> Any: ...
    async def delete(self, *keys: str) -> int: ...
    async def ttl(self, key: str) -> int: ...


@dataclass
class Cache:
    """Async JSON-aware Redis cache with mandatory key prefix."""

    client: _RedisLike
    key_prefix: str

    def _k(self, key: str) -> str:
        return f"{self.key_prefix}:{key}"

    async def get_json(self, key: str) -> dict[str, Any] | None:
        raw = await self.client.get(self._k(key))
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Corrupt cache entry — drop it so the next caller refills.
            await self.client.delete(self._k(key))
            return None

    async def set_json(self, key: str, value: dict[str, Any], *, ttl_seconds: int) -> None:
        await self.client.set(self._k(key), json.dumps(value, ensure_ascii=False), ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self.client.delete(self._k(key))

    async def ttl_seconds(self, key: str) -> int | None:
        v = await self.client.ttl(self._k(key))
        # redis returns -2 for missing, -1 for no expiry; both surface as None
        return v if v >= 0 else None

    async def get_or_set_json(
        self,
        key: str,
        *,
        ttl_seconds: int,
        loader: Callable[[], Awaitable[dict[str, Any]]],
    ) -> dict[str, Any]:
        cached = await self.get_json(key)
        if cached is not None:
            return cached
        fresh = await loader()
        await self.set_json(key, fresh, ttl_seconds=ttl_seconds)
        return fresh
```

- [ ] **Step 5: Verify tests pass**

```powershell
uv run pytest tests/test_infra_cache.py -v
```

Expected: 6 passed.

- [ ] **Step 6: Commit**

```powershell
git add src/alecaframe_api/infra/__init__.py src/alecaframe_api/infra/cache.py tests/test_infra_cache.py
git commit -m "feat(infra): add Redis Cache wrapper with prefixed keys + json helpers"
```

---

## Task 4: WFM static fixtures for tests

To keep tests fast and offline, we record two slices of the real WFM API. Both are tiny JSON files committed under `tests/fixtures/`.

**Files:**
- Create: `tests/fixtures/wfm_items_sample.json`
- Create: `tests/fixtures/wfm_orders_kronen_prime_blade.json`

- [ ] **Step 1: Create the items fixture**

Create `tests/fixtures/wfm_items_sample.json` with this exact content (representative of WFM's `/v1/items` shape, trimmed to 6 items):

```json
{
  "payload": {
    "items": [
      {"id": "54a73e1cc4442b15c5d80f6f", "url_name": "kronen_prime_blade",   "item_name": "Kronen Prime Blade",      "thumb": "/items/images/kronen_prime_blade.thumb.png", "vaulted": true},
      {"id": "54a73e1cc4442b15c5d80f70", "url_name": "kronen_prime_blueprint", "item_name": "Kronen Prime Blueprint", "thumb": "/items/images/kronen_prime_blueprint.thumb.png", "vaulted": true},
      {"id": "54a73e1cc4442b15c5d80f71", "url_name": "mag_prime_blueprint",   "item_name": "Mag Prime Blueprint",     "thumb": "/items/images/mag_prime_blueprint.thumb.png", "vaulted": false},
      {"id": "54a73e1cc4442b15c5d80f72", "url_name": "volt_prime_helmet_blueprint", "item_name": "Volt Prime Helmet Blueprint", "thumb": "/items/images/volt_prime_helmet_blueprint.thumb.png", "vaulted": false},
      {"id": "54a73e1cc4442b15c5d80f73", "url_name": "primed_continuity",    "item_name": "Primed Continuity",       "thumb": "/items/images/primed_continuity.thumb.png", "vaulted": false},
      {"id": "54a73e1cc4442b15c5d80f74", "url_name": "ash_prime_systems_blueprint", "item_name": "Ash Prime Systems Blueprint", "thumb": "/items/images/ash_prime_systems_blueprint.thumb.png", "vaulted": false}
    ]
  }
}
```

- [ ] **Step 2: Create the orders fixture**

Create `tests/fixtures/wfm_orders_kronen_prime_blade.json` with this exact content:

```json
{
  "payload": {
    "orders": [
      {"order_type": "sell", "platinum": 35, "quantity": 1, "user": {"ingame_name": "trader_a", "status": "ingame", "reputation": 120}, "platform": "pc"},
      {"order_type": "sell", "platinum": 36, "quantity": 2, "user": {"ingame_name": "trader_b", "status": "online", "reputation": 75},  "platform": "pc"},
      {"order_type": "sell", "platinum": 38, "quantity": 1, "user": {"ingame_name": "trader_c", "status": "online", "reputation": 12},  "platform": "pc"},
      {"order_type": "sell", "platinum": 40, "quantity": 1, "user": {"ingame_name": "trader_d", "status": "offline", "reputation": 200}, "platform": "pc"},
      {"order_type": "sell", "platinum": 45, "quantity": 3, "user": {"ingame_name": "trader_e", "status": "offline", "reputation": 5},   "platform": "pc"},
      {"order_type": "sell", "platinum": 60, "quantity": 1, "user": {"ingame_name": "trader_f", "status": "offline", "reputation": 0},   "platform": "pc"},
      {"order_type": "buy",  "platinum": 22, "quantity": 1, "user": {"ingame_name": "buyer_a",  "status": "ingame", "reputation": 80},  "platform": "pc"},
      {"order_type": "buy",  "platinum": 25, "quantity": 1, "user": {"ingame_name": "buyer_b",  "status": "online", "reputation": 40},  "platform": "pc"},
      {"order_type": "buy",  "platinum": 28, "quantity": 1, "user": {"ingame_name": "buyer_c",  "status": "offline","reputation": 200}, "platform": "pc"},
      {"order_type": "buy",  "platinum": 10, "quantity": 1, "user": {"ingame_name": "buyer_d",  "status": "offline","reputation": 0},   "platform": "pc"}
    ]
  }
}
```

- [ ] **Step 3: Commit**

```powershell
git add tests/fixtures/wfm_items_sample.json tests/fixtures/wfm_orders_kronen_prime_blade.json
git commit -m "test: add WFM API fixtures (items slice + sample order book)"
```

---

## Task 5: `wfm/slugs.py` — uniqueName ↔ slug resolver

**Files:**
- Create: `src/alecaframe_api/wfm/slugs.py`
- Create: `tests/test_wfm_slugs.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wfm_slugs.py`:

```python
"""SlugResolver tests — uniqueName→slug forward + reverse lookups."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alecaframe_api.wfm.slugs import ItemRef, SlugResolver

FIXTURE = Path(__file__).parent / "fixtures" / "wfm_items_sample.json"


def load_items() -> list[ItemRef]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [
        ItemRef(slug=it["url_name"], item_name=it["item_name"],
                thumb_url=it.get("thumb"), vaulted=bool(it.get("vaulted", False)),
                wfm_id=it["id"])
        for it in raw["payload"]["items"]
    ]


@pytest.fixture
def resolver() -> SlugResolver:
    r = SlugResolver()
    r.load(load_items())
    return r


def test_lookup_by_slug(resolver: SlugResolver) -> None:
    it = resolver.by_slug("kronen_prime_blade")
    assert it is not None
    assert it.item_name == "Kronen Prime Blade"
    assert it.vaulted is True


def test_lookup_missing_slug_returns_none(resolver: SlugResolver) -> None:
    assert resolver.by_slug("does_not_exist") is None


def test_resolve_unique_name_recipes_weapon_parts(resolver: SlugResolver) -> None:
    """/Lotus/Types/Recipes/Weapons/WeaponParts/KronenPrimeBlade -> kronen_prime_blade"""
    slug = resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/KronenPrimeBlade"
    )
    assert slug == "kronen_prime_blade"


def test_resolve_unique_name_warframe_blueprint(resolver: SlugResolver) -> None:
    slug = resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/WarframeRecipes/MagPrimeBlueprint"
    )
    assert slug == "mag_prime_blueprint"


def test_resolve_unique_name_helmet_blueprint(resolver: SlugResolver) -> None:
    slug = resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeHelmetBlueprint"
    )
    assert slug == "volt_prime_helmet_blueprint"


def test_resolve_unique_name_mod_path(resolver: SlugResolver) -> None:
    """Mods don't live under /Recipes/. They use /Upgrades/Mods/."""
    slug = resolver.resolve_unique_name(
        "/Lotus/Upgrades/Mods/Warframe/PrimedContinuityMod"
    )
    assert slug == "primed_continuity"


def test_resolve_unique_name_unknown_returns_none(resolver: SlugResolver) -> None:
    assert resolver.resolve_unique_name("/Lotus/Types/Items/SomeUnknownThing") is None


def test_overrides_take_priority(resolver: SlugResolver) -> None:
    """If data/slug_overrides.json maps a uniqueName, that mapping wins."""
    r = SlugResolver()
    r.load(load_items())
    r.apply_overrides({"/Lotus/Types/Custom/Weird": "kronen_prime_blade"})
    assert r.resolve_unique_name("/Lotus/Types/Custom/Weird") == "kronen_prime_blade"


def test_all_slugs(resolver: SlugResolver) -> None:
    assert sorted(resolver.all_slugs()) == sorted([
        "kronen_prime_blade", "kronen_prime_blueprint", "mag_prime_blueprint",
        "volt_prime_helmet_blueprint", "primed_continuity", "ash_prime_systems_blueprint",
    ])


def test_load_replaces_existing(resolver: SlugResolver) -> None:
    """Calling load() twice should not leave stale slugs."""
    smaller = [load_items()[0]]
    resolver.load(smaller)
    assert resolver.all_slugs() == ["kronen_prime_blade"]
```

- [ ] **Step 2: Verify tests fail**

```powershell
uv run pytest tests/test_wfm_slugs.py -v
```

Expected: `ModuleNotFoundError: No module named 'alecaframe_api.wfm.slugs'`.

- [ ] **Step 3: Implement `slugs.py`**

Create `src/alecaframe_api/wfm/slugs.py`:

```python
"""uniqueName ↔ WFM slug resolution.

WFM uses slugs like `kronen_prime_blade`. DE uniqueNames are paths like
`/Lotus/Types/Recipes/Weapons/WeaponParts/KronenPrimeBlade`. The resolver:

1. Loads the WFM /v1/items catalogue once (passed in via `load()`).
2. Builds a forward index `slug -> ItemRef`.
3. Builds a reverse index by normalising the trailing path segment of each
   known uniqueName template (Recipes/Weapons/WeaponParts/<X>, etc.) to its
   slug.
4. Lets callers add ad-hoc overrides from `data/slug_overrides.json`.

The reverse map is best-effort. If a uniqueName has no rule, `resolve_unique_name`
returns None and the caller falls back to skipping or asking the user to add
an override.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ItemRef:
    slug: str            # e.g. "kronen_prime_blade"
    item_name: str       # e.g. "Kronen Prime Blade"
    thumb_url: str | None
    vaulted: bool
    wfm_id: str          # WFM internal id


# Path prefixes that have a deterministic CamelCase -> slug rule.
# Order matters: more specific first.
_RECIPE_PREFIXES = (
    "/Lotus/Types/Recipes/Weapons/WeaponParts/",
    "/Lotus/Types/Recipes/SentinelRecipes/",
    "/Lotus/Types/Recipes/WarframeRecipes/",
    "/Lotus/Types/Recipes/Weapons/",
    "/Lotus/Types/Recipes/ArchwingRecipes/",
)

# Mod path prefixes — these don't share the Recipe path layout.
_MOD_PREFIXES = (
    "/Lotus/Upgrades/Mods/",
)

_CAMEL_RX = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _camel_to_snake(s: str) -> str:
    """`KronenPrimeBlade` → `kronen_prime_blade`. `OkinaPrimeBP` stays in two words."""
    return _CAMEL_RX.sub("_", s).lower()


def _normalise_recipe_tail(tail: str) -> str:
    """Strip trailing 'Blueprint' suffix into '_blueprint' (matches WFM naming).

    Example: `MagPrimeBlueprint` → `mag_prime_blueprint`.
    Example: `KronenPrimeBlade` → `kronen_prime_blade`.
    """
    # If the tail ends in "Blueprint" we keep it — already produces the right snake form.
    return _camel_to_snake(tail)


def _normalise_mod_tail(tail: str) -> str:
    """Mod uniqueName tails end with the literal `Mod` suffix that WFM drops.

    `PrimedContinuityMod` → `primed_continuity`.
    `Adaptation` → `adaptation`.
    """
    if tail.endswith("Mod"):
        tail = tail[: -len("Mod")]
    return _camel_to_snake(tail)


class SlugResolver:
    """uniqueName ↔ slug resolution with override hook."""

    def __init__(self) -> None:
        self._by_slug: dict[str, ItemRef] = {}
        self._unique_name_to_slug: dict[str, str] = {}
        self._overrides: dict[str, str] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- ingest

    def load(self, items: list[ItemRef]) -> None:
        """Replace the catalogue. Called at startup with the WFM /v1/items response."""
        with self._lock:
            self._by_slug = {it.slug: it for it in items}
            # Build the reverse map: heuristic-only. We try each known prefix
            # template against each known slug; if the camel form of the tail
            # matches, we record the mapping. This is N(prefixes)*N(slugs) at
            # build time but only once at startup.
            new_map: dict[str, str] = {}
            for slug in self._by_slug:
                for prefix in _RECIPE_PREFIXES:
                    candidate = self._guess_unique_name_for(prefix, slug, _recipe_camel_for)
                    if candidate:
                        new_map[candidate] = slug
                for prefix in _MOD_PREFIXES:
                    # Mods have a deeper path (e.g. /Lotus/Upgrades/Mods/Warframe/PrimedContinuityMod).
                    # We can't guess the warframe/weapon subfolder, so we register every
                    # known subfolder by matching the suffix instead — see resolve_unique_name.
                    candidate = self._guess_mod_unique_name(slug)
                    if candidate:
                        new_map[candidate] = slug
            self._unique_name_to_slug = new_map

    def apply_overrides(self, overrides: dict[str, str]) -> None:
        with self._lock:
            self._overrides.update(overrides)

    # --------------------------------------------------------------- lookups

    def by_slug(self, slug: str) -> ItemRef | None:
        return self._by_slug.get(slug)

    def resolve_unique_name(self, unique_name: str) -> str | None:
        if unique_name in self._overrides:
            return self._overrides[unique_name]
        # 1. Exact match against the precomputed reverse map.
        if unique_name in self._unique_name_to_slug:
            return self._unique_name_to_slug[unique_name]
        # 2. Mod path heuristic — strip subfolder, normalise the tail.
        for prefix in _MOD_PREFIXES:
            if unique_name.startswith(prefix):
                tail = unique_name.rsplit("/", 1)[-1]
                candidate = _normalise_mod_tail(tail)
                if candidate in self._by_slug:
                    return candidate
        # 3. Recipe path generic — last segment camel-to-snake.
        for prefix in _RECIPE_PREFIXES:
            if unique_name.startswith(prefix):
                tail = unique_name[len(prefix):]
                candidate = _normalise_recipe_tail(tail)
                if candidate in self._by_slug:
                    return candidate
        return None

    def all_slugs(self) -> list[str]:
        return list(self._by_slug.keys())

    def size(self) -> int:
        return len(self._by_slug)

    # ---------------------------------------------------------- internal

    def _guess_unique_name_for(self, prefix: str, slug: str, camel: callable) -> str | None:
        # We only know the camel form for *some* slugs (those whose snake form
        # is a clean snake_case of CamelCase). Try the easy reversal: split on
        # underscores and capitalize.
        camel_tail = "".join(part.capitalize() for part in slug.split("_"))
        return f"{prefix}{camel_tail}"

    def _guess_mod_unique_name(self, slug: str) -> str | None:
        camel = "".join(part.capitalize() for part in slug.split("_"))
        # Most owned mods sit under a category subfolder we can't reliably guess.
        # Return None so the resolver falls back to the suffix-match path in
        # resolve_unique_name.
        return None


# Helper exposed only for clarity / future use.
def _recipe_camel_for(slug: str) -> str:
    return "".join(p.capitalize() for p in slug.split("_"))
```

- [ ] **Step 4: Verify tests pass**

```powershell
uv run pytest tests/test_wfm_slugs.py -v
```

Expected: all 10 pass. If `test_resolve_unique_name_mod_path` fails, double-check the suffix-stripping path: the mod heuristic looks at the FINAL segment of the uniqueName (`PrimedContinuityMod`), drops the `Mod` suffix (`PrimedContinuity`), snake-cases it (`primed_continuity`), and confirms that slug exists in the catalogue.

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/wfm/slugs.py tests/test_wfm_slugs.py
git commit -m "feat(wfm): add SlugResolver for uniqueName <-> WFM slug mapping"
```

---

## Task 6: `wfm/client.py` part 1 — auth + rate-limited HTTP wrapper

The client is large; we build it in two tasks. Task 6 wires up auth + rate limiting + the cached `_request` helper. Task 7 adds the typed methods (`get_items`, `get_orders`, …) on top.

**Files:**
- Create: `src/alecaframe_api/wfm/client.py` (initial — partial)
- Create: `tests/test_wfm_client.py`

- [ ] **Step 1: Write the failing tests (just the auth + request infrastructure)**

Create `tests/test_wfm_client.py`:

```python
"""WFMClient tests — auth header, rate-limit, cache, retry."""
from __future__ import annotations

import asyncio

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.client import WFMClient


@pytest.fixture
async def cache() -> Cache:
    import fakeredis.aioredis
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = Cache(client=client, key_prefix="wfm")
    yield c
    await client.aclose()


@pytest.fixture
def static_token() -> "callable":
    async def _provider() -> str:
        return "FAKE.JWT.TOKEN"
    return _provider


@pytest.fixture
def client_factory(cache: Cache, static_token: callable) -> "callable":
    """Build a WFMClient with explicit base URL and rate limit raised for tests."""
    def _factory(**overrides) -> WFMClient:
        kwargs = dict(
            cache=cache,
            base_url="https://mock.wfm.test/v1",
            token_provider=static_token,
            platform="pc",
            language="en",
            rate_limit_per_second=100,  # don't throttle test runs
        )
        kwargs.update(overrides)
        return WFMClient(**kwargs)
    return _factory


@pytest.mark.asyncio
async def test_request_sends_jwt_header(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items",
        method="GET",
        json={"payload": {"items": []}},
    )
    c = client_factory()
    await c._request("GET", "/items", cache_key="items", cache_ttl=10)
    req = httpx_mock.get_request()
    assert req.headers["Authorization"] == "JWT FAKE.JWT.TOKEN"
    assert req.headers["Language"] == "en"
    assert req.headers["Platform"] == "pc"


@pytest.mark.asyncio
async def test_request_caches_response(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items",
        method="GET",
        json={"payload": {"items": []}},
    )
    c = client_factory()
    a = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    b = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    assert a == b
    # Only one HTTP call should have happened — the second came from Redis.
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_request_fresh_bypasses_cache(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET",
        json={"payload": {"items": [{"url_name": "a"}]}},
    )
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET",
        json={"payload": {"items": [{"url_name": "b"}]}},
    )
    c = client_factory()
    a = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    b = await c._request("GET", "/items", cache_key="items", cache_ttl=60, fresh=True)
    assert a["payload"]["items"][0]["url_name"] == "a"
    assert b["payload"]["items"][0]["url_name"] == "b"


@pytest.mark.asyncio
async def test_request_raises_on_5xx(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET", status_code=500,
        text="boom",
    )
    c = client_factory()
    with pytest.raises(Exception):
        await c._request("GET", "/items", cache_key="items", cache_ttl=60)


@pytest.mark.asyncio
async def test_request_returns_stale_if_5xx_and_cache_has_value(
    client_factory, httpx_mock: HTTPXMock
) -> None:
    """When the upstream fails but Redis has a previous value, return it."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET",
        json={"payload": {"items": [{"url_name": "stale"}]}},
    )
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET",
        status_code=503, text="upstream gone",
    )
    c = client_factory()
    # Prime cache with the first call (success).
    first = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    assert first["payload"]["items"][0]["url_name"] == "stale"
    # Second call hits 503 — but cache is fresh so we never get there.
    # Drop the cache to force a refresh attempt, then verify stale-fallback.
    await c._cache.delete("items")
    # Re-prime with a known value, then expire its TTL via direct delete.
    await c._cache.set_json("items", {"payload": {"items": [{"url_name": "stale"}]}}, ttl_seconds=60)
    # Now call with fresh=True so the cache lookup short-circuits and the
    # 503 path is exercised. Stale-fallback should still serve from cache.
    second = await c._request("GET", "/items", cache_key="items", cache_ttl=60, fresh=True)
    assert second["payload"]["items"][0]["url_name"] == "stale"
    # Optional sanity: the fallback marks the response with a `_stale=True` flag.
    assert second.get("_stale") is True
```

- [ ] **Step 2: Verify tests fail**

```powershell
uv run pytest tests/test_wfm_client.py -v
```

Expected: `ModuleNotFoundError: No module named 'alecaframe_api.wfm.client'`.

- [ ] **Step 3: Implement `client.py` (auth + request infrastructure only)**

Create `src/alecaframe_api/wfm/client.py`:

```python
"""WFM REST client — the single point of contact with api.warframe.market.

Owns:
- Auth header (JWT from decrypt-agent's /wfm-token)
- Rate limiting (aiolimiter, default 3 req/s)
- L1 cache (Redis, TTL per resource)
- Stale-while-error fallback

All public methods land in `wfm/client.py` part 2 (next task). This task adds
the `_request` plumbing and types only.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import httpx
from aiolimiter import AsyncLimiter

from alecaframe_api.infra.cache import Cache

log = logging.getLogger("alecaframe.wfm.client")


TokenProvider = Callable[[], Awaitable[str]]


class WFMError(RuntimeError):
    """Raised when a non-cached call to WFM fails irrecoverably."""


@dataclass
class WFMClient:
    """Rate-limited, cached async HTTP client for warframe.market."""

    cache: Cache
    base_url: str
    token_provider: TokenProvider
    platform: str = "pc"
    language: str = "en"
    rate_limit_per_second: int = 3
    request_timeout: float = 15.0

    _limiter: AsyncLimiter = field(init=False, repr=False)
    _http: httpx.AsyncClient | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        # max_rate is allowed to be > rate_limit_per_second to "burst",
        # but the time_period is fixed at 1s — we want a steady cap.
        self._limiter = AsyncLimiter(max_rate=self.rate_limit_per_second, time_period=1.0)

    @property
    def _cache(self) -> Cache:
        """Alias kept so tests can poke at the cache (`client._cache.delete(...)`)."""
        return self.cache

    async def _client(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.request_timeout,
            )
        return self._http

    async def aclose(self) -> None:
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ----------------------------------------------------------- request

    async def _request(
        self,
        method: str,
        path: str,
        *,
        cache_key: str,
        cache_ttl: int,
        fresh: bool = False,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Cached, rate-limited, stale-on-error HTTP request returning parsed JSON."""
        if not fresh:
            cached = await self.cache.get_json(cache_key)
            if cached is not None:
                return cached

        token = await self.token_provider()
        headers = {
            "Authorization": f"JWT {token}",
            "Platform": self.platform,
            "Language": self.language,
            "Accept": "application/json",
        }

        try:
            async with self._limiter:
                client = await self._client()
                resp = await client.request(method, path, headers=headers, params=params)
                resp.raise_for_status()
                payload: dict[str, Any] = resp.json()
        except Exception as e:
            log.warning("wfm %s %s failed: %s; trying stale fallback", method, path, e)
            stale = await self.cache.get_json(cache_key)
            if stale is not None:
                stale = {**stale, "_stale": True}
                return stale
            raise WFMError(f"{method} {path} failed and no stale cache available: {e}") from e

        await self.cache.set_json(cache_key, payload, ttl_seconds=cache_ttl)
        return payload
```

- [ ] **Step 4: Verify tests pass**

```powershell
uv run pytest tests/test_wfm_client.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/wfm/client.py tests/test_wfm_client.py
git commit -m "feat(wfm): add WFMClient request infrastructure (auth, rate-limit, cache, stale-fallback)"
```

---

## Task 7: `wfm/client.py` part 2 — typed methods

Layer the typed WFM-resource methods on top of `_request`.

**Files:**
- Modify: `src/alecaframe_api/wfm/client.py` (append)
- Modify: `tests/test_wfm_client.py` (append)

- [ ] **Step 1: Append failing tests**

Append to `tests/test_wfm_client.py`:

```python


@pytest.mark.asyncio
async def test_get_items_returns_item_refs(client_factory, httpx_mock: HTTPXMock) -> None:
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / "fixtures" / "wfm_items_sample.json").read_text(encoding="utf-8"))
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET", json=fixture,
    )
    c = client_factory()
    items = await c.get_items()
    assert len(items) == 6
    kp = next(i for i in items if i.slug == "kronen_prime_blade")
    assert kp.item_name == "Kronen Prime Blade"
    assert kp.vaulted is True


@pytest.mark.asyncio
async def test_get_orders_returns_payload(client_factory, httpx_mock: HTTPXMock) -> None:
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / "fixtures" / "wfm_orders_kronen_prime_blade.json").read_text(encoding="utf-8"))
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items/kronen_prime_blade/orders", method="GET", json=fixture,
    )
    c = client_factory()
    payload = await c.get_orders("kronen_prime_blade")
    assert len(payload["payload"]["orders"]) == 10


@pytest.mark.asyncio
async def test_get_orders_includes_platform_param(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items/kronen_prime_blade/orders?include=item",
        method="GET", json={"payload": {"orders": []}},
    )
    c = client_factory()
    await c.get_orders("kronen_prime_blade", include_item_info=True)
    req = httpx_mock.get_request()
    assert "include=item" in str(req.url)


@pytest.mark.asyncio
async def test_get_profile_orders_uses_username(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/profile/klawisha012/orders",
        method="GET",
        json={"payload": {"sell_orders": [], "buy_orders": []}},
    )
    c = client_factory()
    payload = await c.get_profile_orders("klawisha012")
    assert "sell_orders" in payload["payload"]
```

- [ ] **Step 2: Append typed methods to `client.py`**

Append at the end of `src/alecaframe_api/wfm/client.py`:

```python


from alecaframe_api.wfm.slugs import ItemRef


# Per-resource TTLs (seconds). Adjust if WFM rate limits or product needs change.
_TTL_ITEMS = 24 * 3600       # 24h — catalogue is stable
_TTL_ORDERS = 60             # 60s — order book churn
_TTL_PROFILE = 300           # 5min
_TTL_STATISTICS = 300        # 5min


class _WFMTypedMethods:
    """Mixin-style namespace for typed methods. Mixed in via plain inheritance below."""

    cache: Cache  # type: ignore[assignment]  # supplied by WFMClient

    async def _request(self, *a, **kw) -> dict[str, Any]: ...  # type: ignore[empty-body]

    async def get_items(self) -> list[ItemRef]:
        payload = await self._request(
            "GET", "/items",
            cache_key="items",
            cache_ttl=_TTL_ITEMS,
        )
        items = payload.get("payload", {}).get("items", [])
        return [
            ItemRef(
                slug=it["url_name"],
                item_name=it["item_name"],
                thumb_url=it.get("thumb"),
                vaulted=bool(it.get("vaulted", False)),
                wfm_id=it["id"],
            )
            for it in items
        ]

    async def get_orders(
        self,
        slug: str,
        *,
        include_item_info: bool = False,
        fresh: bool = False,
    ) -> dict[str, Any]:
        params = {"include": "item"} if include_item_info else None
        return await self._request(
            "GET",
            f"/items/{slug}/orders",
            cache_key=f"orders:{slug}:{int(include_item_info)}",
            cache_ttl=_TTL_ORDERS,
            fresh=fresh,
            params=params,
        )

    async def get_profile(self, username: str, *, fresh: bool = False) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/profile/{username}",
            cache_key=f"profile:{username}",
            cache_ttl=_TTL_PROFILE,
            fresh=fresh,
        )

    async def get_profile_orders(self, username: str, *, fresh: bool = False) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/profile/{username}/orders",
            cache_key=f"profile-orders:{username}",
            cache_ttl=_TTL_ORDERS,
            fresh=fresh,
        )

    async def get_statistics(self, slug: str, *, fresh: bool = False) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/items/{slug}/statistics",
            cache_key=f"statistics:{slug}",
            cache_ttl=_TTL_STATISTICS,
            fresh=fresh,
        )


# Re-export under WFMClient so callers see a single type.
# We use multiple-inheritance composition rather than monkey-patching.
WFMClient.__bases__ = (_WFMTypedMethods,) + WFMClient.__bases__
```

Note on that last line: `WFMClient` is a `@dataclass` defined in Task 6. Splicing a mixin into its `__bases__` post-hoc is unusual; if mypy complains, an alternative is to define the typed methods directly inside `WFMClient` in the original file. The cleaner refactor is to **inline** the typed methods at the bottom of the existing `WFMClient` class. Pick whichever your tooling prefers. The tests don't care — they exercise the public methods.

**Recommended cleaner approach:** just add the methods directly to `WFMClient`. Open `src/alecaframe_api/wfm/client.py` and append the four methods (`get_items`, `get_orders`, `get_profile`, `get_profile_orders`, `get_statistics`) inside the `WFMClient` class body, immediately before its `__post_init__`. Drop the `_WFMTypedMethods` mixin and the trailing splicing line entirely.

- [ ] **Step 3: Verify tests pass**

```powershell
uv run pytest tests/test_wfm_client.py -v
```

Expected: 9 passed (5 from Task 6 + 4 new).

- [ ] **Step 4: Commit**

```powershell
git add src/alecaframe_api/wfm/client.py tests/test_wfm_client.py
git commit -m "feat(wfm): add typed methods (get_items/get_orders/get_profile/get_profile_orders/get_statistics)"
```

---

## Task 8: `wfm/prices.py` — order book aggregations

**Files:**
- Create: `src/alecaframe_api/wfm/prices.py`
- Create: `tests/test_wfm_prices.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wfm_prices.py`:

```python
"""Tests for order-book aggregation functions."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alecaframe_api.wfm.prices import compute_stats, OrderBookStats

FIXTURE = Path(__file__).parent / "fixtures" / "wfm_orders_kronen_prime_blade.json"


def load_orders() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["payload"]["orders"]


def test_compute_stats_sell_online_only() -> None:
    orders = load_orders()
    stats = compute_stats(orders, side="sell", online_only=True)
    # Online sells in fixture: 35 x1 (ingame), 36 x2 (online), 38 x1 (online) = 4 qty
    assert stats.count_orders == 3
    assert stats.volume_qty == 4
    assert stats.min_price == 35
    assert stats.max_price == 38
    assert stats.median is not None
    # With qty-weighted prices [35,36,36,38]: median is mean of two middle = 36
    assert stats.median == 36


def test_compute_stats_sell_all() -> None:
    orders = load_orders()
    stats = compute_stats(orders, side="sell", online_only=False)
    # 6 sell orders, total qty 9 (1+2+1+1+3+1)
    assert stats.count_orders == 6
    assert stats.volume_qty == 9


def test_compute_stats_buy_online_only() -> None:
    orders = load_orders()
    stats = compute_stats(orders, side="buy", online_only=True)
    # Online buys: 22 x1 (ingame), 25 x1 (online) = 2 orders
    assert stats.count_orders == 2
    assert stats.min_price == 22
    assert stats.max_price == 25


def test_compute_stats_empty_returns_zero_record() -> None:
    stats = compute_stats([], side="sell", online_only=True)
    assert stats.count_orders == 0
    assert stats.volume_qty == 0
    assert stats.min_price is None
    assert stats.median is None
    assert stats.max_price is None


def test_compute_stats_top5_attached() -> None:
    """compute_stats should attach the first 5 prices for context."""
    orders = load_orders()
    stats = compute_stats(orders, side="sell", online_only=False)
    assert len(stats.top5) == 5
    # Sorted ascending by price
    assert stats.top5 == [35, 36, 38, 40, 45]


def test_compute_stats_percentiles_are_monotonic() -> None:
    orders = load_orders()
    stats = compute_stats(orders, side="sell", online_only=False)
    assert stats.p10 is not None and stats.p25 is not None and stats.p75 is not None and stats.p90 is not None
    assert stats.min_price <= stats.p10 <= stats.p25 <= stats.median <= stats.p75 <= stats.p90 <= stats.max_price


def test_compute_stats_handles_non_pc_platform_filter() -> None:
    """If the fixture had xbox orders mixed in, the helper should accept a platform filter."""
    orders = load_orders() + [
        {"order_type": "sell", "platinum": 999, "quantity": 1,
         "user": {"ingame_name": "xbox_a", "status": "online", "reputation": 0},
         "platform": "xbox"},
    ]
    stats = compute_stats(orders, side="sell", online_only=False, platform="pc")
    assert stats.max_price == 60  # xbox 999 not counted
```

- [ ] **Step 2: Verify failures**

```powershell
uv run pytest tests/test_wfm_prices.py -v
```

Expected: `ModuleNotFoundError: No module named 'alecaframe_api.wfm.prices'`.

- [ ] **Step 3: Implement**

Create `src/alecaframe_api/wfm/prices.py`:

```python
"""Order-book aggregations.

Takes a raw WFM /orders payload (list of dicts), filters by side / online /
platform, and computes a typed stats record: min/p10/p25/median/p75/p90/max,
order count, total quantity, top 5 prices.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Literal


Side = Literal["sell", "buy"]


@dataclass(frozen=True)
class OrderBookStats:
    side: Side
    online_only: bool
    count_orders: int
    volume_qty: int
    min_price: int | None
    p10: int | None
    p25: int | None
    median: int | None
    p75: int | None
    p90: int | None
    max_price: int | None
    top5: list[int]


def _percentile(values: list[int], pct: float) -> int | None:
    if not values:
        return None
    # statistics.quantiles wants n>=2; degrade gracefully for tiny samples.
    if len(values) == 1:
        return int(values[0])
    cuts = statistics.quantiles(values, n=100, method="inclusive")
    return int(round(cuts[int(pct) - 1]))


def compute_stats(
    orders: list[dict],
    *,
    side: Side,
    online_only: bool,
    platform: str = "pc",
) -> OrderBookStats:
    """Aggregate a raw WFM /orders payload into a single stats record."""
    filtered: list[dict] = []
    for o in orders:
        if o.get("order_type") != side:
            continue
        if o.get("platform") != platform:
            continue
        if online_only:
            status = (o.get("user") or {}).get("status")
            if status not in {"ingame", "online"}:
                continue
        filtered.append(o)

    # Quantity-weighted price list for percentiles.
    weighted_prices: list[int] = []
    for o in filtered:
        qty = int(o.get("quantity", 1) or 1)
        try:
            price = int(o["platinum"])
        except (KeyError, TypeError, ValueError):
            continue
        weighted_prices.extend([price] * qty)

    weighted_prices.sort()
    count_orders = len(filtered)
    volume_qty = sum(int(o.get("quantity", 1) or 1) for o in filtered)

    if not weighted_prices:
        return OrderBookStats(
            side=side, online_only=online_only,
            count_orders=count_orders, volume_qty=volume_qty,
            min_price=None, p10=None, p25=None, median=None,
            p75=None, p90=None, max_price=None, top5=[],
        )

    return OrderBookStats(
        side=side, online_only=online_only,
        count_orders=count_orders, volume_qty=volume_qty,
        min_price=int(weighted_prices[0]),
        p10=_percentile(weighted_prices, 10),
        p25=_percentile(weighted_prices, 25),
        median=int(statistics.median(weighted_prices)),
        p75=_percentile(weighted_prices, 75),
        p90=_percentile(weighted_prices, 90),
        max_price=int(weighted_prices[-1]),
        top5=weighted_prices[:5],
    )
```

- [ ] **Step 4: Verify**

```powershell
uv run pytest tests/test_wfm_prices.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/wfm/prices.py tests/test_wfm_prices.py
git commit -m "feat(wfm): add order-book stats aggregator (min/percentiles/median/max + top5)"
```

---

## Task 9: `wfm/sets.py` — set composition + profit calculator

**Files:**
- Create: `src/alecaframe_api/wfm/sets.py`
- Create: `tests/test_wfm_sets.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_wfm_sets.py`:

```python
"""Tests for set composition + profit calculator."""
from __future__ import annotations

import pytest

from alecaframe_api.wfm.sets import SetIndex, SetComposition, compute_set_profits, SetProfitRow


@pytest.fixture
def index() -> SetIndex:
    idx = SetIndex()
    idx.register(SetComposition(
        set_slug="kronen_prime_set",
        set_name="Kronen Prime Set",
        parts={
            "kronen_prime_blade": 2,
            "kronen_prime_handle": 1,
            "kronen_prime_blueprint": 1,
        },
    ))
    idx.register(SetComposition(
        set_slug="mag_prime_set",
        set_name="Mag Prime Set",
        parts={
            "mag_prime_neuroptics_blueprint": 1,
            "mag_prime_chassis_blueprint": 1,
            "mag_prime_systems_blueprint": 1,
            "mag_prime_blueprint": 1,
        },
    ))
    return idx


def test_register_and_lookup(index: SetIndex) -> None:
    s = index.get("kronen_prime_set")
    assert s is not None and s.set_name == "Kronen Prime Set"
    assert sum(s.parts.values()) == 4  # 2 blades + 1 handle + 1 blueprint


def test_compute_set_profits_buyable_and_owned(index: SetIndex) -> None:
    """User owns 1 of each Kronen part except blades; needs to buy 2 blades.

    Sell price for the whole set = 100p (provided externally).
    Floor prices: blade=35, handle=20, bp=24.
    Tax: 0.1p per part = 0.4p ~ 1p rounded.
    Cost to complete = 2*35 = 70. Sell = 100. Profit = 100 - 70 - 1 = 29.
    """
    inventory_counts = {
        "kronen_prime_handle": 1,
        "kronen_prime_blueprint": 1,
        "kronen_prime_blade": 0,
    }
    floor_prices = {
        "kronen_prime_blade": 35,
        "kronen_prime_handle": 20,
        "kronen_prime_blueprint": 24,
    }
    set_floor_prices = {"kronen_prime_set": 100, "mag_prime_set": None}

    rows = compute_set_profits(
        index=index, inventory=inventory_counts,
        part_floor_prices=floor_prices, set_prices=set_floor_prices,
    )

    kronen = next(r for r in rows if r.set_slug == "kronen_prime_set")
    assert kronen.set_price == 100
    assert kronen.parts_cost == 70    # buy 2 blades @35 each
    assert kronen.tax_estimate == 1   # rounded from 0.4
    assert kronen.profit == 100 - 70 - 1
    assert kronen.missing_parts == {"kronen_prime_blade": 2}


def test_compute_set_profits_skipped_when_no_set_price(index: SetIndex) -> None:
    """If set price is unknown (set_prices[slug] is None), skip the row."""
    inventory_counts = {}
    floor_prices = {"mag_prime_blueprint": 30}
    set_prices = {"mag_prime_set": None}
    rows = compute_set_profits(
        index=index, inventory=inventory_counts,
        part_floor_prices=floor_prices, set_prices=set_prices,
    )
    assert all(r.set_slug != "mag_prime_set" for r in rows)


def test_compute_set_profits_skipped_when_a_part_has_no_floor(index: SetIndex) -> None:
    """If any required part has no floor price, we can't compute — skip."""
    inventory_counts = {}
    floor_prices = {"kronen_prime_blade": 35, "kronen_prime_handle": 20}  # missing bp
    set_prices = {"kronen_prime_set": 100}
    rows = compute_set_profits(
        index=index, inventory=inventory_counts,
        part_floor_prices=floor_prices, set_prices=set_prices,
    )
    assert all(r.set_slug != "kronen_prime_set" for r in rows)


def test_compute_set_profits_filters_by_min_margin(index: SetIndex) -> None:
    """Pass min_margin=50 — Kronen yields only 29 so it should be filtered out."""
    inventory_counts = {}
    floor_prices = {
        "kronen_prime_blade": 35, "kronen_prime_handle": 20, "kronen_prime_blueprint": 24,
    }
    set_prices = {"kronen_prime_set": 100}
    rows = compute_set_profits(
        index=index, inventory=inventory_counts,
        part_floor_prices=floor_prices, set_prices=set_prices, min_margin=50,
    )
    assert rows == []


def test_compute_set_profits_sorted_by_profit_desc(index: SetIndex) -> None:
    """Two sets with different profits — higher profit first."""
    idx = SetIndex()
    idx.register(SetComposition("a_set", "A Set", {"a_part": 1}))
    idx.register(SetComposition("b_set", "B Set", {"b_part": 1}))
    rows = compute_set_profits(
        index=idx, inventory={},
        part_floor_prices={"a_part": 10, "b_part": 30},
        set_prices={"a_set": 50, "b_set": 80},
    )
    assert [r.set_slug for r in rows] == ["a_set", "b_set"]
    # a_set: 50-10-1 = 39, b_set: 80-30-1 = 49 → b_set first
    rows = compute_set_profits(
        index=idx, inventory={},
        part_floor_prices={"a_part": 10, "b_part": 30},
        set_prices={"a_set": 50, "b_set": 80},
    )
    assert rows[0].set_slug == "b_set"
    assert rows[1].set_slug == "a_set"
```

- [ ] **Step 2: Verify failures**

```powershell
uv run pytest tests/test_wfm_sets.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/alecaframe_api/wfm/sets.py`:

```python
"""Set composition + profit calculator.

A `SetComposition` describes how many of each part go into a set. The profit
helper walks every registered set, computes the buy-side cost of completing
it (only what the user doesn't already own), and subtracts a flat WFM tax
estimate (~0.1p per part traded, rounded up).

Set compositions for B.1a come from a hardcoded list. B.2 will read them from
the AlecaFrame `cachedData/json/` files at startup.
"""
from __future__ import annotations

from dataclasses import dataclass


# WFM trade tax: 1% of plat traded + ducats. As a first approximation we
# model it as 0.1p per part times the number of parts in the set, rounded up.
def _tax_estimate(parts_count: int) -> int:
    raw = 0.1 * parts_count
    # Always at least 1p — WFM takes a minimum cut and we don't want to
    # over-promise profit by 0.4p.
    return max(1, int(round(raw)))


@dataclass(frozen=True)
class SetComposition:
    set_slug: str
    set_name: str
    parts: dict[str, int]   # part_slug -> required quantity


@dataclass(frozen=True)
class SetProfitRow:
    set_slug: str
    set_name: str
    set_price: int
    parts_cost: int
    tax_estimate: int
    profit: int
    missing_parts: dict[str, int]   # what you'd need to buy to complete
    owned_parts: dict[str, int]     # what you already have (subset of parts)


class SetIndex:
    """In-memory registry of set compositions, keyed by set_slug."""

    def __init__(self) -> None:
        self._sets: dict[str, SetComposition] = {}

    def register(self, comp: SetComposition) -> None:
        self._sets[comp.set_slug] = comp

    def get(self, set_slug: str) -> SetComposition | None:
        return self._sets.get(set_slug)

    def all_sets(self) -> list[SetComposition]:
        return list(self._sets.values())


def compute_set_profits(
    *,
    index: SetIndex,
    inventory: dict[str, int],           # part_slug -> qty owned
    part_floor_prices: dict[str, int | None],
    set_prices: dict[str, int | None],   # set_slug -> WFM floor for full set
    min_margin: int = 0,
) -> list[SetProfitRow]:
    """Return profit rows for every registered set, sorted by profit desc."""
    rows: list[SetProfitRow] = []
    for comp in index.all_sets():
        set_price = set_prices.get(comp.set_slug)
        if set_price is None:
            continue   # can't compute without set floor
        # Verify every required part has a floor price.
        if any(part_floor_prices.get(p) is None for p in comp.parts):
            continue

        missing: dict[str, int] = {}
        owned: dict[str, int] = {}
        cost = 0
        for part_slug, required_qty in comp.parts.items():
            owned_qty = int(inventory.get(part_slug, 0))
            if owned_qty:
                owned[part_slug] = min(owned_qty, required_qty)
            need = max(0, required_qty - owned_qty)
            if need:
                missing[part_slug] = need
                floor = part_floor_prices[part_slug]
                assert floor is not None  # checked above
                cost += need * floor

        total_parts = sum(comp.parts.values())
        tax = _tax_estimate(total_parts)
        profit = set_price - cost - tax
        if profit < min_margin:
            continue

        rows.append(SetProfitRow(
            set_slug=comp.set_slug, set_name=comp.set_name,
            set_price=set_price, parts_cost=cost, tax_estimate=tax,
            profit=profit, missing_parts=missing, owned_parts=owned,
        ))

    rows.sort(key=lambda r: (-r.profit, r.set_slug))
    return rows
```

- [ ] **Step 4: Verify**

```powershell
uv run pytest tests/test_wfm_sets.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/wfm/sets.py tests/test_wfm_sets.py
git commit -m "feat(wfm): add SetIndex + compute_set_profits"
```

---

## Task 10: `wfm/dependencies.py` — FastAPI dependency providers

**Files:**
- Create: `src/alecaframe_api/wfm/dependencies.py`

This module is dependency-injection plumbing — no tests at this layer; the tests in Task 11 cover it through the endpoint surface.

- [ ] **Step 1: Implement**

Create `src/alecaframe_api/wfm/dependencies.py`:

```python
"""FastAPI dependency providers for the WFM submodule.

We don't import these from main.py's lifespan directly — main.py creates the
real objects in lifespan and stores them on module-level singletons in
`alecaframe_api.wfm.dependencies` (similar to how `bridge` and `resolver`
already live as globals in `main.py`).

This keeps the wfm/router.py clean: it just declares `Depends(get_wfm_client)`
and gets back the singleton.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from alecaframe_api.wfm.client import WFMClient
from alecaframe_api.wfm.sets import SetIndex
from alecaframe_api.wfm.slugs import SlugResolver


# Singletons populated by main.py lifespan.
wfm_client: WFMClient | None = None
slug_resolver: SlugResolver | None = None
set_index: SetIndex | None = None


def get_wfm_client() -> WFMClient:
    if wfm_client is None:
        raise RuntimeError("WFMClient not initialised; main.py lifespan must set it")
    return wfm_client


def get_slug_resolver() -> SlugResolver:
    if slug_resolver is None:
        raise RuntimeError("SlugResolver not initialised")
    return slug_resolver


def get_set_index() -> SetIndex:
    if set_index is None:
        raise RuntimeError("SetIndex not initialised")
    return set_index


WFMClientDep = Annotated[WFMClient, Depends(get_wfm_client)]
SlugResolverDep = Annotated[SlugResolver, Depends(get_slug_resolver)]
SetIndexDep = Annotated[SetIndex, Depends(get_set_index)]
```

- [ ] **Step 2: Verify the module imports cleanly**

```powershell
uv run python -c "from alecaframe_api.wfm.dependencies import get_wfm_client, get_slug_resolver, get_set_index; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/wfm/dependencies.py
git commit -m "feat(wfm): add FastAPI dependency providers (get_wfm_client, get_slug_resolver, get_set_index)"
```

---

## Task 11: Pydantic response schemas

**Files:**
- Modify: `src/alecaframe_api/schemas.py`

- [ ] **Step 1: Append the new models**

Open `src/alecaframe_api/schemas.py` and add at the bottom (after the existing models):

```python


# ---------------------------------------------------------------- WFM models


class OrderRow(BaseModel):
    side: str           # "sell" | "buy"
    price: int
    qty: int
    user: str
    status: str
    reputation: int
    platform: str = "pc"


class OrderBookStatsModel(BaseModel):
    side: str
    online_only: bool
    count_orders: int
    volume_qty: int
    min_price: int | None
    p10: int | None
    p25: int | None
    median: int | None
    p75: int | None
    p90: int | None
    max_price: int | None
    top5: list[int]


class OrderBookResponse(BaseModel):
    slug: str
    item_name: str
    fetched_at: str
    stale: bool = False
    sell: OrderBookStatsModel
    buy: OrderBookStatsModel
    top_orders: list[OrderRow] = Field(default_factory=list)


class PricedItemEntry(BaseModel):
    unique_name: str
    name: str
    slug: str | None
    count: int | None = None
    vaulted: bool | None = None
    sell_min: int | None = None
    sell_median: int | None = None
    sell_spread: int | None = None
    buy_max: int | None = None
    estimated_value: int | None = None
    stale: bool = False


class PricedItemListResponse(BaseModel):
    total: int
    returned: int
    items: list[PricedItemEntry]


class SetProfitRowModel(BaseModel):
    set_slug: str
    set_name: str
    set_price: int
    parts_cost: int
    tax_estimate: int
    profit: int
    missing_parts: dict[str, int]
    owned_parts: dict[str, int]


class SetProfitResponse(BaseModel):
    total: int
    returned: int
    items: list[SetProfitRowModel]


class WtbMatchRow(BaseModel):
    slug: str
    item_name: str
    your_qty: int
    buyer: str
    buyer_status: str
    buyer_reputation: int
    offer_price: int


class WtbMatchResponse(BaseModel):
    total: int
    items: list[WtbMatchRow]


class RelistNudgeRow(BaseModel):
    slug: str
    item_name: str
    your_price: int
    median: int | None
    top5: list[int]
    suggestion: str   # e.g. "raise to 36" / "lower to 33"


class RelistNudgeResponse(BaseModel):
    total: int
    items: list[RelistNudgeRow]


class WFMItemRef(BaseModel):
    slug: str
    item_name: str
    thumb_url: str | None
    vaulted: bool
    wfm_id: str


class WFMItemsResponse(BaseModel):
    total: int
    items: list[WFMItemRef]
```

- [ ] **Step 2: Verify schemas import cleanly**

```powershell
uv run python -c "from alecaframe_api.schemas import OrderBookResponse, SetProfitResponse, WFMItemsResponse, WtbMatchResponse, RelistNudgeResponse, PricedItemListResponse; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/schemas.py
git commit -m "feat(schemas): add WFM-side response models"
```

---

## Task 12: `wfm/router.py` — endpoints

**Files:**
- Create: `src/alecaframe_api/wfm/router.py`

This is the largest single file in B.1a. We don't TDD every endpoint with mocked HTTPX in the router tests — the helper modules already have unit tests. Instead, after Task 13 wires everything together, e2e smoke tests against a real running stack (Task 14) verify the integration.

- [ ] **Step 1: Implement**

Create `src/alecaframe_api/wfm/router.py`:

```python
"""FastAPI router for /wfm/* and /me/* endpoints.

All endpoints depend on the WFMClient + SlugResolver + SetIndex singletons
populated by main.py's lifespan. Heavy lifting lives in `wfm/prices.py`,
`wfm/sets.py`, `wfm/slugs.py`; this module is the thin HTTP surface.
"""
from __future__ import annotations

import datetime as _dt
from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query

from alecaframe_api.bridge import BridgeError
from alecaframe_api.main import BridgeDep, ResolverDep
from alecaframe_api.schemas import (
    OrderBookResponse, OrderBookStatsModel, OrderRow,
    PricedItemEntry, PricedItemListResponse,
    RelistNudgeResponse, RelistNudgeRow,
    SetProfitResponse, SetProfitRowModel,
    WFMItemRef, WFMItemsResponse,
    WtbMatchResponse, WtbMatchRow,
)
from alecaframe_api.wfm.client import WFMError
from alecaframe_api.wfm.dependencies import SetIndexDep, SlugResolverDep, WFMClientDep
from alecaframe_api.wfm.prices import compute_stats
from alecaframe_api.wfm.sets import compute_set_profits


router = APIRouter()


# ----------------------------------------------------------------- helpers

def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _stats_to_model(s) -> OrderBookStatsModel:
    return OrderBookStatsModel(
        side=s.side, online_only=s.online_only,
        count_orders=s.count_orders, volume_qty=s.volume_qty,
        min_price=s.min_price, p10=s.p10, p25=s.p25, median=s.median,
        p75=s.p75, p90=s.p90, max_price=s.max_price, top5=s.top5,
    )


def _order_to_row(o: dict) -> OrderRow:
    user = o.get("user") or {}
    return OrderRow(
        side=o.get("order_type", ""),
        price=int(o.get("platinum", 0)),
        qty=int(o.get("quantity", 1) or 1),
        user=str(user.get("ingame_name") or ""),
        status=str(user.get("status") or "unknown"),
        reputation=int(user.get("reputation", 0) or 0),
        platform=str(o.get("platform", "pc")),
    )


# ----------------------------------------------------------------- /wfm/*


@router.get(
    "/wfm/items", response_model=WFMItemsResponse,
    summary="WFM slug catalogue (24h cache)",
)
async def wfm_items(client: WFMClientDep) -> WFMItemsResponse:
    try:
        items = await client.get_items()
    except WFMError as e:
        raise HTTPException(503, str(e)) from e
    return WFMItemsResponse(
        total=len(items),
        items=[
            WFMItemRef(
                slug=i.slug, item_name=i.item_name, thumb_url=i.thumb_url,
                vaulted=i.vaulted, wfm_id=i.wfm_id,
            )
            for i in items
        ],
    )


@router.get(
    "/wfm/orders/{slug}", response_model=OrderBookResponse,
    summary="Current WFM order book for a slug",
)
async def wfm_orders(
    slug: str,
    client: WFMClientDep,
    resolver: SlugResolverDep,
    include_offline: Annotated[bool, Query(description="Include offline orders")] = False,
    fresh: Annotated[bool, Query(description="Bypass cache")] = False,
) -> OrderBookResponse:
    item = resolver.by_slug(slug)
    if item is None:
        raise HTTPException(404, f"unknown slug '{slug}'")
    try:
        payload = await client.get_orders(slug, fresh=fresh)
    except WFMError as e:
        raise HTTPException(503, str(e)) from e
    orders = payload.get("payload", {}).get("orders", []) or []
    online_only = not include_offline
    sell = compute_stats(orders, side="sell", online_only=online_only)
    buy = compute_stats(orders, side="buy", online_only=online_only)
    top = sorted(
        (o for o in orders if o.get("order_type") == "sell"),
        key=lambda o: int(o.get("platinum", 0)),
    )[:10]
    return OrderBookResponse(
        slug=slug, item_name=item.item_name, fetched_at=_now_iso(),
        stale=bool(payload.get("_stale")),
        sell=_stats_to_model(sell), buy=_stats_to_model(buy),
        top_orders=[_order_to_row(o) for o in top],
    )


@router.get(
    "/wfm/profile/{user}", summary="WFM profile (reputation, status, etc.)",
)
async def wfm_profile(user: str, client: WFMClientDep) -> dict[str, Any]:
    try:
        return await client.get_profile(user)
    except WFMError as e:
        raise HTTPException(503, str(e)) from e


# ----------------------------------------------------------------- /me/*


async def _floor_for(client, slug: str, *, online_only: bool) -> int | None:
    """Helper: fetch min sell price for a slug, online-only by default."""
    try:
        payload = await client.get_orders(slug)
    except WFMError:
        return None
    orders = payload.get("payload", {}).get("orders", []) or []
    stats = compute_stats(orders, side="sell", online_only=online_only)
    return stats.min_price


@router.get(
    "/me/listings", summary="Your active WTS/WTB on WFM",
)
async def me_listings(client: WFMClientDep, br: BridgeDep) -> dict[str, Any]:
    meta = br.meta or {}
    inner = meta.get("meta") or {}
    user = inner.get("wfm_username")
    if not user:
        raise HTTPException(503, "wfm_username not available from agent meta")
    try:
        return await client.get_profile_orders(user)
    except WFMError as e:
        raise HTTPException(503, str(e)) from e


@router.get(
    "/me/inventory-priced", response_model=PricedItemListResponse,
    summary="Inventory enriched with WFM prices",
)
async def me_inventory_priced(
    br: BridgeDep,
    rs: ResolverDep,
    slug_resolver: SlugResolverDep,
    client: WFMClientDep,
    slot: Annotated[str, Query(description="warframe|primary|secondary|melee|all")] = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PricedItemListResponse:
    try:
        data = await br.lastdata()
    except BridgeError as e:
        raise HTTPException(503, f"inventory unavailable: {e}") from e

    section_map = {
        "warframe": "Suits", "primary": "LongGuns", "secondary": "Pistols",
        "melee": "Melee", "all": None,
    }
    if slot not in section_map:
        raise HTTPException(400, f"unknown slot '{slot}'")

    raw_items: list[dict] = []
    if section_map[slot] is None:
        for key in ("Suits", "LongGuns", "Pistols", "Melee"):
            raw_items.extend(data.get(key) or [])
    else:
        raw_items = list(data.get(section_map[slot]) or [])

    enriched: list[PricedItemEntry] = []
    seen_slugs: set[str] = set()
    for it in raw_items[:limit]:
        u = it.get("ItemType") or ""
        slug = slug_resolver.resolve_unique_name(u)
        name = (rs.lookup(u) or {}).get("name") or rs.resolve(u)
        sell_min, sell_median, sell_spread, buy_max, vaulted = None, None, None, None, None
        if slug and slug not in seen_slugs:
            seen_slugs.add(slug)
            ref = slug_resolver.by_slug(slug)
            vaulted = ref.vaulted if ref else None
            try:
                payload = await client.get_orders(slug)
                orders = payload.get("payload", {}).get("orders", []) or []
                sell = compute_stats(orders, side="sell", online_only=True)
                buy = compute_stats(orders, side="buy", online_only=True)
                sell_min, sell_median = sell.min_price, sell.median
                sell_spread = (
                    (sell.max_price - sell.min_price)
                    if sell.min_price is not None and sell.max_price is not None
                    else None
                )
                buy_max = buy.max_price
            except WFMError:
                pass
        enriched.append(PricedItemEntry(
            unique_name=u, name=name, slug=slug,
            count=it.get("ItemCount"), vaulted=vaulted,
            sell_min=sell_min, sell_median=sell_median, sell_spread=sell_spread,
            buy_max=buy_max,
            estimated_value=(sell_median * (it.get("ItemCount") or 1)) if sell_median else None,
        ))

    return PricedItemListResponse(total=len(enriched), returned=len(enriched), items=enriched)


@router.get(
    "/me/prime-parts-priced", response_model=PricedItemListResponse,
    summary="Your prime parts/BPs enriched with WFM floor/median prices",
)
async def me_prime_parts_priced(
    br: BridgeDep,
    rs: ResolverDep,
    slug_resolver: SlugResolverDep,
    client: WFMClientDep,
    min_count: Annotated[int, Query(ge=1)] = 1,
) -> PricedItemListResponse:
    try:
        data = await br.lastdata()
    except BridgeError as e:
        raise HTTPException(503, f"inventory unavailable: {e}") from e

    agg: dict[str, int] = {}
    for src in ("MiscItems", "Recipes"):
        for it in data.get(src) or []:
            t = it.get("ItemType") or ""
            if t.startswith("/Lotus/Types/Recipes/") and "Prime" in t:
                agg[t] = agg.get(t, 0) + int(it.get("ItemCount", 1) or 0)

    rows: list[PricedItemEntry] = []
    for u, count in agg.items():
        if count < min_count:
            continue
        slug = slug_resolver.resolve_unique_name(u)
        name = (rs.lookup(u) or {}).get("name") or rs.resolve(u)
        sell_min, sell_median, sell_spread, buy_max, vaulted = None, None, None, None, None
        if slug:
            ref = slug_resolver.by_slug(slug)
            vaulted = ref.vaulted if ref else None
            try:
                payload = await client.get_orders(slug)
                orders = payload.get("payload", {}).get("orders", []) or []
                sell = compute_stats(orders, side="sell", online_only=True)
                buy = compute_stats(orders, side="buy", online_only=True)
                sell_min, sell_median = sell.min_price, sell.median
                sell_spread = (
                    (sell.max_price - sell.min_price)
                    if sell.min_price is not None and sell.max_price is not None
                    else None
                )
                buy_max = buy.max_price
            except WFMError:
                pass
        rows.append(PricedItemEntry(
            unique_name=u, name=name, slug=slug, count=count, vaulted=vaulted,
            sell_min=sell_min, sell_median=sell_median, sell_spread=sell_spread,
            buy_max=buy_max,
            estimated_value=(sell_median * count) if sell_median else None,
        ))

    rows.sort(key=lambda r: -((r.estimated_value or 0)))
    return PricedItemListResponse(total=len(rows), returned=len(rows), items=rows)


@router.get(
    "/me/sets-profit", response_model=SetProfitResponse,
    summary="Buildable set profit calculator (parts you own + cost to complete)",
)
async def me_sets_profit(
    br: BridgeDep,
    slug_resolver: SlugResolverDep,
    set_index: SetIndexDep,
    client: WFMClientDep,
    min_margin: Annotated[int, Query(ge=0)] = 0,
) -> SetProfitResponse:
    try:
        data = await br.lastdata()
    except BridgeError as e:
        raise HTTPException(503, f"inventory unavailable: {e}") from e

    # Build inventory-by-slug map.
    inv_by_slug: dict[str, int] = {}
    for src in ("MiscItems", "Recipes"):
        for it in data.get(src) or []:
            slug = slug_resolver.resolve_unique_name(it.get("ItemType") or "")
            if slug:
                inv_by_slug[slug] = inv_by_slug.get(slug, 0) + int(it.get("ItemCount", 1) or 0)

    # Fetch floor for every needed slug + every full-set slug.
    needed: set[str] = set()
    for comp in set_index.all_sets():
        needed.update(comp.parts.keys())
        needed.add(comp.set_slug)
    floors: dict[str, int | None] = {}
    for slug in needed:
        floors[slug] = await _floor_for(client, slug, online_only=True)

    part_floors = {s: v for s, v in floors.items() if s in {p for c in set_index.all_sets() for p in c.parts}}
    set_floors = {c.set_slug: floors.get(c.set_slug) for c in set_index.all_sets()}

    rows = compute_set_profits(
        index=set_index, inventory=inv_by_slug,
        part_floor_prices=part_floors, set_prices=set_floors,
        min_margin=min_margin,
    )
    return SetProfitResponse(
        total=len(rows), returned=len(rows),
        items=[SetProfitRowModel(**r.__dict__) for r in rows],
    )


@router.get(
    "/me/wtb-matches", response_model=WtbMatchResponse,
    summary="WTB orders for items you currently own",
)
async def me_wtb_matches(
    br: BridgeDep,
    slug_resolver: SlugResolverDep,
    client: WFMClientDep,
    min_offer: Annotated[int, Query(ge=1)] = 10,
) -> WtbMatchResponse:
    try:
        data = await br.lastdata()
    except BridgeError as e:
        raise HTTPException(503, f"inventory unavailable: {e}") from e

    inv_by_slug: dict[str, int] = {}
    for src in ("MiscItems", "Recipes"):
        for it in data.get(src) or []:
            slug = slug_resolver.resolve_unique_name(it.get("ItemType") or "")
            if slug:
                inv_by_slug[slug] = inv_by_slug.get(slug, 0) + int(it.get("ItemCount", 1) or 0)

    matches: list[WtbMatchRow] = []
    for slug, qty in inv_by_slug.items():
        try:
            payload = await client.get_orders(slug)
        except WFMError:
            continue
        orders = payload.get("payload", {}).get("orders", []) or []
        ref = slug_resolver.by_slug(slug)
        for o in orders:
            if o.get("order_type") != "buy" or o.get("platform") != "pc":
                continue
            status = (o.get("user") or {}).get("status")
            if status not in {"ingame", "online"}:
                continue
            price = int(o.get("platinum", 0))
            if price < min_offer:
                continue
            user = o.get("user") or {}
            matches.append(WtbMatchRow(
                slug=slug, item_name=(ref.item_name if ref else slug),
                your_qty=qty,
                buyer=str(user.get("ingame_name") or ""),
                buyer_status=str(status),
                buyer_reputation=int(user.get("reputation", 0) or 0),
                offer_price=price,
            ))

    matches.sort(key=lambda m: (-m.offer_price, m.slug))
    return WtbMatchResponse(total=len(matches), items=matches)


@router.get(
    "/me/relist-nudges", response_model=RelistNudgeResponse,
    summary="Listings where you've fallen out of top-5 or undercut by median",
)
async def me_relist_nudges(
    client: WFMClientDep,
    br: BridgeDep,
    slug_resolver: SlugResolverDep,
) -> RelistNudgeResponse:
    meta = (br.meta or {}).get("meta") or {}
    user = meta.get("wfm_username")
    if not user:
        raise HTTPException(503, "wfm_username unknown")
    try:
        profile = await client.get_profile_orders(user)
    except WFMError as e:
        raise HTTPException(503, str(e)) from e

    my_orders = (profile.get("payload") or {}).get("sell_orders") or []
    nudges: list[RelistNudgeRow] = []
    for mo in my_orders:
        item_info = mo.get("item") or {}
        slug = item_info.get("url_name") or ""
        my_price = int(mo.get("platinum", 0))
        if not slug or not my_price:
            continue
        try:
            payload = await client.get_orders(slug)
        except WFMError:
            continue
        orders = payload.get("payload", {}).get("orders", []) or []
        sell = compute_stats(orders, side="sell", online_only=True)
        top5 = sell.top5 or []
        suggestion = ""
        if sell.median is not None and my_price > sell.median + 5:
            suggestion = f"lower to ~{sell.median}"
        elif top5 and my_price > top5[0]:
            suggestion = f"undercut top by 1 -> {top5[0] - 1}"
        else:
            continue   # already competitive — skip
        ref = slug_resolver.by_slug(slug)
        nudges.append(RelistNudgeRow(
            slug=slug, item_name=ref.item_name if ref else slug,
            your_price=my_price, median=sell.median, top5=top5,
            suggestion=suggestion,
        ))

    nudges.sort(key=lambda n: -n.your_price)
    return RelistNudgeResponse(total=len(nudges), items=nudges)
```

- [ ] **Step 2: Verify the module imports cleanly**

```powershell
uv run python -c "from alecaframe_api.wfm.router import router; print(len(router.routes))"
```

Expected: `7` (or however many endpoints we defined — count includes all GET routes).

- [ ] **Step 3: Commit**

```powershell
git add src/alecaframe_api/wfm/router.py
git commit -m "feat(wfm): add /wfm/* and /me/* endpoints"
```

---

## Task 13: Wire router + singletons in main.py lifespan

**Files:**
- Modify: `src/alecaframe_api/main.py`

- [ ] **Step 1: Update lifespan to construct WFMClient + SlugResolver + SetIndex**

In `src/alecaframe_api/main.py` add an import at the top:

```python
import redis.asyncio as redis_lib
from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm import dependencies as wfm_deps
from alecaframe_api.wfm.client import WFMClient
from alecaframe_api.wfm.router import router as wfm_router
from alecaframe_api.wfm.sets import SetComposition, SetIndex
from alecaframe_api.wfm.slugs import SlugResolver
```

Find the existing lifespan function (it currently constructs `AlecaBridge` and `NameResolver`). Extend it to also build the WFM stack:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, resolver
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bridge = AlecaBridge(
        agent_url=AGENT_URL,
        data_dir=DATA_DIR,
        ttl_seconds=TTL_SECONDS,
    )
    resolver = NameResolver(ALECA_DATA_HOME / "cachedData" / "json")

    # ----- WFM subsystem -----
    redis_client = redis_lib.from_url(_settings.redis_url, decode_responses=True)
    wfm_cache = Cache(client=redis_client, key_prefix="wfm")

    async def _token_provider() -> str:
        import httpx
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{_settings.agent_url.rstrip('/')}/wfm-token")
            r.raise_for_status()
            return r.json()["token"]

    wfm_client = WFMClient(
        cache=wfm_cache, base_url=_settings.wfm_base_url,
        token_provider=_token_provider, platform=_settings.wfm_platform,
        language=_settings.wfm_language,
        rate_limit_per_second=_settings.wfm_rate_limit_per_second,
    )
    slug_resolver = SlugResolver()
    # Bootstrap slug catalogue (best-effort; if WFM is down we'll retry on first endpoint hit).
    try:
        items = await wfm_client.get_items()
        slug_resolver.load(items)
    except Exception as e:
        log.warning("WFM /items bootstrap failed: %s; slug resolution will be empty until first /wfm/items call", e)

    set_idx = SetIndex()
    # Hardcoded seed set; B.2 will populate from AlecaFrame cachedData.
    set_idx.register(SetComposition(
        set_slug="kronen_prime_set", set_name="Kronen Prime Set",
        parts={"kronen_prime_blade": 2, "kronen_prime_handle": 1, "kronen_prime_blueprint": 1},
    ))

    # Expose singletons to wfm/dependencies.
    wfm_deps.wfm_client = wfm_client
    wfm_deps.slug_resolver = slug_resolver
    wfm_deps.set_index = set_idx

    try:
        await bridge.refresh()
    except BridgeError as e:
        log.warning("startup refresh failed (%s); reading whatever is on disk", e)
        bridge.reload_from_disk(force=True)

    yield

    # Shutdown
    await wfm_client.aclose()
    await redis_client.aclose()
```

- [ ] **Step 2: Include the WFM router**

In the same file, after `app = FastAPI(...)`:

```python
app.include_router(wfm_router)
```

- [ ] **Step 3: Run unit tests — must still all pass**

```powershell
uv run pytest -v
```

Expected: all existing tests pass — WFM stack initialisation does not yet have unit tests at the lifespan level. (E2E coverage comes in Task 14.)

- [ ] **Step 4: Smoke-test the running stack**

Start the host agent + compose:

```powershell
./scripts/start-stack.ps1 -Detached
```

Then:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/ | ConvertTo-Json
```

Expected: the `endpoints` list now includes the new `/wfm/items`, `/wfm/orders/{slug}`, `/wfm/profile/{user}`, `/me/listings`, `/me/inventory-priced`, `/me/prime-parts-priced`, `/me/sets-profit`, `/me/wtb-matches`, `/me/relist-nudges`.

```powershell
Invoke-RestMethod http://127.0.0.1:8765/wfm/items | Select-Object -ExpandProperty total
```

Expected: a number > 5000 (full WFM catalogue size — sanity check that the bootstrap call worked).

- [ ] **Step 5: Commit**

```powershell
git add src/alecaframe_api/main.py
git commit -m "feat(main): wire WFMClient + SlugResolver + SetIndex into lifespan; include /wfm router"
```

---

## Task 14: E2E smoke tests for B.1a endpoints

**Files:**
- Modify: `tests/test_smoke_e2e.py`

- [ ] **Step 1: Append the new e2e tests**

Append to `tests/test_smoke_e2e.py`:

```python


@pytest.mark.e2e
def test_wfm_items_listing() -> None:
    r = httpx.get("http://127.0.0.1:8765/wfm/items", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body["total"] > 1000   # WFM catalogue has thousands of slugs


@pytest.mark.e2e
def test_wfm_orders_for_known_slug() -> None:
    r = httpx.get("http://127.0.0.1:8765/wfm/orders/kronen_prime_blade", timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "kronen_prime_blade"
    assert "sell" in body and "buy" in body
    assert isinstance(body["sell"]["count_orders"], int)


@pytest.mark.e2e
def test_wfm_orders_unknown_slug_returns_404() -> None:
    r = httpx.get("http://127.0.0.1:8765/wfm/orders/this_does_not_exist", timeout=10)
    assert r.status_code == 404


@pytest.mark.e2e
def test_me_sets_profit() -> None:
    r = httpx.get("http://127.0.0.1:8765/me/sets-profit", timeout=20)
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    # Tolerate empty list — depends on user's actual inventory.


@pytest.mark.e2e
def test_proxied_wfm_items_via_frontend() -> None:
    r = httpx.get("http://127.0.0.1:3000/api/wfm/items", timeout=10)
    assert r.status_code == 200
    assert r.json()["total"] > 1000
```

- [ ] **Step 2: Run the e2e suite**

```powershell
uv run pytest tests/test_smoke_e2e.py -m e2e -v
```

Expected: 10 passed (5 from B.0 + 5 new).

- [ ] **Step 3: Run the regular suite — confirms e2e is still deselected by default**

```powershell
uv run pytest -v
```

Expected: 38 passed (10 from B.0 + 6 cache + 10 slugs + 9 client + 7 prices + 6 sets — minus any I miscounted; the key is "all pass, 10 deselected").

Actually let me re-count:
- B.0 unit: 2 config + 4 decrypt-agent + 4 bridge = 10
- B.1a unit: 2 config-extension + 6 cache + 10 slugs + 9 client + 7 prices + 6 sets = 40
- Total unit: 50
- E2E: 10 (B.0 had 5, B.1a adds 5)

So `uv run pytest -v` should say `50 passed, 10 deselected`.

- [ ] **Step 4: Commit**

```powershell
git add tests/test_smoke_e2e.py
git commit -m "test: add B.1a e2e smoke tests"
```

---

## Task 15: README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the new endpoints to the Endpoints section**

In `README.md`, find the `## Endpoints` section. Under `### Сводные` keep what's there. Insert a new subsection BEFORE `### Списки инвентаря`:

```markdown
### WFM market (B.1a)

- `GET /wfm/items` — каталог slug-ов из warframe.market (24h cache)
- `GET /wfm/orders/{slug}?include_offline=0&fresh=0` — текущий order book с агрегациями (min/median/percentiles/spread/volume)
- `GET /wfm/profile/{user}` — репутация и статус
- `GET /me/listings` — твои активные WTS/WTB
- `GET /me/inventory-priced?slot=warframe|primary|secondary|melee|all&limit=50` — инвентарь с медианной ценой и spread
- `GET /me/prime-parts-priced?min_count=1` — расширение `/prime-parts` с ценами + Vaulted-флаг
- `GET /me/sets-profit?min_margin=0` — buildable сеты + cost-to-complete + profit
- `GET /me/wtb-matches?min_offer=10` — WTB-ордера на items, которые у тебя есть
- `GET /me/relist-nudges` — listings, выпавшие из топ-5 / ниже медианы
```

- [ ] **Step 2: Commit**

```powershell
git add README.md
git commit -m "docs: add B.1a endpoints to README"
```

---

## Definition of Done — Phase B.1a

- `./scripts/start-stack.ps1` brings the stack up; `/wfm/items` returns a catalogue with > 1000 entries
- `/wfm/orders/kronen_prime_blade` returns an `OrderBookResponse` with non-null `sell.min_price`
- `/me/inventory-priced?slot=warframe` returns ≥ 1 entry with a non-null `sell_median` (assuming the user owns at least one warframe with WFM market data)
- `/me/sets-profit` returns a list (may be empty depending on inventory)
- `uv run pytest` passes 50/50 unit tests (numbers may shift ±5 depending on exact test counts)
- `uv run pytest -m e2e` passes 10/10 against a running stack
- WFM HTTP traffic is rate-limited (verifiable via `docker compose logs poller` — the rate limiter logs are not yet emitted, but no 429 should be observed in normal operation)

---

## Self-Review Notes

**Spec coverage** (against design doc section 6 — Phase B.1):
- ✅ `GET /wfm/orders/{slug}?include_offline=0&fresh=0`
- ✅ `GET /wfm/items`
- ✅ `GET /wfm/profile/{user}`
- ✅ `GET /me/listings`
- ✅ `GET /me/inventory-priced?slot=warframe|weapon|all`
- ✅ `GET /me/prime-parts-priced`
- ✅ `GET /me/sets-profit?min_margin=10`
- ✅ `GET /me/wtb-matches?min_offer=10p`
- ✅ `GET /me/relist-nudges`
- ⏭ `POST /wfm/listings` (stretch — deferred to B.3)
- ⏭ `DELETE /wfm/listings/{id}` (stretch — deferred to B.3)
- ⏭ WebSocket integration — deferred to B.1c
- ⏭ Frontend pages — deferred to B.1b

**Type / name consistency:**
- `WFMClient.get_orders(slug, *, include_item_info=False, fresh=False)` — used identically in router and tests
- `SlugResolver.by_slug(slug) -> ItemRef | None` — same in router, tests, lifespan
- `compute_stats(orders, *, side, online_only, platform="pc") -> OrderBookStats` — keyword-only signature consistent across prices.py / tests / router
- `compute_set_profits(*, index, inventory, part_floor_prices, set_prices, min_margin=0)` — keyword-only consistent
- `Cache.get_json` / `set_json` / `delete` / `ttl_seconds` / `get_or_set_json` — all used consistently
- `BridgeDep`, `ResolverDep`, `WFMClientDep`, `SlugResolverDep`, `SetIndexDep` — annotated types consistent across router

**Scope:** no scope creep into B.1b (frontend) or B.1c (WebSocket / RabbitMQ / Centrifugo).

**Open assumption to verify during execution:**
- The hardcoded seed `SetComposition` for Kronen Prime is enough to demonstrate `/me/sets-profit`. If the user wants a more complete set list before B.2, add more compositions in Task 13's lifespan block.
- `redis.asyncio.from_url(...)` succeeds against the running compose Redis. If not, `redis>=5.2` may have a different API entry point — check `redis-py` docs.

---

**End of Phase B.1a plan.** B.1b (frontend pages) and B.1c (real-time) plans will be written after B.1a is merged and live.
