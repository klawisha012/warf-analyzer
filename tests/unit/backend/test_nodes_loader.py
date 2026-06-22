from __future__ import annotations

from alecaframe_api.reference.nodes_loader import build_nodes_by_planet


def test_build_nodes_by_planet_groups_sorts_dedupes_and_skips_junk() -> None:
    # Shape mirrors WFCD warframe-worldstate-data solNodes.json: keyed by
    # SolNodeN, each {value: "<Node> (<Planet>)", enemy, type}. Entries with no
    # parenthesised planet (e.g. SolNode0) are not real star-chart nodes.
    sample = {
        "SolNode0": {
            "value": "SolNode0",
            "enemy": "Sentient",
            "type": "Ancient Retribution",
        },
        "SolNode1": {
            "value": "Galatea (Neptune)",
            "enemy": "Corpus",
            "type": "Capture",
        },
        "SolNode2": {"value": "Kappa (Sedna)", "enemy": "Grineer", "type": "Survival"},
        "SolNode3": {
            "value": "Adaro (Sedna)",
            "enemy": "Grineer",
            "type": "Exterminate",
        },
        "SolNode4": {
            "value": "Adaro (Sedna)",
            "enemy": "Grineer",
            "type": "Exterminate",
        },
    }
    out = build_nodes_by_planet(sample)

    assert out["Sedna"] == ["Adaro (Sedna)", "Kappa (Sedna)"]  # sorted + deduped
    assert out["Neptune"] == ["Galatea (Neptune)"]
    assert "SolNode0" not in out and "" not in out  # junk / empty planet skipped
    assert set(out) == {"Neptune", "Sedna"}


def test_build_nodes_by_planet_handles_empty_and_malformed() -> None:
    assert build_nodes_by_planet({}) == {}
    # non-dict values and missing 'value' are skipped without raising
    assert build_nodes_by_planet({"a": "x", "b": {}, "c": {"value": None}}) == {}
