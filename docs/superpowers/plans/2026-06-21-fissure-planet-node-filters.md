# Fissure Planet + Node Subscription Filters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two new optional filter axes — `planet` (exact match) and `node` (case-insensitive substring) — to Void Fissure subscriptions, end to end.

**Architecture:** Extend the existing axis-AND matcher (`None` = "any" on each axis) with `planet`/`node`. Persist the two new columns via the project's idempotent `_try_add_column` migration helper. The `/fissures/meta` endpoint gains a static `planets` list (∪ live) and a `nodes` list (live, for autocomplete). The UI adds a planet `<select>` and a free-text node `<input>` backed by a `<datalist>`.

**Tech Stack:** Python 3.12 / FastAPI / Pydantic / aiosqlite (backend); Solid.js / TanStack Query / TypeScript / Tailwind (frontend); pytest.

## Global Constraints

- Code, comments, commit messages: English. (Chat: Russian.)
- No new dependencies.
- Backward compatible: every new field is optional; `None`/`NULL`/`""` = "any". Existing subscriptions and DBs keep working (migration is idempotent `ALTER TABLE ADD COLUMN`).
- `node` matching is **case-insensitive substring**; `planet` matching is **exact**. All axes combine with AND.
- Follow existing patterns (the file already has `era`/`mission_type` axes — mirror them).

---

## File Structure

**Backend (`backend/src/alecaframe_api/`)**
- `fissures/models.py` — `Subscription` dataclass gains `planet`, `node`.
- `fissures/matcher.py` — two new predicates.
- `db/schema.sql` — two new columns on `fissure_subscription`.
- `db/repo.py` — migration calls + `add_`/`list_fissure_subscriptions` carry the columns.
- `schemas.py` — `FissureSubscriptionCreate`, `FissureSubscriptionRow`, `FissureMetaResponse`.
- `fissures/router.py` — `KNOWN_PLANETS`, `_norm_sub`, `add_subscription`, `fissures_meta`.
- `fissures/poller.py` — `_row_to_sub` carries the columns.

**Frontend (`frontend/src/`)**
- `api/types.ts` — three fissure types.
- `routes/Fissures.tsx` — planet select + node input + badges.
- `i18n/dict/ru.ts`, `i18n/dict/en.ts` — `planet`, `node`, `nodePlaceholder` keys.

**Tests**
- `tests/unit/test_fissures_matcher.py`
- `tests/integration/backend/test_fissures_repo.py`
- `tests/integration/backend/test_fissures_router.py`
- `tests/integration/backend/test_fissures_poller.py`

> Test runner: `python -m pytest` from the repo root (the configured venv resolves `alecaframe_api`). Frontend check: `npm run build` inside `frontend/`.

---

## Task 1: Matcher + model (planet exact, node substring)

**Files:**
- Modify: `backend/src/alecaframe_api/fissures/models.py:24-32`
- Modify: `backend/src/alecaframe_api/fissures/matcher.py:10-19`
- Test: `tests/unit/test_fissures_matcher.py`

**Interfaces:**
- Produces: `Subscription(id, era, mission_type, planet, node, is_hard, is_storm, enabled, created_at)` — `planet: str | None`, `node: str | None` (both keyword-constructed everywhere).
- Produces: `matches(fissure, sub) -> bool` — now also gates on `planet` (exact) and `node` (case-insensitive substring of `fissure.node`).

- [ ] **Step 1: Update the `_sub` test helper and add failing tests**

In `tests/unit/test_fissures_matcher.py`, replace the `_sub` helper so it carries the new fields:

```python
def _sub(**over) -> Subscription:
    base = dict(id=1, era=None, mission_type=None, planet=None, node=None,
                is_hard=None, is_storm=None, enabled=True, created_at=0)
    base.update(over)
    return Subscription(**base)
```

Append these tests:

