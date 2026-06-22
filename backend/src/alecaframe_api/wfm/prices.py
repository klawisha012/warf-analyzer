"""Order-book aggregations.

Takes a raw WFM v2 orders list (list of dicts from
`/v2/orders/item/{slug}` `.data`), filters by side / online / platform, and
computes a typed stats record: min/p10/p25/median/p75/p90/max, order count,
total quantity, top 5 prices.

v2 per-order shape: `{type: "sell"|"buy", platinum: int, quantity: int,
visible: bool, user: {status: "ingame"|"online"|"offline", platform: "pc"|...,
ingameName: str, ...}}`. Note v1's top-level `order_type` and `platform`
moved to `type` and `user.platform`.
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
    mod_rank: int | None = None,
) -> OrderBookStats:
    """Aggregate a raw WFM v2 orders list into a single stats record."""
    filtered: list[dict] = []
    for o in orders:
        if o.get("type") != side:
            continue
        user = o.get("user") or {}
        if user.get("platform") != platform:
            continue
        actual_rank = o.get("rank") if o.get("rank") is not None else o.get("mod_rank")
        if mod_rank is not None and actual_rank != mod_rank:
            continue
        # v2 adds `visible` — invisible orders are paused listings, skip them.
        if o.get("visible") is False:
            continue
        if online_only:
            status = user.get("status")
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
            side=side,
            online_only=online_only,
            count_orders=count_orders,
            volume_qty=volume_qty,
            min_price=None,
            p10=None,
            p25=None,
            median=None,
            p75=None,
            p90=None,
            max_price=None,
            top5=[],
        )

    # top5: unique prices sorted ascending (one entry per order, not per unit)
    unique_prices = sorted({int(o["platinum"]) for o in filtered if "platinum" in o})

    return OrderBookStats(
        side=side,
        online_only=online_only,
        count_orders=count_orders,
        volume_qty=volume_qty,
        min_price=int(weighted_prices[0]),
        p10=_percentile(weighted_prices, 10),
        p25=_percentile(weighted_prices, 25),
        median=int(statistics.median(weighted_prices)),
        p75=_percentile(weighted_prices, 75),
        p90=_percentile(weighted_prices, 90),
        max_price=int(weighted_prices[-1]),
        top5=unique_prices[:5],
    )
