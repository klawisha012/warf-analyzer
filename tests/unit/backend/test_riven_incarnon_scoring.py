"""S3b: scoring against the base + Incarnon profile set."""

from __future__ import annotations

from types import SimpleNamespace

from alecaframe_api.reference.incarnon_profiles import incarnon_index
from alecaframe_api.wfm.riven_scoring import build_profiles, score_riven


def _torid_base() -> dict:
    # Base Torid: a status launcher (low crit, high status).
    return {
        "name": "Torid",
        "category": "primary",
        "stats": {
            "crit_chance": 0.15,
            "status_chance": 0.27,
            "type": "Launcher",
            "omega_attenuation": 1.30,
        },
    }


def _attr(name: str, value: float, positive: bool = True) -> dict:
    return {"name": name, "value": value, "positive": positive}


def test_build_profiles_adds_incarnon_when_curated() -> None:
    profiles = build_profiles(_torid_base(), incarnon=incarnon_index()["torid"])
    assert [p.kind for p in profiles] == ["base", "incarnon"]
    base, inc = profiles
    # Base reads status-leaning; Incarnon is the crit form.
    assert inc.critness > base.critness
    # Incarnon inherits the weapon's disposition.
    assert inc.omega_attenuation == base.omega_attenuation == 1.30


def test_build_profiles_base_only_without_incarnon() -> None:
    profiles = build_profiles(_torid_base())
    assert [p.kind for p in profiles] == ["base"]


def test_crit_riven_has_real_delta_base_to_incarnon() -> None:
    # The whole point of Incarnon support: a crit roll is mediocre on the base
    # status form and excellent on the Incarnon crit form.
    profiles = build_profiles(_torid_base(), incarnon=incarnon_index()["torid"])
    crit_riven = [_attr("critical_chance", 180), _attr("critical_damage", 180)]
    res = score_riven(crit_riven, profiles)

    per = {ps.kind: ps for ps in res.per_profile}
    assert per["incarnon"].score > per["base"].score  # real delta
    assert per["incarnon"].grade == "S"
    # Headline defaults to the Incarnon (endgame) profile.
    assert res.headline.kind == "incarnon"


def test_status_riven_prefers_base_on_pure_crit_incarnon() -> None:
    # Mirror direction (profile-dependence both ways): when the Incarnon form is
    # PURE crit (negligible status), a status roll suits the base form better.
    base = {
        "name": "X",
        "category": "primary",
        "stats": {"crit_chance": 0.10, "status_chance": 0.30, "type": "Rifle"},
    }
    pure_crit_inc = SimpleNamespace(
        crit_chance=0.40, status_chance=0.01, crit_damage=3.0, weapon_type="Rifle"
    )
    profiles = build_profiles(base, incarnon=pure_crit_inc)
    status_riven = [_attr("status_chance", 180), _attr("status_duration", 180)]
    per = {ps.kind: ps for ps in score_riven(status_riven, profiles).per_profile}
    assert per["base"].score > per["incarnon"].score


def test_headline_epsilon_prefers_incarnon_when_close() -> None:
    # Even if base edges incarnon by a hair, the Incarnon headline wins within ε.
    base = {
        "name": "X",
        "category": "primary",
        "stats": {"crit_chance": 0.30, "status_chance": 0.30, "type": "Rifle"},
    }
    inc = SimpleNamespace(
        crit_chance=0.29, status_chance=0.29, crit_damage=3.0, weapon_type="Rifle"
    )
    profiles = build_profiles(base, incarnon=inc)
    res = score_riven(
        [_attr("critical_chance", 180), _attr("multishot", 180)], profiles
    )
    assert res.headline.kind == "incarnon"


def test_per_profile_has_both_kinds() -> None:
    profiles = build_profiles(_torid_base(), incarnon=incarnon_index()["torid"])
    res = score_riven([_attr("multishot", 120)], profiles)
    assert {ps.kind for ps in res.per_profile} == {"base", "incarnon"}
