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

log = logging.getLogger("alecaframe.wfm.router")

from fastapi import APIRouter, Depends, HTTPException, Query

from alecaframe_api.bridge import AlecaBridge, BridgeError
from alecaframe_api.naming import NameResolver
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


# Deferred imports to avoid circular dependency with main.py (which will
# import this router in Task 13). The actual singletons are accessed at
# request-time, by which point main.py's lifespan has already run.

def _get_bridge() -> AlecaBridge:
    from alecaframe_api.main import bridge  # noqa: PLC0415
    return bridge


def _get_resolver() -> NameResolver:
    from alecaframe_api.main import resolver  # noqa: PLC0415
    return resolver


BridgeDep = Annotated[AlecaBridge, Depends(_get_bridge)]
ResolverDep = Annotated[NameResolver, Depends(_get_resolver)]


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
    "/wfm/items", response_model=WFMItemsResponse,
    summary="WFM slug catalogue (24h cache)",
)
async def wfm_items(client: WFMClientDep, resolver: SlugResolverDep) -> WFMItemsResponse:
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
    orders = payload.get("data") or []
    stats = compute_stats(orders, side="sell", online_only=online_only)
    return stats.min_price


@router.get("/me/listings", summary="Your active WTS/WTB on WFM")
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
                orders = payload.get("data") or []
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

    # Resolve slugs first, then parallel-fetch orders for each known slug.
    eligible = [(u, count) for u, count in agg.items() if count >= min_count]
    slugs_for: dict[str, str | None] = {u: slug_resolver.resolve_unique_name(u) for u, _ in eligible}

    async def _fetch_orders(slug: str | None) -> list[dict] | None:
        if not slug:
            return None
        try:
            payload = await client.get_orders(slug)
            return payload.get("data") or []
        except WFMError:
            return None

    fetch_results = await asyncio.gather(*[_fetch_orders(slugs_for[u]) for u, _ in eligible])

    rows: list[PricedItemEntry] = []
    for (u, count), orders in zip(eligible, fetch_results):
        slug = slugs_for[u]
        name = (rs.lookup(u) or {}).get("name") or rs.resolve(u)
        sell_min, sell_median, sell_spread, buy_max, vaulted = None, None, None, None, None
        if slug:
            ref = slug_resolver.by_slug(slug)
            vaulted = ref.vaulted if ref else None
            if orders is not None:
                sell = compute_stats(orders, side="sell", online_only=True)
                buy = compute_stats(orders, side="buy", online_only=True)
                sell_min, sell_median = sell.min_price, sell.median
                sell_spread = (
                    (sell.max_price - sell.min_price)
                    if sell.min_price is not None and sell.max_price is not None
                    else None
                )
                buy_max = buy.max_price
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

    # Fetch floor for every needed slug + every full-set slug — in parallel.
    # The WFMClient's AsyncLimiter throttles to ~3 req/s; gather just queues
    # them, turning N × 333ms sequential into ceil(N/3) × 333ms wall time.
    needed: set[str] = set()
    for comp in set_index.all_sets():
        needed.update(comp.parts.keys())
        needed.add(comp.set_slug)
    needed_list = list(needed)
    floor_results = await asyncio.gather(
        *[_floor_for(client, s, online_only=True) for s in needed_list],
        return_exceptions=True,
    )
    floors: dict[str, int | None] = {}
    for slug, res in zip(needed_list, floor_results):
        floors[slug] = None if isinstance(res, BaseException) else res

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

    # Parallel fetch — AsyncLimiter handles pacing inside WFMClient.
    async def _fetch(slug: str) -> tuple[str, list[dict] | None]:
        try:
            payload = await client.get_orders(slug)
        except WFMError:
            return slug, None
        return slug, payload.get("data") or []

    slug_payloads = await asyncio.gather(*[_fetch(s) for s in inv_by_slug.keys()])

    matches: list[WtbMatchRow] = []
    for slug, orders in slug_payloads:
        if orders is None:
            continue
        qty = inv_by_slug[slug]
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
            matches.append(WtbMatchRow(
                slug=slug, item_name=(ref.item_name if ref else slug),
                your_qty=qty,
                buyer=str(user.get("ingameName") or ""),
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
        orders = payload.get("data") or []
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
