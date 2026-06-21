"""Unit tests for the weapon-aware riven scoring engine (pure, no I/O)."""
from __future__ import annotations

from alecaframe_api.wfm.riven_scoring import (
    Profile,
    build_profiles,
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
