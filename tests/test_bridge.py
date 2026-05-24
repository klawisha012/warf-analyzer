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
        url="http://agent.test/refresh", method="POST",
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
