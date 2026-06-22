"""Snapshot writer — turn raw WFM orders into 4 stat rows in the DB."""

from __future__ import annotations

import time
from typing import Any

from alecaframe_api.db.repo import Repo
from alecaframe_api.wfm.prices import compute_stats


async def write_snapshot(
    *,
    repo: Repo,
    slug: str,
    orders: list[dict[str, Any]],
    ts: int | None = None,
    platform: str = "pc",
) -> None:
    """Compute sell+buy × online_only/all stats and persist all 4 rows."""
    ts = ts if ts is not None else int(time.time())
    for side in ("sell", "buy"):
        for online_only in (1, 0):
            s = compute_stats(
                orders, side=side, online_only=bool(online_only), platform=platform
            )
            await repo.insert_snapshot(
                slug=slug,
                ts=ts,
                side=side,
                online_only=online_only,
                count_orders=s.count_orders,
                min_price=s.min_price,
                p10=s.p10,
                p25=s.p25,
                median=s.median,
                p75=s.p75,
                p90=s.p90,
                max_price=s.max_price,
                volume_qty=s.volume_qty,
                top5=s.top5,
            )
