"""Build SetComposition[] from AlecaFrame `cachedData/json/*.json`.

Each AlecaFrame catalogue entry has `name`, `uniqueName`, and (for sets) a
`components` list. We synthesise the set slug from the warframe/weapon name
(`Mag Prime` → `mag_prime_set`) and resolve each component's `uniqueName`
through SlugResolver. If any component is unresolvable, the whole set is
dropped — partial sets would mislead the profit calculator.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from alecaframe_api.wfm.sets import SetComposition
from alecaframe_api.wfm.slugs import SlugResolver

log = logging.getLogger("alecaframe.wfm.sets_loader")

_CATALOGUE_FILES = (
    "Warframes.json",
    "Primary.json",
    "Secondary.json",
    "Melee.json",
    "Sentinels.json",
    "Arch-Gun.json",
    "Arch-Melee.json",
)


def _to_set_slug(item_name: str) -> str:
    """`Mag Prime` → `mag_prime_set`."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", item_name.lower()).strip("_")
    if cleaned.endswith("_set"):
        return cleaned
    return f"{cleaned}_set"


def load_set_compositions_from_aleca(
    *,
    cached_json_dir: Path,
    resolver: SlugResolver,
) -> list[SetComposition]:
    out: list[SetComposition] = []
    for fname in _CATALOGUE_FILES:
        path = cached_json_dir / fname
        if not path.exists():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.warning("can't parse %s: %s", path, e)
            continue
        items = (
            raw
            if isinstance(raw, list)
            else (list(raw.values()) if isinstance(raw, dict) else [])
        )
        for it in items:
            if not isinstance(it, dict):
                continue
            components = it.get("components")
            name = it.get("name")
            if not components or not isinstance(components, list) or not name:
                continue
            parts: dict[str, int] = {}
            bad = False
            for c in components:
                u = c.get("uniqueName")
                qty = int(c.get("itemCount", 1) or 1)
                slug = resolver.resolve_unique_name(u) if u else None
                if not slug:
                    bad = True
                    break
                parts[slug] = parts.get(slug, 0) + qty
            if bad or not parts:
                continue
            out.append(
                SetComposition(
                    set_slug=_to_set_slug(name),
                    set_name=f"{name} Set" if not name.endswith(" Set") else name,
                    parts=parts,
                )
            )
    return out
