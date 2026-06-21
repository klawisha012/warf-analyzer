"""uniqueName ↔ WFM slug resolution.

WFM uses slugs like `kronen_prime_blade`. DE uniqueNames are paths like
`/Lotus/Types/Recipes/Weapons/WeaponParts/KronenPrimeBlade`. The resolver:

1. Loads the WFM /v2/items catalogue once (passed in via `load()`).
2. Builds a forward index `slug -> ItemRef`.
3. Resolves uniqueNames by stripping known path prefixes and reversing
   CamelCase → snake_case on the trailing segment.
4. Lets callers add ad-hoc overrides from `data/slug_overrides.json`.

The reverse map is best-effort. If a uniqueName has no rule, `resolve_unique_name`
returns None and the caller falls back to skipping or asking the user to add
an override.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass


@dataclass(frozen=True)
class ItemRef:
    slug: str            # e.g. "kronen_prime_blade"
    item_name: str       # e.g. "Kronen Prime Blade"
    thumb_url: str | None
    # v2 listing omits vaulted; it's only on the per-item detail endpoint.
    # Lifted to Optional so unknown ≠ False.
    vaulted: bool | None
    wfm_id: str          # WFM internal id


# Path prefixes that have a deterministic CamelCase -> slug rule.
# Order matters: more specific first.
_RECIPE_PREFIXES = (
    "/Lotus/Types/Recipes/Weapons/WeaponParts/",
    "/Lotus/Types/Recipes/SentinelRecipes/",
    "/Lotus/Types/Recipes/WarframeRecipes/",
    "/Lotus/Types/Recipes/Weapons/",
    "/Lotus/Types/Recipes/ArchwingRecipes/",
)

# Mod path prefixes — these don't share the Recipe path layout.
_MOD_PREFIXES = (
    "/Lotus/Upgrades/Mods/",
)

_CAMEL_RX = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _camel_to_snake(s: str) -> str:
    """`KronenPrimeBlade` → `kronen_prime_blade`."""
    return _CAMEL_RX.sub("_", s).lower()


_SUFFIXES = (
    "_blueprint",
    "_chassis_component",
    "_chassis",
    "_systems",
    "_cerebrum",
    "_carapace",
    "_brain",
    "_helmet",
    "_neuroptics",
    "_blade",
    "_handle",
    "_receiver",
    "_barrel",
    "_stock",
    "_grip",
    "_string",
    "_lower_limb",
    "_upper_limb",
    "_pouch",
    "_link",
)

_WEAPON_COMP_SUFFIXES = (
    "_blade",
    "_handle",
    "_receiver",
    "_barrel",
    "_stock",
    "_grip",
    "_string",
    "_limb",
    "_pouch",
    "_link",
    "_hilt",
    "_guard",
)


def _normalise_recipe_tail(tail: str) -> str:
    """Transform internal DE CamelCase naming to correct WFM slug style."""
    slug = _camel_to_snake(tail)
    
    # 1. Strip '_sentinel' suffix from Sentinels (e.g. nautilus_prime_sentinel_blueprint -> nautilus_prime_blueprint)
    slug = slug.replace("_sentinel", "")
    
    # 2. Suffix normalization for components (Helmet -> Neuroptics, ChassisComponent -> Chassis)
    if slug.endswith("_chassis_component"):
        slug = slug.replace("_chassis_component", "_chassis")
    # Replace 'helmet' with 'neuroptics' anywhere in the slug to support helmet_blueprint
    slug = slug.replace("helmet", "neuroptics")
        
    # 3. Strip redundant '_blueprint' suffix from weapon/sentinel parts (but NOT Warframe/Archwing components)
    if slug.endswith("_blueprint"):
        base = slug[:-10]
        if any(base.endswith(sfx) for sfx in _WEAPON_COMP_SUFFIXES):
            slug = base
                
    # 4. Handle leading 'prime_' prefixes (e.g. prime_hikou_holster -> hikou_prime_pouch)
    # Common holster replacement
    if "holster" in slug:
        slug = slug.replace("holster", "pouch")
        
    if slug.startswith("prime_"):
        # Look for the suffix in the slug
        for suffix in _SUFFIXES:
            sfx = suffix
            if suffix == "_chassis_component":
                sfx = "_chassis"
            elif suffix == "_helmet":
                sfx = "_neuroptics"
                
            if slug.endswith(suffix):
                # Strip prime_ from start
                base = slug[6:]
                # Strip suffix from base
                item = base[:-len(suffix)]
                slug = f"{item}_prime{sfx}"
                break
                
    # 5. Internal codename translations
    # Dakra Prime Long Sword
    if "cronus_long_sword" in slug:
        slug = slug.replace("cronus_long_sword", "dakra")
    if "cronus" in slug:
        slug = slug.replace("cronus", "dakra")

    if "sagek" in slug:
        slug = slug.replace("sagek", "sybaris")
    if "prime1_h_shotgun" in slug:
        slug = slug.replace("prime1_h_shotgun", "tigris_prime")
    if "lightning_gun" in slug:
        slug = slug.replace("lightning_gun", "tenora")
    if "polearm" in slug:
        slug = slug.replace("polearm", "orthos")
    if "archwing" in slug:
        slug = slug.replace("archwing", "odonata")
    if "vento" in slug:
        slug = slug.replace("vento", "venato")
        
    # Special weapon name mappings
    if "silva_aegis" in slug:
        slug = slug.replace("silva_aegis", "silva_and_aegis")
    if "cobra_crane" in slug:
        slug = slug.replace("cobra_crane", "cobra_and_crane")
        
    # Handle to hilt for Silva/Cobra
    if "silva_and_aegis" in slug or "cobra_and_crane" in slug:
        slug = slug.replace("_handle", "_hilt")
        
    # Bow mappings (only for Bow Prime / Prime Bow)
    if slug == "bow_prime_blueprint":
        slug = "paris_prime_blueprint"
    elif slug == "bow_prime":
        slug = "paris_prime"
    # If the base got stripped of prime_ but still has bow:
    if "bow_prime" in slug:
        slug = slug.replace("bow_prime", "paris_prime")
    if "prime_bow" in slug:
        slug = slug.replace("prime_bow", "paris_prime")
        
    # Odonata component mappings
    if slug == "odonata_prime_chassis":
        slug = "odonata_prime_harness_blueprint"
    elif slug == "odonata_prime_systems":
        slug = "odonata_prime_systems_blueprint"
    elif slug == "odonata_prime_wings":
        slug = "odonata_prime_wings_blueprint"
        
    return slug


def _normalise_mod_tail(tail: str) -> str:
    """Mod uniqueName tails end with `Mod` suffix that WFM drops.

    `PrimedContinuityMod` → `primed_continuity`.
    `Adaptation` → `adaptation`.
    """
    if tail.endswith("Mod"):
        tail = tail[: -len("Mod")]
    return _camel_to_snake(tail)


class SlugResolver:
    """uniqueName ↔ slug resolution with override hook."""

    def __init__(self) -> None:
        self._by_slug: dict[str, ItemRef] = {}
        self._by_id: dict[str, ItemRef] = {}
        self._overrides: dict[str, str] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- ingest

    def load(self, items: list[ItemRef]) -> None:
        """Replace the catalogue. Called at startup with the WFM /v2/items response."""
        with self._lock:
            self._by_slug = {it.slug: it for it in items}
            # v2 /me/orders carries `itemId` per row, not `slug`. Build the
            # reverse map once so the router doesn't have to walk the
            # catalogue on every order.
            self._by_id = {it.wfm_id: it for it in items}

    def apply_overrides(self, overrides: dict[str, str]) -> None:
        with self._lock:
            self._overrides.update(overrides)

    # --------------------------------------------------------------- lookups

    def by_slug(self, slug: str) -> ItemRef | None:
        return self._by_slug.get(slug)

    def by_wfm_id(self, wfm_id: str) -> ItemRef | None:
        """Reverse lookup itemId -> ItemRef. Used by /me/* parsers that
        receive v2 orders carrying `itemId` instead of `slug`."""
        return self._by_id.get(wfm_id)

    def resolve_unique_name(self, unique_name: str, pretty_name: str | None = None) -> str | None:
        if unique_name in self._overrides:
            return self._overrides[unique_name]
        # Try resolving by pretty name first if provided (extremely robust for arcanes and mods)
        if pretty_name:
            slug = pretty_name.lower()
            slug = slug.replace(" & ", " and ")
            slug = re.sub(r"[^a-z0-9\s_-]", "", slug)
            slug = re.sub(r"[\s-]+", "_", slug)
            if slug in self._by_slug:
                return slug
        # 1. Mod path heuristic — strip subfolder, drop "Mod", normalise the tail.
        for prefix in _MOD_PREFIXES:
            if unique_name.startswith(prefix):
                tail = unique_name.rsplit("/", 1)[-1]
                candidate = _normalise_mod_tail(tail)
                if candidate in self._by_slug:
                    return candidate
        # 2. Recipe path — strip prefix, camel-to-snake the tail.
        for prefix in _RECIPE_PREFIXES:
            if unique_name.startswith(prefix):
                tail = unique_name.rsplit("/", 1)[-1]
                candidate = _normalise_recipe_tail(tail)
                if candidate in self._by_slug:
                    return candidate
        return None

    def all_slugs(self) -> list[str]:
        return list(self._by_slug.keys())

    def size(self) -> int:
        return len(self._by_slug)
