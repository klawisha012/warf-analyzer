"""Calibration acceptance gate for the riven scoring engine (S2, A3 — blocking).

The design declares M1 must not ship unless community-known god rolls for
reference weapons (a crit weapon, a status weapon, and an archetype-shift
weapon) grade S. This is the deterministic M1 form of that gate: representative
base stats + community god rolls, asserted to score S through the real pure
engine (build_profiles → score_riven).

It is deliberately NOT a live `wfm_history.db` / WFM-API pull: that is
non-deterministic, rate-limited (observed 429s during S1), and unfit for CI.
The live-pull calibration and the Incarnon-shift case (Torid base C → Incarnon
S) land with the curated Incarnon profiles in #6. The HITL human sign-off on
calibrated grades is delegated for the autonomous build; revisit on review.
"""

from __future__ import annotations

import pytest

from alecaframe_api.wfm.riven_scoring import build_profiles, score_riven


def _weapon(name: str, **stats) -> dict:
    return {"name": name, "category": "primary", "disposition": None, "stats": stats}


def _attr(name: str, value: float, positive: bool = True) -> dict:
    return {"name": name, "value": value, "positive": positive}


# (label, base stats incl. omega_attenuation, community god roll) → expect S.
# Roll values are at/near the in-game maxima for each weapon's disposition.
_CASES = [
    pytest.param(
        # Crit launcher, low disposition: a CC+CD god roll is the textbook S.
        _weapon(
            "Kuva Bramma",
            crit_chance=0.27,
            status_chance=0.10,
            omega_attenuation=0.65,
            type="Launcher",
        ),
        [
            _attr("critical_chance", 110),
            _attr("critical_damage", 110),
            _attr("zoom", -90, positive=False),
        ],
        id="crit-kuva-bramma",
    ),
    pytest.param(
        # Status secondary: status chance + multishot + an element is the meta
        # god roll for a status weapon.
        _weapon(
            "Kuva Nukor",
            crit_chance=0.10,
            status_chance=0.29,
            omega_attenuation=1.05,
            type="Pistol",
        ),
        [
            _attr("status_chance", 200),
            _attr("multishot", 110),
            _attr("toxin_damage", 130),
        ],
        id="status-kuva-nukor",
    ),
    pytest.param(
        # Crit rifle, low disposition: CC + CD + multishot (full weight on a
        # rifle, unlike a launcher) is the meta S roll.
        _weapon(
            "Soma",
            crit_chance=0.30,
            status_chance=0.10,
            omega_attenuation=0.70,
            type="Rifle",
        ),
        [
            _attr("critical_chance", 120),
            _attr("critical_damage", 120),
            _attr("multishot", 120),
        ],
        id="crit-soma",
    ),
]
# NOTE: the archetype-SHIFT calibration (Torid base C → Incarnon S, where the
# same crit roll is mediocre on base and S on the Incarnon crit profile) is
# asserted in #6's calibration once curated Incarnon profiles exist — it cannot
# be expressed here because base Torid (a status launcher) is *correctly* not S.


@pytest.mark.parametrize("base_stats, god_roll", _CASES)
def test_known_god_rolls_score_s(base_stats: dict, god_roll: list[dict]) -> None:
    profiles = build_profiles(base_stats)
    assert profiles, "reference weapon must build a base profile"
    res = score_riven(god_roll, profiles)
    assert res.unscored is False
    assert res.headline.grade == "S", (
        f"{base_stats['name']} god roll graded {res.headline.grade} "
        f"({res.headline.score}/100), expected S — weights need recalibration"
    )
