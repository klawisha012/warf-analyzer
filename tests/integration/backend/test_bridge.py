"""Tests for the HTTP-bridge backend reading agent-decrypted JSON from disk."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.bridge import AlecaBridge, BridgeError


@pytest.mark.asyncio
async def test_lastdata_reads_from_disk(tmp_data_dir: Path) -> None:
    br = AlecaBridge(agent_url="http://agent.invalid", data_dir=tmp_data_dir)
    br.reload_from_disk(force=True)
    data = await br.lastdata()
    assert data["PremiumCredits"] == 169


@pytest.mark.asyncio
async def test_refresh_calls_agent_then_reloads(
    tmp_data_dir: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="http://agent.test/refresh",
        method="POST",
        json={"ok": True, "stub": True, "elapsed_ms": 1, "files": {}, "meta": {}},
    )
    br = AlecaBridge(agent_url="http://agent.test", data_dir=tmp_data_dir)
    result = await br.refresh()
    assert result["ok"] is True
    data = await br.lastdata()
    assert data["PlayerLevel"] == 15


@pytest.mark.asyncio
async def test_refresh_agent_down_raises(
    tmp_data_dir: Path, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_exception(
        httpx.ConnectError("connection refused"),
        url="http://agent.test/refresh",
        method="POST",
    )
    br = AlecaBridge(agent_url="http://agent.test", data_dir=tmp_data_dir)
    with pytest.raises(BridgeError):
        await br.refresh()


@pytest.mark.asyncio
async def test_lastdata_works_offline_if_disk_has_file(tmp_data_dir: Path) -> None:
    """Even if the agent is unreachable, on-disk JSON serves reads."""
    br = AlecaBridge(agent_url="http://nope.invalid", data_dir=tmp_data_dir)
    data = await br.lastdata()
    assert "PremiumCredits" in data


@pytest.mark.asyncio
async def test_lastdata_unwraps_mission_completion_wrapper(tmp_path: Path) -> None:
    """If lastData.json is a mission-completion wrapper, the bridge unwraps InventoryJson.

    AlecaFrame's lastData.dat can hold post-mission events whose payload nests
    the real inventory as a JSON-string under the InventoryJson key.
    """
    import json

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    real_inventory = {
        "PremiumCredits": 169,
        "RegularCredits": 32_539_253,
        "Suits": [{"ItemType": "/Lotus/Powersuits/Cowgirl/MesaPrime", "XP": 1}],
        "MiscItems": [
            {"ItemType": "/Lotus/Types/Items/Misc/Rubedo", "ItemCount": 10000}
        ],
        "Recipes": [],
    }
    wrapper = {
        "InventoryChanges": {},
        "MissionRewards": [],
        "TotalCredits": [],
        "InventoryJson": json.dumps(real_inventory),
    }
    (data_dir / "lastData.json").write_text(json.dumps(wrapper), encoding="utf-8")
    (data_dir / "_meta.json").write_text(
        '{"meta":{"wfm_username":"x"}}', encoding="utf-8"
    )

    br = AlecaBridge(agent_url="http://agent.invalid", data_dir=data_dir)
    br.reload_from_disk(force=True)
    data = await br.lastdata()
    # We get the unwrapped 173-key shape, not the 4-key wrapper.
    assert data["PremiumCredits"] == 169
    assert len(data["Suits"]) == 1
    assert len(data["MiscItems"]) == 1
    assert "InventoryJson" not in data  # wrapper key gone after unwrap


@pytest.mark.asyncio
async def test_lastdata_passes_through_when_not_wrapped(tmp_data_dir: Path) -> None:
    """Direct 173-key inventory (no InventoryJson) is returned as-is."""
    br = AlecaBridge(agent_url="http://agent.invalid", data_dir=tmp_data_dir)
    br.reload_from_disk(force=True)
    data = await br.lastdata()
    # tmp_data_dir fixture writes a direct-shape lastData.json with PremiumCredits at top.
    assert "InventoryJson" not in data
    assert data["PremiumCredits"] == 169
