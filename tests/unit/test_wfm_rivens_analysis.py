"""Tier classification + outlier detection — pure functions, no I/O."""
from __future__ import annotations

import pytest

from alecaframe_api.wfm.rivens_analysis import (
    Outlier,
    classify_tiers,
    compute_tier_stats,
    detect_outliers,
    summarize_attributes,
    suggest_strategies,
)


def _auc(aid: str, price: int, attrs: list[tuple[str, int, bool]] | None = None) -> dict:
    return {
        "id": aid,
        "buyout_price": price,
        "item": {
            "attributes": [
                {"url_name": n, "value": v, "positive": p} for (n, v, p) in (attrs or [])
            ],
        },
    }


# ----------------------------------------------------------------- tiers


def test_classify_tiers_uses_price_quartiles() -> None:
    aucs = [_auc(f"a{i}", price=i * 10) for i in range(1, 13)]  # 10..120
    tiers = classify_tiers(aucs)
    # Bottom quartile by buyout = low; top = god; middle = mid.
    god_ids = {a["id"] for a in tiers["god"]}
    low_ids = {a["id"] for a in tiers["low"]}
    mid_ids = {a["id"] for a in tiers["mid"]}
    assert "a12" in god_ids  # highest price
    assert "a1" in low_ids   # lowest price
    # Mid and god/low must not overlap
    assert god_ids.isdisjoint(low_ids)
    assert god_ids.isdisjoint(mid_ids)
    # Counts roughly: ~3 god, ~3 low, ~6 mid
    assert len(tiers["god"]) >= 2
    assert len(tiers["low"]) >= 2
    assert len(tiers["mid"]) >= 2


def test_classify_tiers_handles_empty_list() -> None:
    tiers = classify_tiers([])
    assert tiers == {"god": [], "mid": [], "low": []}


def test_classify_tiers_skips_auctions_without_buyout() -> None:
    aucs = [_auc("a1", price=100), {"id": "noprice", "buyout_price": None, "item": {}}]
    tiers = classify_tiers(aucs)
    all_ids = {a["id"] for tier in tiers.values() for a in tier}
    assert "noprice" not in all_ids
    assert "a1" in all_ids


# ----------------------------------------------------------------- stats


def test_compute_tier_stats_basic() -> None:
    aucs = [_auc(f"a{i}", price=p) for i, p in enumerate([100, 200, 300, 400, 500])]
    stats = compute_tier_stats(aucs)
    assert stats.count == 5
    assert stats.min_price == 100
    assert stats.max_price == 500
    assert stats.median == 300
    assert stats.p25 == 200
    assert stats.p75 == 400


def test_compute_tier_stats_empty() -> None:
    s = compute_tier_stats([])
    assert s.count == 0
    assert s.min_price is None
    assert s.median is None


# ----------------------------------------------------------------- outliers


def test_detect_outliers_flags_below_threshold() -> None:
    """Tier median was historically 100; threshold 0.8 → anything < 80 is flagged."""
    aucs = [_auc("normal", price=90), _auc("deal", price=50), _auc("steal", price=10)]
    outliers = detect_outliers(aucs, historical_median=100, threshold=0.8, tier="mid")
    ids = {o.auction_id for o in outliers}
    assert ids == {"deal", "steal"}
    # Discount % matches.
    deal = next(o for o in outliers if o.auction_id == "deal")
    assert deal.discount_pct == 50    # 50/100 = 50%
    assert deal.tier == "mid"


def test_detect_outliers_no_history_returns_empty() -> None:
    aucs = [_auc("any", price=10)]
    assert detect_outliers(aucs, historical_median=None, threshold=0.8, tier="god") == []


def test_detect_outliers_returns_outlier_dataclass() -> None:
    outliers = detect_outliers([_auc("a", 30)], historical_median=100, threshold=0.8, tier="god")
    assert len(outliers) == 1
    assert isinstance(outliers[0], Outlier)


# ----------------------------------------------------------------- summary helpers


def test_summarize_attributes_picks_top_stats_from_god_tier() -> None:
    """The top-stat list reflects what's premium for this weapon, data-driven
    from the god-tier auctions (no curated rules per weapon)."""
    god = [
        _auc("a", 1000, [("critical_damage", 121, True), ("multishot", 78, True)]),
        _auc("b", 900,  [("critical_damage", 110, True), ("damage", 99, True)]),
        _auc("c", 800,  [("critical_damage", 130, True), ("multishot", 80, True)]),
    ]
    summary = summarize_attributes(god, top_n=3)
    names = [s["name"] for s in summary]
    assert "critical_damage" in names
    # CD appears in 3/3, multishot in 2/3, damage in 1/3 — CD should be first.
    assert names[0] == "critical_damage"


# ----------------------------------------------------------------- strategies


def test_suggest_strategies_buy_flip_when_outliers_present() -> None:
    tips = suggest_strategies(
        outliers=[Outlier(auction_id="x", tier="mid", price=50, historical_median=100, discount_pct=50)],
        god_tier_count=5, mid_tier_count=10, low_tier_count=4,
    )
    # At least one tip references the outlier.
    assert any("flip" in t["kind"].lower() or "buy" in t["kind"].lower() for t in tips)


def test_suggest_strategies_kuva_roll_when_low_tier_dominates() -> None:
    """Lots of cheap unrolled mods → kuva-roll strategy is relevant."""
    tips = suggest_strategies(
        outliers=[], god_tier_count=2, mid_tier_count=5, low_tier_count=30,
    )
    assert any("kuva" in t["kind"].lower() or "roll" in t["kind"].lower() for t in tips)


def test_suggest_strategies_includes_base_education() -> None:
    """Always include 2-3 educational tips so a new user has context."""
    tips = suggest_strategies(outliers=[], god_tier_count=0, mid_tier_count=0, low_tier_count=0)
    assert len(tips) >= 1
