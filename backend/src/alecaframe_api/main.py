"""FastAPI app exposing AlecaFrame inventory data.

Run with:
    uv run uvicorn alecaframe_api.main:app --reload
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from typing import Annotated, Any

import redis.asyncio as redis_lib
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from . import __version__
from .bridge import AlecaBridge, BridgeError
from .config import get_settings
from .db.repo import Repo
from .fissures import dependencies as fissures_deps
from .fissures.client import FissureClient
from .fissures.poller import FissurePoller
from .fissures.router import router as fissures_router
from .fissures.telegram import TelegramBot, TelegramClient
from .infra.broker import RabbitMQBus
from .infra.cache import Cache
from .infra.push import CentrifugoPublisher
from .naming import NameResolver
from .reference import stats_loader
from .reference.nodes_loader import NodeCatalog
from .reference.router import router as reference_router
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
from .wfm import dependencies as wfm_deps
from .wfm.auction_poller import AuctionPoller
from .wfm.auctions_client import WFMAuctionClient
from .wfm.client import WFMClient
from .wfm.consumer import handle_live_order
from .wfm.history_router import router as history_router
from .wfm.me_router import router as me_router
from .wfm.price_poller import PricePoller
from .wfm.price_store import PriceStore
from .wfm.recipe_uses import RecipeUse, load_recipe_uses
from .wfm.rivens_router import router as rivens_router
from .wfm.router import router as wfm_router
from .wfm.sets import SetComposition, SetIndex
from .wfm.sets_loader import load_set_compositions_from_aleca
from .wfm.slugs import SlugResolver

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
# Static name DB ships with AlecaFrame on the host. Two ways to reach it:
#   1. ALECA_DATA_HOME env var pointing at .../AlecaFrame (the directory that
#      contains cachedData/json/) — set by docker-compose to /aleca-data when
#      it bind-mounts ${ALECA_DATA_HOME_HOST}.
#   2. Fallback to DATA_DIR (containers without the mount get a graceful empty
#      catalogue + warning rather than a corrupted /data/cachedData/cachedData
#      path).
# The previous default of `(DATA_DIR / "cachedData" / "json").parent` produced
# /data/cachedData which then got "cachedData/json" appended again — double
# segment, never resolved on disk.
ALECA_DATA_HOME = _settings.aleca_data_home or DATA_DIR

# ----------------------------------------------------------------- lifespan

bridge: AlecaBridge
resolver: NameResolver
repo: Repo | None = None
recipe_uses_idx: dict[str, list[RecipeUse]] = {}
auctions_client: WFMAuctionClient | None = None
auction_poller: AuctionPoller | None = None
telegram_client: TelegramClient | None = None
fissure_poller: FissurePoller | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, resolver, recipe_uses_idx
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    bridge = AlecaBridge(
        agent_url=AGENT_URL,
        data_dir=DATA_DIR,
        ttl_seconds=TTL_SECONDS,
    )
    resolver = NameResolver(ALECA_DATA_HOME / "cachedData" / "json")
    recipe_uses_idx = load_recipe_uses(
        cached_json_dir=ALECA_DATA_HOME / "cachedData" / "json",
    )

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
        cache=wfm_cache,
        base_url=_settings.wfm_base_url,
        token_provider=_token_provider,
        platform=_settings.wfm_platform,
        language=_settings.wfm_language,
        rate_limit_per_second=_settings.wfm_rate_limit_per_second,
    )
    slug_resolver = SlugResolver()
    # Bootstrap slug catalogue (best-effort; if WFM is down we'll retry on first endpoint hit).
    try:
        items = await wfm_client.get_items()
        slug_resolver.load(items)
    except Exception as e:
        log.warning(
            "WFM /items bootstrap failed: %s; slug resolution will be empty until first /wfm/items call",
            e,
        )

    # Load ad-hoc overrides from data/slug_overrides.json if it exists
    overrides_path = DATA_DIR / "slug_overrides.json"
    if overrides_path.exists():
        try:
            import json

            with open(overrides_path, encoding="utf-8") as f:
                overrides = json.load(f)
                if isinstance(overrides, dict):
                    slug_resolver.apply_overrides(overrides)
                    log.info(
                        "loaded %d ad-hoc slug overrides from %s",
                        len(overrides),
                        overrides_path,
                    )
        except Exception as e:
            log.warning("failed to load slug overrides from %s: %s", overrides_path, e)

    set_idx = SetIndex()
    # Hardcoded fallback seed when neither DB nor AlecaFrame cachedData provides
    # set compositions. Quantities match WFM v2 `quantityInSet` per part:
    #   kronen_prime_blade=2, kronen_prime_handle=2, kronen_prime_blueprint=1.
    # (Previous seed had handle=1, which under-counted missing parts by one.)
    set_idx.register(
        SetComposition(
            set_slug="kronen_prime_set",
            set_name="Kronen Prime Set",
            parts={
                "kronen_prime_blade": 2,
                "kronen_prime_handle": 2,
                "kronen_prime_blueprint": 1,
            },
        )
    )

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
            log.info(
                "loaded %d set compositions from AlecaFrame cachedData", len(loaded)
            )
        except Exception as e:
            log.warning("set composition load failed: %s", e)
    else:
        # Use DB copy. set_name is lost (not stored), so fall back to slug.
        for row in existing:
            set_idx.register(
                SetComposition(
                    set_slug=row["set_slug"],
                    set_name=row["set_slug"],
                    parts=row["parts"],
                )
            )
        log.info("loaded %d set compositions from DB", len(existing))

    # ----- Base-stats reference (WFCD) -----
    # Populate on first boot if empty, then refresh weekly. Background + best
    # effort: WFM/inventory features never wait on it.
    async def _base_stats_loop() -> None:
        try:
            if await repo.count_base_stats() == 0:
                await stats_loader.refresh(repo)
        except Exception as e:
            log.warning("initial base-stats load failed: %s", e)
        while True:
            await asyncio.sleep(7 * 24 * 3600)
            try:
                await stats_loader.refresh(repo)
            except Exception as e:
                log.warning("weekly base-stats refresh failed: %s", e)

    base_stats_task = asyncio.create_task(_base_stats_loop())

    # Expose singletons to wfm/dependencies.
    wfm_deps.wfm_client = wfm_client
    wfm_deps.slug_resolver = slug_resolver
    wfm_deps.set_index = set_idx
    wfm_deps.repo = repo
    wfm_deps.price_store = PriceStore()

    # ----- Real-time subsystem -----
    centrifugo = CentrifugoPublisher(
        api_url=_settings.centrifugo_api,
        api_key=_settings.centrifugo_api_key,
        token_hmac_secret=_settings.centrifugo_token_hmac_secret,
    )

    # Price poller: keeps wfm.orders.{slug} live for any subscribed slug.
    price_poller = PricePoller(
        store=wfm_deps.price_store,
        wfm_client=wfm_client,
        publisher=centrifugo,
        name_resolver=resolver,
        slug_resolver=slug_resolver,
    )
    price_poller_task = asyncio.create_task(price_poller.run())

    # Riven auctions live on the v1 host — separate client, separate poller.
    global auctions_client
    # base_url derives from wfm_base_url by stripping the /v2 tail (or kept
    # as-is if it's already v1). docker-compose / .env normally sets v2.
    v1_base = _settings.wfm_base_url.replace("/v2", "/v1")
    if not v1_base.endswith("/v1"):
        v1_base = v1_base.rstrip("/") + "/v1"
    auctions_client = WFMAuctionClient(
        cache=Cache(client=redis_client, key_prefix="wfm-auc"),
        base_url=v1_base,
        token_provider=_token_provider,
        platform=_settings.wfm_platform,
        language=_settings.wfm_language,
        rate_limit_per_second=_settings.wfm_rate_limit_per_second,
    )
    global auction_poller
    auction_poller = AuctionPoller(
        repo=repo,
        client=auctions_client,
        publisher=centrifugo,
    )
    auction_poller_task = asyncio.create_task(auction_poller.run())

    # ----- Void Fissure subsystem -----
    global telegram_client, fissure_poller
    fissures_deps.fissure_client = FissureClient(
        base_url=_settings.fissure_source_base_url,
        platform=_settings.wfm_platform,
    )
    fissures_deps.node_catalog = NodeCatalog()
    if _settings.tg_api_key:
        telegram_client = TelegramClient(token=_settings.tg_api_key)
    fissure_poller = FissurePoller(
        repo=repo,
        client=fissures_deps.fissure_client,
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
    bus = RabbitMQBus(url=_settings.rabbitmq_url)
    _consumer_subscribed = {"v": False}

    async def _on_live_order(msg: dict) -> None:
        await handle_live_order(
            msg=msg, cache=wfm_cache, publisher=centrifugo, repo=repo
        )

    async def _try_subscribe() -> bool:
        try:
            await bus.connect()
            if not _consumer_subscribed["v"]:
                await bus.subscribe("wfm.live.orders", _on_live_order)
                _consumer_subscribed["v"] = True
            return True
        except Exception as e:
            log.warning("RabbitMQ connect failed: %s", e)
            return False

    # Try a few times at startup
    for _attempt in range(3):
        if await _try_subscribe():
            break
        await asyncio.sleep(5)
    else:
        log.warning(
            "RabbitMQ unreachable after 3 attempts; scheduling background retry every 60s"
        )

        async def _retry_loop() -> None:
            while not _consumer_subscribed["v"]:
                await asyncio.sleep(60)
                if await _try_subscribe():
                    log.info("RabbitMQ connected on retry; consumer live")
                    break

        asyncio.create_task(_retry_loop())

    try:
        await bridge.refresh()
    except BridgeError as e:
        log.warning("startup refresh failed (%s); reading whatever is on disk", e)
        bridge.reload_from_disk(force=True)

    yield

    # Shutdown
    price_poller_task.cancel()
    auction_poller_task.cancel()
    fissure_poller_task.cancel()
    base_stats_task.cancel()
    if telegram_bot_task is not None:
        telegram_bot_task.cancel()
    for task in (
        price_poller_task,
        auction_poller_task,
        fissure_poller_task,
        telegram_bot_task,
        base_stats_task,
    ):
        if task is None:
            continue
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    await wfm_client.aclose()
    if auctions_client is not None:
        await auctions_client.aclose()
    await bus.aclose()
    if repo is not None:
        await repo.close()
    await redis_client.aclose()


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

app.include_router(wfm_router)
app.include_router(me_router)
app.include_router(history_router)
app.include_router(rivens_router)
app.include_router(fissures_router)
app.include_router(reference_router)

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
                    if k not in {"ItemType", "ItemCount", "XP", "ItemId"}
                    and v not in (None, "", [])
                }
                or None,
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
    routes = sorted(
        {r.path for r in app.routes if getattr(r, "include_in_schema", False)}
    )
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


@app.post(
    "/refresh", response_model=RefreshResponse, summary="Force-decrypt the .dat files"
)
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
    slot: Annotated[
        str, Query(description=f"One of: {', '.join(_WEAPON_SLOTS)}")
    ] = "primary",
) -> ItemListResponse:
    key = _WEAPON_SLOTS.get(slot.lower())
    if key is None:
        raise HTTPException(
            status_code=400,
            detail=f"unknown slot '{slot}'; try one of {sorted(_WEAPON_SLOTS)}",
        )
    data = await _safe_get_lastdata(br)
    src = data.get(key) or []
    items = _enrich_list(src, rs)
    return ItemListResponse(total=len(items), returned=len(items), items=items)


@app.get("/mods", response_model=ItemListResponse, summary="Owned mods (RawUpgrades)")
async def mods(
    br: BridgeDep,
    rs: ResolverDep,
    q: Annotated[
        str | None, Query(description="case-insensitive substring of mod name")
    ] = None,
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
        items = [
            it
            for it in items
            if needle in it.name.lower() or needle in it.unique_name.lower()
        ]
    items.sort(key=lambda it: (it.name or "").lower())
    total = len(items)
    items = items[offset : offset + limit]
    return ItemListResponse(total=total, returned=len(items), items=items)


@app.get(
    "/misc", response_model=ItemListResponse, summary="MiscItems (resources + parts)"
)
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
        items = [
            it
            for it in items
            if needle in it.name.lower() or needle in it.unique_name.lower()
        ]
    if sort == "count_desc":
        items.sort(key=lambda it: -(it.count or 0))
    elif sort == "count_asc":
        items.sort(key=lambda it: it.count or 0)
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
        Query(
            description="dotted/numeric path slice, e.g. `Suits.0` or `SeasonChallengeHistory`"
        ),
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
                raise HTTPException(
                    status_code=400, detail=f"bad path at '{seg}': {e}"
                ) from e
        elif isinstance(cur, dict):
            if seg not in cur:
                raise HTTPException(
                    status_code=404,
                    detail=f"no key '{seg}' (available: {sorted(cur)[:20]} ...)",
                )
            cur = cur[seg]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"cannot descend into {type(cur).__name__} at '{seg}'",
            )
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

                    return _dt.datetime.fromtimestamp(
                        int(ms) / 1000, tz=_dt.UTC
                    ).isoformat()
                except Exception:
                    return None
        if isinstance(d, str):
            return d
    return None if v is None else str(v)