```python
def test_planet_filter() -> None:
    assert matches(_fissure(planet="Neptune"), _sub(planet="Neptune")) is True
    assert matches(_fissure(planet="Neptune"), _sub(planet="Eris")) is False


def test_node_substring_case_insensitive() -> None:
    f = _fissure(node="Proteus (Neptune)")
    assert matches(f, _sub(node="Proteus")) is True
    assert matches(f, _sub(node="proteus")) is True       # case-insensitive
    assert matches(f, _sub(node="(Neptune)")) is True      # substring anywhere
    assert matches(f, _sub(node="Xini")) is False


def test_node_filter_empty_node_never_matches() -> None:
    assert matches(_fissure(node=""), _sub(node="Proteus")) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/unit/test_fissures_matcher.py -v`
Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'planet'` (Subscription has no such field yet).

- [ ] **Step 3: Add the fields to `Subscription`**

In `backend/src/alecaframe_api/fissures/models.py`, replace the `Subscription` dataclass:

```python
@dataclass(frozen=True)
class Subscription:
    id: int
    era: str | None          # None = any
    mission_type: str | None # None = any
    planet: str | None       # None = any (exact match)
    node: str | None         # None = any (case-insensitive substring)
    is_hard: bool | None     # None = any
    is_storm: bool | None    # None = any
    enabled: bool
    created_at: int
