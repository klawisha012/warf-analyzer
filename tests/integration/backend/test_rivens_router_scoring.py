"""Wiring tests for the riven scoring path in the router.

Covers the slug -> item_name -> base_row -> score integration and the
unscored reason-code branches — none of which the pure-engine unit tests reach.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from alecaframe_api.db.repo import Repo
from alecaframe_api.wfm.auctions_client import WFMAuctionError
from alecaframe_api.wfm.riven_scoring import build_profiles
from alecaframe_api.wfm.rivens_router import _resolve_weapon_profiles, _to_row


@pytest.fixture
async def repo(tmp_path: Path) -> Repo:
    r = Repo(db_path=tmp_path / "test.db")
    await r.connect()
    await r.upsert_base_stats([
        {"unique_name": "/w/dread", "category": "primary", "name": "Dread",
         "disposition": 5, "stats": {"crit_chance": 0.5, "status_chance": 0.1,
                                     "omega_attenuation": 1.0}, "source": "wfcd"},
        {"unique_name": "/w/nikana", "category": "melee", "name": "Nikana",
         "disposition": 3, "stats": {"crit_chance": 0.2}, "source": "wfcd"},
    ])
    yield r
    await r.close()


class _FakeClient:
    def __init__(self, weapons: list[dict], *, raise_error: bool = False) -> None:
        self._weapons = weapons
        self._raise = raise_error

    async def get_riven_weapons(self) -> list[dict]:
        if self._raise:
            raise WFMAuctionError("market down")
        return self._weapons


def _auction(*attrs: dict) -> dict:
    return {"id": "a1", "item": {"weapon_url_name": "dread", "attributes": list(attrs)}}


# ----- _to_row scoring (the engine actually reaches a row) ------------------

def test_to_row_attaches_grade_and_score() -> None:
    profiles = build_profiles({"name": "Dread", "category": "primary",
                               "stats": {"crit_chance": 0.5, "status_chance": 0.1}})
    row = _to_row(
        _auction({"url_name": "critical_chance", "value": 150, "positive": True},
                 {"url_name": "critical_damage", "value": 90, "positive": True}),
        "god", profiles=profiles,
    )
    assert row.unscored is False
    assert row.grade is not None and row.score is not None


def test_to_row_sets_market_signal_steal() -> None:
    profiles = build_profiles({"name": "Dread", "category": "primary",
                               "stats": {"crit_chance": 0.5, "status_chance": 0.1}})
    auction = {"id": "a1", "buyout_price": 80, "item": {"weapon_url_name": "dread",
        "attributes": [
            {"url_name": "critical_chance", "value": 150, "positive": True},
            {"url_name": "critical_damage", "value": 90, "positive": True}]}}
    row = _to_row(auction, "low", profiles=profiles, market_median=120)
    assert row.grade in {"S", "A"}              # strong roll
    assert row.market_signal == "steal"         # priced under the 120 median


def test_to_row_passes_through_unscored_reason() -> None:
    row = _to_row(_auction(), "god", profiles=None,
                  weapon_unscored_reason="melee_out_of_scope_m1")
    assert row.unscored is True
    assert row.grade is None and row.score is None
    assert row.unscored_reason == "melee_out_of_scope_m1"


# ----- _resolve_weapon_profiles reason-code branches -----------------------

@pytest.mark.asyncio
async def test_resolve_happy_path(repo: Repo) -> None:
    client = _FakeClient([{"url_name": "dread", "item_name": "Dread"}])
    profiles, reason = await _resolve_weapon_profiles("dread", client, repo)
    assert reason is None
    assert profiles and profiles[0].kind == "base"


@pytest.mark.asyncio
async def test_resolve_fetch_failure_is_distinct(repo: Repo) -> None:
    client = _FakeClient([], raise_error=True)
    profiles, reason = await _resolve_weapon_profiles("dread", client, repo)
    assert profiles == [] and reason == "weapon_fetch_failed"


@pytest.mark.asyncio
async def test_resolve_slug_not_in_catalogue(repo: Repo) -> None:
    client = _FakeClient([{"url_name": "other", "item_name": "Other"}])
    profiles, reason = await _resolve_weapon_profiles("missing", client, repo)
    assert profiles == [] and reason == "no_base_profile"


@pytest.mark.asyncio
async def test_resolve_name_join_miss(repo: Repo) -> None:
    client = _FakeClient([{"url_name": "ghost", "item_name": "Ghost Gun"}])
    profiles, reason = await _resolve_weapon_profiles("ghost", client, repo)
    assert profiles == [] and reason == "no_base_profile"


@pytest.mark.asyncio
async def test_resolve_melee_out_of_scope(repo: Repo) -> None:
    client = _FakeClient([{"url_name": "nikana", "item_name": "Nikana"}])
    profiles, reason = await _resolve_weapon_profiles("nikana", client, repo)
    assert profiles == [] and reason == "melee_out_of_scope_m1"
