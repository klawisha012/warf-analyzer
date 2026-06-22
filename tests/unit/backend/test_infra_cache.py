"""Tests for the Redis cache wrapper."""

from __future__ import annotations

import pytest

from alecaframe_api.infra.cache import Cache


@pytest.fixture
async def cache() -> Cache:
    """fakeredis-backed Cache instance, isolated per test."""
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    c = Cache(client=client, key_prefix="test")
    yield c
    await client.aclose()


@pytest.mark.asyncio
async def test_set_then_get_json_roundtrip(cache: Cache) -> None:
    await cache.set_json("foo", {"a": 1, "b": [2, 3]}, ttl_seconds=60)
    got = await cache.get_json("foo")
    assert got == {"a": 1, "b": [2, 3]}


@pytest.mark.asyncio
async def test_get_json_missing_returns_none(cache: Cache) -> None:
    got = await cache.get_json("nope")
    assert got is None


@pytest.mark.asyncio
async def test_delete(cache: Cache) -> None:
    await cache.set_json("k", {"x": 1}, ttl_seconds=60)
    await cache.delete("k")
    assert await cache.get_json("k") is None


@pytest.mark.asyncio
async def test_key_prefix_isolation() -> None:
    """Two caches with different prefixes must not see each other's keys."""
    import fakeredis.aioredis

    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    a = Cache(client=client, key_prefix="a")
    b = Cache(client=client, key_prefix="b")
    await a.set_json("k", {"who": "a"}, ttl_seconds=60)
    assert await b.get_json("k") is None
    assert (await a.get_json("k")) == {"who": "a"}
    await client.aclose()


@pytest.mark.asyncio
async def test_ttl_is_applied(cache: Cache) -> None:
    """The wrapper sets EXPIRE — verify TTL is non-negative on a fresh key."""
    await cache.set_json("ttlcheck", {"k": 1}, ttl_seconds=60)
    ttl = await cache.ttl_seconds("ttlcheck")
    assert ttl is not None and 0 < ttl <= 60


@pytest.mark.asyncio
async def test_get_or_set_calls_loader_on_miss(cache: Cache) -> None:
    calls = {"n": 0}

    async def loader() -> dict:
        calls["n"] += 1
        return {"computed": True}

    first = await cache.get_or_set_json("lazy", ttl_seconds=60, loader=loader)
    second = await cache.get_or_set_json("lazy", ttl_seconds=60, loader=loader)
    assert first == {"computed": True}
    assert second == {"computed": True}
    assert calls["n"] == 1  # loader called once, second hit was cached
