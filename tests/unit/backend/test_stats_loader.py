"""Unit tests for the WFCD base-stats normalizers (pure, no network)."""

from __future__ import annotations

from alecaframe_api.reference.stats_loader import (
    WFCD_FILES,
    _norm_frame,
    _norm_weapon,
    build_rows,
)


def test_build_rows_frame_maps_core_fields() -> None:
    items = [
        {
            "name": "Ash",
            "uniqueName": "/Lotus/Powersuits/Ninja/Ninja",
            "masteryReq": 0,
            "health": 455,
            "shield": 270,
            "armor": 105,
            "power": 100,
            "sprintSpeed": 1.15,
            "polarities": ["madurai", "naramon"],
            "abilities": [{"name": "Shuriken"}, {"name": "Smoke Screen"}],
            "isPrime": False,
        }
    ]
    rows = build_rows("warframe", items, _norm_frame)
    assert len(rows) == 1
    r = rows[0]
    assert r["unique_name"] == "/Lotus/Powersuits/Ninja/Ninja"
    assert r["category"] == "warframe"
    assert r["name"] == "Ash"
    assert r["source"] == "wfcd"
    s = r["stats"]
    assert s["health"] == 455
    assert s["armor"] == 105
    assert s["energy"] == 100
    assert s["abilities"] == ["Shuriken", "Smoke Screen"]
    assert s["polarities"] == ["madurai", "naramon"]


def test_build_rows_weapon_maps_and_rounds() -> None:
    items = [
        {
            "name": "Acceltra",
            "uniqueName": "/Lotus/Weapons/Tenno/LongGuns/SapientPrimary/SapientPrimaryWeapon",
            "masteryReq": 8,
            "fireRate": 12.000001,  # WFCD float noise → rounded
            "magazineSize": 48,
            "reloadTime": 2,
            "accuracy": 23.529411,
            "multishot": 1,
            "criticalChance": 0.31999999,
            "criticalMultiplier": 2.8,
            "procChance": 0.060000002,
            "totalDamage": 70,
            "damage": {"impact": 26, "puncture": 35.2, "slash": 8.8, "heat": 0},
            "trigger": "Auto",
            "slot": 0,
            "disposition": 0.7,
        }
    ]
    rows = build_rows("primary", items, _norm_weapon)
    r = rows[0]
    assert r["mastery_req"] == 8
    assert r["disposition"] == 0.7
    s = r["stats"]
    assert s["fire_rate"] == 12.0  # rounded from 12.000001
    assert s["crit_chance"] == 0.32
    assert s["status_chance"] == 0.06
    assert s["magazine"] == 48
    # zero-valued damage components are dropped, real ones kept
    assert s["damage"] == {"impact": 26, "puncture": 35.2, "slash": 8.8}


def test_build_rows_weapon_captures_omega_attenuation_and_type() -> None:
    # WFCD ships the riven-disposition *multiplier* as `omegaAttenuation`
    # (Torid=1.3), while `disposition` is the cosmetic 1-5 dot-rank. The scorer
    # needs the multiplier; `type` is needed to down-weight multishot on
    # beam/AoE weapons (e.g. Launcher).
    items = [
        {
            "name": "Torid",
            "uniqueName": "/Lotus/Weapons/ClanTech/Bio/BioWeapon",
            "criticalChance": 0.15,
            "disposition": 4,
            "omegaAttenuation": 1.2999999,  # float noise → rounded
            "type": "Launcher",
            "trigger": "Semi",
        }
    ]
    s = build_rows("primary", items, _norm_weapon)[0]["stats"]
    assert s["omega_attenuation"] == 1.3
    assert s["type"] == "Launcher"


def test_build_rows_skips_entries_without_unique_name() -> None:
    rows = build_rows("warframe", [{"name": "NoKey"}], _norm_frame)
    assert rows == []


def test_wfcd_files_cover_expected_categories() -> None:
    cats = {c for _, c, _ in WFCD_FILES}
    assert {"warframe", "primary", "secondary", "melee", "mod", "arcane"} <= cats
