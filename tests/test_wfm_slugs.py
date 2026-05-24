"""SlugResolver tests — uniqueName→slug forward + reverse lookups."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from alecaframe_api.wfm.slugs import ItemRef, SlugResolver

FIXTURE = Path(__file__).parent / "fixtures" / "wfm_items_sample.json"


def load_items() -> list[ItemRef]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return [
        ItemRef(slug=it["url_name"], item_name=it["item_name"],
                thumb_url=it.get("thumb"), vaulted=bool(it.get("vaulted", False)),
                wfm_id=it["id"])
        for it in raw["payload"]["items"]
    ]


@pytest.fixture
def resolver() -> SlugResolver:
    r = SlugResolver()
    r.load(load_items())
    return r


def test_lookup_by_slug(resolver: SlugResolver) -> None:
    it = resolver.by_slug("kronen_prime_blade")
    assert it is not None
    assert it.item_name == "Kronen Prime Blade"
    assert it.vaulted is True


def test_lookup_missing_slug_returns_none(resolver: SlugResolver) -> None:
    assert resolver.by_slug("does_not_exist") is None


def test_resolve_unique_name_recipes_weapon_parts(resolver: SlugResolver) -> None:
    """/Lotus/Types/Recipes/Weapons/WeaponParts/KronenPrimeBlade -> kronen_prime_blade"""
    slug = resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/KronenPrimeBlade"
    )
    assert slug == "kronen_prime_blade"


def test_resolve_unique_name_warframe_blueprint(resolver: SlugResolver) -> None:
    slug = resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/WarframeRecipes/MagPrimeBlueprint"
    )
    assert slug == "mag_prime_blueprint"


def test_resolve_unique_name_helmet_blueprint(resolver: SlugResolver) -> None:
    slug = resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeHelmetBlueprint"
    )
    assert slug == "volt_prime_helmet_blueprint"


def test_resolve_unique_name_mod_path(resolver: SlugResolver) -> None:
    """Mods don't live under /Recipes/. They use /Upgrades/Mods/."""
    slug = resolver.resolve_unique_name(
        "/Lotus/Upgrades/Mods/Warframe/PrimedContinuityMod"
    )
    assert slug == "primed_continuity"


def test_resolve_unique_name_unknown_returns_none(resolver: SlugResolver) -> None:
    assert resolver.resolve_unique_name("/Lotus/Types/Items/SomeUnknownThing") is None


def test_overrides_take_priority(resolver: SlugResolver) -> None:
    """If data/slug_overrides.json maps a uniqueName, that mapping wins."""
    r = SlugResolver()
    r.load(load_items())
    r.apply_overrides({"/Lotus/Types/Custom/Weird": "kronen_prime_blade"})
    assert r.resolve_unique_name("/Lotus/Types/Custom/Weird") == "kronen_prime_blade"


def test_all_slugs(resolver: SlugResolver) -> None:
    assert sorted(resolver.all_slugs()) == sorted([
        "kronen_prime_blade", "kronen_prime_blueprint", "mag_prime_blueprint",
        "volt_prime_helmet_blueprint", "primed_continuity", "ash_prime_systems_blueprint",
    ])


def test_load_replaces_existing(resolver: SlugResolver) -> None:
    """Calling load() twice should not leave stale slugs."""
    smaller = [load_items()[0]]
    resolver.load(smaller)
    assert resolver.all_slugs() == ["kronen_prime_blade"]
