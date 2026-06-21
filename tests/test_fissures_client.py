from __future__ import annotations

import json
from pathlib import Path

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.fissures.client import FissureClient, FissureClientError


def _fixture() -> list[dict]:
    p = Path(__file__).parent / "fixtures" / "wfm_fissures_sample.json"
    return json.loads(p.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_get_fissures_parses(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://wf.test/pc/fissures", method="GET", json=_fixture(),
    )
    c = FissureClient(base_url="https://wf.test", platform="pc")
    out = await c.get_fissures(now=1000.0)
    assert len(out) == 3
    assert {f.era for f in out} == {"Omnia", "Neo", "Lith"}


@pytest.mark.asyncio
async def test_get_fissures_uses_ttl_cache(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://wf.test/pc/fissures", method="GET", json=_fixture(),
    )
    c = FissureClient(base_url="https://wf.test", platform="pc", cache_ttl=30.0)
    await c.get_fissures(now=1000.0)
    await c.get_fissures(now=1010.0)  # within TTL -> served from cache
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_platform_maps_to_warframestat_segment(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://wf.test/xb1/fissures", method="GET", json=[])
    c = FissureClient(base_url="https://wf.test", platform="xbox")
    await c.get_fissures(now=1.0)
    assert str(httpx_mock.get_request().url).endswith("/xb1/fissures")


@pytest.mark.asyncio
async def test_raises_on_5xx(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(url="https://wf.test/pc/fissures", method="GET", status_code=502)
    c = FissureClient(base_url="https://wf.test", platform="pc")
    with pytest.raises(FissureClientError):
        await c.get_fissures(now=1.0)
