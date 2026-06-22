from __future__ import annotations

from alecaframe_api.fissures.matcher import matches
from alecaframe_api.fissures.models import Fissure, Subscription


def _fissure(**over) -> Fissure:
    base = dict(
        id="f1", era="Axi", mission_type="Survival", node="Xini (Eris)",
        planet="Eris", enemy="Infested", is_hard=False, is_storm=False,
        activation=None, expiry=None,
    )
    base.update(over)
    return Fissure(**base)


def _sub(**over) -> Subscription:
    base = dict(id=1, era=None, mission_type=None, planet=None, node=None,
                is_hard=None, is_storm=None, enabled=True, created_at=0)
    base.update(over)
    return Subscription(**base)


def test_empty_subscription_matches_everything() -> None:
    assert matches(_fissure(), _sub()) is True


def test_era_filter() -> None:
    assert matches(_fissure(era="Axi"), _sub(era="Axi")) is True
    assert matches(_fissure(era="Axi"), _sub(era="Lith")) is False


def test_mission_filter() -> None:
    assert matches(_fissure(mission_type="Survival"), _sub(mission_type="Survival")) is True
    assert matches(_fissure(mission_type="Survival"), _sub(mission_type="Capture")) is False


def test_steel_path_and_storm_filters() -> None:
    assert matches(_fissure(is_hard=True), _sub(is_hard=True)) is True
    assert matches(_fissure(is_hard=False), _sub(is_hard=True)) is False
    assert matches(_fissure(is_storm=True), _sub(is_storm=True)) is True
    assert matches(_fissure(is_storm=False), _sub(is_storm=True)) is False


def test_combined_filter_all_must_match() -> None:
    f = _fissure(era="Axi", mission_type="Survival", is_hard=False, is_storm=False)
    assert matches(f, _sub(era="Axi", mission_type="Survival", is_hard=False, is_storm=False)) is True
    assert matches(f, _sub(era="Axi", mission_type="Defense")) is False


def test_planet_filter() -> None:
    assert matches(_fissure(planet="Neptune"), _sub(planet="Neptune")) is True
    assert matches(_fissure(planet="Neptune"), _sub(planet="Eris")) is False


def test_node_substring_case_insensitive() -> None:
    f = _fissure(node="Proteus (Neptune)")
    assert matches(f, _sub(node="Proteus")) is True
    assert matches(f, _sub(node="proteus")) is True       # case-insensitive
    assert matches(f, _sub(node="(Neptune)")) is True      # substring anywhere
    assert matches(f, _sub(node="Xini")) is False


def test_node_filter_empty_node_never_matches() -> None:
    assert matches(_fissure(node=""), _sub(node="Proteus")) is False
