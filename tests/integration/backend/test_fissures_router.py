from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from alecaframe_api.db.repo import Repo
from alecaframe_api.fissures.models import Fissure
from alecaframe_api.fissures.router import router
from alecaframe_api.fissures.dependencies import get_fissure_client, get_node_catalog
from alecaframe_api.wfm.dependencies import get_repo


class _FakeClient:
    async def get_fissures(self, *, now=None, fresh=False) -> list[Fissure]:
        return [Fissure(id="a1", era="Axi", mission_type="Survival", node="X (Eris)",
                        planet="Eris", enemy="Infested", is_hard=False, is_storm=False,
                        activation=None, expiry=None)]


class _FakeCatalog:
    async def get(self, *, now=None) -> dict[str, list[str]]:
        return {"Sedna": ["Adaro (Sedna)", "Kappa (Sedna)"], "Neptune": ["Galatea (Neptune)"]}


@pytest.fixture
async def client(tmp_path):
    repo = Repo(db_path=tmp_path / "t.db")
    await repo.connect()
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_repo] = lambda: repo
    app.dependency_overrides[get_fissure_client] = lambda: _FakeClient()
    app.dependency_overrides[get_node_catalog] = lambda: _FakeCatalog()
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


@pytest.mark.asyncio
async def test_meta_includes_planets_and_nodes(client: httpx.AsyncClient) -> None:
    r = await client.get("/fissures/meta")
    assert r.status_code == 200
    body = r.json()
    assert "Eris" in body["planets"]       # live planet from the fake client
    assert "Neptune" in body["planets"]     # static known planet
    assert "X (Eris)" in body["nodes"]      # live node from the fake client


@pytest.mark.asyncio
async def test_subscription_with_planet_and_node(client: httpx.AsyncClient) -> None:
    r = await client.post("/fissures/subscriptions",
                          json={"planet": "Neptune", "node": "Proteus"})
    assert r.status_code == 201
    item = r.json()["items"][0]
    assert item["planet"] == "Neptune"
    assert item["node"] == "Proteus"


@pytest.mark.asyncio
async def test_meta_includes_nodes_by_planet(client: httpx.AsyncClient) -> None:
    r = await client.get("/fissures/meta")
    assert r.status_code == 200
    body = r.json()
    # full star-chart catalogue (incl. nodes with no live fissure right now)
    assert body["nodes_by_planet"]["Sedna"] == ["Adaro (Sedna)", "Kappa (Sedna)"]
    # catalogue planets are unioned into the selectable planet list
    assert "Sedna" in body["planets"]
