"""Unit tests for the weapon-aware riven scoring engine (pure, no I/O)."""
from __future__ import annotations

from alecaframe_api.wfm.riven_scoring import (
    Profile,
    _grade,
    build_profiles,
    classify_market_signal,
    critness,
    is_scoreable_category,
    resolve_weapon,
    score_riven,
    stat_weight,
    statusness,
)


def _weapon_row(name: str, **stats) -> dict:
    return {"name": name, "category": "primary", "disposition": 4, "stats": stats}


def _pos(name: str, value: float = 100.0) -> dict:
    return {"name": name, "value": value, "positive": True}


def _neg(name: str, value: float = -50.0) -> dict:
    return {"name": name, "value": value, "positive": False}


def _profile(critness: float, statusness: float, **stats) -> Profile:
    return Profile(
        kind="base", critness=critness, statusness=statusness,
        stats=stats, omega_attenuation=1.0,
    )


def _row(name: str, **stats) -> dict:
    return {"name": name, "category": "primary", "disposition": None, "stats": stats}


def test_resolve_weapon_matches_by_normalized_display_name() -> None:
    # WFM riven slugs do not map to WFCD uniqueName deterministically
    # (torid -> /Lotus/Weapons/ClanTech/Bio/BioWeapon). The join is by the
    # weapon's display name, normalized (lowercased, trimmed).
    index = {
        "kuva bramma": _row("Kuva Bramma", crit_chance=0.27),
        "torid": _row("Torid", crit_chance=0.15),
    }
    hit = resolve_weapon("Kuva Bramma", index)
    assert hit is not None
    assert hit["name"] == "Kuva Bramma"


def test_resolve_weapon_returns_none_on_miss() -> None:
    assert resolve_weapon("Nonexistent Gun", {"torid": _row("Torid")}) is None


def test_resolve_weapon_applies_override_map() -> None:
    # Overrides bridge genuine display-name mismatches (item_name -> WFCD name).
    index = {"real wfcd name": _row("Real WFCD Name")}
    hit = resolve_weapon(
        "Market Alias", index, overrides={"market alias": "real wfcd name"}
    )
    assert hit is not None
    assert hit["name"] == "Real WFCD Name"


def test_critness_high_for_crit_weapon_low_for_status_weapon() -> None:
    crit = {"crit_chance": 0.5, "status_chance": 0.1}      # e.g. Kuva Bramma-ish
    status = {"crit_chance": 0.1, "status_chance": 0.4}    # e.g. Kuva Nukor-ish
    assert critness(crit) > critness(status)
    assert critness(crit) == 1.0          # clamps at the top of the range


def test_statusness_high_for_status_weapon_low_for_crit_weapon() -> None:
    crit = {"crit_chance": 0.5, "status_chance": 0.1}
    status = {"crit_chance": 0.1, "status_chance": 0.4}
    assert statusness(status) > statusness(crit)
    assert statusness(status) == 1.0


def test_critness_statusness_handle_missing_stats() -> None:
    assert critness({}) == 0.0
    assert statusness({}) == 0.0


def test_stat_weight_archetype_sensitive() -> None:
    crit = _profile(critness=1.0, statusness=0.0)
    status = _profile(critness=0.0, statusness=1.0)
    # CC matters on a crit weapon, barely on a status weapon.
    assert stat_weight("critical_chance", crit) > stat_weight("critical_chance", status)
    # status_chance is the mirror image.
    assert stat_weight("status_chance", status) > stat_weight("status_chance", crit)
    # archetype stat on its weapon outweighs a universal stat.
    assert stat_weight("critical_chance", crit) > stat_weight("damage", crit)


def test_stat_weight_universal_is_archetype_independent() -> None:
    crit = _profile(critness=1.0, statusness=0.0)
    status = _profile(critness=0.0, statusness=1.0)
    # damage/elements are strong on everything → same weight regardless of archetype.
    assert stat_weight("damage", crit) == stat_weight("damage", status)
    assert stat_weight("heat", crit) == stat_weight("damage", crit)
    assert stat_weight("damage", crit) > 0


def test_stat_weight_utility_is_near_zero() -> None:
    crit = _profile(critness=1.0, statusness=0.0)
    assert stat_weight("zoom", crit) == 0.0
    assert stat_weight("ammo_maximum", crit) == 0.0


def test_stat_weight_multishot_lower_on_beam() -> None:
    # multishot scales oddly on beam/AoE weapons → down-weighted there (A7).
    normal = _profile(critness=0.5, statusness=0.5, trigger="Auto", type="Rifle")
    beam = _profile(critness=0.5, statusness=0.5, trigger="Held", type="Rifle")
    launcher = _profile(critness=0.5, statusness=0.5, trigger="Semi", type="Launcher")
    assert stat_weight("multishot", normal) > stat_weight("multishot", beam)
    assert stat_weight("multishot", normal) > stat_weight("multishot", launcher)


def test_build_profiles_base_only_in_m1() -> None:
    profiles = build_profiles(_weapon_row("Kuva Bramma", crit_chance=0.5, omega_attenuation=0.65))
    assert [p.kind for p in profiles] == ["base"]
    assert profiles[0].critness == 1.0


