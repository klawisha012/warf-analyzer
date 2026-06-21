"""HTTP-level tests for the host decrypt-agent."""
from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def agent_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Any:
    """Build the agent app pointed at a tmp data dir, with subprocess monkey-patched."""
    out_dir = tmp_path / "data"
    out_dir.mkdir()
    (out_dir / "lastData.json").write_text('{"_test":1}', encoding="utf-8")

    token_file = tmp_path / "WFMarketToken.tk"
    token_file.write_text("FAKE.JWT.TOKEN", encoding="utf-8")

    monkeypatch.setenv("AGENT_OUT_DIR", str(out_dir))
    monkeypatch.setenv("AGENT_TOKEN_FILE", str(token_file))
    monkeypatch.setenv("AGENT_DUMP_SCRIPT", "")  # disables real pwsh call

    from decrypt_agent.main import build_app
    return build_app()


@pytest.mark.asyncio
async def test_healthz(agent_app: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://test") as ac:
        r = await ac.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True


@pytest.mark.asyncio
async def test_get_wfm_token(agent_app: Any) -> None:
    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://test") as ac:
        r = await ac.get("/wfm-token")
    assert r.status_code == 200
    assert r.json() == {"token": "FAKE.JWT.TOKEN"}


@pytest.mark.asyncio
async def test_refresh_without_script_returns_stub(agent_app: Any) -> None:
    """With AGENT_DUMP_SCRIPT empty, /refresh returns a stub result instead of running pwsh."""
    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://test") as ac:
        r = await ac.post("/refresh")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["stub"] is True


@pytest.mark.asyncio
async def test_toast_endpoint_accepts_payload(agent_app: Any) -> None:
    """Toast endpoint must accept title/body and return 202 even if no GUI."""
    async with AsyncClient(transport=ASGITransport(app=agent_app), base_url="http://test") as ac:
        r = await ac.post("/toast", json={"title": "Hi", "body": "Test", "click_url": None})
    assert r.status_code in (202, 200)
