from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.models import Fissure
from alecaframe_api.fissures.router import router
from alecaframe_api.fissures.dependencies import get_fissure_client
from alecaframe_api.wfm.dependencies import get_repo


class _FakeClient:
    async def get_fissures(self, *, now=None, fresh=False) -> list[Fissure]:
        return [Fissure(id="a1", era="Axi", mission_type="Survival", node="X (Eris)",
                        planet="Eris", enemy="Infested", is_hard=False, is_storm=False,
                        activation=None, expiry=None)]


@pytest.fixture
async def client(tmp_path):
    repo = Repo(db_path=tmp_path / "t.db")
    await repo.connect()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_fissure_client] = lambda: _FakeClient()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        yield c
    await repo.close()


@pytest.mark.asyncio
async def test_live_fissures(client: httpx.AsyncClient) -> None:
    r = await client.get("/fissures")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1 and body["items"][0]["era"] == "Axi"


@pytest.mark.asyncio
async def test_meta_includes_eras_and_live_mission(client: httpx.AsyncClient) -> None:
    r = await client.get("/fissures/meta")
    assert r.status_code == 200
    body = r.json()
    assert "Axi" in body["eras"]
    assert "Survival" in body["mission_types"]


@pytest.mark.asyncio
async def test_subscription_crud(client: httpx.AsyncClient) -> None:
    r = await client.post("/fissures/subscriptions", json={"era": "Axi", "is_hard": True})
    assert r.status_code == 201
    body = r.json()
    assert body["total"] == 1
    sub_id = body["items"][0]["id"]
    assert body["items"][0]["era"] == "Axi"
    assert body["items"][0]["is_hard"] is True

    r = await client.delete(f"/fissures/subscriptions/{sub_id}")
    assert r.status_code == 200
    r = await client.get("/fissures/subscriptions")
    assert r.json()["total"] == 0

    r = await client.delete(f"/fissures/subscriptions/{sub_id}")
    assert r.status_code == 404
