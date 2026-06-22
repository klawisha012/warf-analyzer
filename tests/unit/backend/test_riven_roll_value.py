"""Unit tests for S2 roll-value grading + contextual negative penalty."""
from __future__ import annotations

from alecaframe_api.wfm.riven_scoring import (
    Profile,
    build_profiles,
    grade_roll_value,
    negative_penalty,
    score_riven,
)


def _weapon_row(name: str, **stats) -> dict:
    return {"name": name, "category": "primary", "disposition": 4, "stats": stats}


def _attr(name: str, value: float, positive: bool = True) -> dict:
    return {"name": name, "value": value, "positive": positive}


def _profile(critness: float, statusness: float, **stats) -> Profile:
    return Profile(
        kind="base", critness=critness, statusness=statusness,
        stats=stats, omega_attenuation=1.0,
    )


# --- grade_roll_value: monotonic in value -----------------------------------

def test_higher_roll_value_grades_higher() -> None:
    hi = grade_roll_value("critical_damage", 180, stat_count=2, has_negative=False, disposition=1.0)
    lo = grade_roll_value("critical_damage", 90, stat_count=2, has_negative=False, disposition=1.0)
    assert hi > lo
    assert 0.0 <= lo < hi <= 1.0


def test_roll_value_saturates_at_ceiling() -> None:
    # At/above the nominal ceiling the grade saturates to 1.0 (presence mode).
    assert grade_roll_value("critical_chance", 999, stat_count=2, has_negative=False, disposition=1.0) == 1.0


def test_unknown_stat_gets_full_presence_credit() -> None:
    # Faction damage uses a `multiply` unit we don't normalize against → full credit,
    # never a mis-normalized fraction.
    assert grade_roll_value("damage_vs_grineer", 45, stat_count=2, has_negative=False, disposition=1.0) == 1.0


# --- grade_roll_value: ceiling shifts with roll shape -----------------------

def test_three_positive_roll_has_lower_ceiling_than_two() -> None:
    # 3 positives roll smaller numbers each → a fixed value is a larger fraction
    # of the (lower) 3-pos ceiling.
    two = grade_roll_value("critical_damage", 90, stat_count=2, has_negative=False, disposition=1.0)
    three = grade_roll_value("critical_damage", 90, stat_count=3, has_negative=False, disposition=1.0)
    assert three > two


def test_negative_raises_ceiling() -> None:
    # A curse boosts the positives → higher ceiling → a fixed value is a smaller
    # fraction of it.
    no_neg = grade_roll_value("critical_damage", 90, stat_count=2, has_negative=False, disposition=1.0)
    with_neg = grade_roll_value("critical_damage", 90, stat_count=2, has_negative=True, disposition=1.0)
    assert with_neg < no_neg


def test_low_disposition_grades_a_fixed_value_higher() -> None:
    # Low-dispo weapons roll smaller numbers, so the same +90% is relatively
    # stronger there than on a high-dispo weapon.
    low = grade_roll_value("critical_damage", 90, stat_count=2, has_negative=False, disposition=0.65)
    high = grade_roll_value("critical_damage", 90, stat_count=2, has_negative=False, disposition=1.3)
    assert low > high


# --- score_riven reflects roll value ----------------------------------------

def test_score_riven_180cd_beats_90cd_same_weapon() -> None:
    # The headline S2 acceptance: +180% CD must grade strictly higher than
    # +90% CD on the same weapon, all else equal. Pair CD with a universal stat
    # (multishot) so the roll doesn't saturate the ideal at both CD values —
    # otherwise two archetype stats both clamp to 100 and hide the delta.
    crit = build_profiles(_weapon_row("Dread", crit_chance=0.5, status_chance=0.1))
    strong = score_riven([_attr("critical_damage", 180), _attr("multishot", 180)], crit)
    weak = score_riven([_attr("critical_damage", 90), _attr("multishot", 180)], crit)
    assert strong.headline.score > weak.headline.score


# --- negative_penalty: contextual -------------------------------------------

def test_negative_penalty_zero_for_utility() -> None:
    crit = _profile(critness=1.0, statusness=0.0)
    assert negative_penalty("zoom", crit) == 0.0
    assert negative_penalty("recoil", crit) == 0.0


def test_negative_penalty_full_weight_for_archetype_fatal() -> None:
    crit = _profile(critness=1.0, statusness=0.0)
    # −CC on a crit weapon costs the full archetype weight (fatal); on a status
    # weapon the same curse costs ≈0.
    status = _profile(critness=0.0, statusness=1.0)
    assert negative_penalty("critical_chance", crit) > negative_penalty("critical_chance", status)
    assert negative_penalty("critical_chance", crit) > negative_penalty("zoom", crit)


def test_dead_negative_on_god_roll_barely_dents_grade() -> None:
    crit = build_profiles(_weapon_row("Dread", crit_chance=0.5, status_chance=0.1))
    god = [_attr("critical_chance", 180), _attr("critical_damage", 180)]
    with_zoom = god + [_attr("zoom", -50, positive=False)]
    assert score_riven(god, crit).headline.grade == score_riven(with_zoom, crit).headline.grade


def test_fatal_negative_drops_crit_weapon_to_f() -> None:
    crit = build_profiles(_weapon_row("Dread", crit_chance=0.5, status_chance=0.1))
    # A roll whose only merits are crit, but with a −CC curse, collapses.
    roll = [_attr("critical_damage", 90), _attr("critical_chance", -50, positive=False)]
    assert score_riven(roll, crit).headline.grade == "F"
