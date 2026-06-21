"""Repo round-trip tests for the item_base_stats reference table."""
from __future__ import annotations

from pathlib import Path

import pytest

from alecaframe_api.db.repo import Repo


@pytest.fixture
async def repo(tmp_path: Path) -> Repo:
    r = Repo(db_path=tmp_path / "test.db")
    await r.connect()
    yield r
    await r.close()


def _frame_row(u: str, name: str) -> dict:
    return {
        "unique_name": u, "category": "warframe", "name": name,
        "mastery_req": 0, "disposition": None,
        "stats": {"health": 455, "armor": 105}, "source": "wfcd",
    }


@pytest.mark.asyncio
async def test_upsert_get_count(repo: Repo) -> None:
    assert await repo.count_base_stats() == 0
    n = await repo.upsert_base_stats([
        _frame_row("/Lotus/Powersuits/Ninja/Ninja", "Ash"),
        {"unique_name": "/Lotus/Weapons/X", "category": "primary", "name": "Boltor",
         "mastery_req": 2, "disposition": 0.7, "stats": {"fire_rate": 10}, "source": "wfcd"},
    ])
    assert n == 2
    assert await repo.count_base_stats() == 2

    ash = await repo.get_base_stats("/Lotus/Powersuits/Ninja/Ninja")
    assert ash is not None
    assert ash["name"] == "Ash"
    assert ash["stats"]["health"] == 455   # JSON blob round-trips to a dict
    assert await repo.get_base_stats("/nope") is None


@pytest.mark.asyncio
async def test_upsert_is_idempotent_and_updates(repo: Repo) -> None:
    u = "/Lotus/Powersuits/Ninja/Ninja"
    await repo.upsert_base_stats([_frame_row(u, "Ash")])
    updated = _frame_row(u, "Ash Prime")
    updated["stats"] = {"health": 480, "armor": 125}
    await repo.upsert_base_stats([updated])
    assert await repo.count_base_stats() == 1   # same PK → updated, not duplicated
    row = await repo.get_base_stats(u)
    assert row["name"] == "Ash Prime"
    assert row["stats"]["health"] == 480


@pytest.mark.asyncio
async def test_weapon_base_stats_index_keys_by_normalized_name(repo: Repo) -> None:
    # The riven name-join (CRITICAL-1 fix) relies on a name-keyed index because
    # WFM slugs don't map to WFCD uniqueName deterministically.
    await repo.upsert_base_stats([
        {"unique_name": "/Lotus/Weapons/ClanTech/Bio/BioWeapon", "category": "primary",
         "name": "Torid", "disposition": 4, "stats": {"crit_chance": 0.15}, "source": "wfcd"},
        {"unique_name": "/Lotus/Weapons/Grineer/Bows/GrnBow/GrnBowWeapon", "category": "primary",
         "name": "Kuva Bramma", "disposition": 1, "stats": {"crit_chance": 0.27}, "source": "wfcd"},
    ])
    index = await repo.weapon_base_stats_index()
    assert index["torid"]["name"] == "Torid"                  # lowercased key
    assert index["kuva bramma"]["name"] == "Kuva Bramma"      # multi-word survives
    assert index["torid"]["stats"]["crit_chance"] == 0.15     # stats blob round-trips


@pytest.mark.asyncio
async def test_list_filters_by_category(repo: Repo) -> None:
    await repo.upsert_base_stats([
        _frame_row("/wf/a", "Ash"),
        _frame_row("/wf/b", "Banshee"),
        {"unique_name": "/w/x", "category": "primary", "name": "Boltor",
         "stats": {}, "source": "wfcd"},
    ])
    frames = await repo.list_base_stats(category="warframe")
    assert {r["name"] for r in frames} == {"Ash", "Banshee"}
    assert len(await repo.list_base_stats()) == 3
