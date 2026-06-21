"""Loader test — read AlecaFrame Warframes.json slice + resolve via SlugResolver."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import FIXTURES_DIR
from alecaframe_api.wfm.sets_loader import load_set_compositions_from_aleca
from alecaframe_api.wfm.slugs import ItemRef, SlugResolver


@pytest.fixture
def resolver() -> SlugResolver:
    r = SlugResolver()
    r.load([
        ItemRef(slug="mag_prime_set",                 item_name="Mag Prime Set",            thumb_url=None, vaulted=False, wfm_id="1"),
        ItemRef(slug="mag_prime_blueprint",           item_name="Mag Prime Blueprint",      thumb_url=None, vaulted=False, wfm_id="2"),
        ItemRef(slug="mag_prime_neuroptics_blueprint", item_name="Mag Prime Neuroptics BP",  thumb_url=None, vaulted=False, wfm_id="3"),
        ItemRef(slug="mag_prime_chassis_blueprint",    item_name="Mag Prime Chassis BP",     thumb_url=None, vaulted=False, wfm_id="4"),
        ItemRef(slug="mag_prime_systems_blueprint",    item_name="Mag Prime Systems BP",     thumb_url=None, vaulted=False, wfm_id="5"),
    ])
    return r


def test_loader_builds_mag_prime_set(tmp_path: Path, resolver: SlugResolver) -> None:
    fixture = FIXTURES_DIR / "aleca_warframes_sample.json"
    cached_dir = tmp_path
    (cached_dir / "Warframes.json").write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")

    sets = load_set_compositions_from_aleca(cached_json_dir=cached_dir, resolver=resolver)
    by_slug = {s.set_slug: s for s in sets}
    assert "mag_prime_set" in by_slug
    s = by_slug["mag_prime_set"]
    assert s.set_name == "Mag Prime Set"
    assert s.parts == {
        "mag_prime_blueprint": 1,
        "mag_prime_neuroptics_blueprint": 1,
        "mag_prime_chassis_blueprint": 1,
        "mag_prime_systems_blueprint": 1,
    }


def test_loader_skips_items_without_components(tmp_path: Path, resolver: SlugResolver) -> None:
    (tmp_path / "Warframes.json").write_text(
        json.dumps([{"name": "Excalibur", "uniqueName": "/Lotus/Powersuits/Excalibur/Excalibur"}]),
        encoding="utf-8",
    )
    sets = load_set_compositions_from_aleca(cached_json_dir=tmp_path, resolver=resolver)
    assert sets == []


def test_loader_skips_unresolvable_components(tmp_path: Path, resolver: SlugResolver) -> None:
    """If any part can't resolve to a slug, skip the whole set rather than producing a partial."""
    (tmp_path / "Warframes.json").write_text(
        json.dumps([{
            "name": "Mystery Prime", "uniqueName": "/Lotus/Powersuits/Mystery/MysteryPrime",
            "components": [
                {"uniqueName": "/Lotus/Types/Recipes/WarframeRecipes/MysteryPrimeBlueprint", "itemCount": 1}
            ],
        }]),
        encoding="utf-8",
    )
    sets = load_set_compositions_from_aleca(cached_json_dir=tmp_path, resolver=resolver)
    assert sets == []
