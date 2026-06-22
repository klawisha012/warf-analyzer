"""WFMClient tests — auth header, rate-limit, cache, retry."""

from __future__ import annotations

import asyncio

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.client import WFMClient, WFMError
from tests import FIXTURES_DIR


@pytest.fixture
async def cache() -> Cache:
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = Cache(client=client, key_prefix="wfm")
    yield c
    await client.aclose()


@pytest.fixture
def static_token() -> callable:
    async def _provider() -> str:
        return "FAKE.JWT.TOKEN"

    return _provider


@pytest.fixture
def client_factory(cache: Cache, static_token: callable) -> callable:
    """Build a WFMClient with explicit base URL and rate limit raised for tests."""

    def _factory(**overrides) -> WFMClient:
        kwargs = dict(
            cache=cache,
            base_url="https://mock.wfm.test/v2",  # bumped from v1 in WFM v2 migration
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
        url="https://mock.wfm.test/v2/items",
        method="GET",
        json={"apiVersion": "0.23.1", "data": []},
    )
    c = client_factory()
    await c._request("GET", "/items", cache_key="items", cache_ttl=10)
    req = httpx_mock.get_request()
    # v2 uses Bearer (was JWT in v1) — RFC 6750 standard scheme.
    assert req.headers["Authorization"] == "Bearer FAKE.JWT.TOKEN"
    assert req.headers["Language"] == "en"
    assert req.headers["Platform"] == "pc"


@pytest.mark.asyncio
async def test_request_caches_response(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/items",
        method="GET",
        json={"apiVersion": "0.23.1", "data": []},
    )
    c = client_factory()
    a = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    b = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    assert a == b
    # Only one HTTP call should have happened — the second came from Redis.
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_request_fresh_bypasses_cache(
    client_factory, httpx_mock: HTTPXMock
) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/items",
        method="GET",
        json={"apiVersion": "0.23.1", "data": [{"slug": "a"}]},
    )
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/items",
        method="GET",
        json={"apiVersion": "0.23.1", "data": [{"slug": "b"}]},
    )
    c = client_factory()
    a = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    b = await c._request("GET", "/items", cache_key="items", cache_ttl=60, fresh=True)
    assert a["data"][0]["slug"] == "a"
    assert b["data"][0]["slug"] == "b"


@pytest.mark.asyncio
async def test_request_raises_on_5xx(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/items",
        method="GET",
        status_code=500,
        text="boom",
    )
    c = client_factory()
    with pytest.raises(WFMError):
        await c._request("GET", "/items", cache_key="items", cache_ttl=60)


@pytest.mark.asyncio
async def test_request_returns_stale_if_5xx_and_cache_has_value(
    client_factory, httpx_mock: HTTPXMock
) -> None:
    """When the upstream fails but Redis has a previous value, return it."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/items",
        method="GET",
        json={"apiVersion": "0.23.1", "data": [{"slug": "stale"}]},
    )
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/items",
        method="GET",
        status_code=503,
        text="upstream gone",
    )
    c = client_factory()
    # Prime cache with the first call (success).
    first = await c._request("GET", "/items", cache_key="items", cache_ttl=60)
    assert first["data"][0]["slug"] == "stale"
    # Re-prime with a known value to make the stale-fallback test deterministic.
    await c._cache.set_json(
        "items", {"apiVersion": "0.23.1", "data": [{"slug": "stale"}]}, ttl_seconds=60
    )
    # Now call with fresh=True so the cache lookup short-circuits and the
    # 503 path is exercised. Stale-fallback should still serve from cache.
    second = await c._request(
        "GET", "/items", cache_key="items", cache_ttl=60, fresh=True
    )
    assert second["data"][0]["slug"] == "stale"
    assert second.get("_stale") is True


@pytest.mark.asyncio
async def test_get_items_returns_item_refs(
    client_factory, httpx_mock: HTTPXMock
) -> None:
    import json

    fixture = json.loads(
        (FIXTURES_DIR / "wfm_items_sample.json").read_text(encoding="utf-8")
    )
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/items",
        method="GET",
        json=fixture,
    )
    c = client_factory()
    items = await c.get_items()
    assert len(items) == len(fixture["data"])
    kp = next(i for i in items if i.slug == "kronen_prime_blade")
    assert kp.item_name == "Kronen Prime Blade"
    # v2 listing omits vaulted — populated only by per-item /v2/items/{slug}.
    assert kp.vaulted is None


@pytest.mark.asyncio
async def test_get_orders_returns_payload(
    client_factory, httpx_mock: HTTPXMock
) -> None:
    """v2: orders moved to /v2/orders/item/{slug} and return {"data": [...]}."""
    import json

    fixture = json.loads(
        (FIXTURES_DIR / "wfm_orders_kronen_prime_blade.json").read_text(
            encoding="utf-8"
        )
    )
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/orders/item/kronen_prime_blade",
        method="GET",
        json=fixture,
    )
    c = client_factory()
    payload = await c.get_orders("kronen_prime_blade")
    assert len(payload["data"]) == 10


@pytest.mark.asyncio
async def test_get_orders_uses_v2_path(client_factory, httpx_mock: HTTPXMock) -> None:
    """v2 path: /orders/item/{slug} (was /items/{slug}/orders in v1)."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/orders/item/kronen_prime_blade",
        method="GET",
        json={"apiVersion": "0.23.1", "data": []},
    )
    c = client_factory()
    await c.get_orders("kronen_prime_blade")
    req = httpx_mock.get_request()
    assert str(req.url).endswith("/v2/orders/item/kronen_prime_blade")


