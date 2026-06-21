"""Reference (static game data) endpoints: base item/warframe stats."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from alecaframe_api.reference import stats_loader
from alecaframe_api.schemas import ItemBaseStats, ItemBaseStatsListResponse
from alecaframe_api.wfm.dependencies import RepoDep

router = APIRouter(tags=["reference"])


@router.get("/reference/item", response_model=ItemBaseStats, summary="Base stats for one item by uniqueName")
async def reference_item(
    repo: RepoDep,
    unique_name: Annotated[str, Query(description="DE uniqueName, e.g. /Lotus/Powersuits/Ninja/Ninja")],
) -> ItemBaseStats:
    row = await repo.get_base_stats(unique_name)
    if row is None:
        raise HTTPException(404, f"no base stats for {unique_name!r} (try POST /reference/refresh)")
    return ItemBaseStats(**row)


@router.get("/reference/items", response_model=ItemBaseStatsListResponse, summary="Browse base stats by category")
async def reference_items(
    repo: RepoDep,
    category: Annotated[str | None, Query(description="warframe|primary|secondary|melee|mod|arcane|...")] = None,
    limit: Annotated[int, Query(ge=1, le=5000)] = 2000,
) -> ItemBaseStatsListResponse:
    rows = await repo.list_base_stats(category=category, limit=limit)
    return ItemBaseStatsListResponse(total=len(rows), items=[ItemBaseStats(**r) for r in rows])


@router.post("/reference/refresh", summary="Re-pull base stats from WFCD")
async def reference_refresh(repo: RepoDep) -> dict[str, int]:
    upserted = await stats_loader.refresh(repo)
    return {"upserted": upserted}
