"""Tests for the 9 signal functions + runner."""
from __future__ import annotations

import time

import pytest

from alecaframe_api.wfm.signals import (
    Snapshot, SignalContext,
    undervalued_mine, overpriced_mine, competitor_undercut,
    bid_match, floor_drop, momentum_up,
    volume_spike, vault_premium, set_profit_window,
    run_signals,
)


def _snap(*, ts, side="sell", online_only=1, median=None, min_price=None,
          max_price=None, volume=10, top5=None, count=5) -> Snapshot:
    return Snapshot(
        slug="x", ts=ts, side=side, online_only=online_only,
        count_orders=count, min_price=min_price, median=median, max_price=max_price,
        p10=min_price, p25=min_price, p75=max_price, p90=max_price,
        volume_qty=volume, top5=top5 or [],
    )


def test_undervalued_mine_fires_when_my_price_below_median_minus_2sigma() -> None:
    now = int(time.time())
    history = [_snap(ts=now - 86400 * d, median=40) for d in range(1, 8)]
    ctx = SignalContext(
        slug="x", now_ts=now,
        history_7d=history,
        current_sell=_snap(ts=now, median=40, min_price=30, top5=[30, 31, 32, 33, 35]),
        current_buy=_snap(ts=now, side="buy", median=20),
        my_listing_price=20,   # below median 40 - any sigma
    )
    ev = undervalued_mine(ctx)
    assert ev is not None
    assert ev.signal_type == "undervalued_mine"


def test_undervalued_mine_silent_when_competitive() -> None:
    now = int(time.time())
    history = [_snap(ts=now - 86400 * d, median=40) for d in range(1, 8)]
    ctx = SignalContext(
        slug="x", now_ts=now, history_7d=history,
        current_sell=_snap(ts=now, median=40, min_price=38), current_buy=None,
        my_listing_price=39,
    )
    assert undervalued_mine(ctx) is None


def test_competitor_undercut_fires() -> None:
    now = int(time.time())
    ctx = SignalContext(
        slug="x", now_ts=now, history_7d=[],
        current_sell=_snap(ts=now, top5=[30, 32, 34, 35, 38]),
        current_buy=None, my_listing_price=35,
    )
    ev = competitor_undercut(ctx)
    assert ev is not None


def test_bid_match_fires_when_high_buyer() -> None:
    now = int(time.time())
    ctx = SignalContext(
        slug="x", now_ts=now, history_7d=[],
        current_sell=_snap(ts=now, median=30),
        current_buy=_snap(ts=now, side="buy", max_price=40),
        my_listing_price=None,
    )
    ev = bid_match(ctx)
    assert ev is not None and ev.payload["offer_price"] == 40


def test_floor_drop_fires_on_minus_10pct() -> None:
    now = int(time.time())
    earlier = _snap(ts=now - 3600 * 6, min_price=40)
    current = _snap(ts=now, min_price=35)  # -12.5%
    ctx = SignalContext(slug="x", now_ts=now, history_7d=[earlier],
                        current_sell=current, current_buy=None, my_listing_price=None)
    ev = floor_drop(ctx)
    assert ev is not None


def test_momentum_up_fires_on_ema_cross() -> None:
    now = int(time.time())
    history = [
        _snap(ts=now - 86400 + 6*3600*i, median=30 + i * 2)
        for i in range(8)
    ]
    ctx = SignalContext(slug="x", now_ts=now, history_7d=history,
                        current_sell=_snap(ts=now, median=46), current_buy=None,
                        my_listing_price=None)
    ev = momentum_up(ctx)
    assert ev is not None


def test_volume_spike_fires() -> None:
    now = int(time.time())
    history = [_snap(ts=now - 3600 * h, volume=5) for h in range(1, 25)]
    ctx = SignalContext(slug="x", now_ts=now, history_7d=history,
                        current_sell=_snap(ts=now, volume=20), current_buy=None,
                        my_listing_price=None)
    ev = volume_spike(ctx)
    assert ev is not None


def test_run_signals_returns_list_of_events() -> None:
    now = int(time.time())
    ctx = SignalContext(slug="x", now_ts=now, history_7d=[],
                        current_sell=_snap(ts=now, top5=[30, 32, 34, 35, 38]),
                        current_buy=_snap(ts=now, side="buy", max_price=40),
                        my_listing_price=35)
    events = run_signals(ctx)
    types = {e.signal_type for e in events}
    assert "competitor_undercut" in types
    assert "bid_match" in types
