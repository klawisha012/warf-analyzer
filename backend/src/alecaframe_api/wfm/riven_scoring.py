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


# ---- stat vocabulary (fail-closed; S2) -------------------------------------
# Canonical riven-stat classes. Keyed by the WFM v2 attribute `slug` (snapshot
# in data/wfm_riven_attributes.json), plus a few legacy/bare aliases that show
# up in older auction payloads. Classes drive `stat_weight`:
#   crit / status — archetype-sensitive (weight scales with critness/statusness)
#   universal      — strong on ~every gun (flat weight; multishot modulated)
#   utility        — zoom/ammo/recoil etc. (weight 0 as a positive)
#   melee_other    — melee-only stats, weight 0 in the M1 gun engine
# A future WFM rename surfaces as a missing slug in test_riven_vocab's coverage
# test (fail-closed), not as a silently zero-weighted stat.
_CRIT = "crit"
_STATUS = "status"
_UNIVERSAL = "universal"
_UTILITY = "utility"
_MELEE_OTHER = "melee_other"

STAT_CLASS: dict[str, str] = {
    # --- archetype: crit ---
    "critical_chance": _CRIT,
    "critical_damage": _CRIT,
    "critical_chance_on_slide_attack": _CRIT,
    "critical_chance_on_slide": _CRIT,        # legacy alias
    # --- archetype: status ---
    "status_chance": _STATUS,
    "status_duration": _STATUS,
    # --- universal ---
    "base_damage_/_melee_damage": _UNIVERSAL,
    "damage": _UNIVERSAL,                      # legacy bare alias
    "multishot": _UNIVERSAL,
    "fire_rate_/_attack_speed": _UNIVERSAL,
    "fire_rate": _UNIVERSAL,                   # legacy bare alias
    "cold_damage": _UNIVERSAL, "cold": _UNIVERSAL,
    "heat_damage": _UNIVERSAL, "heat": _UNIVERSAL,
    "electric_damage": _UNIVERSAL, "electricity": _UNIVERSAL,
    "toxin_damage": _UNIVERSAL, "toxin": _UNIVERSAL,
    "impact_damage": _UNIVERSAL,
    "puncture_damage": _UNIVERSAL,
    "slash_damage": _UNIVERSAL,
    "damage_vs_grineer": _UNIVERSAL,
    "damage_vs_corpus": _UNIVERSAL,
    "damage_vs_infested": _UNIVERSAL,
    # --- utility (weight 0 as a positive; ~free as a negative) ---
    "ammo_maximum": _UTILITY,
    "magazine_capacity": _UTILITY,
    "punch_through": _UTILITY,
    "projectile_speed": _UTILITY,
    "recoil": _UTILITY,
    "reload_speed": _UTILITY,
    "zoom": _UTILITY,
    # --- melee-only (out of the M1 gun engine; weight 0) ---
    "range": _MELEE_OTHER,
    "combo_duration": _MELEE_OTHER,
    "channeling_damage": _MELEE_OTHER,
    "channeling_efficiency": _MELEE_OTHER,
    "chance_to_gain_combo_count": _MELEE_OTHER,
    "chance_to_gain_extra_combo_count": _MELEE_OTHER,
    "finisher_damage": _MELEE_OTHER,
}

_W_ARCHETYPE = 2.0
_W_UNIVERSAL = 1.0
_MULTISHOT_PENALTY = 0.5   # beam/AoE multishot scales poorly → down-weighted


def _norm_stat(stat: str | None) -> str:
    return (stat or "").lower().strip().replace(" ", "_").replace("-", "_")


def stat_class(stat: str | None) -> str | None:
    """Class of a riven stat (crit/status/universal/utility/melee_other), or
    None if the stat is unknown to the vocabulary."""
    return STAT_CLASS.get(_norm_stat(stat))


def stat_weight(stat: str, profile: Profile) -> float:
    """Weight of a positive riven stat for this weapon profile.

    Archetype-sensitive stats scale continuously with critness/statusness (no
    hard buckets — a weapon at CC 0.199 vs 0.201 must not flip). Universal stats
    carry a flat weight; utility/unknown stats are zero.
    """
    cls = stat_class(stat)
    if cls == _CRIT:
        return _W_ARCHETYPE * profile.critness
    if cls == _STATUS:
        return _W_ARCHETYPE * profile.statusness
    if cls == _UNIVERSAL:
        if _norm_stat(stat) == "multishot":
            trigger = (profile.stats.get("trigger") or "").lower()
            wtype = (profile.stats.get("type") or "").lower()
            if trigger == "held" or wtype == "launcher":
                return _W_UNIVERSAL * _MULTISHOT_PENALTY
            return _W_UNIVERSAL
        return _W_UNIVERSAL
    return 0.0


