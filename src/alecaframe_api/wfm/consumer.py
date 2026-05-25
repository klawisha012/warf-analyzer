"""Backend consumer for `wfm.live.orders` topic.

For each event:
1. Extract the slug.
2. Invalidate the cached order book so next REST request refetches.
3. Publish a Centrifugo event on `wfm.orders.{slug}`.
4. (If `repo` provided) append a live_event audit row.

Per-event snapshots + signal compute are NOT done here — the live event
payload doesn't carry enough state for a full order-book stats row. The
30-min REST-snapshot job in poller.py (Task 9) writes proper snapshots
from /v1/items/{slug}/orders.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Protocol

from alecaframe_api.db.repo import Repo
from alecaframe_api.infra.cache import Cache

log = logging.getLogger("alecaframe.wfm.consumer")


class _PublisherProto(Protocol):
    async def publish(self, channel: str, data: dict[str, Any]) -> None: ...


async def handle_live_order(
    *, msg: dict, cache: Cache, publisher: _PublisherProto,
    repo: Repo | None = None,
) -> None:
    payload = msg.get("payload") or {}
    item = payload.get("item") or {}
    slug = item.get("url_name") or payload.get("url_name")
    if not slug:
        return
    try:
        for k in (f"orders:{slug}:0", f"orders:{slug}:1"):
            await cache.delete(k)
    except Exception as e:
        log.warning("cache invalidate failed for %s: %s", slug, e)
    await publisher.publish(f"wfm.orders.{slug}", {"slug": slug})
    if repo is not None:
        try:
            await repo.append_live_event(
                ts=int(time.time()), slug=slug,
                event_type=str(msg.get("type") or ""), payload=msg,
            )
        except Exception as e:
            log.warning("append_live_event failed for %s: %s", slug, e)
