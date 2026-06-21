"""Load base (unmodded) stats for every item & warframe from WFCD warframe-items.

WFCD publishes per-category JSON keyed by DE `uniqueName` (same `/Lotus/...`
form AlecaFrame uses for inventory `ItemType`), so these rows join straight to
the player's inventory and to `wfm_items`. We normalize a per-category subset
and upsert it into the `item_base_stats` table.

Data: https://github.com/WFCD/warframe-items (MIT). Factual game stats.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

import httpx

log = logging.getLogger("alecaframe.reference.stats_loader")

_WFCD_BASE = "https://raw.githubusercontent.com/WFCD/warframe-items/master/data/json"


def _r(x: Any) -> Any:
    """Round float noise (WFCD ships e.g. 0.31999999) but leave ints/None alone."""
    return round(x, 4) if isinstance(x, float) else x


def _common(it: dict[str, Any]) -> dict[str, Any]:
    return {"name": it.get("name"), "mastery_req": it.get("masteryReq")}


# ----- per-category normalizers (it -> stats dict) -------------------------

def _norm_frame(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "health": _r(it.get("health")),
        "shield": _r(it.get("shield")),
        "armor": _r(it.get("armor")),
        "energy": _r(it.get("power")),
        "sprint_speed": _r(it.get("sprintSpeed")),
        "polarities": it.get("polarities") or [],
        "aura": it.get("aura"),
        "abilities": [a.get("name") for a in (it.get("abilities") or []) if a.get("name")],
        "is_prime": it.get("isPrime"),
    }


def _norm_companion(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "health": _r(it.get("health")),
        "shield": _r(it.get("shield")),
        "armor": _r(it.get("armor")),
        "energy": _r(it.get("power")),
        "polarities": it.get("polarities") or [],
    }


def _norm_weapon(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "fire_rate": _r(it.get("fireRate")),
        "magazine": it.get("magazineSize"),
        "reload": _r(it.get("reloadTime")),
        "accuracy": _r(it.get("accuracy")),
        "multishot": _r(it.get("multishot")),
        "crit_chance": _r(it.get("criticalChance")),
        "crit_multiplier": _r(it.get("criticalMultiplier")),
        "status_chance": _r(it.get("procChance")),
        "total_damage": _r(it.get("totalDamage")),
        "damage": {k: _r(v) for k, v in (it.get("damage") or {}).items() if v},
        "trigger": it.get("trigger"),
        "slot": it.get("slot"),
        "is_prime": it.get("isPrime"),
    }


def _norm_mod(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "polarity": it.get("polarity"),
        "rarity": it.get("rarity"),
        "base_drain": it.get("baseDrain"),
        "max_rank": it.get("fusionLimit"),
        "compat_name": it.get("compatName"),
        "mod_set": it.get("modSet"),
    }


def _norm_arcane(it: dict[str, Any]) -> dict[str, Any]:
    return {
        "rarity": it.get("rarity"),
        "max_rank": it.get("fusionLimit"),
    }


# (filename, our category tag, normalizer). Aligned with naming.py SOURCES.
WFCD_FILES: tuple[tuple[str, str, Callable[[dict[str, Any]], dict[str, Any]]], ...] = (
    ("Warframes.json", "warframe", _norm_frame),
    ("Primary.json", "primary", _norm_weapon),
    ("Secondary.json", "secondary", _norm_weapon),
    ("Melee.json", "melee", _norm_weapon),
    ("SentinelWeapons.json", "sentinel_weapon", _norm_weapon),
    ("Arch-Gun.json", "arch_gun", _norm_weapon),
    ("Arch-Melee.json", "arch_melee", _norm_weapon),
    ("Sentinels.json", "sentinel", _norm_companion),
    ("Archwing.json", "archwing", _norm_companion),
    ("Pets.json", "pet", _norm_companion),
    ("Mods.json", "mod", _norm_mod),
    ("Arcanes.json", "arcane", _norm_arcane),
)


def build_rows(
    category: str, items: list[dict[str, Any]],
    normalizer: Callable[[dict[str, Any]], dict[str, Any]],
) -> list[dict[str, Any]]:
    """Pure transform (no network) — used directly by tests."""
    out: list[dict[str, Any]] = []
    for it in items:
        u = it.get("uniqueName")
        if not u:
            continue
        c = _common(it)
        out.append({
            "unique_name": u,
            "category": category,
            "name": c["name"],
            "mastery_req": c["mastery_req"],
            "disposition": _r(it.get("disposition")),
            "stats": normalizer(it),
            "source": "wfcd",
        })
    return out


async def _fetch(client: httpx.AsyncClient, fname: str) -> list[dict[str, Any]]:
    r = await client.get(f"{_WFCD_BASE}/{fname}")
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else []


async def refresh(repo, *, client: httpx.AsyncClient | None = None) -> int:
    """Fetch every WFCD category, normalize, and upsert into item_base_stats.
    Returns total rows written. Per-file failures are logged and skipped."""
    owns_client = client is None
    client = client or httpx.AsyncClient(timeout=30.0, follow_redirects=True)
    total = 0
    try:
        for fname, category, normalizer in WFCD_FILES:
            try:
                items = await _fetch(client, fname)
            except Exception as e:
                log.warning("WFCD fetch failed for %s: %s", fname, e)
                continue
            rows = build_rows(category, items, normalizer)
            total += await repo.upsert_base_stats(rows)
            log.info("base-stats: %s -> %d rows", category, len(rows))
    finally:
        if owns_client:
            await client.aclose()
    log.info("base-stats refresh complete: %d rows", total)
    return total
