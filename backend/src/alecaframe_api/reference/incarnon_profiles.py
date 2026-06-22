"""Curated Incarnon-form stat profiles (S3a, #4).

WFCD's warframe-items dataset ships no Incarnon data (verified: 194 primaries,
zero `incarnon/evolution/modes` keys), so the Incarnon archetype shift that makes
the redesign worthwhile (Torid: status launcher in base → crit weapon in Incarnon)
has to be curated by hand. This module is that curated table, behind a typed
Pydantic schema so a malformed/typo'd entry fails at load (a test), never in
production with a confidently-wrong grade.

Scope (M1): the top-traded **gun** Incarnon Genesis weapons. Each entry records
the Incarnon Form's *base* effective stats (the canonical assumption, no specific
EVO4 perk applied — see `evolution_build`), plus provenance (`source_url`,
`entered_date`, `game_version`) and a `verified_by_human` gate.

PROVENANCE NOTE: these values were machine-curated from the official wiki on the
`entered_date` and cross-checked against each weapon's normal-form crit chance for
plausibility, but `verified_by_human=False` on every entry — the HITL sign-off
(#4's blocking gate) is still owed. Soma was deliberately omitted: the fetched
Incarnon CC (10%) is implausible for a base-30%-crit weapon and needs a human check.

Stat scale matches `item_base_stats`: crit_chance/status_chance are fractions
([0,1]), crit_damage is a multiplier (>= 1.0).
"""

from __future__ import annotations

import datetime as _dt

from pydantic import BaseModel, ConfigDict, Field, field_validator

from alecaframe_api.wfm.riven_scoring import normalize_name

# Bump when re-curating against a new game build; entries whose `game_version`
# differs are surfaced with a "may be outdated" badge (A8 freshness).
CURRENT_GAME_VERSION = "wiki-2026-06-22"


class IncarnonProfile(BaseModel):
    """One weapon's Incarnon-form effective stats, for a fixed evolution build."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    weapon_name: str = Field(min_length=1)  # WFCD display name (join key)
    weapon_type: str = Field(
        min_length=1
    )  # for multishot modulation (Launcher/Rifle/...)
    crit_chance: float = Field(ge=0.0, le=1.0)  # fraction, e.g. 0.29
    crit_damage: float = Field(ge=1.0)  # multiplier, e.g. 3.10
    status_chance: float = Field(ge=0.0, le=1.0)  # fraction, e.g. 0.39
    evolution_build: str = Field(min_length=1)  # which build the stats assume
    source_url: str = Field(min_length=1)
    entered_date: _dt.date
    game_version: str = Field(min_length=1)
    verified_by_human: bool = False  # the #4 HITL gate, per entry

    @field_validator("source_url")
    @classmethod
    def _source_is_http(cls, v: str) -> str:
        if not v.startswith("http"):
            raise ValueError("source_url must be an http(s) link for provenance")
        return v


_TODAY = _dt.date(2026, 6, 22)
_BASE = "Incarnon Form base stats (no EVO4 crit perk applied)"


def _p(
    name: str, wtype: str, cc: float, cd: float, sc: float, slug: str
) -> IncarnonProfile:
    return IncarnonProfile(
        weapon_name=name,
        weapon_type=wtype,
        crit_chance=cc,
        crit_damage=cd,
        status_chance=sc,
        evolution_build=_BASE,
        source_url=f"https://wiki.warframe.com/w/{slug}",
        entered_date=_TODAY,
        game_version=CURRENT_GAME_VERSION,
    )


# Curated Incarnon Form base stats. Values from the official wiki (2026-06-22),
# each sanity-checked against the weapon's normal-form crit chance.
INCARNON_PROFILES: list[IncarnonProfile] = [
    _p("Torid", "Launcher", 0.29, 3.10, 0.39, "Torid"),  # base CC 15%, status 27%
    _p("Boltor", "Rifle", 0.22, 2.80, 0.0933, "Boltor"),
    _p("Latron", "Rifle", 0.32, 3.00, 0.24, "Latron"),
    _p("Dread", "Bow", 0.50, 3.00, 0.30, "Dread"),  # Incarnon charged shot
    _p("Braton", "Rifle", 0.30, 3.00, 0.12, "Braton"),  # normal CC 12%
    _p("Burston", "Rifle", 0.30, 3.00, 0.30, "Burston"),  # normal CC 6%
    _p("Sybaris", "Rifle", 0.20, 3.00, 0.20, "Sybaris"),  # normal CC 25%
    _p("Strun", "Shotgun", 0.44, 2.80, 0.40, "Strun"),  # normal CC 7.5%
    _p("Kunai", "Thrown", 0.18, 2.00, 0.16, "Kunai"),  # normal CC 8%
    _p("Vasto", "Pistol", 0.30, 2.80, 0.0267, "Vasto"),  # normal CC 20%
]


# Known Incarnon Genesis *gun* weapons (The Circuit Steel Path rotation, melee
# excluded — M1 is guns only). The missing-curation guard/badge compares this to
# the curated index so uncurated weapons render "Incarnon not curated", not a
# silent gap.
KNOWN_INCARNON_WEAPONS: frozenset[str] = frozenset(
    normalize_name(n)
    for n in (
        "Braton",
        "Lato",
        "Paris",
        "Kunai",
        "Boar",
        "Gammacor",
        "Angstrum",
        "Gorgon",
        "Latron",
        "Furis",
        "Strun",
        "Lex",
        "Boltor",
        "Bronco",
        "Torid",
        "Dual Toxocyst",
        "Miter",
        "Atomos",
        "Soma",
        "Vasto",
        "Burston",
        "Zylok",
        "Dread",
        "Despair",
        "Dera",
        "Sybaris",
        "Cestra",
        "Sicarus",
        "Vectis",
        "Stug",
        "Ballistica",
    )
)


def incarnon_index() -> dict[str, IncarnonProfile]:
    """Curated Incarnon profiles keyed by normalized weapon display name."""
    return {normalize_name(p.weapon_name): p for p in INCARNON_PROFILES}


def is_outdated(profile: IncarnonProfile) -> bool:
    """True when a profile was curated against an older build than the current one."""
    return profile.game_version != CURRENT_GAME_VERSION
