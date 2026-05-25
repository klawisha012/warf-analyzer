"""HTTP surface for the rivens analysis subsystem.

GET  /rivens/auctions/{weapon_slug}     — current auctions + tier stats + outliers + strategies
GET  /rivens/watchlist                  — list watched weapons
POST /rivens/watchlist                  — add a weapon
DELETE /rivens/watchlist/{weapon_slug}  — remove
GET  /rivens/history/{weapon_slug}      — snapshot trend for a tier
GET  /rivens/weapons                    — WFM catalogue of riven-capable weapons

Pricing & outliers are computed live on each /auctions request from the
currently-cached WFM payload + the rolling 7-day historical median in
`riven_snapshot`. The poller fills that history; the request itself does
not write to the DB — that keeps the HTTP path read-mostly.
"""
from __future__ import annotations

import datetime as _dt
import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from alecaframe_api.db.repo import Repo
from alecaframe_api.schemas import (
    RivenAuctionRow, RivenAuctionsResponse, RivenHistoryResponse,
    RivenOutlier, RivenSnapshotRow, RivenStrategyTip, RivenTierStats,
    RivenTopAttribute, RivenWatchAddRequest, RivenWatchEntry,
    RivenWatchlistResponse,
)
from alecaframe_api.wfm.auctions_client import WFMAuctionClient, WFMAuctionError
from alecaframe_api.wfm.dependencies import RepoDep
from alecaframe_api.wfm.rivens_analysis import (
    classify_tiers, compute_tier_stats, detect_outliers,
    suggest_strategies, summarize_attributes,
)

log = logging.getLogger("alecaframe.wfm.rivens_router")


router = APIRouter(prefix="/rivens", tags=["rivens"])


def _get_auctions_client() -> WFMAuctionClient:
    from alecaframe_api.main import auctions_client  # noqa: PLC0415
    if auctions_client is None:
        raise RuntimeError("auctions_client not initialised; main.py lifespan must set it")
    return auctions_client


AuctionsClientDep = Annotated[WFMAuctionClient, Depends(_get_auctions_client)]


def _now_iso() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat()


def _to_row(a: dict, tier: str) -> RivenAuctionRow:
    item = a.get("item") or {}
    owner = a.get("owner") or {}
    attrs = []
    for at in item.get("attributes") or []:
        attrs.append({
            "name": at.get("url_name") or at.get("name") or "",
            "value": at.get("value") or 0,
            "positive": bool(at.get("positive")),
        })
    return RivenAuctionRow(
        auction_id=str(a.get("id") or ""),
        weapon_slug=item.get("weapon_url_name") or "",
        buyout_price=_safe_int(a.get("buyout_price")),
        starting_price=_safe_int(a.get("starting_price")),
        top_bid=_safe_int(a.get("top_bid")),
        re_rolls=_safe_int(item.get("re_rolls")),
        mod_rank=_safe_int(item.get("mod_rank")),
        polarity=item.get("polarity"),
        owner_name=owner.get("ingame_name"),
        owner_status=owner.get("status"),
        tier=tier,
        attributes=attrs,
    )


def _safe_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- endpoints


@router.get(
    "/auctions/{weapon_slug}",
    response_model=RivenAuctionsResponse,
    summary="Current riven auctions for a weapon, classified into tiers with outliers + strategies",
)
async def riven_auctions(
    weapon_slug: str,
    client: AuctionsClientDep,
    repo: RepoDep,
    fresh: Annotated[bool, Query(description="Bypass cache")] = False,
    outlier_threshold: Annotated[
        float, Query(ge=0.1, le=1.0, description="Auctions priced < threshold × historical median are flagged"),
    ] = 0.8,
) -> RivenAuctionsResponse:
    try:
        auctions = await client.get_riven_auctions(weapon_slug, fresh=fresh)
    except WFMAuctionError as e:
        raise HTTPException(503, str(e)) from e

    tiers_raw = classify_tiers(auctions)
    tiers_rows: dict[str, list[RivenAuctionRow]] = {
        name: [_to_row(a, name) for a in tiers_raw[name]] for name in ("god", "mid", "low")
    }

    # Stats per tier + overall
    stats_models: list[RivenTierStats] = []
    for name in ("god", "mid", "low"):
        s = compute_tier_stats(tiers_raw[name])
        stats_models.append(RivenTierStats(
            tier=name, count=s.count, min_price=s.min_price,
            p25=s.p25, median=s.median, p75=s.p75, max_price=s.max_price,
        ))
    s_all = compute_tier_stats(auctions)
    stats_models.append(RivenTierStats(
        tier="all", count=s_all.count, min_price=s_all.min_price,
        p25=s_all.p25, median=s_all.median, p75=s_all.p75, max_price=s_all.max_price,
    ))

    # Outliers vs 7-day historical median per tier
    now = int(time.time())
    since = now - 7 * 24 * 3600
    outliers: list[RivenOutlier] = []
    import statistics as _stats
    for name in ("god", "mid", "low"):
        history = await repo.riven_snapshot_history(weapon_slug=weapon_slug, tier=name, since_ts=since)
        medians = [r["median"] for r in history if r["median"] is not None]
        if not medians:
            continue
        hist_median = int(_stats.median(medians))
        for o in detect_outliers(
            tiers_raw[name], historical_median=hist_median,
            threshold=outlier_threshold, tier=name,
        ):
            outliers.append(RivenOutlier(
                auction_id=o.auction_id, tier=o.tier, price=o.price,
                historical_median=o.historical_median, discount_pct=o.discount_pct,
            ))

    # Top stats (data-driven from god tier)
    top_attrs_dicts = summarize_attributes(tiers_raw["god"], top_n=5)
    top_attrs = [RivenTopAttribute(**d) for d in top_attrs_dicts]

    # Strategy tips
    from alecaframe_api.wfm.rivens_analysis import Outlier as _O
    tip_dicts = suggest_strategies(
        outliers=[
            _O(auction_id=o.auction_id, tier=o.tier, price=o.price,
               historical_median=o.historical_median, discount_pct=o.discount_pct)
            for o in outliers
        ],
        god_tier_count=len(tiers_raw["god"]),
        mid_tier_count=len(tiers_raw["mid"]),
        low_tier_count=len(tiers_raw["low"]),
    )
    strategies = [RivenStrategyTip(**t) for t in tip_dicts]

    return RivenAuctionsResponse(
        weapon_slug=weapon_slug, fetched_at=_now_iso(),
        stale=False, tiers=tiers_rows, stats=stats_models,
        outliers=outliers, top_attributes=top_attrs, strategies=strategies,
    )