```

- [ ] **Step 4: Add the predicates to `matches`**

In `backend/src/alecaframe_api/fissures/matcher.py`, replace the body of `matches`:

```python
def matches(fissure: Fissure, sub: Subscription) -> bool:
    if sub.era is not None and fissure.era != sub.era:
        return False
    if sub.mission_type is not None and fissure.mission_type != sub.mission_type:
        return False
    if sub.planet is not None and fissure.planet != sub.planet:
        return False
    if sub.node is not None and sub.node.lower() not in (fissure.node or "").lower():
        return False
    if sub.is_hard is not None and fissure.is_hard != sub.is_hard:
        return False
    if sub.is_storm is not None and fissure.is_storm != sub.is_storm:
        return False
    return True
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/unit/test_fissures_matcher.py -v`
Expected: PASS (all tests, including the pre-existing ones).

- [ ] **Step 6: Commit**

```bash
git add backend/src/alecaframe_api/fissures/models.py backend/src/alecaframe_api/fissures/matcher.py tests/unit/test_fissures_matcher.py
git commit -m "feat(fissures): match subscriptions on planet (exact) and node (substring)"
```

---

## Task 2: DB layer (schema migration + repo round-trip)

**Files:**
- Modify: `backend/src/alecaframe_api/db/schema.sql:102-110`
- Modify: `backend/src/alecaframe_api/db/repo.py:52` (migration), `:431-446` (add), `:448-457` (list)
- Test: `tests/integration/backend/test_fissures_repo.py`

**Interfaces:**
- Consumes: nothing from Task 1 (independent).
- Produces: `repo.add_fissure_subscription(*, era, mission_type, planet=None, node=None, is_hard, is_storm, ts) -> int` and `repo.list_fissure_subscriptions(...)` rows that include `planet` and `node` keys.

- [ ] **Step 1: Add a failing round-trip test**

Append to `tests/integration/backend/test_fissures_repo.py`:

```python
async def test_subscription_planet_node_round_trip(repo: Repo) -> None:
    await repo.add_fissure_subscription(
        era=None, mission_type=None, planet="Neptune", node="Proteus",
        is_hard=None, is_storm=None, ts=100,
    )
    await repo.add_fissure_subscription(
        era="Axi", mission_type=None, is_hard=None, is_storm=None, ts=101,
    )
    rows = await repo.list_fissure_subscriptions()
    by_era = {r["era"]: r for r in rows}
    assert by_era[None]["planet"] == "Neptune" and by_era[None]["node"] == "Proteus"
    assert by_era["Axi"]["planet"] is None and by_era["Axi"]["node"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/integration/backend/test_fissures_repo.py::test_subscription_planet_node_round_trip -v`
Expected: FAIL — `TypeError: ... unexpected keyword argument 'planet'` (or a `KeyError: 'planet'` on the row).

- [ ] **Step 3: Add the columns to the schema**

In `backend/src/alecaframe_api/db/schema.sql`, replace the `fissure_subscription` table definition:

```sql
CREATE TABLE IF NOT EXISTS fissure_subscription (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  era          TEXT,            -- NULL = any
  mission_type TEXT,            -- NULL = any
  planet       TEXT,            -- NULL = any (exact match)
  node         TEXT,            -- NULL = any (case-insensitive substring)
  is_hard      INTEGER,         -- 0 | 1 | NULL(any)
  is_storm     INTEGER,         -- 0 | 1 | NULL(any)
  enabled      INTEGER NOT NULL DEFAULT 1,
  created_at   INTEGER NOT NULL
);
```

- [ ] **Step 4: Add idempotent migration calls for existing DBs**

In `backend/src/alecaframe_api/db/repo.py`, in `connect()`, just after the existing `riven_auction` migration line (`await _try_add_column(conn, "riven_auction", "owner_status TEXT")`):

```python
            await _try_add_column(conn, "riven_auction", "owner_status TEXT")
            await _try_add_column(conn, "fissure_subscription", "planet TEXT")
            await _try_add_column(conn, "fissure_subscription", "node TEXT")
            await conn.commit()
```

- [ ] **Step 5: Carry the columns through `add_` and `list_`**

In `backend/src/alecaframe_api/db/repo.py`, replace `add_fissure_subscription`:

```python
    async def add_fissure_subscription(
        self, *, era: str | None, mission_type: str | None,
        planet: str | None = None, node: str | None = None,
        is_hard: bool | None, is_storm: bool | None, ts: int,
    ) -> int:
        conn = self._require_conn()
        cur = await conn.execute(
            """INSERT INTO fissure_subscription
               (era, mission_type, planet, node, is_hard, is_storm, enabled, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 1, ?)""",
            (era, mission_type, planet, node,
             None if is_hard is None else int(is_hard),
             None if is_storm is None else int(is_storm),
             ts),
        )
        await conn.commit()
        return int(cur.lastrowid)
```

And in `list_fissure_subscriptions`, replace the SELECT column list:

```python
        sql = ("SELECT id, era, mission_type, planet, node, is_hard, is_storm, enabled, created_at "
               "FROM fissure_subscription")
```

- [ ] **Step 6: Run the repo tests to verify they pass**

Run: `python -m pytest tests/integration/backend/test_fissures_repo.py -v`
Expected: PASS (new round-trip test + all pre-existing repo tests).

- [ ] **Step 7: Commit**

```bash
git add backend/src/alecaframe_api/db/schema.sql backend/src/alecaframe_api/db/repo.py tests/integration/backend/test_fissures_repo.py
git commit -m "feat(fissures): persist planet/node subscription columns with idempotent migration"
```

---

## Task 3: API schemas + router + meta

**Files:**
- Modify: `backend/src/alecaframe_api/schemas.py:374-399`
- Modify: `backend/src/alecaframe_api/fissures/router.py:24-30` (constant), `:51-58` (`_norm_sub`), `:73-84` (`fissures_meta`), `:96-100` (`add_subscription`)
- Test: `tests/integration/backend/test_fissures_router.py`

**Interfaces:**
- Consumes: `repo.add_fissure_subscription(..., planet=, node=)` and `list_fissure_subscriptions` rows with `planet`/`node` keys (Task 2).
- Produces: `POST /fissures/subscriptions` accepts `planet`/`node`; `FissureSubscriptionRow` echoes them; `GET /fissures/meta` returns `planets: list[str]` and `nodes: list[str]`.

- [ ] **Step 1: Add failing router tests**

Append to `tests/integration/backend/test_fissures_router.py`:

```python
@pytest.mark.asyncio
async def test_meta_includes_planets_and_nodes(client: httpx.AsyncClient) -> None:
    r = await client.get("/fissures/meta")
    assert r.status_code == 200
    body = r.json()
    assert "Eris" in body["planets"]       # live planet from the fake client
    assert "Neptune" in body["planets"]     # static known planet
    assert "X (Eris)" in body["nodes"]      # live node from the fake client


@pytest.mark.asyncio
async def test_subscription_with_planet_and_node(client: httpx.AsyncClient) -> None:
    r = await client.post("/fissures/subscriptions",
                          json={"planet": "Neptune", "node": "Proteus"})
    assert r.status_code == 201
    item = r.json()["items"][0]
    assert item["planet"] == "Neptune"
    assert item["node"] == "Proteus"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/integration/backend/test_fissures_router.py::test_meta_includes_planets_and_nodes tests/integration/backend/test_fissures_router.py::test_subscription_with_planet_and_node -v`
Expected: FAIL — `KeyError: 'planets'` on meta; the create test fails on `item["planet"]` (response model lacks the field).

- [ ] **Step 3: Extend the schemas**

In `backend/src/alecaframe_api/schemas.py`, replace the three fissure subscription/meta models:

```python
class FissureMetaResponse(BaseModel):
    eras: list[str]
    mission_types: list[str]
    planets: list[str]
    nodes: list[str]


class FissureSubscriptionRow(BaseModel):
    id: int
    era: str | None = None
    mission_type: str | None = None
    planet: str | None = None
    node: str | None = None
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
    planet: str | None = None
    node: str | None = None
    is_hard: bool | None = None
    is_storm: bool | None = None
```

> Leave `FissureSubscriptionsResponse` unchanged in content — it is shown only to anchor placement between the two models.

- [ ] **Step 4: Add `KNOWN_PLANETS` and wire `_norm_sub` + `add_subscription`**

In `backend/src/alecaframe_api/fissures/router.py`, add the constant after `KNOWN_MISSION_TYPES`:

```python
KNOWN_PLANETS = [
    "Mercury", "Venus", "Earth", "Lua", "Mars", "Deimos", "Phobos",
    "Ceres", "Jupiter", "Europa", "Saturn", "Uranus", "Neptune", "Pluto",
    "Sedna", "Eris", "Void", "Kuva Fortress", "Zariman", "Höllvania",
]
```

Replace `_norm_sub`:

```python
def _norm_sub(r: dict) -> dict:
    def _b(v) -> bool | None:
        return None if v is None else bool(v)
    return {
        "id": r["id"], "era": r["era"], "mission_type": r["mission_type"],
        "planet": r["planet"], "node": r["node"],
        "is_hard": _b(r["is_hard"]), "is_storm": _b(r["is_storm"]),
        "enabled": bool(r["enabled"]), "created_at": r["created_at"],
    }
```

Replace the `repo.add_fissure_subscription(...)` call inside `add_subscription`:

```python
    await repo.add_fissure_subscription(
        era=req.era or None, mission_type=req.mission_type or None,
        planet=req.planet or None, node=req.node or None,
        is_hard=req.is_hard, is_storm=req.is_storm, ts=int(time.time()),
    )
```

- [ ] **Step 5: Extend the meta endpoint to collect planets + nodes**

In `backend/src/alecaframe_api/fissures/router.py`, replace `fissures_meta`:

```python
@router.get("/meta", response_model=FissureMetaResponse,
            summary="All fissure axes (eras, mission types, planets, live nodes)")
async def fissures_meta(client: FissureClientDep) -> FissureMetaResponse:
    live_missions: set[str] = set()
    live_planets: set[str] = set()
    live_nodes: set[str] = set()
    try:
        for f in await client.get_fissures():
            live_missions.add(f.mission_type)
            if f.planet:
                live_planets.add(f.planet)
            if f.node:
                live_nodes.add(f.node)
    except FissureClientError:
        pass
    return FissureMetaResponse(
        eras=ERAS,
        mission_types=sorted(set(KNOWN_MISSION_TYPES) | live_missions),
        planets=sorted(set(KNOWN_PLANETS) | live_planets),
        nodes=sorted(live_nodes),
    )
```

- [ ] **Step 6: Run the router tests to verify they pass**

Run: `python -m pytest tests/integration/backend/test_fissures_router.py -v`
Expected: PASS (new tests + all pre-existing router tests).

- [ ] **Step 7: Commit**

```bash
git add backend/src/alecaframe_api/schemas.py backend/src/alecaframe_api/fissures/router.py tests/integration/backend/test_fissures_router.py
git commit -m "feat(fissures): expose planet/node in subscription API and meta lists"
```

---

## Task 4: Poller wiring

**Files:**
- Modify: `backend/src/alecaframe_api/fissures/poller.py:43-50`
- Test: `tests/integration/backend/test_fissures_poller.py`

**Interfaces:**
- Consumes: `Subscription` with `planet`/`node` (Task 1); rows with `planet`/`node` keys from `list_fissure_subscriptions` (Task 2).
- Produces: poller notifies only for fissures whose `planet`/`node` also satisfy the subscription.

- [ ] **Step 1: Add a failing node-filter notification test**

Append to `tests/integration/backend/test_fissures_poller.py`:

```python
@pytest.mark.asyncio
async def test_node_filtered_subscription_only_fires_for_match(repo: Repo) -> None:
    await repo.add_fissure_subscription(
        era=None, mission_type=None, planet=None, node="Proteus",
        is_hard=None, is_storm=None, ts=1,
    )
    await repo.register_telegram_chat(chat_id=42, username=None, ts=1)
    f_match = Fissure(id="m1", era="Axi", mission_type="Survival",
                      node="Proteus (Neptune)", planet="Neptune", enemy=None,
                      is_hard=False, is_storm=False, activation=None, expiry=None)
    f_other = _f("o1", "Axi")  # node "X (Eris)"
    tg = _FakeTelegram()
    poller = FissurePoller(repo=repo, client=_FakeClient([f_match, f_other]), telegram=tg)

    await poller.tick(now=1000)
    assert len(tg.sent) == 1  # only the Proteus node matched
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/integration/backend/test_fissures_poller.py::test_node_filtered_subscription_only_fires_for_match -v`
Expected: FAIL — `KeyError: 'planet'` raised inside `_row_to_sub` (it does not read the new columns yet), surfaced as a poller tick error.

- [ ] **Step 3: Read the new columns in `_row_to_sub`**

In `backend/src/alecaframe_api/fissures/poller.py`, replace `_row_to_sub`:

```python
def _row_to_sub(r: dict) -> Subscription:
    def _b(v) -> bool | None:
        return None if v is None else bool(v)
    return Subscription(
        id=int(r["id"]), era=r["era"], mission_type=r["mission_type"],
        planet=r["planet"], node=r["node"],
        is_hard=_b(r["is_hard"]), is_storm=_b(r["is_storm"]),
        enabled=bool(r["enabled"]), created_at=int(r["created_at"]),
    )
```

- [ ] **Step 4: Run the poller tests to verify they pass**

Run: `python -m pytest tests/integration/backend/test_fissures_poller.py -v`
Expected: PASS (new test + all pre-existing poller tests).

- [ ] **Step 5: Run the full backend fissure suite as a regression gate**

Run: `python -m pytest tests/unit/test_fissures_matcher.py tests/unit/test_fissures_models.py tests/integration/backend/test_fissures_repo.py tests/integration/backend/test_fissures_router.py tests/integration/backend/test_fissures_poller.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit**

```bash
git add backend/src/alecaframe_api/fissures/poller.py tests/integration/backend/test_fissures_poller.py
git commit -m "feat(fissures): apply planet/node filters in the notification poller"
```

---

## Task 5: Frontend (types + UI + i18n)

**Files:**
- Modify: `frontend/src/api/types.ts:276` (meta), `:278-295` (row + create)
- Modify: `frontend/src/routes/Fissures.tsx:48-62` (signals + addSub), `:88-92` (filter inputs), `:122-126` (badges)
- Modify: `frontend/src/i18n/dict/ru.ts:154`, `frontend/src/i18n/dict/en.ts:153`

**Interfaces:**
- Consumes: `GET /fissures/meta` → `{ planets, nodes }`; `POST /fissures/subscriptions` accepts `{ planet, node }`; rows echo `planet`/`node` (Task 3).
- Produces: UI controls; no downstream consumers.

- [ ] **Step 1: Update the TypeScript contract**

In `frontend/src/api/types.ts`, replace `FissureMetaResponse`:

```typescript
export type FissureMetaResponse = {
  eras: string[];
  mission_types: string[];
  planets: string[];
  nodes: string[];
};
```

Replace `FissureSubscriptionRow` and `FissureSubscriptionCreate`:

```typescript
export type FissureSubscriptionRow = {
  id: number;
  era: string | null;
  mission_type: string | null;
  planet: string | null;
  node: string | null;
  is_hard: boolean | null;
  is_storm: boolean | null;
  enabled: boolean;
  created_at: number;
};

export type FissureSubscriptionsResponse = { total: number; items: FissureSubscriptionRow[] };

export type FissureSubscriptionCreate = {
  era: string | null;
  mission_type: string | null;
  planet: string | null;
  node: string | null;
  is_hard: boolean | null;
  is_storm: boolean | null;
};
```

- [ ] **Step 2: Add i18n keys (ru + en)**

In `frontend/src/i18n/dict/ru.ts`, inside the `fissures` block, after the `mission:` line:

```typescript
    mission: "Тип миссии",
    planet: "Планета",
    node: "Миссия (нода)",
    nodePlaceholder: "напр. Proteus",
```

In `frontend/src/i18n/dict/en.ts`, inside the `fissures` block, after the `mission:` line:

```typescript
    mission: "Mission type",
    planet: "Planet",
    node: "Mission (node)",
    nodePlaceholder: "e.g. Proteus",
```

- [ ] **Step 3: Add the signals and extend `addSub`**

In `frontend/src/routes/Fissures.tsx`, add two signals after the `mission` signal:

```tsx
  const [era, setEra] = createSignal("");
  const [mission, setMission] = createSignal("");
  const [planet, setPlanet] = createSignal("");
  const [node, setNode] = createSignal("");
  const [hard, setHard] = createSignal("");
  const [storm, setStorm] = createSignal("");
```

Replace `addSub`:

```tsx
  async function addSub() {
    await fetchers.fissuresSubAdd({
      era: era() || null,
      mission_type: mission() || null,
      planet: planet() || null,
      node: node().trim() || null,
      is_hard: triToBool(hard()),
      is_storm: triToBool(storm()),
    });
    setEra(""); setMission(""); setPlanet(""); setNode(""); setHard(""); setStorm("");
    await qc.invalidateQueries({ queryKey: keys.fissuresSubs() });
  }
```

- [ ] **Step 4: Add the planet select + node input to the form**

In `frontend/src/routes/Fissures.tsx`, insert this block between the mission `<select>` and the Steel Path `<label>` (i.e. directly after the closing `</select>` of the mission filter):

```tsx
              <label class="block text-xs text-sub">{t("fissures.planet")}</label>
              <select value={planet()} onChange={(e) => setPlanet(e.currentTarget.value)} class="field">
                <option value="">{t("fissures.any")}</option>
                <For each={meta.data?.planets ?? []}>{(x) => <option value={x}>{x}</option>}</For>
              </select>

              <label class="block text-xs text-sub">{t("fissures.node")}</label>
              <input
                value={node()}
                onInput={(e) => setNode(e.currentTarget.value)}
                list="fissure-nodes"
                placeholder={t("fissures.nodePlaceholder")}
                class="field"
              />
              <datalist id="fissure-nodes">
                <For each={meta.data?.nodes ?? []}>{(x) => <option value={x} />}</For>
              </datalist>
```

- [ ] **Step 5: Show planet/node badges in the subscription list**

In `frontend/src/routes/Fissures.tsx`, inside the subscription `<li>` badge row, after the `mission_type` Badge and before the Steel Path `<Show>`:

```tsx
                          <Badge>{s.mission_type ?? t("fissures.any")}</Badge>
                          <Show when={s.planet}><Badge variant="info">{s.planet}</Badge></Show>
                          <Show when={s.node}><Badge>{s.node}</Badge></Show>
                          <Show when={s.is_hard === true}><Badge variant="warn">SP</Badge></Show>
```

- [ ] **Step 6: Typecheck / build the frontend**

Run: `npm run build` (inside `frontend/`)
Expected: build succeeds, no TypeScript errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/api/types.ts frontend/src/routes/Fissures.tsx frontend/src/i18n/dict/ru.ts frontend/src/i18n/dict/en.ts
git commit -m "feat(fissures): planet select + free-text node filter with autocomplete in UI"
```

---

## Final Verification

- [ ] Backend regression: `python -m pytest tests/ -q` → all green.
- [ ] Frontend: `npm run build` inside `frontend/` → succeeds.
- [ ] Manual smoke (optional, requires running stack): open the Fissures page, pick a planet, type a node fragment (e.g. `Proteus`), subscribe, confirm the new subscription chip shows the planet/node badges.

## Self-Review Notes

- **Spec coverage:** planet filter (Tasks 1–5), node filter incl. case-insensitive substring (Tasks 1–5), meta `planets`/`nodes` source — static ∪ live planets, live nodes (Task 3), UI free-text + datalist autocomplete (Task 5), backward-compat migration (Task 2), poller honors new axes (Task 4). ✅
- **Type consistency:** `planet`/`node` are `str | None` everywhere; repo method gives them `= None` defaults so the three pre-existing callers (two repo tests + one poller test) keep compiling without edits, while the router passes them explicitly. `Subscription` is keyword-constructed at both sites (`_sub` helper, `_row_to_sub`), both updated.
- **No placeholders:** every code/edit step shows the full replacement content and an exact run command with expected result.
