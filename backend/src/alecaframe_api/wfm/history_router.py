"""History + signals endpoints. Read from the Repo singleton injected via Depends."""
from __future__ import annotations

import time
from typing import Annotated, Any, Literal

from fastapi import APIRouter, HTTPException, Query

from alecaframe_api.wfm.dependencies import RepoDep, SlugResolverDep

router = APIRouter()


@router.get("/history/{slug}", summary="Price history snapshots for a slug")
async def history(
    slug: str,
    repo: RepoDep,
    resolver: SlugResolverDep,
    days: Annotated[int, Query(ge=1, le=90)] = 30,
    granularity: Annotated[Literal["hour", "day"], Query()] = "hour",
    online_only: Annotated[bool, Query()] = True,
    side: Annotated[Literal["sell", "buy"], Query()] = "sell",
) -> dict[str, Any]:
    if resolver.by_slug(slug) is None:
        raise HTTPException(404, f"unknown slug '{slug}'")
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
    repo: RepoDep,
    type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    since_hours: Annotated[int, Query(ge=1, le=168)] = 24,
) -> dict[str, Any]:
    since = int(time.time()) - since_hours * 3600
    types = [type] if type else None
    rows = await repo.recent_signals(types=types, limit=limit, since_ts=since)
    return {"total": len(rows), "items": rows}


@router.get("/signals/feed", summary="Infinite-scroll signal stream")
async def signals_feed(
    repo: RepoDep,
    since: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, Any]:
    rows = await repo.recent_signals(since_ts=since, limit=limit)
    return {"total": len(rows), "items": rows, "cursor_ts": rows[0]["ts"] if rows else None}


@router.get("/me/dashboard-actions", summary="Top 10 ranked todo for the user")
async def dashboard_actions(
    repo: RepoDep,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
) -> dict[str, Any]:
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
