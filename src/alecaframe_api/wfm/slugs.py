"""uniqueName ↔ WFM slug resolution.

WFM uses slugs like `kronen_prime_blade`. DE uniqueNames are paths like
`/Lotus/Types/Recipes/Weapons/WeaponParts/KronenPrimeBlade`. The resolver:

1. Loads the WFM /v1/items catalogue once (passed in via `load()`).
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
    vaulted: bool
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


def _normalise_recipe_tail(tail: str) -> str:
    """Strip nothing — just camel→snake.

    `MagPrimeBlueprint` → `mag_prime_blueprint`.
    `KronenPrimeBlade` → `kronen_prime_blade`.
    """
    return _camel_to_snake(tail)


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
        self._overrides: dict[str, str] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- ingest

    def load(self, items: list[ItemRef]) -> None:
        """Replace the catalogue. Called at startup with the WFM /v1/items response."""
        with self._lock:
            self._by_slug = {it.slug: it for it in items}

    def apply_overrides(self, overrides: dict[str, str]) -> None:
        with self._lock:
            self._overrides.update(overrides)

    # --------------------------------------------------------------- lookups

    def by_slug(self, slug: str) -> ItemRef | None:
        return self._by_slug.get(slug)

    def resolve_unique_name(self, unique_name: str) -> str | None:
        if unique_name in self._overrides:
            return self._overrides[unique_name]
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
                tail = unique_name[len(prefix):]
                candidate = _normalise_recipe_tail(tail)
                if candidate in self._by_slug:
                    return candidate
        return None

    def all_slugs(self) -> list[str]:
        return list(self._by_slug.keys())

    def size(self) -> int:
        return len(self._by_slug)
