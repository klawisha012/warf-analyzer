"""Pure alert-detection logic ported from ``scanner2.py``.

No I/O, no DB, no httpx — just functions over the auction dict shape returned
by warframe.market. Unit tests live in ``backend/tests/test_alert_rules.py``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Constants — copied verbatim from scanner2.py (single source of truth here).
# ---------------------------------------------------------------------------

GOOD_STATS: list[str] = [
    "critical_chance",
    "critical_damage",
    "multishot",
]

GOOD_NEGATIVES: set[str] = {
    "projectile_speed",
    "zoom",
    "ammo_maximum",
}

# Weapon-specific synergy bands: per-stat [min, max] percentages.
# Lifted verbatim from scanner2.synergies.
SYNERGIES: dict[str, dict[str, list[float]]] = {
    "torid": {
        "multishot": [98.7, 120.7],
        "critical_damage": [131.6, 160.7],
        "critical_chance": [164.5, 201.1],
    },
    "dual_toxocyst": {
        "multishot": [136.3, 166.6],
        "critical_damage": [102.5, 125.3],
        "critical_chance": [170.9, 208.8],
    },
    "burston": {
        "multishot": [110.1, 134.6],
        "critical_damage": [146.8, 179.4],
        "critical_chance": [183.5, 224.3],
    },
    "latron": {
        "multishot": [106.3, 129.9],
        "critical_damage": [141.7, 173.2],
        "critical_chance": [177.2, 216.6],
    },
}

AlertReason = Literal["good stats", "endo", "pod roll", "none"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def minutes_since_updated(updated_str: str) -> int:
    """Minutes between *now* (UTC) and the ISO-8601 ``updated`` timestamp.

    Accepts both ``...+00:00`` and bare ``Z`` suffixes (some market payloads
    use ``Z``). Negative values are clamped to 0 — clock skew shouldn't make
    auctions appear "from the future" to the alerting code.
    """
    s = updated_str.replace("Z", "+00:00") if updated_str.endswith("Z") else updated_str
    updated_dt = datetime.fromisoformat(s)
    if updated_dt.tzinfo is None:
        updated_dt = updated_dt.replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    delta = now - updated_dt
    return max(0, int(delta.total_seconds() // 60))


def are_stats_good(auction: dict[str, Any]) -> bool:
    """Return True iff every positive stat is in GOOD_STATS, the negative (if
    any) is in GOOD_NEGATIVES, and the auction passes the freshness / size /
    price guards from ``scanner2.are_stats_good``.
    """
    updated = auction.get("updated")
    owner = auction.get("owner") or {}
    if owner.get("ingame_name") == "--Cube":
        return False

    item = auction.get("item") or {}
    attributes = item.get("attributes") or []
    weapon = item.get("weapon_url_name")

    # Stale rivens are only acceptable for the synergy-tracked weapons.
    if updated and minutes_since_updated(updated) > 4 and weapon not in SYNERGIES:
        return False

    if len(attributes) < 4:
        return False

    # Last attribute must be the negative stat (legacy invariant: positives
    # come first, negative last).
    if attributes[-1].get("positive", False) is True:
        return False

    for stat in attributes:
        if stat.get("positive", False) is True:
            if stat.get("url_name") not in GOOD_STATS:
                return False
        else:
            if stat.get("url_name") not in GOOD_NEGATIVES:
                return False

    buyout = auction.get("buyout_price") or 0
    if buyout > 500 and weapon not in SYNERGIES:
        return False

    return True


def riven_alert_check(
    auction: dict[str, Any],
    good_weapons: dict[str, int],
) -> AlertReason:
    """Classify an auction.

    Mirrors ``scanner2.riven_alert_check`` plus a final price-threshold gate:
    an alert is only surfaced when the auction's buyout is at or below the
    configured threshold for that weapon in ``good_weapons``. Weapons missing
    from ``good_weapons`` have no defined threshold and are rejected, no
    matter how attractive their stats or rerolls/price ratio look.
    """
    buyout = auction.get("buyout_price")
    item = auction.get("item") or {}

    if not buyout or buyout <= 0 or buyout == 1:
        return "none"
    if item.get("type") != "riven":
        return "none"

    updated = auction.get("updated")
    re_rolls = item.get("re_rolls", 0) or 0
    weapon = item.get("weapon_url_name")

    reason: AlertReason = "none"
    if are_stats_good(auction):
        reason = "good stats"
    elif updated and minutes_since_updated(updated) <= 4:
        if re_rolls / buyout > 3 and re_rolls > 50:
            reason = "endo"
        elif weapon in good_weapons and buyout <= good_weapons[weapon]:
            reason = "pod roll"

    if reason == "none":
        return reason

    threshold = good_weapons.get(weapon)
    if threshold is None or buyout > threshold:
        return "none"
    return reason
