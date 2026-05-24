"""Poller worker entry point — stub for phase B.0.

In B.1 this gains:
  - APScheduler with WFM REST snapshots every 30 minutes
  - WFMSocketClient (long-running WS listener)
  - RabbitMQ command consumer (`wfm.commands`)

For now it just logs, idles, and responds to SIGTERM cleanly so docker-compose
can supervise it without restart loops.
"""
from __future__ import annotations

import asyncio
import logging
import signal
import sys

from alecaframe_api.config import get_settings

log = logging.getLogger("alecaframe.poller")


async def _main() -> None:
    s = get_settings()
    logging.basicConfig(
        level=s.log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    log.info("poller stub starting; will idle until B.1 lands")
    log.info("settings: agent=%s redis=%s rabbit=%s", s.agent_url, s.redis_url, s.rabbitmq_url)

    stop = asyncio.Event()

    def _handler() -> None:
        log.info("shutdown signal received")
        stop.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _handler)
        except NotImplementedError:
            # Windows asyncio does not implement add_signal_handler
            signal.signal(sig, lambda *_: _handler())

    # heartbeat every 60s; will be replaced by real polling in B.1
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except asyncio.TimeoutError:
            log.debug("poller heartbeat")

    log.info("poller stopped")


def run() -> None:
    """Console entry point: `uv run alecaframe-poller`."""
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        sys.exit(0)
