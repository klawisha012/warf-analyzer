"""WFMAuctionClient tests — v1 /auctions endpoints, auth, cache, stale fallback."""
from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.auctions_client import WFMAuctionClient, WFMAuctionError


@pytest.fixture
async def cache() -> Cache:
    import fakeredis.aioredis
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = Cache(client=client, key_prefix="wfm-auc")
    yield c
    await client.aclose()


@pytest.fixture
def token():
    async def _t() -> str:
        return "FAKE.JWT.TOKEN"
    return _t


@pytest.fixture
def client_factory(cache: Cache, token):
    def _factory(**overrides) -> WFMAuctionClient:
        kwargs = dict(
            cache=cache,
            base_url="https://mock.wfm.test/v1",
            token_provider=token,
            platform="pc",
            language="en",
            rate_limit_per_second=100,
        )
        kwargs.update(overrides)
        return WFMAuctionClient(**kwargs)
    return _factory


@pytest.mark.asyncio
async def test_get_riven_auctions_sends_auth_and_filters(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/auctions/search?type=riven&weapon_url_name=tonkor&sort_by=price_asc",
        method="GET",
        json={"payload": {"auctions": [
            {"id": "a1", "buyout_price": 200, "starting_price": 50, "top_bid": None,
             "item": {"weapon_url_name": "tonkor", "polarity": "vazarin",
                      "attributes": [{"url_name": "critical_damage", "value": 120, "positive": True}],
                      "mod_rank": 8, "re_rolls": 4, "mastery_level": 12, "name": "rivenname"},
             "owner": {"ingame_name": "user", "status": "ingame", "platform": "pc"},
             "visible": True, "private": False, "is_direct_sell": True},
        ]}},
    )
    c = client_factory()
    auctions = await c.get_riven_auctions("tonkor")
    assert len(auctions) == 1
    assert auctions[0]["id"] == "a1"
    req = httpx_mock.get_request()
    assert req.headers["Authorization"] == "Bearer FAKE.JWT.TOKEN"
    assert req.headers["Platform"] == "pc"


@pytest.mark.asyncio
async def test_get_riven_auctions_cached(client_factory, httpx_mock: HTTPXMock) -> None:
    """Second call within TTL must not hit WFM again."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/auctions/search?type=riven&weapon_url_name=tonkor&sort_by=price_asc",
        method="GET",
        json={"payload": {"auctions": [{"id": "a1"}]}},
    )
    c = client_factory()
    await c.get_riven_auctions("tonkor")
    await c.get_riven_auctions("tonkor")
    # One request total — the second hit cache.
    assert len(httpx_mock.get_requests()) == 1


@pytest.mark.asyncio
async def test_get_riven_auctions_stale_fallback(client_factory, httpx_mock: HTTPXMock) -> None:
    """WFM 5xx after a successful cached fetch → return stale + flag."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/auctions/search?type=riven&weapon_url_name=tonkor&sort_by=price_asc",
        method="GET",
        json={"payload": {"auctions": [{"id": "stale"}]}},
    )
    c = client_factory()
    first = await c.get_riven_auctions("tonkor")
    assert first[0]["id"] == "stale"

    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/auctions/search?type=riven&weapon_url_name=tonkor&sort_by=price_asc",
        method="GET",
        status_code=503, text="boom",
    )
    # Force fresh — should fallback to stale instead of raising.
    second = await c.get_riven_auctions("tonkor", fresh=True)
    assert second[0]["id"] == "stale"
    # The wrapping payload should carry _stale.
    # (Internal detail: we test it via get_raw helper if needed; for now just assert no raise.)


@pytest.mark.asyncio
async def test_get_riven_auctions_raises_on_first_failure(client_factory, httpx_mock: HTTPXMock) -> None:
    """No cache + WFM fails → WFMAuctionError."""
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/auctions/search?type=riven&weapon_url_name=tonkor&sort_by=price_asc",
        method="GET",
        status_code=503, text="boom",
    )
    c = client_factory()
    with pytest.raises(WFMAuctionError):
        await c.get_riven_auctions("tonkor")


@pytest.mark.asyncio
async def test_get_riven_weapons_uses_v2_and_maps_to_v1_shape(client_factory, httpx_mock: HTTPXMock) -> None:
    # The catalogue migrated to v2 /riven/weapons (v1 /riven/items now errors).
    # The client must hit v2 and map the new shape back to the v1 keys callers use.
    httpx_mock.add_response(
        url="https://mock.wfm.test/v2/riven/weapons",
        method="GET",
        json={"apiVersion": "0.25.0", "data": [
            {"id": "x", "slug": "torid", "group": "primary", "rivenType": "rifle",
             "disposition": 1.3, "reqMasteryRank": 5,
             "i18n": {"en": {"name": "Torid", "icon": "items/images/en/torid.png",
                             "thumb": "items/images/en/thumbs/torid.png"}}},
        ]},
    )
    c = client_factory()
    weapons = await c.get_riven_weapons()
    assert len(weapons) == 1
    w = weapons[0]
    assert w["url_name"] == "torid"
    assert w["item_name"] == "Torid"
    assert w["icon"] == "items/images/en/torid.png"
    assert w["riven_disposition"] == 1.3
    assert w["riven_type"] == "rifle"
    assert w["group"] == "primary"


@pytest.mark.asyncio
async def test_get_auction_entry_returns_payload(client_factory, httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="https://mock.wfm.test/v1/auctions/entry/abc123",
        method="GET",
        json={"payload": {"auction": {"id": "abc123", "buyout_price": 500}}},
    )
    c = client_factory()
    detail = await c.get_auction_entry("abc123")
    assert detail["id"] == "abc123"
    assert detail["buyout_price"] == 500
