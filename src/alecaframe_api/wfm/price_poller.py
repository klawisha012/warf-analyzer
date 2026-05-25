"""PricePoller — background task that keeps PriceStore fresh for slugs the UI watches.

Cycle (`tick()`):
1. Ask Centrifugo for active channels matching `wfm.orders.*`.
2. Extract slugs; ask PriceStore which of them are stale (missing or older
   than `stale_threshold` seconds).
3. For each stale slug, parallel-fetch /v2/orders/item/{slug} with fresh=True
   (bypass Redis L1 — we want a true poll, not yesterday's cache).
4. Compute PriceStats, write to PriceStore, publish to Centrifugo channel
   so already-connected clients see the update without re-querying.

Failure modes:
- Centrifugo list_channels fails → empty set → no fetches this tick. Self-heals next tick.
- WFM fetch fails for a slug → log + skip that one; other slugs still progress.
- Publish fails → swallowed inside CentrifugoPublisher; store update sticks.

The poller is a thin orchestrator — almost all logic is in helpers that are
unit-testable without an event loop or a real Centrifugo.
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Iterable

from alecaframe_api.infra.push import CentrifugoPublisher
from alecaframe_api.wfm.client import WFMClient, WFMError
from alecaframe_api.wfm.prices import compute_stats
from alecaframe_api.wfm.price_store import PriceStats, PriceStore

log = logging.getLogger("alecaframe.wfm.price_poller")


PRICE_CHANNEL_PREFIX = "wfm.orders."
DEFAULT_POLL_INTERVAL_S = 15.0
DEFAULT_STALE_THRESHOLD_S = 10.0


def slugs_from_channels(channels: Iterable[str]) -> set[str]:
    """Extract slug names from a list of `wfm.orders.{slug}` channels.

    Channels not matching the prefix are ignored — Centrifugo may have other
    channels (presence, live order broadcast) we don't care about here.
    """
    out: set[str] = set()
    for ch in channels:
        if ch.startswith(PRICE_CHANNEL_PREFIX):
            out.add(ch[len(PRICE_CHANNEL_PREFIX):])
    return out


def stats_from_orders(
    slug: str, orders: list[dict], *, now: float, stale: bool = False,
) -> PriceStats:
    """Project a raw WFM orders list into a PriceStats record.

    Marks `stale=True` when the data is from the stale-fallback path (WFM was
    down and we served whatever was in Redis). UI distinguishes a real price
    from a "last known" price.
    """
    sell = compute_stats(orders, side="sell", online_only=True)
    buy = compute_stats(orders, side="buy", online_only=True)
    spread = (
        (sell.max_price - sell.min_price)
        if sell.min_price is not None and sell.max_price is not None
        else None
    )
    return PriceStats(
        slug=slug,
        sell_min=sell.min_price,
        sell_median=sell.median,
        sell_spread=spread,
        buy_max=buy.max_price,
        fetched_at=now,
        stale=stale,
    )


@dataclass
class PricePoller:
    store: PriceStore
    wfm_client: WFMClient
    publisher: CentrifugoPublisher
    poll_interval: float = DEFAULT_POLL_INTERVAL_S
    stale_threshold: float = DEFAULT_STALE_THRESHOLD_S

    async def tick(self) -> None:
        """Run one poll cycle. Safe to call from tests directly."""
        try:
            channels = await self.publisher.list_channels(pattern=f"{PRICE_CHANNEL_PREFIX}*")
        except Exception as e:
            log.warning("list_channels failed: %s; skipping tick", e)
            return

        slugs = slugs_from_channels(channels)
        if not slugs:
            return

        stale = self.store.stale_slugs(slugs, max_age=self.stale_threshold)
        if not stale:
            return

        await asyncio.gather(*[self._refresh_one(s) for s in stale])

    async def _refresh_one(self, slug: str) -> None:
        try:
            payload = await self.wfm_client.get_orders(slug, fresh=True)
        except WFMError as e:
            log.warning("refresh %s failed: %s", slug, e)
            return
        except Exception as e:
            log.warning("refresh %s unexpected error: %s", slug, e)
            return
        orders = payload.get("data") or []
        is_stale = bool(payload.get("_stale"))
        stats = stats_from_orders(slug, orders, now=time.time(), stale=is_stale)
        self.store.set(stats)
        await self.publisher.publish(
            f"{PRICE_CHANNEL_PREFIX}{slug}",
            {
                "slug": stats.slug,
                "sell_min": stats.sell_min,
                "sell_median": stats.sell_median,
                "sell_spread": stats.sell_spread,
                "buy_max": stats.buy_max,
                "fetched_at": stats.fetched_at,
                "stale": stats.stale,
            },
        )

    async def run(self) -> None:
        """Long-running loop — call from a lifespan asyncio.create_task()."""
        log.info("price poller starting; interval=%.1fs stale_threshold=%.1fs",
                 self.poll_interval, self.stale_threshold)
        while True:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception as e:
                log.warning("poller tick failed: %s", e)
            await asyncio.sleep(self.poll_interval)
