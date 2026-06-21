"""Reverse-index: which items use a given component to be built.

Mirror of `sets_loader.py` but indexes the OTHER direction. Sets-loader gives
us "Mag Prime → [BP, Helmet BP, Chassis BP, Systems BP]"; this gives us
"Akstiletto → [Aksomati, Sarpa]" — what an inventory item *gets crafted into*.

Unlike sets-loader, the key here is the raw catalogue `uniqueName` (matches
inventory items' `ItemType` directly). No slug resolution required, so items
with non-WFM-tradeable ingredients (Forma BP, Salvage, etc.) are included.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("alecaframe.wfm.recipe_uses")

_CATALOGUE_FILES = (
    "Warframes.json", "Primary.json", "Secondary.json", "Melee.json",
    "Sentinels.json", "Arch-Gun.json", "Arch-Melee.json",
)


@dataclass(frozen=True)
class RecipeUse:
    """An item that uses some component as part of its recipe."""
    result_unique_name: str
    result_name: str
    count_required: int


def load_recipe_uses(*, cached_json_dir: Path) -> dict[str, list[RecipeUse]]:
    """Build reverse index: component_unique_name -> items that use it.

    Returns empty dict if the catalogue dir is missing or unreadable. Each
    component's use list is sorted by result_name for predictable rendering.
    """
    out: dict[str, list[RecipeUse]] = {}
    if not cached_json_dir.exists():
        log.warning("recipe_uses: cached_json_dir missing: %s", cached_json_dir)
        return out
    for fname in _CATALOGUE_FILES:
        path = cached_json_dir / fname
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("can't parse %s: %s", path, e)
            continue
        items = raw if isinstance(raw, list) else (
            list(raw.values()) if isinstance(raw, dict) else []
        )
        for it in items:
            if not isinstance(it, dict):
                continue
            components = it.get("components")
            result_name = it.get("name")
            result_unique_name = it.get("uniqueName")
            if not components or not isinstance(components, list):
                continue
            if not result_name or not result_unique_name:
                continue
            for c in components:
                if not isinstance(c, dict):
                    continue
                cu = c.get("uniqueName")
                qty = int(c.get("itemCount", 1) or 1)
                if not cu:
                    continue
                out.setdefault(cu, []).append(RecipeUse(
                    result_unique_name=result_unique_name,
                    result_name=result_name,
                    count_required=qty,
                ))
    for uses in out.values():
        uses.sort(key=lambda u: u.result_name)
    log.info(
        "recipe_uses: %d components indexed (%d total uses)",
        len(out), sum(len(v) for v in out.values()),
    )
    return out