# ---- roll-value grading (S2) -----------------------------------------------
# Nominal max roll magnitude (percent) for a 2-positive / 0-negative riven at
# disposition 1.0. The achievable ceiling for a given roll is this value scaled
# by the buff/curse multiplier (more positives → smaller each; a curse boosts
# the positives) and by the weapon's disposition. A roll's value is graded as a
# fraction of that ceiling, so +180% CD outscores +90% CD. These are deliberately
# coarse M1 constants (no full per-dispo min/max math — that is M2); the
# calibration gate (test_rivens_calibration) checks god rolls still reach S.
# Stats absent here get full presence credit (grade_roll_value == 1.0) rather
# than being mis-normalized against an unknown ceiling (e.g. faction `multiply`).
_NOMINAL_MAX: dict[str, float] = {
    "critical_chance": 180.0,
    "critical_damage": 180.0,
    "multishot": 180.0,
    "status_chance": 180.0,
    "status_duration": 180.0,
    "base_damage_/_melee_damage": 165.0, "damage": 165.0,
    "cold_damage": 180.0, "cold": 180.0,
    "heat_damage": 180.0, "heat": 180.0,
    "electric_damage": 180.0, "electricity": 180.0,
    "toxin_damage": 180.0, "toxin": 180.0,
    "impact_damage": 180.0,
    "puncture_damage": 180.0,
    "slash_damage": 180.0,
    "fire_rate_/_attack_speed": 90.0, "fire_rate": 90.0,
}


def _buff_factor(stat_count: int, has_negative: bool) -> float:
    """Multiplier on the nominal ceiling from the roll's buff/curse shape.

    Mirrors Warframe's riven value scaling: more positives shrink each stat; a
    curse boosts the positives. A roll with fewer positives and a curse rolls
    higher numbers, so its per-stat ceiling is higher.
    """
    if stat_count >= 3:
        return 0.9375 if has_negative else 0.75
    return 1.2375 if has_negative else 1.0


def grade_roll_value(
    stat: str, value: float, stat_count: int, has_negative: bool, disposition: float,
) -> float:
    """How close a rolled stat is to its achievable max, in [0, 1].

    ceiling = nominal_max(stat) × buff_factor(stat_count, has_negative) × disposition
    A low-disposition weapon rolls smaller numbers, so the same numeric value is
    relatively closer to its (lower) ceiling — graded higher. Unknown stats get
    full credit (1.0) so we never mis-normalize against a ceiling we don't know.
    """
    nominal = _NOMINAL_MAX.get(_norm_stat(stat))
    if nominal is None:
        return 1.0
    dispo = disposition if disposition and disposition > 0 else 1.0
    ceiling = nominal * _buff_factor(stat_count, has_negative) * dispo
    if ceiling <= 0:
        return 1.0
    return _clamp01(abs(value) / ceiling)


def negative_penalty(stat: str, profile: Profile) -> float:
    """Cost of a curse (negative stat), contextual to the build.

    A curse hurts in proportion to how much that stat would have helped: an
    archetype-fatal curse (−CC on a crit weapon) carries the full archetype
    weight; a dead/utility curse (−zoom, −recoil) costs ≈0. This replaces the
    old static FATAL/HARMLESS sets — the context decides, not a hardcoded list.
    """
    return stat_weight(stat, profile)


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


def build_profiles(weapon_row: dict, incarnon=None) -> list[Profile]:
    """Compute a weapon's combat profile set: base (+ Incarnon when curated).

    Returns [] when the row has no usable base stats AND no Incarnon profile (a
    WFCD data gap) so the caller renders it as `unscored` rather than emitting a
    confident grade off all-zero stats.

    `incarnon` is duck-typed (any object exposing `crit_chance`, `status_chance`,
    `weapon_type`, optional `crit_damage`) — typically a reference
    `IncarnonProfile`. Kept structural so scoring stays decoupled from the
    reference layer (no import cycle). The Incarnon profile inherits the
    weapon's disposition (Incarnon shares the base weapon's omegaAttenuation).
    """
    profiles: list[Profile] = []
    stats = weapon_row.get("stats") or {}
    dispo = stats.get("omega_attenuation") or 1.0
    if stats:
        profiles.append(Profile(
            kind="base",
            critness=critness(stats),
            statusness=statusness(stats),
            stats=stats,
            omega_attenuation=dispo,
        ))
    if incarnon is not None:
        inc_stats = {
            "crit_chance": incarnon.crit_chance,
            "status_chance": incarnon.status_chance,
            "crit_damage": getattr(incarnon, "crit_damage", None),
            "type": incarnon.weapon_type,
        }
        profiles.append(Profile(
            kind="incarnon",
            critness=critness(inc_stats),
            statusness=statusness(inc_stats),
            stats=inc_stats,
            omega_attenuation=dispo,
        ))
    return profiles


