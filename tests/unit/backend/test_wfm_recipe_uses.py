"""Tests for the reverse-recipe-use index."""

from __future__ import annotations

import json
from pathlib import Path

from alecaframe_api.wfm.recipe_uses import RecipeUse, load_recipe_uses


def test_reverse_index_lists_consumers(tmp_path: Path) -> None:
    """Akstiletto is used as a component in Aksomati and Sarpa recipes."""
    (tmp_path / "Secondary.json").write_text(
        json.dumps(
            [
                {
                    "uniqueName": "/Lotus/Weapons/Tenno/Pistol/Akstiletto",
                    "name": "Akstiletto",
                },
                {
                    "uniqueName": "/Lotus/Weapons/Tenno/Pistol/Aksomati",
                    "name": "Aksomati",
                    "components": [
                        {
                            "uniqueName": "/Lotus/Weapons/Tenno/Pistol/Akstiletto",
                            "itemCount": 1,
                        },
                        {
                            "uniqueName": "/Lotus/Types/Items/MiscItems/Gallium",
                            "itemCount": 2,
                        },
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "Melee.json").write_text(
        json.dumps(
            [
                {
                    "uniqueName": "/Lotus/Weapons/Tenno/Melee/Sarpa",
                    "name": "Sarpa",
                    "components": [
                        {
                            "uniqueName": "/Lotus/Weapons/Tenno/Pistol/Akstiletto",
                            "itemCount": 1,
                        },
                    ],
                },
            ]
        ),
        encoding="utf-8",
    )

    idx = load_recipe_uses(cached_json_dir=tmp_path)

    uses = idx.get("/Lotus/Weapons/Tenno/Pistol/Akstiletto") or []
    assert {u.result_name for u in uses} == {"Aksomati", "Sarpa"}
    assert all(u.count_required == 1 for u in uses)
    # Sorted by result_name.
    assert [u.result_name for u in uses] == ["Aksomati", "Sarpa"]

    gallium_uses = idx.get("/Lotus/Types/Items/MiscItems/Gallium") or []
    assert len(gallium_uses) == 1
    assert gallium_uses[0] == RecipeUse(
        result_unique_name="/Lotus/Weapons/Tenno/Pistol/Aksomati",
        result_name="Aksomati",
        count_required=2,
    )


def test_missing_directory_returns_empty(tmp_path: Path) -> None:
    idx = load_recipe_uses(cached_json_dir=tmp_path / "does-not-exist")
    assert idx == {}


def test_items_without_components_are_skipped(tmp_path: Path) -> None:
    """End-product warframes with no recipe shouldn't crash the loader."""
    (tmp_path / "Warframes.json").write_text(
        json.dumps(
            [
                {
                    "uniqueName": "/Lotus/Powersuits/Excalibur/Excalibur",
                    "name": "Excalibur",
                },
            ]
        ),
        encoding="utf-8",
    )
    idx = load_recipe_uses(cached_json_dir=tmp_path)
    assert idx == {}


def test_unreadable_file_is_skipped(tmp_path: Path) -> None:
    (tmp_path / "Primary.json").write_text("{ not valid json", encoding="utf-8")
    (tmp_path / "Secondary.json").write_text(
        json.dumps(
            [
                {
                    "uniqueName": "/A",
                    "name": "A",
                    "components": [{"uniqueName": "/B", "itemCount": 1}],
                },
            ]
        ),
        encoding="utf-8",
    )
    idx = load_recipe_uses(cached_json_dir=tmp_path)
    # Bad file ignored; good file still loaded.
    assert "/B" in idx
