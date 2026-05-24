"""Map Warframe uniqueName paths to display names using AlecaFrame's local cache.

AlecaFrame ships a static JSON catalogue at
    %LOCALAPPDATA%\\AlecaFrame\\cachedData\\json\\

Each *.json there is a list (or dict) of items with `uniqueName` and `name`
fields. We load all of them lazily at first use.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from pathlib import Path
from typing import Any

log = logging.getLogger("alecaframe.naming")

# Order matters only for category-tagging; we union the lookup table.
SOURCES: tuple[tuple[str, str], ...] = (
    ("Warframes.json", "warframe"),
    ("Primary.json", "primary"),
    ("Secondary.json", "secondary"),
    ("Melee.json", "melee"),
    ("Sentinels.json", "sentinel"),
    ("SentinelWeapons.json", "sentinel_weapon"),
    ("Archwing.json", "archwing"),
    ("Arch-Gun.json", "arch_gun"),
    ("Arch-Melee.json", "arch_melee"),
    ("Pets.json", "pet"),
    ("Mods.json", "mod"),
    ("Arcanes.json", "arcane"),
    ("Resources.json", "resource"),
    ("Gear.json", "gear"),
    ("Glyphs.json", "glyph"),
    ("Misc.json", "misc"),
    ("Skins.json", "skin"),
    ("Sigils.json", "sigil"),
    ("Relics.json", "relic"),
    ("Quests.json", "quest"),
    ("Railjack.json", "railjack"),
    ("Fish.json", "fish"),
    ("Node.json", "node"),
)


class NameResolver:
    """uniqueName -> {name, category, meta...} lookup."""

    def __init__(self, cached_json_dir: Path) -> None:
        self.cached_json_dir = cached_json_dir
        self._table: dict[str, dict[str, Any]] = {}
        self._loaded = False
        self._lock = threading.Lock()

    # ----------------------------------------------------------- loading

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            if not self.cached_json_dir.exists():
                log.warning("cached_json_dir missing: %s", self.cached_json_dir)
                self._loaded = True
                return
            for fname, category in SOURCES:
                path = self.cached_json_dir / fname
                if not path.exists():
                    continue
                try:
                    raw = json.loads(path.read_text(encoding="utf-8"))
                except Exception as e:
                    log.warning("can't parse %s: %s", path, e)
                    continue
                self._index(raw, category)
            log.info("name resolver: %d entries from %s", len(self._table), self.cached_json_dir)
            self._loaded = True

    def _index(self, raw: Any, category: str) -> None:
        if isinstance(raw, list):
            for it in raw:
                if isinstance(it, dict):
                    self._add(it, category)
        elif isinstance(raw, dict):
            for k, v in raw.items():
                if isinstance(v, dict):
                    if "uniqueName" not in v:
                        v = dict(v, uniqueName=k)
                    self._add(v, category)

    def _add(self, it: dict[str, Any], category: str) -> None:
        u = it.get("uniqueName")
        n = it.get("name")
        if not u or not n:
            return
        if u in self._table:
            return  # first source wins
        self._table[u] = {
            "name": n,
            "category": category,
            "image": it.get("imageName") or it.get("image"),
            "ducats": it.get("ducats"),
            "trading_tax": it.get("tradingTax"),
            "tradable": it.get("tradable"),
            "mastery_req": it.get("masteryReq"),
        }

    # --------------------------------------------------------- lookups

    def resolve(self, unique_name: str | None) -> str:
        """Pretty display name; falls back to last path segment."""
        if not unique_name:
            return ""
        self._ensure_loaded()
        hit = self._table.get(unique_name)
        if hit:
            return hit["name"]
        return _camel_to_words(unique_name.rsplit("/", 1)[-1])

    def lookup(self, unique_name: str | None) -> dict[str, Any] | None:
        if not unique_name:
            return None
        self._ensure_loaded()
        return self._table.get(unique_name)

    def enrich(self, items: list[dict[str, Any]], *, key: str = "ItemType") -> list[dict[str, Any]]:
        """Return new list with `name`, `category`, `ducats` added per item."""
        self._ensure_loaded()
        out: list[dict[str, Any]] = []
        for it in items:
            u = it.get(key) or it.get("uniqueName")
            meta = self._table.get(u) if u else None
            row = dict(it)
            if meta:
                row.setdefault("name", meta["name"])
                row.setdefault("category", meta["category"])
                if meta.get("ducats") is not None:
                    row.setdefault("ducats", meta["ducats"])
            else:
                row.setdefault("name", _camel_to_words((u or "").rsplit("/", 1)[-1]))
            out.append(row)
        return out

    def size(self) -> int:
        self._ensure_loaded()
        return len(self._table)


_CAMEL_RX = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")


def _camel_to_words(s: str) -> str:
    s = s.replace("Blueprint", " Blueprint").replace("_", " ")
    return _CAMEL_RX.sub(" ", s).strip()
