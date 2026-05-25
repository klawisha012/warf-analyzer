"""Long-running WebSocket client for WFM live order updates.

Connects to `wss://warframe.market/socket?platform=pc`, sends a SUBSCRIBE
message per slug, and forwards every order-book event to a user-supplied
handler. Reconnects on disconnect with exponential backoff.

This file is consumed by the poller; backend never imports it.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Awaitable, Callable

import websockets

log = logging.getLogger("alecaframe.wfm.socket")

Handler = Callable[[dict], Awaitable[None]]


class WFMSocketClient:
    """Subscribe to live order updates for a list of slugs."""

    def __init__(
        self,
        token_provider: Callable[[], Awaitable[str]],
        platform: str = "pc",
        base_ws: str = "wss://warframe.market/socket",
    ) -> None:
        self._token_provider = token_provider
        self._platform = platform
        self._base_ws = base_ws
        self._slugs: set[str] = set()
        self._stop = asyncio.Event()

    def set_subscription(self, slugs: set[str]) -> None:
        """Update the set of slugs to listen for. Picked up on next reconnect."""
        self._slugs = set(slugs)

    async def run(self, handler: Handler) -> None:
        """Long-running loop with exponential backoff."""
        backoff = 1.0
        while not self._stop.is_set():
            try:
                token = await self._token_provider()
                url = f"{self._base_ws}?platform={self._platform}"
                headers = {"Cookie": f"JWT={token}; platform={self._platform}"}
                async with websockets.connect(url, additional_headers=headers, ping_interval=20) as ws:
                    backoff = 1.0
                    # Subscribe to current slug set.
                    for slug in list(self._slugs):
                        await ws.send(json.dumps({
                            "type": "@WS/SUBSCRIBE/NEW_ORDERS", "payload": slug,
                        }))
                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        # WFM sends @WS/SUBSCRIBE/NEW_ORDERS responses, plus order events.
                        if msg.get("type", "").endswith("/UPDATE") or msg.get("type", "").endswith("/CREATED"):
                            await handler(msg)
            except Exception as e:
                if self._stop.is_set():
                    return
                jitter = random.uniform(0, 0.5)
                wait = min(60.0, backoff) + jitter
                log.warning("WFM WS error (%s); reconnect in %.1fs", e, wait)
                await asyncio.sleep(wait)
                backoff = min(60.0, backoff * 2)

    def stop(self) -> None:
        self._stop.set()
