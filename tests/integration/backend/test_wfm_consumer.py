"""Backend consumer: drain wfm.live.orders, update Redis, publish to Centrifugo."""

from __future__ import annotations

import pytest

from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.consumer import handle_live_order


@pytest.mark.asyncio
async def test_handle_live_order_publishes_to_centrifugo() -> None:
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(client=redis, key_prefix="wfm")
    published: list[tuple[str, dict]] = []

    class FakePublisher:
        async def publish(self, channel: str, data: dict) -> None:
            published.append((channel, data))

    await handle_live_order(
        msg={
            "type": "@WS/SUBSCRIBE/NEW_ORDERS/UPDATE",
            "payload": {
                "item": {"url_name": "kronen_prime_blade"},
                "platinum": 33,
                "order_type": "sell",
            },
        },
        cache=cache,
        publisher=FakePublisher(),
    )
    assert len(published) == 1
    chan, data = published[0]
    assert chan == "wfm.orders.kronen_prime_blade"
    assert data["slug"] == "kronen_prime_blade"
    await redis.aclose()


@pytest.mark.asyncio
async def test_handle_live_order_skips_when_no_slug() -> None:
    import fakeredis.aioredis

    redis = fakeredis.aioredis.FakeRedis(decode_responses=True)
    cache = Cache(client=redis, key_prefix="wfm")
    published = []

    class FakePublisher:
        async def publish(self, channel: str, data: dict) -> None:
            published.append((channel, data))

    await handle_live_order(
        msg={"type": "@WS/SOMETHING_ELSE", "payload": {}},
        cache=cache,
        publisher=FakePublisher(),
    )
    assert published == []
    await redis.aclose()
