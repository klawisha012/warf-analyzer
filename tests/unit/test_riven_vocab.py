"""Fail-closed coverage test for the riven stat vocabulary (S2, A5).

The canonical WFM v2 attribute set is snapshotted (committed) at
backend/src/alecaframe_api/reference/wfm_riven_attributes.json. Every slug in
that snapshot MUST resolve to a known class in STAT_CLASS. If WFM renames or
adds an attribute, this test goes red — surfacing the gap loudly instead of
silently zero-weighting a stat in production.
"""
from __future__ import annotations

import json
from importlib.resources import files

import pytest

from alecaframe_api.wfm.riven_scoring import STAT_CLASS, stat_class

_SNAPSHOT = files("alecaframe_api.reference") / "wfm_riven_attributes.json"


def _snapshot_slugs() -> list[str]:
    data = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    return [a["slug"] for a in data["data"]]


def test_snapshot_present_and_nonempty() -> None:
    slugs = _snapshot_slugs()
    assert len(slugs) >= 30  # WFM ships ~32 riven attributes


@pytest.mark.parametrize("slug", _snapshot_slugs())
def test_every_wfm_slug_resolves_to_a_class(slug: str) -> None:
    cls = stat_class(slug)
    assert cls is not None, f"WFM riven slug {slug!r} is not classified in STAT_CLASS"
    assert cls in {"crit", "status", "universal", "utility", "melee_other"}


def test_faction_damage_uses_vs_spelling() -> None:
    # Regression: faction damage on WFM is damage_vs_* (multiply), NOT the old
    # damage_to_* spelling. The snapshot is the source of truth.
    slugs = set(_snapshot_slugs())
    assert "damage_vs_grineer" in slugs
    assert "damage_to_grineer" not in slugs


def test_elements_use_suffixed_damage_spelling() -> None:
    slugs = set(_snapshot_slugs())
    for el in ("heat_damage", "cold_damage", "electric_damage", "toxin_damage"):
        assert el in slugs
        assert stat_class(el) == "universal"


def test_crit_and_status_classes_are_archetype_sensitive() -> None:
    assert STAT_CLASS["critical_chance"] == "crit"
    assert STAT_CLASS["critical_damage"] == "crit"
    assert STAT_CLASS["status_chance"] == "status"
