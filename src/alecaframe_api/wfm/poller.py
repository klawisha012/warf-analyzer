"""Poller worker — long-running process.

Responsibilities (B.1c version):
- Connect to RabbitMQ.
- Bootstrap the slug catalogue from WFM /v1/items (sets the subscription set).
- Open a long-running WFM WebSocket and forward every order event to the
  `wfm.live.orders` topic on RabbitMQ.
- APScheduler: every 30 minutes refresh the slug catalogue + the subscription set.

The slug subscription set comes from:
1. Slugs derived from the user's inventory (read once via the data folder
   that decrypt-agent writes — we read JSON directly to avoid a circular HTTP loop).
2. A static watchlist file at `data/watchlist.txt` (one slug per line; optional).
"""
from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx
import redis.asyncio as redis_lib

from alecaframe_api.config import get_settings
from alecaframe_api.infra.broker import RabbitMQBus
from alecaframe_api.infra.cache import Cache
from alecaframe_api.wfm.client import WFMClient
from alecaframe_api.wfm.slugs import SlugResolver
from alecaframe_api.wfm.socket import WFMSocketClient

log = logging.getLogger("alecaframe.poller")


def _read_inventory_slugs(data_dir: Path, resolver: SlugResolver) -> set[str]:
    """Best-effort: walk lastData.json, resolve unique-names to slugs."""
    path = data_dir / "lastData.json"
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        log.warning("can't read %s: %s", path, e)
        return set()
    slugs: set[str] = set()
    for key in ("MiscItems", "Recipes", "RawUpgrades"):
        for it in data.get(key) or []:
            slug = resolver.resolve_unique_name(it.get("ItemType") or "")
            if slug:
                slugs.add(slug)
    return slugs


def _read_watchlist(data_dir: Path) -> set[str]:
    path = data_dir / "watchlist.txt"
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


async def _refresh_subscription(
    *,
    wfm_client: WFMClient,
    resolver: SlugResolver,
    socket_client: WFMSocketClient,
    data_dir: Path,
) -> None:
    try:
        items = await wfm_client.get_items()
        resolver.load(items)
    except Exception as e:
        log.warning("WFM /items refresh failed: %s", e)
    slugs = _read_inventory_slugs(data_dir, resolver) | _read_watchlist(data_dir)
    # WFM allows ~50 simultaneous subscriptions. Cap and log.
    if len(slugs) > 50:
        slugs = set(list(slugs)[:50])
    socket_client.set_subscription(slugs)
    log.info("subscription set: %d slugs", len(slugs))


async def _main() -> None:
    s = get_settings()
    logging.basicConfig(
        level=s.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("poller starting; agent=%s redis=%s rabbit=%s", s.agent_url, s.redis_url, s.rabbitmq_url)

    redis_client = redis_lib.from_url(s.redis_url, decode_responses=True)
    wfm_cache = Cache(client=redis_client, key_prefix="wfm")

    async def _token() -> str:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"{s.agent_url.rstrip('/')}/wfm-token")
            r.raise_for_status()
            return r.json()["token"]

    wfm_client = WFMClient(
        cache=wfm_cache, base_url=s.wfm_base_url, token_provider=_token,
        platform=s.wfm_platform, language=s.wfm_language,
        rate_limit_per_second=s.wfm_rate_limit_per_second,
    )
    resolver = SlugResolver()
    bus = RabbitMQBus(url=s.rabbitmq_url)
    socket_client = WFMSocketClient(token_provider=_token, platform=s.wfm_platform)

    async def _on_event(msg: dict) -> None:
        payload = msg.get("payload") or {}
        item = payload.get("item") or {}
        slug = item.get("url_name") or payload.get("url_name")
        if not slug:
            return
        try:
            await bus.publish("wfm", f"live.orders.{slug}", msg)
        except Exception as e:
            log.warning("publish to wfm.live.orders failed for %s: %s", slug, e)

    # First-time bootstrap
    await _refresh_subscription(
        wfm_client=wfm_client, resolver=resolver,
        socket_client=socket_client, data_dir=s.data_dir,
    )

    sched = AsyncIOScheduler()
    sched.add_job(
        lambda: asyncio.create_task(_refresh_subscription(
            wfm_client=wfm_client, resolver=resolver,
            socket_client=socket_client, data_dir=s.data_dir,
        )),
        trigger="interval", minutes=30,
    )
    sched.start()

    stop = asyncio.Event()
    def _handler() -> None:
        log.info("shutdown signal received")
        stop.set()
        socket_client.stop()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            signal.signal(sig, lambda *_: _handler())

    ws_task = asyncio.create_task(socket_client.run(_on_event))
    await stop.wait()
    sched.shutdown(wait=False)
    ws_task.cancel()
    await bus.aclose()
    await wfm_client.aclose()
    await redis_client.aclose()
    log.info("poller stopped")


def run() -> None:
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)
