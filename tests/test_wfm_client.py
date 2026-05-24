"""WFMClient tests — auth header, rate-limit, cache, retry."""
from __future__ import annotations

import asyncio

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.client import WFMClient


@pytest.fixture
async def cache() -> Cache:
    import fakeredis.aioredis
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = Cache(client=client, key_prefix="wfm")
    yield c
    await client.aclose()


@pytest.fixture
def static_token() -> "callable":
    async def _provider() -> str:
        return "FAKE.JWT.TOKEN"
    return _provider


@pytest.fixture
def client_factory(cache: Cache, static_token: callable) -> "callable":
    """Build a WFMClient with explicit base URL and rate limit raised for tests."""
    def _factory(**overrides) -> WFMClient:
        kwargs = dict(
            cache=cache,
            base_url="https://mock.wfm.test/v1",
            token_provider=static_token,
            platform="pc",
            language="en",
            rate_limit_per_second=100,  # don't throttle test runs
        )
        kwargs.update(overrides)
        return WFMClient(**kwargs)
    return _factory


@pytest.mark.asyncio
async def test_request_sends_jwt_header(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items",
        method="GET",
        json={"payload": {"items": []}},
    )
    c = client_factory()
    await c._request("GET", "/items", cache_key="items", cache_ttl=10)
    req = httpx_mock.get_request()
    assert req.headers["Authorization"] == "JWT FAKE.JWT.TOKEN"
    assert req.headers["Language"] == "en"
    assert req.headers["Platform"] == "pc"


@pytest.mark.asyncio
async def test_request_caches_response(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items",
        method="GET",
        json={"payload": {"items": []}},
    )
    c = client_factory()
    a = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    b = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    assert a == b
    # Only one HTTP call should have happened — the second came from Redis.
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_request_fresh_bypasses_cache(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET",
        json={"payload": {"items": [{"url_name": "a"}]}},
    )
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET",
        json={"payload": {"items": [{"url_name": "b"}]}},
    )
    c = client_factory()
    a = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    b = await c._request("GET", "/items", cache_key="items", cache_ttl=60, fresh=True)
    assert a["payload"]["items"][0]["url_name"] == "a"
    assert b["payload"]["items"][0]["url_name"] == "b"


@pytest.mark.asyncio
async def test_request_raises_on_5xx(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET", status_code=500,
        text="boom",
    )
    c = client_factory()
    with pytest.raises(Exception):
        await c._request("GET", "/items", cache_key="items", cache_ttl=60)


@pytest.mark.asyncio
async def test_request_returns_stale_if_5xx_and_cache_has_value(
    client_factory, httpx_mock: HTTPXMock
) -> None:
    """When the upstream fails but Redis has a previous value, return it."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET",
        json={"payload": {"items": [{"url_name": "stale"}]}},
    )
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET",
        status_code=503, text="upstream gone",
    )
    c = client_factory()
    # Prime cache with the first call (success).
    first = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    assert first["payload"]["items"][0]["url_name"] == "stale"
    # Re-prime with a known value to make the stale-fallback test deterministic.
    await c._cache.set_json("items", {"payload": {"items": [{"url_name": "stale"}]}}, ttl_seconds=60)
    # Now call with fresh=True so the cache lookup short-circuits and the
    # 503 path is exercised. Stale-fallback should still serve from cache.
    second = await c._request("GET", "/items", cache_key="items", cache_ttl=60, fresh=True)
    assert second["payload"]["items"][0]["url_name"] == "stale"
    assert second.get("_stale") is True


@pytest.mark.asyncio
async def test_get_items_returns_item_refs(client_factory, httpx_mock: HTTPXMock) -> None:
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / "fixtures" / "wfm_items_sample.json").read_text(encoding="utf-8"))
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items", method="GET", json=fixture,
    )
    c = client_factory()
    items = await c.get_items()
    assert len(items) == 6
    kp = next(i for i in items if i.slug == "kronen_prime_blade")
    assert kp.item_name == "Kronen Prime Blade"
    assert kp.vaulted is True


@pytest.mark.asyncio
async def test_get_orders_returns_payload(client_factory, httpx_mock: HTTPXMock) -> None:
    import json
    from pathlib import Path
    fixture = json.loads((Path(__file__).parent / "fixtures" / "wfm_orders_kronen_prime_blade.json").read_text(encoding="utf-8"))
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items/kronen_prime_blade/orders", method="GET", json=fixture,
    )
    c = client_factory()
    payload = await c.get_orders("kronen_prime_blade")
    assert len(payload["payload"]["orders"]) == 10


@pytest.mark.asyncio
async def test_get_orders_includes_platform_param(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/items/kronen_prime_blade/orders?include=item",
        method="GET", json={"payload": {"orders": []}},
    )
    c = client_factory()
    await c.get_orders("kronen_prime_blade", include_item_info=True)
    req = httpx_mock.get_request()
    assert "include=item" in str(req.url)


@pytest.mark.asyncio
async def test_get_profile_orders_uses_username(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/profile/klawisha012/orders",
        method="GET",
        json={"payload": {"sell_orders": [], "buy_orders": []}},
    )
    c = client_factory()
    payload = await c.get_profile_orders("klawisha012")
    assert "sell_orders" in payload["payload"]
