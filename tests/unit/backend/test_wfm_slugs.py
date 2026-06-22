"""SlugResolver tests — uniqueName→slug forward + reverse lookups."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests import FIXTURES_DIR
from alecaframe_api.wfm.slugs import ItemRef, SlugResolver

FIXTURE = FIXTURES_DIR / "wfm_items_sample.json"


def load_items() -> list[ItemRef]:
    """Parse the v2-shaped fixture into ItemRef[] the same way client.get_items does."""
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    out: list[ItemRef] = []
    for it in raw["data"]:
        en = (it.get("i18n") or {}).get("en") or {}
        out.append(ItemRef(
            slug=it["slug"], item_name=en.get("name") or it["slug"],
            thumb_url=en.get("thumb"), vaulted=None, wfm_id=it["id"],
        ))
    return out


@pytest.fixture
def resolver() -> SlugResolver:
    r = SlugResolver()
    r.load(load_items())
    return r


def test_lookup_by_slug(resolver: SlugResolver) -> None:
    it = resolver.by_slug("kronen_prime_blade")
    assert it is not None
    assert it.item_name == "Kronen Prime Blade"
    # v2 listing omits vaulted; legacy "Kronen Prime Blade is vaulted" lives elsewhere now.
    assert it.vaulted is None


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
    """Warframe helmets map to neuroptics on WFM, and keep the blueprint suffix."""
    slug = resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/WarframeRecipes/VoltPrimeHelmetBlueprint"
    )
    assert slug == "volt_prime_neuroptics_blueprint"


def test_resolve_unique_name_systems_blueprint(resolver: SlugResolver) -> None:
    """Warframe components keep the _blueprint suffix in WFM."""
    slug = resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/WarframeRecipes/AshPrimeSystemsBlueprint"
    )
    assert slug == "ash_prime_systems_blueprint"


def test_resolve_unique_name_leading_prime_prefixes(resolver: SlugResolver) -> None:
    """Test leading 'Prime' uniqueNames are re-ordered and mapped correctly."""
    # 1. prime_hikou_holster -> hikou_prime_pouch
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeHikouHolster"
    ) == "hikou_prime_pouch"

    # 2. prime_carrier_systems -> carrier_prime_systems
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeCarrierSystems"
    ) == "carrier_prime_systems"

    # 3. prime_polearm_blade -> orthos_prime_blade
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimePolearmBlade"
    ) == "orthos_prime_blade"

    # 4. prime_archwing_chassis_component -> odonata_prime_harness_blueprint
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/ArchwingRecipes/PrimeArchwing/PrimeArchwingChassisComponent"
    ) == "odonata_prime_harness_blueprint"

    # 5. prime_daikyu_lower_limb -> daikyu_prime_lower_limb
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeDaikyuLowerLimb"
    ) == "daikyu_prime_lower_limb"

    # 6. prime_wyrm_carapace -> wyrm_prime_carapace
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeWyrmCarapace"
    ) == "wyrm_prime_carapace"

    # 7. prime_ballistica_receiver -> ballistica_prime_receiver
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeBallisticaReceiver"
    ) == "ballistica_prime_receiver"

    # 8. prime_bow_grip -> paris_prime_grip
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeBowGrip"
    ) == "paris_prime_grip"

    # 9. prime_bow_string -> paris_prime_string
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeBowString"
    ) == "paris_prime_string"

    # 10. prime_dual_kamas_blade -> dual_kamas_prime_blade
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeDualKamasBlade"
    ) == "dual_kamas_prime_blade"


def test_resolve_unique_name_sentinel_and_weapons_codenames(resolver: SlugResolver) -> None:
    """Test various sentinel and weapon internal codename mappings."""
    # 1. NautilusPrimeSentinelBlueprint -> nautilus_prime_blueprint
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/SentinelRecipes/NautilusPrimeSentinelBlueprint"
    ) == "nautilus_prime_blueprint"

    # 2. PrimeDethcubeSentinelBlueprint -> dethcube_prime_blueprint
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/SentinelRecipes/PrimeDethcubeSentinelBlueprint"
    ) == "dethcube_prime_blueprint"

    # 3. PrimeHeliosSentinelBlueprint -> helios_prime_blueprint
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/SentinelRecipes/PrimeHeliosSentinelBlueprint"
    ) == "helios_prime_blueprint"

    # 4. SagekPrimeBlueprint -> sybaris_prime_blueprint
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/SagekPrimeBlueprint"
    ) == "sybaris_prime_blueprint"

    # 5. SagekPrimeBarrelBlueprint -> sybaris_prime_barrel
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/SagekPrimeBarrelBlueprint"
    ) == "sybaris_prime_barrel"

    # 6. SagekPrimeReceiverBlueprint -> sybaris_prime_receiver
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/SagekPrimeReceiverBlueprint"
    ) == "sybaris_prime_receiver"

    # 7. PrimeLightningGunStock -> tenora_prime_stock
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeLightningGunStock"
    ) == "tenora_prime_stock"

    # 8. PrimeLightningGunBarrel -> tenora_prime_barrel
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/PrimeLightningGunBarrel"
    ) == "tenora_prime_barrel"

    # 9. Prime1HShotgunBlueprint -> tigris_prime_blueprint
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/Prime1HShotgunBlueprint"
    ) == "tigris_prime_blueprint"

    # 10. BowPrimeBlueprint -> paris_prime_blueprint
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/BowPrimeBlueprint"
    ) == "paris_prime_blueprint"

    # 11. VentoPrimeBlueprint -> venato_prime_blueprint
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/VentoPrimeBlueprint"
    ) == "venato_prime_blueprint"


def test_resolve_unique_name_special_weapon_names(resolver: SlugResolver) -> None:
    """Test complex special weapon names that require adding '_and_' or hilt mapping."""
    # 1. SilvaAegisPrimeHandle -> silva_and_aegis_prime_hilt
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/SilvaAegisPrimeHandle"
    ) == "silva_and_aegis_prime_hilt"

    # 2. CobraCranePrimeHandle -> cobra_and_crane_prime_hilt
    assert resolver.resolve_unique_name(
        "/Lotus/Types/Recipes/Weapons/WeaponParts/CobraCranePrimeHandle"
    ) == "cobra_and_crane_prime_hilt"


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


def test_load_replaces_existing(resolver: SlugResolver) -> None:
    """Calling load() twice should not leave stale slugs."""
    smaller = [load_items()[0]]
    resolver.load(smaller)
    assert resolver.all_slugs() == ["kronen_prime_blade"]
