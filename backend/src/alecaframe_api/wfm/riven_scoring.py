"""Weapon-aware riven scoring engine.

Everything here is a pure function (no I/O, no async) so the router and the
poller can share it and the tests stay fast — same ethos as `rivens_analysis`
(which it complements: that module scores the *market*, this one scores the
*stat quality for the specific weapon*).

The join from a riven auction to a weapon's base stats goes through the
weapon's **display name**, not the WFM slug: WFM riven slugs do not map to the
WFCD `uniqueName` deterministically (e.g. `torid` -> `/Lotus/Weapons/ClanTech/
Bio/BioWeapon`). Callers pass a name-keyed index of `item_base_stats` rows.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    """One combat profile of a weapon (base form in M1; Incarnon/perk in M2)."""
    kind: str                 # "base" | "incarnon" | "perk"
    critness: float           # [0, 1]
    statusness: float         # [0, 1]
    stats: dict               # the weapon's effective base stats for this profile
    omega_attenuation: float  # riven-disposition multiplier


# Base-stat values at/above which a weapon reads as fully crit/status oriented.
# Tuned at the top of the typical base range; calibration against real god-rolls
# is S2's blocking gate. Kept as module constants so they're easy to sweep.
CC_REF = 0.30
STATUS_REF = 0.30


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def normalize_name(name: str | None) -> str:
    """Canonical key for the name join: lowercased, trimmed."""
    return (name or "").strip().lower()


def critness(stats: dict) -> float:
    """How crit-oriented the weapon is, in [0, 1], from base crit chance."""
    return _clamp01((stats.get("crit_chance") or 0.0) / CC_REF)


def statusness(stats: dict) -> float:
    """How status-oriented the weapon is, in [0, 1], from base status chance."""
    return _clamp01((stats.get("status_chance") or 0.0) / STATUS_REF)


# ---- stat vocabulary (minimal for M1; fail-closed full vocab is S2) --------
# Archetype-sensitive: weight scales with the weapon's critness/statusness.
_CRIT_STATS = {"critical_chance", "critical_damage", "critical_chance_on_slide"}
_STATUS_STATS = {"status_chance"}
# Universal: strong on virtually every weapon → archetype-independent weight.
# Defensive UNION of known spellings: WFM's v2 attribute slugs use the suffixed
# forms (base_damage_/_melee_damage, toxin_damage, electric_damage,
# damage_vs_<faction>), while older code/auctions may use bare forms. Matching
# either is correct; an unused key is harmless. The authoritative fail-closed
# vocab (snapshot of /riven/attributes + coverage test) lands in S2 (#3).
_UNIVERSAL_STATS = {
    "damage", "base_damage_/_melee_damage",
    "multishot", "fire_rate", "fire_rate_/_attack_speed",
    "toxin", "toxin_damage", "cold", "cold_damage",
    "heat", "heat_damage", "electricity", "electric_damage",
    "damage_vs_grineer", "damage_vs_corpus", "damage_vs_infested",
}

_W_ARCHETYPE = 2.0
_W_UNIVERSAL = 1.0
_MULTISHOT_PENALTY = 0.5   # beam/AoE multishot scales poorly → down-weighted


def _norm_stat(stat: str | None) -> str:
    return (stat or "").lower().strip().replace(" ", "_").replace("-", "_")


def stat_weight(stat: str, profile: Profile) -> float:
    """Weight of a positive riven stat for this weapon profile.

    Archetype-sensitive stats scale continuously with critness/statusness (no
    hard buckets — a weapon at CC 0.199 vs 0.201 must not flip). Universal stats
    carry a flat weight; utility/unknown stats are zero.
    """
    s = _norm_stat(stat)
    if s in _CRIT_STATS:
        return _W_ARCHETYPE * profile.critness
    if s in _STATUS_STATS:
        return _W_ARCHETYPE * profile.statusness
    if s == "multishot":
        trigger = (profile.stats.get("trigger") or "").lower()
        wtype = (profile.stats.get("type") or "").lower()
        if trigger == "held" or wtype == "launcher":
            return _W_UNIVERSAL * _MULTISHOT_PENALTY
        return _W_UNIVERSAL
    if s in _UNIVERSAL_STATS:
        return _W_UNIVERSAL
    return 0.0


# ---- scoring ---------------------------------------------------------------

# Grade letter cutoffs over the 0-100 score.
_GRADE_CUTOFFS = (("S", 85), ("A", 70), ("B", 50), ("C", 30), ("F", 0))


@dataclass(frozen=True)
class ProfileScore:
    kind: str
    score: int        # 0-100
    grade: str        # S/A/B/C/F


@dataclass(frozen=True)
class RivenScore:
    unscored: bool
    headline: ProfileScore | None
    per_profile: list[ProfileScore]
    reason: str | None = None   # set when unscored


# Gun categories the M1 engine scores. Melee (range/attack_speed/combo) needs
# its own stat track → S2; everything else is `unscored` with a distinct reason.
_SCOREABLE_CATEGORIES = {"primary", "secondary", "sentinel_weapon", "arch_gun"}


def is_scoreable_category(category: str | None) -> bool:
    """True for gun categories the M1 engine grades (A6); False for melee/unknown."""
    return category in _SCOREABLE_CATEGORIES


def build_profiles(weapon_row: dict) -> list[Profile]:
    """Compute a weapon's combat profiles. M1 ships the base form only;
    Incarnon/perk profiles are added in S3 behind the same interface.

    Returns [] when the row has no usable base stats (a WFCD data gap) so the
    caller renders it as `unscored` rather than emitting a confident grade off
    of all-zero stats. `omega_attenuation` is plumbed here but consumed in S2's
    roll-value grading, not in S1's presence-based score.
    """
    stats = weapon_row.get("stats") or {}
    if not stats:
        return []
    return [Profile(
        kind="base",
        critness=critness(stats),
        statusness=statusness(stats),
        stats=stats,
        omega_attenuation=stats.get("omega_attenuation") or 1.0,
    )]


def _grade(score: int) -> str:
    for letter, lo in _GRADE_CUTOFFS:
        if score >= lo:
            return letter
    return "F"


def _score_one(attrs: list[dict], profile: Profile) -> ProfileScore:
    positives = [a for a in attrs if a.get("positive")]
    negatives = [a for a in attrs if not a.get("positive")]
    # S1 is presence-based: roll *values* (grade_roll_value) arrive in S2.
    raw = sum(stat_weight(a.get("name", ""), profile) for a in positives)
    raw -= sum(stat_weight(a.get("name", ""), profile) for a in negatives)
    # Normalize against the ideal roll = every positive at the best weight
    # ACHIEVABLE on THIS profile, not a global archetype max. Otherwise a
    # raw-damage weapon (critness=statusness=0, so archetype stats weigh 0)
    # could never exceed B on its best possible universal roll.
    n_pos = max(1, len(positives))
    profile_max = max(_W_UNIVERSAL, _W_ARCHETYPE * max(profile.critness, profile.statusness))
    ideal = n_pos * profile_max
    score = int(round(100 * max(0.0, raw) / ideal))
    score = 0 if score < 0 else 100 if score > 100 else score
    return ProfileScore(kind=profile.kind, score=score, grade=_grade(score))


def score_riven(attrs: list[dict], profiles: list[Profile]) -> RivenScore:
    """Score a riven (its attribute list) against a weapon's profile set.

    Headline = the best-scoring profile (M1 has only `base`; S3 adds the
    Incarnon-preferring tiebreak). Callers handle the unscored case via
    `score_unscored`.
    """
    if not profiles:
        return score_unscored("no_base_profile")
    per_profile = [_score_one(attrs, p) for p in profiles]
    headline = max(per_profile, key=lambda ps: ps.score)
    return RivenScore(unscored=False, headline=headline, per_profile=per_profile)


def score_unscored(reason: str) -> RivenScore:
    """A riven we deliberately don't grade (no base profile, melee, etc.)."""
    return RivenScore(unscored=True, headline=None, per_profile=[], reason=reason)


# Display-name overrides bridge genuine WFM-item -> WFCD-name mismatches.
# Most weapons (incl. Kuva/Tenet variants, which are distinct WFCD rows) join
# directly by name; this map stays small and grows only on observed collisions.
WEAPON_NAME_OVERRIDES: dict[str, str] = {}


def resolve_weapon(
    item_name: str,
    index: dict[str, dict],
    *,
    overrides: dict[str, str] = WEAPON_NAME_OVERRIDES,
) -> dict | None:
    """Resolve a riven weapon's base-stats row by normalized display name.

    `index` maps normalized WFCD name -> base-stats row. Returns the row, or
    None when the weapon is absent (caller renders it as `unscored`).
    """
    key = normalize_name(item_name)
    key = overrides.get(key, key)
    return index.get(key)
