"""Load-time validation of the curated Incarnon profile table (S3a, #4, A8).

A malformed or out-of-range curated value must fail HERE (a red test), never
reach production as a confidently-wrong Incarnon grade.
"""

from __future__ import annotations

import datetime as _dt

import pytest
from pydantic import ValidationError

from alecaframe_api.reference.incarnon_profiles import (
    CURRENT_GAME_VERSION,
    INCARNON_PROFILES,
    KNOWN_INCARNON_WEAPONS,
    IncarnonProfile,
    incarnon_index,
    is_outdated,
)
from alecaframe_api.wfm.riven_scoring import normalize_name


def test_table_loads_and_is_nonempty() -> None:
    # Pydantic validates every entry at import; reaching here means they all pass.
    assert len(INCARNON_PROFILES) >= 10
    assert any(p.weapon_name == "Torid" for p in INCARNON_PROFILES)


def test_every_entry_has_provenance_and_freshness() -> None:
    for p in INCARNON_PROFILES:
        assert p.source_url.startswith("https://")
        assert isinstance(p.entered_date, _dt.date)
        assert p.game_version
        assert p.evolution_build


def test_stats_are_in_fraction_scale() -> None:
    # crit_chance/status_chance are fractions ([0,1]) like item_base_stats, not
    # percents — a 29 here instead of 0.29 would silently wreck critness().
    for p in INCARNON_PROFILES:
        assert 0.0 <= p.crit_chance <= 1.0, p.weapon_name
        assert 0.0 <= p.status_chance <= 1.0, p.weapon_name
        assert p.crit_damage >= 1.0, p.weapon_name


def test_index_keys_are_normalized() -> None:
    idx = incarnon_index()
    assert idx[normalize_name("Torid")].weapon_name == "Torid"
    assert "torid" in idx  # already lowercased/trimmed


def test_curated_weapons_are_in_the_known_roster() -> None:
    # Every curated weapon must be a real Incarnon Genesis weapon.
    for p in INCARNON_PROFILES:
        assert normalize_name(p.weapon_name) in KNOWN_INCARNON_WEAPONS, p.weapon_name


def test_validator_rejects_percent_scale_crit_chance() -> None:
    with pytest.raises(ValidationError):
        IncarnonProfile(
            weapon_name="Bad",
            weapon_type="Rifle",
            crit_chance=29.0,  # percent, not fraction → out of [0,1]
            crit_damage=3.0,
            status_chance=0.3,
            evolution_build="x",
            source_url="https://example.com",
            entered_date=_dt.date(2026, 6, 22),
            game_version="x",
        )


def test_validator_rejects_non_http_source() -> None:
    with pytest.raises(ValidationError):
        IncarnonProfile(
            weapon_name="Bad",
            weapon_type="Rifle",
            crit_chance=0.3,
            crit_damage=3.0,
            status_chance=0.3,
            evolution_build="x",
            source_url="not-a-url",
            entered_date=_dt.date(2026, 6, 22),
            game_version="x",
        )


def test_validator_rejects_unknown_field() -> None:
    # extra="forbid": a typo'd field name is a load error, not a silent drop.
    with pytest.raises(ValidationError):
        IncarnonProfile(
            weapon_name="Bad",
            weapon_type="Rifle",
            crit_chancee=0.3,  # typo
            crit_damage=3.0,
            status_chance=0.3,
            evolution_build="x",
            source_url="https://example.com",
            entered_date=_dt.date(2026, 6, 22),
            game_version="x",
        )


def test_freshness_marks_old_builds_outdated() -> None:
    fresh = incarnon_index()["torid"]
    assert is_outdated(fresh) is False
    stale = fresh.model_copy(update={"game_version": "wiki-2020-01-01"})
    assert is_outdated(stale) is True


def test_curated_entries_are_unverified_pending_hitl() -> None:
    # The #4 HITL gate: machine-curated values await human sign-off. This test
    # documents that state; flip entries to verified_by_human=True as they're
    # checked, and this assertion will guide the remaining work.
    assert all(p.verified_by_human is False for p in INCARNON_PROFILES)
    assert CURRENT_GAME_VERSION  # freshness anchor exists
