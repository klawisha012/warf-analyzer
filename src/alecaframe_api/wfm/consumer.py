"""Backend consumer for `wfm.live.orders` topic.

For each event:
1. Extract the slug.
2. Optionally update Redis-cached order book (best effort — full refetch is
   cheaper than incremental merge for the order shapes we use).
3. Publish a Centrifugo event on `wfm.orders.{slug}` so subscribed clients
   know to refetch.
"""
from __future__ import annotations

import logging
from typing import Any, Protocol

from alecaframe_api.infra.cache import Cache

log = logging.getLogger("alecaframe.wfm.consumer")


class _PublisherProto(Protocol):
    async def publish(self, channel: str, data: dict[str, Any]) -> None: ...


async def handle_live_order(*, msg: dict, cache: Cache, publisher: _PublisherProto) -> None:
    payload = msg.get("payload") or {}
    item = payload.get("item") or {}
    slug = item.get("url_name") or payload.get("url_name")
    if not slug:
        return
    # Invalidate the cached order book so next REST request refetches.
    try:
        for k in (f"orders:{slug}:0", f"orders:{slug}:1"):
            await cache.delete(k)
    except Exception as e:
        log.warning("cache invalidate failed for %s: %s", slug, e)
    await publisher.publish(f"wfm.orders.{slug}", {"slug": slug})