@pytest.mark.asyncio
async def test_get_profile_orders_hits_v2_orders_my(
    client_factory, httpx_mock: HTTPXMock
) -> None:
    """v2: /orders/my replaces v1 /profile/{user}/orders (NOT /me/orders — 404)."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/orders/my",
        method="GET",
        json={
            "apiVersion": "0.23.1",
            "data": [
                {
                    "id": "o1",
                    "type": "sell",
                    "platinum": 50,
                    "itemId": "iid1",
                    "visible": True,
                },
            ],
        },
    )
    c = client_factory()
    payload = await c.get_profile_orders("ignored-username")
    assert payload["data"][0]["itemId"] == "iid1"
    # Confirm the request actually went to /v2/orders/my, not the v1 path.
    req = httpx_mock.get_request()
    assert str(req.url).endswith("/v2/orders/my")


@pytest.mark.asyncio
async def test_get_profile_hits_v2_me(client_factory, httpx_mock: HTTPXMock) -> None:
    """v2: /me replaces v1 /profile/{user}; username arg ignored."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/me",
        method="GET",
        json={"apiVersion": "0.23.1", "data": {"ingameName": "me", "reputation": 100}},
    )
    c = client_factory()
    payload = await c.get_profile("ignored-username")
    assert payload["data"]["ingameName"] == "me"


@pytest.mark.asyncio
async def test_token_provider_called_once_across_concurrent_requests(
    cache: Cache,
    httpx_mock: HTTPXMock,
) -> None:
    """Regression: 50 parallel WFM calls must NOT trigger 50 token fetches.

    Before the fix every `_request` called `token_provider()` directly, which
    in production hammered decrypt-agent's /wfm-token at the rate of WFM
    requests. The cache + lock should serialise refresh to one fetch even
    under high concurrency.
    """
    import base64
    import json
    import time as _time

    call_count = {"n": 0}
    # Build a JWT with a far-future exp so the cache stays warm for the run.
    payload = {"exp": int(_time.time()) + 3600}
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    )
    token = f"header.{payload_b64}.signature"

    async def counting_provider() -> str:
        call_count["n"] += 1
        return token

    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/orders/item/some_slug",
        method="GET",
        json={"apiVersion": "0.23.1", "data": []},
        is_reusable=True,
    )
    c = WFMClient(
        cache=cache,
        base_url="https://mock.wfm.test/v2",
        token_provider=counting_provider,
        platform="pc",
        language="en",
        rate_limit_per_second=100,
    )
    # 20 concurrent get_orders, all with fresh=True so cache doesn't short-circuit.
    await asyncio.gather(*[c.get_orders("some_slug", fresh=True) for _ in range(20)])

    assert call_count["n"] == 1, f"expected 1 token fetch, got {call_count['n']}"


@pytest.mark.asyncio
async def test_token_refreshed_when_expired(
    cache: Cache, httpx_mock: HTTPXMock
) -> None:
    """When the cached JWT is within 30s of expiry, refresh must fire again."""
    import base64
    import json
    import time as _time

    call_count = {"n": 0}

    def _make_token(exp: int) -> str:
        payload_b64 = (
            base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode())
            .rstrip(b"=")
            .decode()
        )
        return f"header.{payload_b64}.signature"

    async def provider() -> str:
        call_count["n"] += 1
        # First call: token expiring in 5s (well within the 30s refresh window).
        # Second call: fresh token expiring in 1h.
        return _make_token(int(_time.time()) + (5 if call_count["n"] == 1 else 3600))

    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/orders/item/x",
        method="GET",
        json={"apiVersion": "0.23.1", "data": []},
        is_reusable=True,
    )
    c = WFMClient(
        cache=cache,
        base_url="https://mock.wfm.test/v2",
        token_provider=provider,
        platform="pc",
        language="en",
        rate_limit_per_second=100,
    )
    await c.get_orders("x", fresh=True)
    await c.get_orders("x", fresh=True)
    assert call_count["n"] == 2  # first cached <30s exp, second refresh


def test_extract_jwt_exp_round_trip() -> None:
    import base64
    import json
    import time as _time

    from alecaframe_api.wfm.client import _extract_jwt_exp

    exp = int(_time.time()) + 600
    payload_b64 = (
        base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode())
        .rstrip(b"=")
        .decode()
    )
    token = f"hdr.{payload_b64}.sig"
    assert _extract_jwt_exp(token, default_ttl=10) == float(exp)


def test_extract_jwt_exp_falls_back_on_malformed() -> None:
    import time as _time

    from alecaframe_api.wfm.client import _extract_jwt_exp

    now = _time.time()
    out = _extract_jwt_exp("not-a-jwt", default_ttl=42)
    assert now <= out <= now + 50
