"""9 signal functions + runner.

Each signal: pure function over (slug, history, current state, optional my_listing).
Returns SignalEvent or None. dedup_key embedded in the event so the DB layer
can drop duplicates.
"""
from __future__ import annotations

import datetime as _dt
import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger("alecaframe.wfm.signals")


@dataclass(frozen=True)
class Snapshot:
    slug: str
    ts: int
    side: str
    online_only: int
    count_orders: int
    min_price: int | None
    p10: int | None
    p25: int | None
    median: int | None
    p75: int | None
    p90: int | None
    max_price: int | None
    volume_qty: int
    top5: list[int]


@dataclass
class SignalContext:
    slug: str
    now_ts: int
    history_7d: list[Snapshot]   # sell-side, online-only, last 7 days, newest first or oldest first — caller's choice
    current_sell: Snapshot | None
    current_buy: Snapshot | None
    my_listing_price: int | None
    # cross-slug helpers — optional, used by vault_premium / set_profit_window
    is_vaulted: bool | None = None
    set_context: dict[str, Any] | None = None   # {set_slug, parts_cost, set_price} when applicable


@dataclass(frozen=True)
class SignalEvent:
    slug: str
    ts: int
    signal_type: str
    payload: dict[str, Any]
    dedup_key: str


def _today_iso(ts: int) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).date().isoformat()


def _hour_iso(ts: int) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).strftime("%Y-%m-%dT%H")


def _week_iso(ts: int) -> str:
    return _dt.datetime.fromtimestamp(ts, tz=_dt.UTC).strftime("%G-W%V")


def _medians(snaps: list[Snapshot]) -> list[int]:
    return [s.median for s in snaps if s.median is not None]


# ----------------------------------------------------------------- signals


def undervalued_mine(ctx: SignalContext) -> SignalEvent | None:
    if ctx.my_listing_price is None:
        return None
    medians = _medians(ctx.history_7d)
    if len(medians) < 3:
        return None
    mu = statistics.mean(medians)
    sigma = statistics.pstdev(medians) if len(medians) > 1 else 0
    threshold = mu - max(2 * sigma, 2)
    if ctx.my_listing_price < threshold:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="undervalued_mine",
            payload={
                "my_price": ctx.my_listing_price,
                "median_7d": int(mu),
                "sigma_7d": round(sigma, 1),
            },
            dedup_key=f"undervalued_mine:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def overpriced_mine(ctx: SignalContext) -> SignalEvent | None:
    if ctx.my_listing_price is None or ctx.current_sell is None or not ctx.current_sell.top5:
        return None
    top5_mean = statistics.mean(ctx.current_sell.top5)
    if ctx.my_listing_price > top5_mean * 1.10:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="overpriced_mine",
            payload={"my_price": ctx.my_listing_price, "top5_mean": int(top5_mean)},
            dedup_key=f"overpriced_mine:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def competitor_undercut(ctx: SignalContext) -> SignalEvent | None:
    if ctx.my_listing_price is None or ctx.current_sell is None or not ctx.current_sell.top5:
        return None
    if ctx.current_sell.top5[0] < ctx.my_listing_price - 1:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="competitor_undercut",
            payload={"my_price": ctx.my_listing_price, "top": ctx.current_sell.top5[0]},
            dedup_key=f"competitor_undercut:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def bid_match(ctx: SignalContext) -> SignalEvent | None:
    if ctx.current_buy is None or ctx.current_buy.max_price is None:
        return None
    floor = ctx.current_sell.min_price if ctx.current_sell else 0
    if floor and ctx.current_buy.max_price >= floor:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="bid_match",
            payload={"offer_price": ctx.current_buy.max_price, "floor": floor},
            dedup_key=f"bid_match:{ctx.slug}:{_today_iso(ctx.now_ts)}:{ctx.current_buy.max_price}",
        )
    if not floor and ctx.current_buy.max_price:
        # No usable sell floor (either no sell side at all OR all sell orders were
        # filtered out leaving min_price=None) but a buyer wants in — interesting.
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="bid_match",
            payload={"offer_price": ctx.current_buy.max_price, "floor": None},
            dedup_key=f"bid_match:{ctx.slug}:{_today_iso(ctx.now_ts)}:{ctx.current_buy.max_price}",
        )
    return None