def _grade(score: int) -> str:
    for letter, lo in _GRADE_CUTOFFS:
        if score >= lo:
            return letter
    return "F"


def _score_one(attrs: list[dict], profile: Profile) -> ProfileScore:
    positives = [a for a in attrs if a.get("positive")]
    negatives = [a for a in attrs if not a.get("positive")]
    n_pos = len(positives)
    has_neg = bool(negatives)
    dispo = profile.omega_attenuation or 1.0
    # Each positive contributes its weight scaled by how good the roll *value* is
    # (S2): +180% CD earns more than +90% CD. Curses subtract a contextual
    # penalty (archetype-fatal curse ≈ full weight, dead curse ≈ 0).
    raw = 0.0
    for a in positives:
        name = a.get("name", "")
        gv = grade_roll_value(name, a.get("value") or 0.0, n_pos, has_neg, dispo)
        raw += stat_weight(name, profile) * gv
    raw -= sum(negative_penalty(a.get("name", ""), profile) for a in negatives)
    # Normalize against a realistic ideal roll: ONE stat at the best archetype
    # weight achievable on this profile + the remaining slots at solid universal
    # weight. (Not n_pos × archetype_max — that all-archetype ideal under-grades
    # real god rolls, which mix one archetype stat with multishot/element/damage,
    # and fails the calibration gate. Two archetype stats, e.g. CC+CD, overshoot
    # this ideal and clamp to S — correct, that *is* an S roll.) A raw-damage
    # weapon (critness=statusness=0) still reaches S on its best universal roll.
    denom_n = max(1, n_pos)
    profile_max = max(_W_UNIVERSAL, _W_ARCHETYPE * max(profile.critness, profile.statusness))
    ideal = profile_max + (denom_n - 1) * _W_UNIVERSAL
    score = int(round(100 * max(0.0, raw) / ideal))
    score = 0 if score < 0 else 100 if score > 100 else score
    return ProfileScore(kind=profile.kind, score=score, grade=_grade(score))


# How close an Incarnon profile must be to the top score to win the headline.
# Endgame play is through the Incarnon form, so when it's within a few points of
# the best profile it's the default the player cares about.
_HEADLINE_EPSILON = 5


def score_riven(attrs: list[dict], profiles: list[Profile]) -> RivenScore:
    """Score a riven (its attribute list) against a weapon's profile set.

    Headline = the best-scoring profile, except an Incarnon profile within
    `_HEADLINE_EPSILON` of the best wins (endgame default). Callers handle the
    unscored case via `score_unscored`.
    """
    if not profiles:
        return score_unscored("no_base_profile")
    per_profile = [_score_one(attrs, p) for p in profiles]
    best = max(per_profile, key=lambda ps: ps.score)
    headline = best
    inc = next((ps for ps in per_profile if ps.kind == "incarnon"), None)
    if inc is not None and inc.score >= best.score - _HEADLINE_EPSILON:
        headline = inc
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


# ---- market signal (S4) ----------------------------------------------------
# Crosses the weapon-aware quality grade with the live market price to flag
# where quality and price disagree. `median` is the overall market median for
# the weapon (compute_tier_stats over all auctions).
_STEAL_GRADES = {"S", "A"}
# Require a meaningful margin off the median, not a 1-platinum difference (which
# is noise on cheap-median weapons). 0.8 mirrors `detect_outliers`'s existing
# "meaningfully cheap" threshold; 1.25 is its inverse for the overpriced side.
# NOTE: ratios + the use of the OVERALL median (vs a peer/tier median) and
# outlier-trimming of the reference price are calibration choices to revisit in
# S2's calibration gate against real god-roll data (see #3).
_STEAL_RATIO = 0.8
_TRAP_RATIO = 1.25


def classify_market_signal(
    grade: str | None, buyout_price: int | None, median: int | None,
) -> str | None:
    """Cross the quality grade with the market price.

    - "steal": a strong roll (S/A) priced at/below 0.8x the market median —
      good and undervalued, the actionable buy.
    - "trap": junk (F) priced at/above 1.25x the market median — overpriced.
    Returns None when inputs are missing or the price is within the fair band.
    """
    if grade is None or buyout_price is None or buyout_price <= 0 or not median or median <= 0:
        return None
    if grade in _STEAL_GRADES and buyout_price <= _STEAL_RATIO * median:
        return "steal"
    if grade == "F" and buyout_price >= _TRAP_RATIO * median:
        return "trap"
    return None
