"""FastAPI router for /wfm/* and /me/* endpoints.

All endpoints depend on the WFMClient + SlugResolver + SetIndex singletons
populated by main.py's lifespan. Heavy lifting lives in `wfm/prices.py`,
`wfm/sets.py`, `wfm/slugs.py`; this module is the thin HTTP surface.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query

from alecaframe_api.bridge import AlecaBridge, BridgeError
from alecaframe_api.naming import NameResolver
from alecaframe_api.schemas import (
    ItemUseRef,
    OrderBookResponse,
    OrderBookStatsModel,
    OrderRow,
    PricedItemEntry,
    PricedItemListResponse,
    PricesSnapshotResponse,
    PriceStatsModel,
    RelistNudgeResponse,
    RelistNudgeRow,
    SetProfitResponse,
    SetProfitRowModel,
    WFMItemRef,
    WFMItemsResponse,
    WtbMatchResponse,
    WtbMatchRow,
)
from alecaframe_api.wfm.client import WFMClient, WFMError
from alecaframe_api.wfm.dependencies import (
    PriceStoreDep,
    SetIndexDep,
    SlugResolverDep,
    WFMClientDep,
)
from alecaframe_api.wfm.price_poller import stats_from_orders
from alecaframe_api.wfm.price_store import PriceStats, PriceStore
from alecaframe_api.wfm.prices import compute_stats
from alecaframe_api.wfm.sets import compute_set_profits

log = logging.getLogger("alecaframe.wfm.router")

# Deferred imports to avoid circular dependency with main.py (which will
# import this router in Task 13). The actual singletons are accessed at
# request-time, by which point main.py's lifespan has already run.


def _get_bridge() -> AlecaBridge:
    from alecaframe_api.main import bridge  # noqa: PLC0415

    return bridge


def _get_resolver() -> NameResolver:
    from alecaframe_api.main import resolver  # noqa: PLC0415

    return resolver


def _get_recipe_uses() -> dict[str, list]:
    from alecaframe_api.main import recipe_uses_idx  # noqa: PLC0415

    return recipe_uses_idx


BridgeDep = Annotated[AlecaBridge, Depends(_get_bridge)]
ResolverDep = Annotated[NameResolver, Depends(_get_resolver)]


router = APIRouter()


# ----------------------------------------------------------------- helpers


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _stats_to_model(s) -> OrderBookStatsModel:
    return OrderBookStatsModel(
        side=s.side,
        online_only=s.online_only,
        count_orders=s.count_orders,
        volume_qty=s.volume_qty,
        min_price=s.min_price,
        p10=s.p10,
        p25=s.p25,
        median=s.median,
        p75=s.p75,
        p90=s.p90,
        max_price=s.max_price,
        top5=s.top5,
    )


def _order_to_row(o: dict) -> OrderRow:
    user = o.get("user") or {}
    return OrderRow(
        side=o.get("type", ""),
        price=int(o.get("platinum", 0)),
        qty=int(o.get("quantity", 1) or 1),
        user=str(user.get("ingameName") or ""),
        status=str(user.get("status") or "unknown"),
        reputation=int(user.get("reputation", 0) or 0),
        platform=str(o.get("platform", "pc")),
    )


async def _ensure_slug_catalogue(client, resolver) -> None:
    """Lazy-bootstrap the slug catalogue if it's empty.

    Lifespan tries this once; if it failed (e.g. agent down), the catalogue
    stays empty for the lifetime of the process. This helper retries on the
    first endpoint hit that needs it. Best-effort — if WFM is unreachable too,
    we just leave the resolver empty and the endpoint surfaces the WFM error.
    """
    if resolver.size() > 0:
        return
    try:
        items = await client.get_items()
        resolver.load(items)
    except Exception as e:
        log.warning("lazy slug bootstrap failed: %s", e)


# ----------------------------------------------------------------- /wfm/*


@router.get(
    "/wfm/items",
    response_model=WFMItemsResponse,
    summary="WFM slug catalogue (24h cache)",
)
async def wfm_items(
    client: WFMClientDep, resolver: SlugResolverDep
) -> WFMItemsResponse:
    try:
        items = await client.get_items()
    except WFMError as e:
        raise HTTPException(503, str(e)) from e
    # Side effect: refresh the in-memory resolver so subsequent /wfm/orders/{slug}
    # works even if lifespan bootstrap failed.
    resolver.load(items)
    return WFMItemsResponse(
        total=len(items),
        items=[
            WFMItemRef(
                slug=i.slug,
                item_name=i.item_name,
                thumb_url=i.thumb_url,
                vaulted=i.vaulted,
                wfm_id=i.wfm_id,
            )
            for i in items
        ],
    )


@router.get(
    "/wfm/orders/{slug}",
    response_model=OrderBookResponse,
    summary="Current WFM order book for a slug",
)
async def wfm_orders(
    slug: str,
    client: WFMClientDep,
    resolver: SlugResolverDep,
    include_offline: Annotated[
        bool, Query(description="Include offline orders")
    ] = False,
    fresh: Annotated[bool, Query(description="Bypass cache")] = False,
) -> OrderBookResponse:
    await _ensure_slug_catalogue(client, resolver)
    item = resolver.by_slug(slug)
    if item is None:
        raise HTTPException(404, f"unknown slug '{slug}'")
    try:
        payload = await client.get_orders(slug, fresh=fresh)
    except WFMError as e:
        raise HTTPException(503, str(e)) from e
    orders = payload.get("data") or []
    online_only = not include_offline
    sell = compute_stats(orders, side="sell", online_only=online_only)
    buy = compute_stats(orders, side="buy", online_only=online_only)
    top = sorted(
        (o for o in orders if o.get("type") == "sell"),
        key=lambda o: int(o.get("platinum", 0)),
    )[:10]
    return OrderBookResponse(
        slug=slug,
        item_name=item.item_name,
        fetched_at=_now_iso(),
        stale=bool(payload.get("_stale")),
        sell=_stats_to_model(sell),
        buy=_stats_to_model(buy),
        top_orders=[_order_to_row(o) for o in top],
    )


@router.get(
    "/wfm/profile/{user}",
    summary="WFM profile (reputation, status, etc.)",
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
    orders = payload.get("data") or []
    stats = compute_stats(orders, side="sell", online_only=online_only)
    return stats.min_price


async def _fetch_one_into_store(
    client: WFMClient,
    store: PriceStore,
    slug: str,
    max_rank: int | None = None,
) -> PriceStats | None:
    """Fetch a single slug's orders from WFM and write the projected PriceStats
    into the store. Returns the new record (or None on failure)."""
    import time as _t

    try:
        payload = await client.get_orders(slug)
    except WFMError:
        return None
    orders = payload.get("data") or []
    stats = stats_from_orders(
        slug,
        orders,
        now=_t.time(),
        stale=bool(payload.get("_stale")),
        max_rank=max_rank,
    )
    store.set(stats)
    return stats


async def ensure_prices(
    client: WFMClient,
    store: PriceStore,
    slugs: list[str],
    max_ranks: dict[str, int] | None = None,
    max_sync: int = 10,
) -> dict[str, PriceStats]:
    """Make sure every slug in `slugs` has a PriceStats in the store.

    For slugs already present: returns the cached value (the poller keeps it
    fresh once a frontend subscribes via Centrifugo).
    For slugs absent: parallel-fetches up to `max_sync` items from WFM synchronously, and
    schedules the remainder in the background to prevent request gateway timeouts.
    """
    have = store.bulk_get(slugs)
    missing = [s for s in slugs if s not in have]
    if not missing:
        return have

    mr_dict = max_ranks or {}
    sync_batch = missing[:max_sync]
    async_batch = missing[max_sync:]

    fetched = await asyncio.gather(
        *[_fetch_one_into_store(client, store, s, mr_dict.get(s)) for s in sync_batch],
        return_exceptions=True,
    )

    if async_batch:

        async def _fetch_background():
            for s in async_batch:
                try:
                    await _fetch_one_into_store(client, store, s, mr_dict.get(s))
                except Exception as e:
                    log.warning("background fetch for %s failed: %s", s, e)

        asyncio.create_task(_fetch_background())

    out = dict(have)
    for slug, res in zip(sync_batch, fetched, strict=False):
        if isinstance(res, PriceStats):
            out[slug] = res
    return out


@router.get(
    "/prices",
    response_model=PricesSnapshotResponse,
    summary="Bulk price snapshot for a list of slugs (lazy-populates the store)",
)
async def prices_snapshot(
    client: WFMClientDep,
    store: PriceStoreDep,
    slugs: Annotated[str, Query(description="Comma-separated list of slugs")] = "",
) -> PricesSnapshotResponse:
    slug_list = [s.strip() for s in slugs.split(",") if s.strip()]
    if not slug_list:
        return PricesSnapshotResponse(total=0, prices={})
    found = await ensure_prices(client, store, slug_list)
    out: dict[str, PriceStatsModel] = {
        slug: PriceStatsModel(
            slug=stats.slug,
            sell_min=stats.sell_min,
            sell_median=stats.sell_median,
            sell_spread=stats.sell_spread,
            buy_max=stats.buy_max,
            fetched_at=stats.fetched_at,
            stale=stats.stale,
        )
        for slug, stats in found.items()
    }
    return PricesSnapshotResponse(total=len(out), prices=out)


@router.get("/me/listings", summary="Your active WTS/WTB on WFM (raw v2 payload)")
async def me_listings(client: WFMClientDep) -> dict[str, Any]:
    """Returns the raw `/v2/me/orders` payload (`{apiVersion, data: [...]}`).

    On WFM failure returns a synthetic empty payload with 200 — callers
    should treat absent data as "not yet available" rather than an outage.
    """
    try:
        return await client.get_profile_orders("")  # arg ignored in v2
    except WFMError as e:
        log.warning("me_listings: profile fetch failed: %s; returning empty", e)
        return {"apiVersion": "v2", "data": [], "_stale": True}


@router.get(
    "/me/inventory-priced",
    response_model=PricedItemListResponse,
    summary="Inventory enriched with WFM prices",
)
async def me_inventory_priced(
    br: BridgeDep,
    rs: ResolverDep,
    slug_resolver: SlugResolverDep,
    client: WFMClientDep,
    store: PriceStoreDep,
    slot: Annotated[
        str, Query(description="warframe|primary|secondary|melee|all")
    ] = "all",
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> PricedItemListResponse:
    try:
        data = await br.lastdata()
    except BridgeError as e:
        raise HTTPException(503, f"inventory unavailable: {e}") from e

    section_map = {
        "warframe": "Suits",
        "primary": "LongGuns",
        "secondary": "Pistols",
        "melee": "Melee",
        "all": None,
    }
    if slot not in section_map:
        raise HTTPException(400, f"unknown slot '{slot}'")

    raw_items: list[dict] = []
    if section_map[slot] is None:
        for key in ("Suits", "LongGuns", "Pistols", "Melee"):
            raw_items.extend(data.get(key) or [])
    else:
        raw_items = list(data.get(section_map[slot]) or [])

    recipe_uses = _get_recipe_uses()

    # First pass: resolve slugs for items we're about to ship. Collect uniques
    # so we hit the price store + WFM exactly once per slug instead of once
    # per inventory row.
    rows_to_emit: list[
        tuple[dict, str, str | None]
    ] = []  # (raw_item, unique_name, slug)
    needed_slugs: list[str] = []
    seen_for_fetch: set[str] = set()
    for it in raw_items[:limit]:
        u = it.get("ItemType") or ""
        slug = slug_resolver.resolve_unique_name(u)
        rows_to_emit.append((it, u, slug))
        if slug and slug not in seen_for_fetch:
            seen_for_fetch.add(slug)
            needed_slugs.append(slug)

    prices = await ensure_prices(client, store, needed_slugs)

    enriched: list[PricedItemEntry] = []
    for it, u, slug in rows_to_emit:
        name = (rs.lookup(u) or {}).get("name") or rs.resolve(u)
        stats = prices.get(slug) if slug else None
        ref = slug_resolver.by_slug(slug) if slug else None
        vaulted = ref.vaulted if ref else None
        sell_median = stats.sell_median if stats else None
        used_in = [
            ItemUseRef(
                name=use.result_name,
                unique_name=use.result_unique_name,
                count=use.count_required,
            )
            for use in recipe_uses.get(u, [])
        ]
        sell_min = stats.sell_min if stats else None
        enriched.append(
            PricedItemEntry(
                unique_name=u,
                name=name,
                slug=slug,
                image_name=(rs.lookup(u) or {}).get("image"),
                count=it.get("ItemCount"),
                vaulted=vaulted,
                sell_min=sell_min,
                sell_median=sell_median,
                sell_spread=stats.sell_spread if stats else None,
                buy_max=stats.buy_max if stats else None,
                estimated_value=(sell_min * (it.get("ItemCount") or 1))
                if sell_min
                else None,
                stale=bool(stats.stale) if stats else False,
                used_in=used_in,
            )
        )

    return PricedItemListResponse(
        total=len(enriched), returned=len(enriched), items=enriched
    )


@router.get(
    "/me/prime-parts-priced",
    response_model=PricedItemListResponse,
    summary="Your prime parts/BPs enriched with WFM floor/median prices",
)
async def me_prime_parts_priced(
    br: BridgeDep,
    rs: ResolverDep,
    slug_resolver: SlugResolverDep,
    client: WFMClientDep,
    store: PriceStoreDep,
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

    eligible = [(u, count) for u, count in agg.items() if count >= min_count]
    slugs_for: dict[str, str | None] = {
        u: slug_resolver.resolve_unique_name(u) for u, _ in eligible
    }
    needed = [s for s in slugs_for.values() if s]
    prices = await ensure_prices(client, store, needed)

    rows: list[PricedItemEntry] = []
    for u, count in eligible:
        slug = slugs_for[u]
        name = (rs.lookup(u) or {}).get("name") or rs.resolve(u)
        stats = prices.get(slug) if slug else None
        ref = slug_resolver.by_slug(slug) if slug else None
        vaulted = ref.vaulted if ref else None
        sell_min = stats.sell_min if stats else None
        rows.append(
            PricedItemEntry(
                unique_name=u,
                name=name,
                slug=slug,
                count=count,
                vaulted=vaulted,
                image_name=(rs.lookup(u) or {}).get("image"),
                sell_min=sell_min,
                sell_median=stats.sell_median if stats else None,
                sell_spread=stats.sell_spread if stats else None,
                buy_max=stats.buy_max if stats else None,
                estimated_value=(sell_min * count) if sell_min else None,
                stale=bool(stats.stale) if stats else False,
            )
        )

    rows.sort(key=lambda r: -(r.estimated_value or 0))
    return PricedItemListResponse(total=len(rows), returned=len(rows), items=rows)


@router.get(
    "/me/sets-profit",
    response_model=SetProfitResponse,
    summary="Buildable set profit calculator (parts you own + cost to complete)",
)
async def me_sets_profit(
    br: BridgeDep,
    slug_resolver: SlugResolverDep,
    set_index: SetIndexDep,
    client: WFMClientDep,
    store: PriceStoreDep,
    min_margin: Annotated[int, Query(ge=0)] = 0,
    include_unowned: Annotated[
        bool,
        Query(
            description="Include sets where you own none of the parts (slower; default off)"
        ),
    ] = False,
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
                inv_by_slug[slug] = inv_by_slug.get(slug, 0) + int(
                    it.get("ItemCount", 1) or 0
                )

    # Default: only sets where you own ≥1 part. Drops the fetch list from
    # ~80 sets × 4 parts to whatever the user has, cuts cold-cache wall
    # time on a Dashboard load from ~30-90s to single-digit seconds.
    # Pass include_unowned=true to compute the full opportunity surface.
    relevant_sets = [
        comp
        for comp in set_index.all_sets()
        if include_unowned or any(p in inv_by_slug for p in comp.parts)
    ]

    # Pull floors from the shared PriceStore. Lazy-populate any missing slugs
    # in parallel — once populated, subsequent calls (and other pages) get the
    # same cached value, and the poller refreshes them while the UI is open.
    needed: set[str] = set()
    for comp in relevant_sets:
        needed.update(comp.parts.keys())
        needed.add(comp.set_slug)
    needed_list = list(needed)
    price_map = await ensure_prices(client, store, needed_list)
    floors: dict[str, int | None] = {
        s: (price_map[s].sell_min if s in price_map else None) for s in needed_list
    }

    # Build a reduced SetIndex containing only `relevant_sets` so
    # compute_set_profits doesn't try to scan beyond what we fetched.
    from alecaframe_api.wfm.sets import SetIndex as _SetIndex

    filtered_index = _SetIndex()
    for comp in relevant_sets:
        filtered_index.register(comp)
    part_floors = {
        s: v
        for s, v in floors.items()
        if s in {p for c in relevant_sets for p in c.parts}
    }
    set_floors = {c.set_slug: floors.get(c.set_slug) for c in relevant_sets}

    rows = compute_set_profits(
        index=filtered_index,
        inventory=inv_by_slug,
        part_floor_prices=part_floors,
        set_prices=set_floors,
        min_margin=min_margin,
    )
    return SetProfitResponse(
        total=len(rows),
        returned=len(rows),
        items=[SetProfitRowModel(**r.__dict__) for r in rows],
    )


@router.get(
    "/me/wtb-matches",
    response_model=WtbMatchResponse,
    summary="WTB orders for items you currently own",
)
async def me_wtb_matches(
    br: BridgeDep,
    slug_resolver: SlugResolverDep,
    client: WFMClientDep,
    min_offer: Annotated[int, Query(ge=1)] = 10,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=500,
            description="Cap on inventory slugs to scan (highest qty first)",
        ),
    ] = 50,
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
                inv_by_slug[slug] = inv_by_slug.get(slug, 0) + int(
                    it.get("ItemCount", 1) or 0
                )

    # Cap the scan to top-`limit` slugs by quantity owned. A player with 300+
    # MiscItems would otherwise pay 300 × 200ms per /me/wtb-matches call —
    # most of those are low-count fragments unlikely to surface a buyer
    # offer worth showing on the dashboard.
    top_slugs = sorted(inv_by_slug.items(), key=lambda kv: -kv[1])[:limit]
    scan_slugs = dict(top_slugs)

    # Parallel fetch — AsyncLimiter handles pacing inside WFMClient.
    async def _fetch(slug: str) -> tuple[str, list[dict] | None]:
        try:
            payload = await client.get_orders(slug)
        except WFMError:
            return slug, None
        return slug, payload.get("data") or []

    slug_payloads = await asyncio.gather(*[_fetch(s) for s in scan_slugs.keys()])

    matches: list[WtbMatchRow] = []
    for slug, orders in slug_payloads:
        if orders is None:
            continue
        qty = scan_slugs[slug]
        ref = slug_resolver.by_slug(slug)
        for o in orders:
            user = o.get("user") or {}
            if o.get("type") != "buy" or user.get("platform") != "pc":
                continue
            status = user.get("status")
            if status not in {"ingame", "online"}:
                continue
            price = int(o.get("platinum", 0))
            if price < min_offer:
                continue
            matches.append(
                WtbMatchRow(
                    slug=slug,
                    item_name=(ref.item_name if ref else slug),
                    your_qty=qty,
                    buyer=str(user.get("ingameName") or ""),
                    buyer_status=str(status),
                    buyer_reputation=int(user.get("reputation", 0) or 0),
                    offer_price=price,
                )
            )

    matches.sort(key=lambda m: (-m.offer_price, m.slug))
    return WtbMatchResponse(total=len(matches), items=matches)


@router.get(
    "/me/relist-nudges",
    response_model=RelistNudgeResponse,
    summary="Listings where you've fallen out of top-5 or undercut by median",
)
async def me_relist_nudges(
    client: WFMClientDep,
    br: BridgeDep,
    slug_resolver: SlugResolverDep,
) -> RelistNudgeResponse:
    """Suggest price adjustments for your live WFM sell listings.

    v2 changes vs v1:
    - Profile call moved to `/v2/me/orders` (auth required, no username arg).
    - Each order carries `itemId` (catalogue id) not `item.url_name` — we
      reverse-resolve via SlugResolver.by_wfm_id.
    - Response is shaped `{data: [order...]}` not `{payload: {sell_orders: [...]}}`.

    On any WFM failure (decrypt-agent offline, JWT not minted yet, WFM 5xx)
    we return an empty list with 200 instead of 503 — the UI shows the
    "All competitive" empty state, which is far less alarming than a red
    503 toast on a Dashboard reload.
    """
    try:
        profile = await client.get_profile_orders("")  # arg ignored in v2
    except WFMError as e:
        log.warning("me_relist_nudges: profile fetch failed: %s; returning empty", e)
        return RelistNudgeResponse(total=0, items=[])

    raw_orders = profile.get("data") or []
    # Only my SELL listings that are currently visible to other players.
    my_sells: list[tuple[str, int]] = []  # (slug, my_price)
    for mo in raw_orders:
        if mo.get("type") != "sell" or mo.get("visible") is False:
            continue
        item_id = mo.get("itemId") or ""
        my_price = int(mo.get("platinum", 0) or 0)
        if not item_id or not my_price:
            continue
        ref = slug_resolver.by_wfm_id(item_id)
        if not ref:
            continue  # catalogue not loaded or unknown id
        my_sells.append((ref.slug, my_price))

    if not my_sells:
        return RelistNudgeResponse(total=0, items=[])

    # Parallel-fetch order books for each slug to compute median + top5.
    async def _book(slug: str) -> tuple[str, list[dict] | None]:
        try:
            payload = await client.get_orders(slug)
        except WFMError:
            return slug, None
        return slug, payload.get("data") or []

    books = dict(await asyncio.gather(*[_book(s) for s, _ in my_sells]))

    nudges: list[RelistNudgeRow] = []
    for slug, my_price in my_sells:
        orders = books.get(slug)
        if orders is None:
            continue
        sell = compute_stats(orders, side="sell", online_only=True)
        top5 = sell.top5 or []
        suggestion = ""
        if sell.median is not None and my_price > sell.median + 5:
            suggestion = f"lower to ~{sell.median}"
        elif top5 and my_price > top5[0]:
            suggestion = f"undercut top by 1 -> {top5[0] - 1}"
        else:
            continue  # already competitive — skip
        ref = slug_resolver.by_slug(slug)
        nudges.append(
            RelistNudgeRow(
                slug=slug,
                item_name=ref.item_name if ref else slug,
                your_price=my_price,
                median=sell.median,
                top5=top5,
                suggestion=suggestion,
            )
        )

    nudges.sort(key=lambda n: -n.your_price)
    return RelistNudgeResponse(total=len(nudges), items=nudges)


@router.get(
    "/me/mods-priced",
    response_model=PricedItemListResponse,
    summary="Your mods enriched with WFM floor/median prices",
)
async def me_mods_priced(
    br: BridgeDep,
    rs: ResolverDep,
    slug_resolver: SlugResolverDep,
    client: WFMClientDep,
    store: PriceStoreDep,
    min_count: Annotated[int, Query(ge=1)] = 1,
) -> PricedItemListResponse:
    try:
        data = await br.lastdata()
    except BridgeError as e:
        raise HTTPException(503, f"inventory unavailable: {e}") from e

    # Extract mods from RawUpgrades
    raw_mods = data.get("RawUpgrades") or []
    enriched = rs.enrich(raw_mods)

    # Filter to only mods
    mods_only = [it for it in enriched if it.get("category") == "mod"]

    # Aggregate by uniqueName
    agg: dict[str, tuple[str, int]] = {}
    for it in mods_only:
        u = it.get("ItemType") or it.get("uniqueName") or ""
        name = it.get("name") or ""
        qty = int(it.get("ItemCount", 1) or 1)
        if u:
            prev_name, prev_qty = agg.get(u, (name, 0))
            agg[u] = (name or prev_name, prev_qty + qty)

    eligible = [(u, name, qty) for u, (name, qty) in agg.items() if qty >= min_count]
    slugs_for: dict[str, str | None] = {
        u: slug_resolver.resolve_unique_name(u, name) for u, name, _ in eligible
    }
    needed = [s for s in slugs_for.values() if s]

    # Resolve max rank for each slug to pass to ensure_prices
    slug_max_ranks: dict[str, int] = {}
    for u, _name, _count in eligible:
        slug = slugs_for[u]
        if not slug:
            continue
        meta = rs.lookup(u) or {}
        fusion_limit = meta.get("fusion_limit")
        level_stats = meta.get("level_stats")
        max_rank = 0
        if fusion_limit is not None:
            max_rank = int(fusion_limit)
        elif level_stats:
            max_rank = len(level_stats) - 1
        slug_max_ranks[slug] = max_rank

    # Use the highly optimized batch-caching pricing loader!
    price_map = await ensure_prices(client, store, needed, max_ranks=slug_max_ranks)

    rows: list[PricedItemEntry] = []
    for u, name, count in eligible:
        slug = slugs_for[u]
        stats = price_map.get(slug) if slug else None
        ref = slug_resolver.by_slug(slug) if slug else None
        vaulted = ref.vaulted if ref else None

        sell_min = stats.sell_min if stats else None
        sell_median = stats.sell_median if stats else None
        sell_spread = stats.sell_spread if stats else None
        buy_max = stats.buy_max if stats else None
        sell_min_max_rank = stats.sell_min_max_rank if stats else None
        buy_max_max_rank = stats.buy_max_max_rank if stats else None
        max_rank = slug_max_ranks.get(slug, 0) if slug else 0

        rows.append(
            PricedItemEntry(
                unique_name=u,
                name=name,
                slug=slug,
                count=count,
                vaulted=vaulted,
                image_name=(rs.lookup(u) or {}).get("image"),
                sell_min=sell_min,
                sell_median=sell_median,
                sell_spread=sell_spread,
                buy_max=buy_max,
                sell_min_max_rank=sell_min_max_rank,
                buy_max_max_rank=buy_max_max_rank,
                max_rank=max_rank,
                estimated_value=(sell_min * count) if sell_min else None,
                stale=stats.stale if stats else False,
            )
        )

    rows.sort(key=lambda r: -(r.estimated_value or 0))
    return PricedItemListResponse(total=len(rows), returned=len(rows), items=rows)


@router.get(
    "/me/arcanes-priced",
    response_model=PricedItemListResponse,
    summary="Your arcanes enriched with WFM floor/median prices",
)
async def me_arcanes_priced(
    br: BridgeDep,
    rs: ResolverDep,
    slug_resolver: SlugResolverDep,
    client: WFMClientDep,
    store: PriceStoreDep,
    min_count: Annotated[int, Query(ge=1)] = 1,
) -> PricedItemListResponse:
    try:
        data = await br.lastdata()
    except BridgeError as e:
        raise HTTPException(503, f"inventory unavailable: {e}") from e

    # Extract arcanes from RawUpgrades and MiscItems
    enriched_upgrades = rs.enrich(data.get("RawUpgrades") or [])
    enriched_misc = rs.enrich(data.get("MiscItems") or [])

    # Filter to only arcanes
    arcanes_only = [
        it for it in enriched_upgrades + enriched_misc if it.get("category") == "arcane"
    ]

    # Aggregate by uniqueName
    agg: dict[str, tuple[str, int]] = {}
    for it in arcanes_only:
        u = it.get("ItemType") or it.get("uniqueName") or ""
        name = it.get("name") or ""
        qty = int(it.get("ItemCount", 1) or 1)
        if u:
            prev_name, prev_qty = agg.get(u, (name, 0))
            agg[u] = (name or prev_name, prev_qty + qty)

    eligible = [(u, name, qty) for u, (name, qty) in agg.items() if qty >= min_count]
    slugs_for: dict[str, str | None] = {
        u: slug_resolver.resolve_unique_name(u, name) for u, name, _ in eligible
    }
    needed = [s for s in slugs_for.values() if s]

    # Resolve max rank for each slug to pass to ensure_prices
    slug_max_ranks: dict[str, int] = {}
    for u, _name, _count in eligible:
        slug = slugs_for[u]
        if not slug:
            continue
        meta = rs.lookup(u) or {}
        fusion_limit = meta.get("fusion_limit")
        level_stats = meta.get("level_stats")
        max_rank = 0
        if fusion_limit is not None:
            max_rank = int(fusion_limit)
        elif level_stats:
            max_rank = len(level_stats) - 1
        slug_max_ranks[slug] = max_rank

    # Use the highly optimized batch-caching pricing loader!
    price_map = await ensure_prices(client, store, needed, max_ranks=slug_max_ranks)

    rows: list[PricedItemEntry] = []
    for u, name, count in eligible:
        slug = slugs_for[u]
        stats = price_map.get(slug) if slug else None
        ref = slug_resolver.by_slug(slug) if slug else None
        vaulted = ref.vaulted if ref else None

        sell_min = stats.sell_min if stats else None
        sell_median = stats.sell_median if stats else None
        sell_spread = stats.sell_spread if stats else None
        buy_max = stats.buy_max if stats else None
        sell_min_max_rank = stats.sell_min_max_rank if stats else None
        buy_max_max_rank = stats.buy_max_max_rank if stats else None
        max_rank = slug_max_ranks.get(slug, 0) if slug else 0

        rows.append(
            PricedItemEntry(
                unique_name=u,
                name=name,
                slug=slug,
                count=count,
                vaulted=vaulted,
                image_name=(rs.lookup(u) or {}).get("image"),
                sell_min=sell_min,
                sell_median=sell_median,
                sell_spread=sell_spread,
                buy_max=buy_max,
                sell_min_max_rank=sell_min_max_rank,
                buy_max_max_rank=buy_max_max_rank,
                max_rank=max_rank,
                estimated_value=(sell_min * count) if sell_min else None,
                stale=stats.stale if stats else False,
            )
        )

    rows.sort(key=lambda r: -(r.estimated_value or 0))
    return PricedItemListResponse(total=len(rows), returned=len(rows), items=rows)
