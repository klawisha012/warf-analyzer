"""PricePoller — discovers subscribed slugs via Centrifugo, refreshes stale ones."""

from __future__ import annotations

import time
from typing import Any
from unittest.mock import AsyncMock

import pytest

from alecaframe_api.wfm.price_poller import (
    PRICE_CHANNEL_PREFIX,
    PricePoller,
    slugs_from_channels,
    stats_from_orders,
)
from alecaframe_api.wfm.price_store import PriceStats, PriceStore


def test_slugs_from_channels_strips_prefix() -> None:
    channels = {
        f"{PRICE_CHANNEL_PREFIX}kronen_prime_blade",
        f"{PRICE_CHANNEL_PREFIX}lato_vandal_set",
        "wfm.live.orders",  # unrelated channel — must be ignored
        "presence.foo",
    }
    assert slugs_from_channels(channels) == {"kronen_prime_blade", "lato_vandal_set"}


def test_stats_from_orders_populates_fields() -> None:
    """Sanity-check the helper that converts a raw orders list to PriceStats."""
    raw = [
        {
            "type": "sell",
            "platinum": 30,
            "quantity": 1,
            "visible": True,
            "user": {"platform": "pc", "status": "ingame"},
        },
        {
            "type": "sell",
            "platinum": 40,
            "quantity": 1,
            "visible": True,
            "user": {"platform": "pc", "status": "online"},
        },
        {
            "type": "buy",
            "platinum": 25,
            "quantity": 1,
            "visible": True,
            "user": {"platform": "pc", "status": "ingame"},
        },
    ]
    stats = stats_from_orders("kronen_prime_blade", raw, now=1234.0)
    assert stats.slug == "kronen_prime_blade"
    assert stats.sell_min == 30
    assert stats.sell_median == 35
    assert stats.sell_spread == 10
    assert stats.buy_max == 25
    assert stats.fetched_at == 1234.0
    assert stats.stale is False


def test_stats_from_orders_marks_stale_payload() -> None:
    stats = stats_from_orders("x", [], now=1.0, stale=True)
    assert stats.stale is True
    assert stats.sell_min is None
    assert stats.sell_median is None


@pytest.mark.asyncio
async def test_poller_skips_when_no_subscribers() -> None:
    """No active channels → poller does not call WFM."""
    store = PriceStore()
    wfm_client = AsyncMock()
    wfm_client.get_orders = AsyncMock()
    publisher = AsyncMock()
    publisher.list_channels = AsyncMock(return_value=set())
    publisher.publish = AsyncMock()

    poller = PricePoller(
        store=store,
        wfm_client=wfm_client,
        publisher=publisher,
        stale_threshold=10.0,
    )
    await poller.tick()
    wfm_client.get_orders.assert_not_called()
    publisher.publish.assert_not_called()


@pytest.mark.asyncio
async def test_poller_fetches_only_stale_slugs() -> None:
    store = PriceStore()
    now = time.time()
    # "fresh" was fetched 1s ago — skip. "old" was fetched 30s ago — refresh.
    store.set(
        PriceStats(
            slug="fresh",
            sell_min=1,
            sell_median=2,
            sell_spread=0,
            buy_max=1,
            fetched_at=now - 1,
        )
    )
    store.set(
        PriceStats(
            slug="old",
            sell_min=5,
            sell_median=6,
            sell_spread=0,
            buy_max=4,
            fetched_at=now - 30,
        )
    )

    wfm_client = AsyncMock()
    wfm_client.get_orders = AsyncMock(
        return_value={
            "data": [
                {
                    "type": "sell",
                    "platinum": 50,
                    "quantity": 1,
                    "visible": True,
                    "user": {"platform": "pc", "status": "online"},
                },
            ]
        }
    )
    publisher = AsyncMock()
    publisher.list_channels = AsyncMock(
        return_value={
            f"{PRICE_CHANNEL_PREFIX}fresh",
            f"{PRICE_CHANNEL_PREFIX}old",
            f"{PRICE_CHANNEL_PREFIX}new",  # never seen — must be refetched
        }
    )
    publisher.publish = AsyncMock()

    poller = PricePoller(
        store=store,
        wfm_client=wfm_client,
        publisher=publisher,
        stale_threshold=10.0,
    )
    await poller.tick()

    fetched_slugs = {
        c.kwargs.get("slug") or c.args[0] for c in wfm_client.get_orders.call_args_list
    }
    assert fetched_slugs == {"old", "new"}
    # publish on those two channels, fresh stays put
    published_channels = {c.args[0] for c in publisher.publish.call_args_list}
    assert published_channels == {
        f"{PRICE_CHANNEL_PREFIX}old",
        f"{PRICE_CHANNEL_PREFIX}new",
    }


@pytest.mark.asyncio
async def test_poller_writes_to_store_and_publishes_stats() -> None:
    store = PriceStore()
    wfm_client = AsyncMock()
    wfm_client.get_orders = AsyncMock(
        return_value={
            "data": [
                {
                    "type": "sell",
                    "platinum": 30,
                    "quantity": 1,
                    "visible": True,
                    "user": {"platform": "pc", "status": "ingame"},
                },
            ]
        }
    )
    publisher = AsyncMock()
    publisher.list_channels = AsyncMock(return_value={f"{PRICE_CHANNEL_PREFIX}foo"})
    publisher.publish = AsyncMock()

    poller = PricePoller(store=store, wfm_client=wfm_client, publisher=publisher)
    await poller.tick()

    rec = store.get("foo")
    assert rec is not None
    assert rec.sell_min == 30
    publisher.publish.assert_awaited_once()
    chan, data = publisher.publish.call_args.args
    assert chan == f"{PRICE_CHANNEL_PREFIX}foo"
    assert data["slug"] == "foo"
    assert data["sell_min"] == 30


@pytest.mark.asyncio
async def test_poller_swallows_wfm_error_and_keeps_going() -> None:
    """One slug failing must not abort the whole tick."""
    store = PriceStore()
    from alecaframe_api.wfm.client import WFMError

    async def get_orders(slug: str, *, fresh: bool = False) -> dict[str, Any]:
        if slug == "boom":
            raise WFMError("WFM down")
        return {
            "data": [
                {
                    "type": "sell",
                    "platinum": 10,
                    "quantity": 1,
                    "visible": True,
                    "user": {"platform": "pc", "status": "online"},
                },
            ]
        }

    wfm_client = AsyncMock()
    wfm_client.get_orders = AsyncMock(side_effect=get_orders)
    publisher = AsyncMock()
    publisher.list_channels = AsyncMock(
        return_value={
            f"{PRICE_CHANNEL_PREFIX}boom",
            f"{PRICE_CHANNEL_PREFIX}ok",
        }
    )
    publisher.publish = AsyncMock()

    poller = PricePoller(store=store, wfm_client=wfm_client, publisher=publisher)
    await poller.tick()

    assert store.get("ok") is not None
    # "boom" might be absent or have a stale flag; either way the tick survives.
    assert publisher.publish.await_count == 1
