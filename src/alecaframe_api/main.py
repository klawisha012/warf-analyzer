"""FastAPI app exposing AlecaFrame inventory data.

Run with:
    uv run uvicorn alecaframe_api.main:app --reload
"""
from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from . import __version__
from .bridge import AlecaBridge, BridgeError
from .config import get_settings
from .naming import NameResolver
from .schemas import (
    ApiInfo,
    Currencies,
    FoundryItem,
    FoundryResponse,
    HealthResponse,
    ItemEntry,
    ItemListResponse,
    PrimePartRow,
    PrimePartsResponse,
    RefreshResponse,
    Standing,
    StandingsResponse,
    SummaryResponse,
)

logging.basicConfig(
    level=os.getenv("ALECA_LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("alecaframe.main")

# --------------------------------------------------------------------- paths

_settings = get_settings()
DATA_DIR = _settings.data_dir
TTL_SECONDS = _settings.ttl_seconds
AGENT_URL = _settings.agent_url
# Static name DB still comes from the host (it ships with AlecaFrame).
# When backend runs in a container the engineer mounts it as /data/cachedData/json
# (handled by docker-compose in Task 9).
ALECA_DATA_HOME = _settings.aleca_data_home or (DATA_DIR / "cachedData" / "json").parent

# ----------------------------------------------------------------- lifespan

bridge: AlecaBridge
resolver: NameResolver


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
    # Backend MUST start cleanly even when the agent is offline. We prefer fresh
    # data, but tolerate every failure mode.
    try:
        await bridge.refresh()
    except BridgeError as e:
        log.warning("startup refresh failed (%s); reading whatever is on disk", e)
        bridge.reload_from_disk(force=True)
    yield


app = FastAPI(
    title="AlecaFrame inventory API",
    version=__version__,
    description=(
        "Read your Warframe inventory off-line by reusing AlecaFrame's own "
        "decryption routines. Data ultimately comes from Digital Extremes' "
        "/api/inventory snapshot that AlecaFrame caches at "
        "`%LOCALAPPDATA%/AlecaFrame/lastData.dat`."
    ),
    lifespan=lifespan,
)

# ---------------------------------------------------------- helpers / deps


def get_bridge() -> AlecaBridge:
    return bridge


def get_resolver() -> NameResolver:
    return resolver


BridgeDep = Annotated[AlecaBridge, Depends(get_bridge)]
ResolverDep = Annotated[NameResolver, Depends(get_resolver)]


async def _safe_get_lastdata(br: AlecaBridge) -> dict[str, Any]:
    try:
        return await br.lastdata()
    except BridgeError as e:
        raise HTTPException(status_code=503, detail=f"decrypt failed: {e}") from e


async def _safe_get_deltas(br: AlecaBridge) -> dict[str, Any]:
    try:
        return await br.deltas()
    except BridgeError as e:
        raise HTTPException(status_code=503, detail=f"decrypt failed: {e}") from e


def _enrich_list(items: list[dict[str, Any]], rs: NameResolver) -> list[ItemEntry]:
    out: list[ItemEntry] = []
    for it in items:
        u = it.get("ItemType") or it.get("uniqueName") or ""
        meta = rs.lookup(u) or {}
        out.append(
            ItemEntry(
                unique_name=u,
                name=meta.get("name") or rs.resolve(u),
                category=meta.get("category"),
                count=it.get("ItemCount"),
                xp=it.get("XP"),
                item_id=_extract_oid(it.get("ItemId")),
                extra={
                    k: v
                    for k, v in it.items()
                    if k not in {"ItemType", "ItemCount", "XP", "ItemId"} and v not in (None, "", [])
                } or None,
            )
        )
    return out


def _extract_oid(v: Any) -> str | None:
    if isinstance(v, dict):
        return v.get("$oid") or v.get("$id")
    if isinstance(v, str):
        return v
    return None


# --------------------------------------------------------------- endpoints


@app.get("/", response_model=ApiInfo, summary="Service info & endpoint list")
async def index() -> ApiInfo:
    routes = sorted({r.path for r in app.routes if getattr(r, "include_in_schema", False)})
    return ApiInfo(version=__version__, endpoints=routes)


@app.get("/healthz", response_model=HealthResponse, summary="Liveness + cache status")
async def healthz(br: BridgeDep) -> HealthResponse:
    meta = br.meta or {}
    return HealthResponse(
        ok=True,
        wfm_username=(meta.get("meta") or {}).get("wfm_username"),
        aleca_version=(meta.get("meta") or {}).get("aleca_version"),
        cache=br.cache_status,
    )


@app.post("/refresh", response_model=RefreshResponse, summary="Force-decrypt the .dat files")
async def refresh(br: BridgeDep) -> RefreshResponse:
    try:
        result = await br.refresh()
    except BridgeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return RefreshResponse(
        ok=bool(result.get("ok")),
        files=result.get("files") or {},
        meta=result.get("meta") or {},
        elapsed_ms=result.get("elapsed_ms"),
    )


# ----- summary / currencies / standings ------------------------------------


@app.get("/summary", response_model=SummaryResponse, summary="One-shot overview")
async def summary(br: BridgeDep) -> SummaryResponse:
    data = await _safe_get_lastdata(br)
    meta_outer = br.meta or {}
    meta_inner = meta_outer.get("meta") or {}

    sections = {
        "warframes": _len(data.get("Suits")),
        "primaries": _len(data.get("LongGuns")),
        "secondaries": _len(data.get("Pistols")),
        "melee": _len(data.get("Melee")),
        "sentinels": _len(data.get("Sentinels")),
        "sentinel_weapons": _len(data.get("SentinelWeapons")),
        "archwings": _len(data.get("SpaceSuits")),
        "arch_guns": _len(data.get("SpaceGuns")),
        "arch_melee": _len(data.get("SpaceMelee")),
        "operator_amps": _len(data.get("OperatorAmps")),
        "kdrives": _len(data.get("Hoverboards")),
        "moa_pets": _len(data.get("MoaPets")),
        "kubrow_pets": _len(data.get("KubrowPets")),
        "mods": _len(data.get("RawUpgrades")),
        "misc_items": _len(data.get("MiscItems")),
        "consumables": _len(data.get("Consumables")),
        "cosmetics": _len(data.get("FlavourItems")),
        "recipes_in_inventory": _len(data.get("Recipes")),
        "pending_foundry": _len(data.get("PendingRecipes")),
    }
    standings_summary = {
        k.replace("DailyAffiliation", "") or "global": v
        for k, v in data.items()
        if k.startswith("DailyAffiliation") and isinstance(v, int)
    }
    return SummaryResponse(
        wfm_username=meta_inner.get("wfm_username"),
        currencies=_currencies(data),
        section_counts=sections,
        standing_summary=standings_summary,
        mastery_rank=data.get("PlayerLevel"),
        aleca_version=meta_inner.get("aleca_version"),
        cache=br.cache_status,
    )


@app.get("/currencies", response_model=Currencies)
async def currencies(br: BridgeDep) -> Currencies:
    return _currencies(await _safe_get_lastdata(br))


@app.get("/standings", response_model=StandingsResponse)
async def standings(br: BridgeDep) -> StandingsResponse:
    data = await _safe_get_lastdata(br)
    items: list[Standing] = []
    for k, v in sorted(data.items()):
        if not (k.startswith("DailyAffiliation") and isinstance(v, int)):
            continue
        syndicate = k.replace("DailyAffiliation", "") or "global"
        items.append(Standing(syndicate=syndicate, earned_today=v))
    cap_guess = max((it.earned_today for it in items if it.earned_today), default=None)
    return StandingsResponse(cap_seems_to_be=cap_guess, items=items)


# ----- inventory lists -----------------------------------------------------

_WEAPON_SLOTS: dict[str, str] = {
    "primary": "LongGuns",
    "secondary": "Pistols",
    "melee": "Melee",
    "sentinel": "Sentinels",
    "sentinel_weapon": "SentinelWeapons",
    "archwing": "SpaceSuits",
    "arch_gun": "SpaceGuns",
    "arch_melee": "SpaceMelee",
    "amp": "OperatorAmps",
    "kdrive": "Hoverboards",
    "moa": "MoaPets",
    "kubrow": "KubrowPets",
}


@app.get("/warframes", response_model=ItemListResponse, summary="Owned Warframes")
async def warframes(br: BridgeDep, rs: ResolverDep) -> ItemListResponse:
    data = await _safe_get_lastdata(br)
    src = data.get("Suits") or []
    items = _enrich_list(src, rs)
    return ItemListResponse(total=len(items), returned=len(items), items=items)


@app.get(
    "/weapons",
    response_model=ItemListResponse,
    summary="Weapons by slot (primary / secondary / melee / sentinel / archwing / ...)",
)
async def weapons(
    br: BridgeDep,
    rs: ResolverDep,
    slot: Annotated[str, Query(description=f"One of: {', '.join(_WEAPON_SLOTS)}")] = "primary",
) -> ItemListResponse:
    key = _WEAPON_SLOTS.get(slot.lower())
    if key is None:
        raise HTTPException(status_code=400, detail=f"unknown slot '{slot}'; try one of {sorted(_WEAPON_SLOTS)}")
    data = await _safe_get_lastdata(br)
    src = data.get(key) or []
    items = _enrich_list(src, rs)
    return ItemListResponse(total=len(items), returned=len(items), items=items)


@app.get("/mods", response_model=ItemListResponse, summary="Owned mods (RawUpgrades)")
async def mods(
    br: BridgeDep,
    rs: ResolverDep,
    q: Annotated[str | None, Query(description="case-insensitive substring of mod name")] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemListResponse:
    data = await _safe_get_lastdata(br)
    src = data.get("RawUpgrades") or []
    items = _enrich_list(src, rs)
    if q:
        needle = q.lower()
        items = [it for it in items if needle in it.name.lower()]
    items.sort(key=lambda it: (it.name or "").lower())
    total = len(items)
    items = items[offset : offset + limit]
    return ItemListResponse(total=total, returned=len(items), items=items)


@app.get("/recipes", response_model=ItemListResponse, summary="Blueprints in inventory")
async def recipes(
    br: BridgeDep,
    rs: ResolverDep,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=2000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ItemListResponse:
    data = await _safe_get_lastdata(br)
    items = _enrich_list(data.get("Recipes") or [], rs)
    if q:
        needle = q.lower()
        items = [it for it in items if needle in it.name.lower() or needle in it.unique_name.lower()]
    items.sort(key=lambda it: (it.name or "").lower())
    total = len(items)
    items = items[offset : offset + limit]
    return ItemListResponse(total=total, returned=len(items), items=items)


@app.get("/misc", response_model=ItemListResponse, summary="MiscItems (resources + parts)")
async def misc(
    br: BridgeDep,
    rs: ResolverDep,
    q: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 500,
    offset: Annotated[int, Query(ge=0)] = 0,
    sort: Annotated[str, Query(description="name | count_desc | count_asc")] = "name",
) -> ItemListResponse:
    data = await _safe_get_lastdata(br)
    items = _enrich_list(data.get("MiscItems") or [], rs)
    if q:
        needle = q.lower()
        items = [it for it in items if needle in it.name.lower() or needle in it.unique_name.lower()]
    if sort == "count_desc":
        items.sort(key=lambda it: -(it.count or 0))
    elif sort == "count_asc":
        items.sort(key=lambda it: (it.count or 0))
    else:
        items.sort(key=lambda it: (it.name or "").lower())
    total = len(items)
    items = items[offset : offset + limit]
    return ItemListResponse(total=total, returned=len(items), items=items)


# ----- prime parts ---------------------------------------------------------

# Tradeable Prime parts live under /Lotus/Types/Recipes/... — Warframe recipes,
# weapon recipes + weapon-parts, sentinel recipes. We exclude relics (under
# /Game/Projections/) and resources that happen to have "Prime" in their name.
_PRIME_PART_PREFIX = "/Lotus/Types/Recipes/"


@app.get(
    "/prime-parts",
    response_model=PrimePartsResponse,
    summary="Aggregated Prime BPs + weapon parts (the trade view)",
)
async def prime_parts(
    br: BridgeDep,
    rs: ResolverDep,
    min_count: Annotated[int, Query(ge=1)] = 1,
) -> PrimePartsResponse:
    data = await _safe_get_lastdata(br)
    agg: dict[str, dict[str, Any]] = {}

    def consume(items: list[dict[str, Any]], *, is_bp: bool) -> None:
        for it in items:
            t = it.get("ItemType") or ""
            if not (t.startswith(_PRIME_PART_PREFIX) and "Prime" in t):
                continue
            row = agg.setdefault(t, {"count": 0, "is_bp": is_bp})
            row["count"] += int(it.get("ItemCount", 1) or 0)
            if is_bp:
                row["is_bp"] = True

    # both buckets carry prime parts; Recipes = full Blueprints, MiscItems = sub-parts
    consume(data.get("MiscItems") or [], is_bp=False)
    consume(data.get("Recipes") or [], is_bp=True)

    rows: list[PrimePartRow] = []
    total_ducats = 0
    have_any_ducats = False
    for u, info in agg.items():
        if info["count"] < min_count:
            continue
        meta = rs.lookup(u) or {}
        ducats = meta.get("ducats")
        if ducats is not None:
            total_ducats += int(ducats) * info["count"]
            have_any_ducats = True
        rows.append(
            PrimePartRow(
                unique_name=u,
                name=meta.get("name") or rs.resolve(u),
                count=info["count"],
                ducats=ducats,
                is_blueprint=info["is_bp"],
            )
        )
    rows.sort(key=lambda r: (-r.count, r.name.lower()))
    return PrimePartsResponse(
        unique_items=len(rows),
        total_count=sum(r.count for r in rows),
        total_ducat_value=total_ducats if have_any_ducats else None,
        items=rows,
    )


# ----- foundry / rivens ----------------------------------------------------


@app.get("/foundry", response_model=FoundryResponse, summary="Items currently crafting")
async def foundry(br: BridgeDep, rs: ResolverDep) -> FoundryResponse:
    data = await _safe_get_lastdata(br)
    pending = data.get("PendingRecipes") or []
    items: list[FoundryItem] = []
    for it in pending:
        u = it.get("ItemType") or ""
        items.append(
            FoundryItem(
                unique_name=u,
                name=rs.resolve(u),
                completion_date=_extract_date(it.get("CompletionDate")),
                skipped=it.get("RushPlatinum") and True,
            )
        )
    return FoundryResponse(pending=items)


@app.get("/rivens", response_model=ItemListResponse, summary="Riven mods")
async def rivens(br: BridgeDep, rs: ResolverDep) -> ItemListResponse:
    data = await _safe_get_lastdata(br)
    upgrades = data.get("Upgrades") or []
    rivens_src = [u for u in upgrades if "Randomized" in (u.get("ItemType") or "")]
    items = _enrich_list(rivens_src, rs)
    return ItemListResponse(total=len(items), returned=len(items), items=items)


# ----- low-level: raw + deltas --------------------------------------------


@app.get(
    "/raw",
    summary="Entire decrypted lastData.json (escape hatch; large)",
    response_class=JSONResponse,
)
async def raw(
    br: BridgeDep,
    path: Annotated[
        str | None,
        Query(description="dotted/numeric path slice, e.g. `Suits.0` or `SeasonChallengeHistory`"),
    ] = None,
) -> Any:
    data = await _safe_get_lastdata(br)
    if not path:
        return data
    return _slice(data, path)


@app.get(
    "/deltas",
    summary="Decrypted deltas.json (previousMiscState + currentDeltas)",
    response_class=JSONResponse,
)
async def deltas(br: BridgeDep) -> Any:
    return await _safe_get_deltas(br)


@app.get("/meta", summary="Aleca version, WFM username, paths used")
async def meta(br: BridgeDep) -> dict[str, Any]:
    return {
        "api_version": __version__,
        "data_dir": str(DATA_DIR),
        "aleca_data_home": str(ALECA_DATA_HOME),
        "agent_url": AGENT_URL,
        "ttl_seconds": TTL_SECONDS,
        "bridge_meta": br.meta,
    }


# ---------------------------------------------------------- helpers (priv)


def _len(v: Any) -> int:
    return len(v) if isinstance(v, list) else 0


def _currencies(data: dict[str, Any]) -> Currencies:
    return Currencies(
        platinum=int(data.get("PremiumCredits") or 0),
        platinum_free=int(data.get("PremiumCreditsFree") or 0),
        credits=int(data.get("RegularCredits") or 0),
        endo=int(data.get("FusionPoints") or 0),
        ducats=int(data.get("PrimeTokens") or 0),
        trades_remaining=int(data.get("TradesRemaining") or 0),
        gifts_remaining=int(data.get("GiftsRemaining") or 0),
    )


def _slice(data: Any, path: str) -> Any:
    cur: Any = data
    for seg in path.split("."):
        if seg == "":
            continue
        if isinstance(cur, list):
            try:
                cur = cur[int(seg)]
            except (ValueError, IndexError) as e:
                raise HTTPException(status_code=400, detail=f"bad path at '{seg}': {e}") from e
        elif isinstance(cur, dict):
            if seg not in cur:
                raise HTTPException(status_code=404, detail=f"no key '{seg}' (available: {sorted(cur)[:20]} ...)")
            cur = cur[seg]
        else:
            raise HTTPException(status_code=400, detail=f"cannot descend into {type(cur).__name__} at '{seg}'")
    return cur


def run() -> None:
    """Console entry point: `uv run alecaframe-api`."""
    import uvicorn

    uvicorn.run(
        "alecaframe_api.main:app",
        host=os.getenv("ALECA_HOST", "127.0.0.1"),
        port=int(os.getenv("ALECA_PORT", "8765")),
        reload=os.getenv("ALECA_RELOAD") == "1",
    )


def _extract_date(v: Any) -> str | None:
    """MongoDB-style date: {'$date': {'$numberLong': '1712345678000'}} -> ISO string."""
    if isinstance(v, dict):
        d = v.get("$date")
        if isinstance(d, dict):
            ms = d.get("$numberLong")
            if ms is not None:
                try:
                    import datetime as _dt
                    return _dt.datetime.fromtimestamp(int(ms) / 1000, tz=_dt.UTC).isoformat()
                except Exception:
                    return None
        if isinstance(d, str):
            return d
    return None if v is None else str(v)