def floor_drop(ctx: SignalContext) -> SignalEvent | None:
    if ctx.current_sell is None or ctx.current_sell.min_price is None:
        return None
    cutoff = ctx.now_ts - 6 * 3600
    earlier_floors = [
        s.min_price for s in ctx.history_7d
        if s.min_price is not None and s.ts >= cutoff and s.ts < ctx.now_ts
    ]
    if not earlier_floors:
        return None
    baseline = max(earlier_floors)
    drop_pct = (baseline - ctx.current_sell.min_price) / baseline if baseline else 0
    if drop_pct >= 0.10:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="floor_drop",
            payload={"current": ctx.current_sell.min_price, "baseline": baseline,
                     "drop_pct": round(drop_pct * 100, 1)},
            dedup_key=f"floor_drop:{ctx.slug}:{_hour_iso(ctx.now_ts)}",
        )
    return None


def _ema(values: list[float], alpha: float) -> float | None:
    if not values:
        return None
    ema = values[0]
    for v in values[1:]:
        ema = alpha * v + (1 - alpha) * ema
    return ema


def momentum_up(ctx: SignalContext) -> SignalEvent | None:
    medians = _medians(ctx.history_7d)
    if len(medians) < 6:
        return None
    # short EMA = α=0.4 over last 4 points; long EMA = α=0.15 over all
    short = _ema(medians[-4:], 0.4)
    long = _ema(medians, 0.15)
    if short is None or long is None:
        return None
    if short > long * 1.05:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="momentum_up",
            payload={"ema_short": round(short, 1), "ema_long": round(long, 1)},
            dedup_key=f"momentum_up:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def volume_spike(ctx: SignalContext) -> SignalEvent | None:
    if ctx.current_sell is None:
        return None
    cutoff = ctx.now_ts - 86400
    recent = [s.volume_qty for s in ctx.history_7d if s.ts >= cutoff]
    if len(recent) < 5:
        return None
    mean_vol = statistics.mean(recent) or 1
    if ctx.current_sell.volume_qty > 3 * mean_vol:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="volume_spike",
            payload={"current_volume": ctx.current_sell.volume_qty,
                     "mean_24h_volume": round(mean_vol, 1)},
            dedup_key=f"volume_spike:{ctx.slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


def vault_premium(ctx: SignalContext) -> SignalEvent | None:
    if not ctx.is_vaulted or ctx.current_sell is None or ctx.current_sell.median is None:
        return None
    medians = _medians(ctx.history_7d)
    if len(medians) < 5:
        return None
    baseline = statistics.median(medians)
    if ctx.current_sell.median > baseline * 1.5:
        return SignalEvent(
            slug=ctx.slug, ts=ctx.now_ts, signal_type="vault_premium",
            payload={"current_median": ctx.current_sell.median, "baseline": int(baseline)},
            dedup_key=f"vault_premium:{ctx.slug}:{_week_iso(ctx.now_ts)}",
        )
    return None


def set_profit_window(ctx: SignalContext) -> SignalEvent | None:
    if not ctx.set_context:
        return None
    parts_cost = ctx.set_context.get("parts_cost")
    set_price = ctx.set_context.get("set_price")
    set_slug = ctx.set_context.get("set_slug")
    if parts_cost is None or set_price is None or not set_slug:
        return None
    if parts_cost < set_price * 0.85:
        return SignalEvent(
            slug=set_slug, ts=ctx.now_ts, signal_type="set_profit_window",
            payload={"parts_cost": parts_cost, "set_price": set_price,
                     "profit_pct": round((1 - parts_cost / set_price) * 100, 1)},
            dedup_key=f"set_profit_window:{set_slug}:{_today_iso(ctx.now_ts)}",
        )
    return None


# ----------------------------------------------------------------- runner

_ALL_SIGNALS: tuple[Callable[[SignalContext], SignalEvent | None], ...] = (
    undervalued_mine, overpriced_mine, competitor_undercut,
    bid_match, floor_drop, momentum_up,
    volume_spike, vault_premium, set_profit_window,
)


def run_signals(ctx: SignalContext) -> list[SignalEvent]:
    out: list[SignalEvent] = []
    for fn in _ALL_SIGNALS:
        try:
            ev = fn(ctx)
        except Exception as e:
            log.warning("signal %s raised: %s", fn.__name__, e)
            continue
        if ev is not None:
            out.append(ev)
    return out
