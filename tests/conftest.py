"""Shared pytest fixtures."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Fresh data dir with realistic dummy lastData / deltas / _meta JSONs."""
    d = tmp_path / "data"
    d.mkdir()
    (d / "lastData.json").write_text(
        json.dumps(
            {
                "PremiumCredits": 169,
                "RegularCredits": 32_539_253,
                "FusionPoints": 95_705,
                "PrimeTokens": 0,
                "TradesRemaining": 8,
                "GiftsRemaining": 15,
                "PlayerLevel": 15,
                "Suits": [
                    {
                        "ItemType": "/Lotus/Powersuits/Cowgirl/MesaPrime",
                        "XP": 125_738_693,
                        "ItemId": {"$oid": "test-mesa-id"},
                    }
                ],
                "RawUpgrades": [],
                "MiscItems": [],
                "Recipes": [],
            }
        ),
        encoding="utf-8",
    )
    (d / "deltas.json").write_text(
        json.dumps({"savedCleanly": True, "previousMiscState": [], "currentDeltas": {}}),
        encoding="utf-8",
    )
    (d / "_meta.json").write_text(
        json.dumps(
            {
                "ok": True,
                "elapsed_ms": 200,
                "meta": {
                    "wfm_username": "test-user",
                    "aleca_version": "2.6.87",
                    "extension_dir": "C:/fake",
                    "aleca_data_dir": "C:/fake",
                    "cached_json_dir": "C:/fake/json",
                },
            }
        ),
        encoding="utf-8",
    )
    return d