def test_score_riven_cc_riven_scores_high_on_crit_low_on_status() -> None:
    # The headline S1 demo: the same CC+CD riven is great on a crit weapon and
    # poor on a status weapon. This is the bug the redesign exists to fix.
    crit = build_profiles(_weapon_row("Kuva Bramma", crit_chance=0.5, status_chance=0.1, omega_attenuation=0.65))
    status = build_profiles(_weapon_row("Kuva Nukor", crit_chance=0.1, status_chance=0.4, omega_attenuation=1.0))
    cc_riven = [_pos("critical_chance"), _pos("critical_damage")]

    crit_res = score_riven(cc_riven, crit)
    status_res = score_riven(cc_riven, status)

    assert crit_res.unscored is False
    assert crit_res.headline.score > status_res.headline.score
    assert crit_res.headline.grade == "S"
    assert status_res.headline.grade in {"F", "C"}
    assert 0 <= crit_res.headline.score <= 100


def test_score_riven_negative_on_archetype_stat_hurts_more_than_utility() -> None:
    crit = build_profiles(_weapon_row("Dread", crit_chance=0.5, status_chance=0.1, omega_attenuation=1.0))
    good = [_pos("critical_chance"), _pos("critical_damage")]
    with_dead_neg = good + [_neg("zoom")]
    with_fatal_neg = good + [_neg("critical_chance")]
    base = score_riven(good, crit).headline.score
    assert score_riven(with_dead_neg, crit).headline.score == base       # utility neg ~free
    assert score_riven(with_fatal_neg, crit).headline.score < base       # archetype neg hurts


def test_score_riven_unscored_when_no_profile() -> None:
    res = score_riven([_pos("critical_chance")], [])
    assert res.unscored is True
    assert res.headline is None
    assert res.reason == "no_base_profile"


def test_is_scoreable_category_guns_only_in_m1() -> None:
    assert is_scoreable_category("primary") is True
    assert is_scoreable_category("secondary") is True
    assert is_scoreable_category("arch_gun") is True
    assert is_scoreable_category("melee") is False        # M1 = guns only (A6)
    assert is_scoreable_category("arch_melee") is False
    assert is_scoreable_category(None) is False


def test_grade_cutoff_boundaries() -> None:
    assert _grade(85) == "S" and _grade(84) == "A"
    assert _grade(70) == "A" and _grade(69) == "B"
    assert _grade(50) == "B" and _grade(49) == "C"
    assert _grade(30) == "C" and _grade(29) == "F"
    assert _grade(0) == "F"


def test_raw_damage_weapon_can_reach_top_grade() -> None:
    # Regression: a pure raw-damage weapon (critness=statusness=0) must be able
    # to score S on its best universal roll — the old fixed archetype divisor
    # capped the whole class at B.
    raw = build_profiles(_weapon_row("Some Launcher", crit_chance=0.0, status_chance=0.0))
    res = score_riven([_pos("damage"), _pos("multishot")], raw)
    assert res.headline.grade in {"S", "A"}


def test_multishot_scores_lower_on_launcher_than_rifle() -> None:
    rifle = build_profiles(_weapon_row("Rifle", crit_chance=0.0, status_chance=0.0, type="Rifle"))
    launcher = build_profiles(_weapon_row("Launcher", crit_chance=0.0, status_chance=0.0, type="Launcher"))
    riven = [_pos("multishot")]
    assert score_riven(riven, launcher).headline.score < score_riven(riven, rifle).headline.score


def test_all_negative_roll_floors_at_f() -> None:
    crit = build_profiles(_weapon_row("Dread", crit_chance=0.5))
    res = score_riven([_neg("critical_chance")], crit)
    assert res.unscored is False and res.headline.score == 0 and res.headline.grade == "F"


def test_empty_attrs_scores_zero() -> None:
    crit = build_profiles(_weapon_row("Dread", crit_chance=0.5))
    assert score_riven([], crit).headline.score == 0


def test_stat_name_normalization_variants() -> None:
    crit = _profile(critness=1.0, statusness=0.0)
    assert stat_weight("Critical Chance", crit) == stat_weight("critical_chance", crit)
    assert stat_weight("critical-chance", crit) == stat_weight("critical_chance", crit)


def test_faction_and_element_and_base_damage_have_weight() -> None:
    p = _profile(critness=0.0, statusness=0.0)
    assert stat_weight("damage_vs_grineer", p) > 0      # v2-confirmed faction slug
    assert stat_weight("heat_damage", p) > 0            # suffixed element slug
    assert stat_weight("base_damage_/_melee_damage", p) > 0
    assert stat_weight("damage", p) > 0                 # bare form also matches


def test_build_profiles_empty_stats_returns_empty() -> None:
    assert build_profiles({"name": "X", "category": "primary", "stats": {}}) == []


def test_market_signal_steal_when_good_grade_priced_below_median() -> None:
    # A strong roll (S/A) priced under the market median is the actionable buy.
    assert classify_market_signal("S", buyout_price=80, median=120) == "steal"
    assert classify_market_signal("A", buyout_price=119, median=120) == "steal"


def test_market_signal_trap_when_bad_grade_priced_above_median() -> None:
    # Junk (F) priced above the market median is overpriced — warn the buyer.
    assert classify_market_signal("F", buyout_price=200, median=120) == "trap"


def test_market_signal_none_for_fair_or_missing_inputs() -> None:
    assert classify_market_signal("S", buyout_price=120, median=120) is None  # fair (not below)
    assert classify_market_signal("B", buyout_price=10, median=120) is None    # mid grade
    assert classify_market_signal("F", buyout_price=10, median=120) is None    # junk but cheap = fine
    assert classify_market_signal(None, buyout_price=10, median=120) is None   # unscored
    assert classify_market_signal("S", buyout_price=None, median=120) is None  # no price
    assert classify_market_signal("S", buyout_price=10, median=None) is None   # no median
    assert classify_market_signal("S", buyout_price=10, median=0) is None      # zero median guard
