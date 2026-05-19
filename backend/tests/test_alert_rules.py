"""Unit tests for ``alert_rules.riven_alert_check`` covering all four branches.

Each test builds the minimum auction dict needed to trigger one branch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.alert_rules import (
    GOOD_STATS,
    are_stats_good,
    minutes_since_updated,
    riven_alert_check,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _iso_now(minutes_offset: int = 0) -> str:
    """ISO-8601 UTC timestamp ``minutes_offset`` minutes in the past."""
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_offset)).isoformat()


def _make_attr(url_name: str, positive: bool, value: float = 100.0) -> dict[str, Any]:
    return {"url_name": url_name, "positive": positive, "value": value}


def _base_auction(
    *,
    buyout: int,
    weapon: str,
    attributes: list[dict[str, Any]],
    re_rolls: int = 0,
    minutes_ago: int = 1,
    owner_name: str = "buyer1",
) -> dict[str, Any]:
    return {
        "id": "auc-" + weapon + "-" + str(buyout),
        "buyout_price": buyout,
        "updated": _iso_now(minutes_ago),
        "owner": {"ingame_name": owner_name, "status": "ingame"},
        "item": {
            "type": "riven",
            "weapon_url_name": weapon,
            "re_rolls": re_rolls,
            "attributes": attributes,
            "name": "Rivenmod",
        },
    }


GOOD_WEAPONS_FIXTURE: dict[str, int] = {"torid": 350, "ogris": 30, "okina": 50}


# ---------------------------------------------------------------------------
# Branch: "good stats"
# ---------------------------------------------------------------------------


def test_good_stats_branch_three_positives_plus_safe_negative() -> None:
    attrs = [
        _make_attr(GOOD_STATS[0], True, 150.0),
        _make_attr(GOOD_STATS[1], True, 180.0),
        _make_attr(GOOD_STATS[2], True, 120.0),
        _make_attr("zoom", False, -30.0),  # GOOD_NEGATIVES
    ]
    auction = _base_auction(
        buyout=300,
        weapon="torid",  # in SYNERGIES, so >500 guard wouldn't even apply
        attributes=attrs,
    )
    assert are_stats_good(auction) is True
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "good stats"


# ---------------------------------------------------------------------------
# Branch: "endo"
# ---------------------------------------------------------------------------


def test_endo_branch_high_rerolls_low_buyout() -> None:
    # Not good_stats (negative isn't in GOOD_NEGATIVES → are_stats_good=False),
    # not pod_roll branch by re_rolls condition, but re_rolls/buyout > 3 and
    # re_rolls > 50. Weapon must be in good_weapons under the threshold-gate.
    attrs = [
        _make_attr(GOOD_STATS[0], True),
        _make_attr(GOOD_STATS[1], True),
        _make_attr(GOOD_STATS[2], True),
        _make_attr("damage_vs_grineer", False),  # NOT in GOOD_NEGATIVES
    ]
    auction = _base_auction(
        buyout=20,
        weapon="ogris",  # threshold 30 in fixture
        attributes=attrs,
        re_rolls=100,  # 100/20 = 5 > 3, and 100 > 50
        minutes_ago=1,
    )
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "endo"


def test_endo_rejected_when_weapon_not_in_good_weapons() -> None:
    attrs = [
        _make_attr(GOOD_STATS[0], True),
        _make_attr(GOOD_STATS[1], True),
        _make_attr(GOOD_STATS[2], True),
        _make_attr("damage_vs_grineer", False),
    ]
    auction = _base_auction(
        buyout=20,
        weapon="unlisted_weapon",
        attributes=attrs,
        re_rolls=100,
        minutes_ago=1,
    )
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "none"


def test_good_stats_rejected_when_buyout_above_threshold() -> None:
    # Mirrors the real-world scenario the user flagged: torid with great stats
    # at 35000p is well above the 350p threshold and must be filtered out.
    attrs = [
        _make_attr(GOOD_STATS[0], True, 150.0),
        _make_attr(GOOD_STATS[1], True, 180.0),
        _make_attr(GOOD_STATS[2], True, 120.0),
        _make_attr("zoom", False, -30.0),
    ]
    auction = _base_auction(
        buyout=35000,
        weapon="torid",
        attributes=attrs,
    )
    assert are_stats_good(auction) is True
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "none"


def test_good_stats_rejected_when_weapon_not_in_good_weapons() -> None:
    attrs = [
        _make_attr(GOOD_STATS[0], True, 150.0),
        _make_attr(GOOD_STATS[1], True, 180.0),
        _make_attr(GOOD_STATS[2], True, 120.0),
        _make_attr("zoom", False, -30.0),
    ]
    auction = _base_auction(
        buyout=100,
        weapon="dual_toxocyst",  # in SYNERGIES but NOT in fixture good_weapons
        attributes=attrs,
    )
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "none"


# ---------------------------------------------------------------------------
# Branch: "pod roll"
# ---------------------------------------------------------------------------


def test_pod_roll_branch_listed_weapon_under_threshold() -> None:
    # Not good_stats (only 3 attrs → fails len >= 4 check),
    # not endo (re_rolls=0), but weapon is in good_weapons and buyout under
    # the threshold.
    attrs = [
        _make_attr("damage", True),
        _make_attr("status_chance", True),
        _make_attr("recoil", False),
    ]
    auction = _base_auction(
        buyout=200,  # under torid's 350 threshold
        weapon="torid",
        attributes=attrs,
        re_rolls=2,
        minutes_ago=1,
    )
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "pod roll"


# ---------------------------------------------------------------------------
# Branch: "none"
# ---------------------------------------------------------------------------


def test_none_branch_stale_and_uninteresting() -> None:
    attrs = [
        _make_attr("damage", True),
        _make_attr("status_chance", True),
        _make_attr("recoil", False),
    ]
    # Stale (>4min), not pod-listed at low price, no endo, not good_stats.
    auction = _base_auction(
        buyout=500,
        weapon="not_a_pod_weapon",
        attributes=attrs,
        re_rolls=1,
        minutes_ago=30,
    )
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "none"


def test_none_branch_zero_buyout() -> None:
    attrs = [
        _make_attr(GOOD_STATS[0], True),
        _make_attr(GOOD_STATS[1], True),
        _make_attr(GOOD_STATS[2], True),
        _make_attr("zoom", False),
    ]
    auction = _base_auction(
        buyout=0,
        weapon="torid",
        attributes=attrs,
    )
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "none"


def test_none_branch_cube_owner_disqualified_from_good_stats() -> None:
    attrs = [
        _make_attr(GOOD_STATS[0], True),
        _make_attr(GOOD_STATS[1], True),
        _make_attr(GOOD_STATS[2], True),
        _make_attr("zoom", False),
    ]
    auction = _base_auction(
        buyout=300,
        weapon="not_synergy_weapon",
        attributes=attrs,
        owner_name="--Cube",
        minutes_ago=1,
    )
    # are_stats_good→False; not pod-listed; re_rolls=0 → endo math fails.
    assert riven_alert_check(auction, GOOD_WEAPONS_FIXTURE) == "none"


# ---------------------------------------------------------------------------
# minutes_since_updated helper
# ---------------------------------------------------------------------------


def test_minutes_since_updated_handles_z_suffix() -> None:
    five_min_ago_z = (
        datetime.now(timezone.utc) - timedelta(minutes=5)
    ).strftime("%Y-%m-%dT%H:%M:%SZ")
    minutes = minutes_since_updated(five_min_ago_z)
    assert 4 <= minutes <= 6


def test_minutes_since_updated_handles_offset_form() -> None:
    minutes = minutes_since_updated(_iso_now(10))
    assert 9 <= minutes <= 11


@pytest.mark.parametrize(
    "weapon",
    ["torid", "dual_toxocyst", "burston", "latron"],
)
def test_good_stats_works_for_each_synergy_weapon(weapon: str) -> None:
    attrs = [
        _make_attr(GOOD_STATS[0], True, 150.0),
        _make_attr(GOOD_STATS[1], True, 180.0),
        _make_attr(GOOD_STATS[2], True, 120.0),
        _make_attr("ammo_maximum", False, -30.0),
    ]
    auction = _base_auction(
        buyout=400,
        weapon=weapon,
        attributes=attrs,
    )
    assert are_stats_good(auction) is True
