from __future__ import annotations

import json
from pathlib import Path

from tests import FIXTURES_DIR
from alecaframe_api.fissures.models import parse_fissure, _planet_from_node


def _load() -> list[dict]:
    p = FIXTURES_DIR / "wfm_fissures_sample.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_parse_normal_storm_hard() -> None:
    raw = _load()
    normal = parse_fissure(raw[0])
    assert normal is not None
    assert normal.era == "Omnia"
    assert normal.mission_type == "Void Cascade"
    assert normal.is_hard is False and normal.is_storm is False
    assert normal.planet == "Zariman"

    hard = parse_fissure(raw[1])
    assert hard.is_hard is True and hard.is_storm is False
    assert hard.planet == "Neptune"

    storm = parse_fissure(raw[2])
    assert storm.is_storm is True and storm.is_hard is False
    assert storm.era == "Lith"
    assert storm.planet == "Earth"


def test_parse_skips_incomplete() -> None:
    assert parse_fissure({"id": "x", "tier": "Lith"}) is None  # no missionType
    assert parse_fissure({"tier": "Lith", "missionType": "Survival"}) is None  # no id


def test_planet_helper() -> None:
    assert _planet_from_node("Proteus (Neptune)") == "Neptune"
    assert _planet_from_node("NoParens") is None
    assert _planet_from_node(None) is None
