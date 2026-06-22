"""Domain model for Void Fissures + parsing of warframestat.us payloads."""

from __future__ import annotations

from dataclasses import dataclass

# Map our settings Platform literal to warframestat.us path segments.
PLATFORM_MAP: dict[str, str] = {
    "pc": "pc",
    "xbox": "xb1",
    "ps4": "ps4",
    "switch": "swi",
}


@dataclass(frozen=True)
class Fissure:
    id: str
    era: str  # warframestat.us `tier`: Lith/Meso/Neo/Axi/Requiem/Omnia
    mission_type: str
    node: str
    planet: str | None
    enemy: str | None
    is_hard: bool  # Steel Path
    is_storm: bool  # Void Storm (Railjack)
    activation: str | None
    expiry: str | None


@dataclass(frozen=True)
class Subscription:
    id: int
    era: str | None  # None = any
    mission_type: str | None  # None = any
    planet: str | None  # None = any (exact match)
    node: str | None  # None = any (case-insensitive substring)
    is_hard: bool | None  # None = any
    is_storm: bool | None  # None = any
    enabled: bool
    created_at: int


def _planet_from_node(node: str | None) -> str | None:
    """`"Proteus (Neptune)"` -> `"Neptune"`. None if no parenthesised tail."""
    if not node:
        return None
    lo = node.rfind("(")
    hi = node.rfind(")")
    if lo != -1 and hi != -1 and hi > lo:
        return node[lo + 1 : hi].strip() or None
    return None


def parse_fissure(raw: dict) -> Fissure | None:
    """Normalise one warframestat.us fissure object. Returns None if the
    minimal identifying fields (id, tier, missionType) are missing."""
    fid = raw.get("id")
    era = raw.get("tier")
    mission_type = raw.get("missionType")
    if not fid or not era or not mission_type:
        return None
    node = raw.get("node") or ""
    return Fissure(
        id=str(fid),
        era=str(era),
        mission_type=str(mission_type),
        node=node,
        planet=_planet_from_node(node),
        enemy=raw.get("enemy"),
        is_hard=bool(raw.get("isHard")),
        is_storm=bool(raw.get("isStorm")),
        activation=raw.get("activation"),
        expiry=raw.get("expiry"),
    )
