"""Tests for order-book aggregation functions."""

from __future__ import annotations

import json

from alecaframe_api.wfm.prices import compute_stats
from tests import FIXTURES_DIR

FIXTURE = FIXTURES_DIR / "wfm_orders_kronen_prime_blade.json"


def load_orders() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))["data"]


def test_compute_stats_sell_online_only() -> None:
    orders = load_orders()
    stats = compute_stats(orders, side="sell", online_only=True)
    # Online sells in fixture: 35 x1 (ingame), 36 x2 (online), 38 x1 (online) = 4 qty
    assert stats.count_orders == 3
    assert stats.volume_qty == 4
    assert stats.min_price == 35
    assert stats.max_price == 38
    assert stats.median is not None
    # With qty-weighted prices [35,36,36,38]: median is mean of two middle = 36
    assert stats.median == 36


def test_compute_stats_sell_all() -> None:
    orders = load_orders()
    stats = compute_stats(orders, side="sell", online_only=False)
    # 6 sell orders, total qty 9 (1+2+1+1+3+1)
    assert stats.count_orders == 6
    assert stats.volume_qty == 9


def test_compute_stats_buy_online_only() -> None:
    orders = load_orders()
    stats = compute_stats(orders, side="buy", online_only=True)
    # Online buys: 22 x1 (ingame), 25 x1 (online) = 2 orders
    assert stats.count_orders == 2
    assert stats.min_price == 22
    assert stats.max_price == 25


def test_compute_stats_empty_returns_zero_record() -> None:
    stats = compute_stats([], side="sell", online_only=True)
    assert stats.count_orders == 0
    assert stats.volume_qty == 0
    assert stats.min_price is None
    assert stats.median is None
    assert stats.max_price is None


def test_compute_stats_top5_attached() -> None:
    """compute_stats should attach the first 5 prices for context."""
    orders = load_orders()
    stats = compute_stats(orders, side="sell", online_only=False)
    assert len(stats.top5) == 5
    # Sorted ascending by price
    assert stats.top5 == [35, 36, 38, 40, 45]


def test_compute_stats_percentiles_are_monotonic() -> None:
    orders = load_orders()
    stats = compute_stats(orders, side="sell", online_only=False)
    assert (
        stats.p10 is not None
        and stats.p25 is not None
        and stats.p75 is not None
        and stats.p90 is not None
    )
    assert (
        stats.min_price
        <= stats.p10
        <= stats.p25
        <= stats.median
        <= stats.p75
        <= stats.p90
        <= stats.max_price
    )


def test_compute_stats_handles_non_pc_platform_filter() -> None:
    """If the fixture had xbox orders mixed in, the helper should accept a platform filter."""
    orders = load_orders() + [
        {
            "id": "x",
            "type": "sell",
            "platinum": 999,
            "quantity": 1,
            "visible": True,
            "user": {
                "ingameName": "xbox_a",
                "status": "online",
                "reputation": 0,
                "platform": "xbox",
            },
        },
    ]
    stats = compute_stats(orders, side="sell", online_only=False, platform="pc")
    assert stats.max_price == 60  # xbox 999 not counted