@router.get(
    "/watchlist", response_model=RivenWatchlistResponse,
    summary="Weapons being polled for riven auctions",
)
async def watchlist_list(repo: RepoDep) -> RivenWatchlistResponse:
    rows = await repo.list_riven_watch()
    items = [RivenWatchEntry(**r) for r in rows]
    return RivenWatchlistResponse(total=len(items), items=items)


@router.post(
    "/watchlist", response_model=RivenWatchlistResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a weapon to the riven watchlist (idempotent)",
)
async def watchlist_add(req: RivenWatchAddRequest, repo: RepoDep) -> RivenWatchlistResponse:
    slug = req.weapon_slug.strip().lower()
    if not slug:
        raise HTTPException(400, "weapon_slug required")
    await repo.add_riven_watch(slug, ts=int(time.time()), notes=req.notes)
    rows = await repo.list_riven_watch()
    items = [RivenWatchEntry(**r) for r in rows]
    return RivenWatchlistResponse(total=len(items), items=items)


@router.delete(
    "/watchlist/{weapon_slug}",
    summary="Remove a weapon from the riven watchlist",
)
async def watchlist_remove(weapon_slug: str, repo: RepoDep) -> dict:
    removed = await repo.remove_riven_watch(weapon_slug)
    if not removed:
        raise HTTPException(404, f"{weapon_slug} not in watchlist")
    return {"removed": weapon_slug}


@router.get(
    "/history/{weapon_slug}", response_model=RivenHistoryResponse,
    summary="Riven snapshot trend for one tier (default 7 days)",
)
async def riven_history(
    weapon_slug: str,
    repo: RepoDep,
    tier: Annotated[str, Query(pattern="^(god|mid|low|all)$")] = "all",
    days: Annotated[int, Query(ge=1, le=90)] = 7,
) -> RivenHistoryResponse:
    since = int(time.time()) - days * 24 * 3600
    rows = await repo.riven_snapshot_history(weapon_slug=weapon_slug, tier=tier, since_ts=since)
    items = [
        RivenSnapshotRow(
            weapon_slug=r["weapon_slug"], ts=r["ts"], tier=r["tier"], count=r["count"],
            min_price=r["min_price"], p25=r["p25"], median=r["median"],
            p75=r["p75"], max_price=r["max_price"],
        )
        for r in rows
    ]
    return RivenHistoryResponse(weapon_slug=weapon_slug, tier=tier, items=items)


@router.post(
    "/poll/{weapon_slug}",
    summary="Trigger an immediate snapshot for one weapon (useful right after add)",
)
async def riven_poll_now(weapon_slug: str) -> dict:
    """Run one AuctionPoller cycle for `weapon_slug` synchronously.

    Without this, a newly-added weapon shows an empty price history until
    the next 60-second poll tick rolls around. Hitting this endpoint right
    after watchlist_add closes that gap.
    """
    from alecaframe_api.main import auction_poller  # noqa: PLC0415
    if auction_poller is None:
        raise HTTPException(503, "auction poller not initialised")
    import time as _t
    await auction_poller._process_weapon(weapon_slug, int(_t.time()))
    return {"polled": weapon_slug}


@router.get(
    "/weapons",
    summary="WFM catalogue of riven-capable weapons (24h cached)",
)
async def riven_weapons(client: AuctionsClientDep) -> dict:
    try:
        items = await client.get_riven_weapons()
    except WFMAuctionError as e:
        raise HTTPException(503, str(e)) from e
    # Project to the minimal shape the UI needs.
    out = [
        {
            "slug": it.get("url_name"),
            "item_name": it.get("item_name"),
            "icon": it.get("icon"),
            "disposition": it.get("riven_disposition"),
            "riven_type": it.get("riven_type"),
            "group": it.get("group"),
        }
        for it in items
    ]
    return {"total": len(out), "items": out}
