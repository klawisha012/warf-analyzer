"""Async rate limiter — replaces the synchronous ``scanner2.RateLimiter``.

A single instance is shared by the market client. ``wait()`` sleeps just long
enough to honour the configured cooldown between calls. All sleeps use
``asyncio.sleep`` — never ``time.sleep`` (would block the event loop).
"""

from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:
    """Token-less interval limiter; mirrors ``scanner2.RateLimiter`` semantics."""

    def __init__(self, cooldown: float = 2.0) -> None:
        self.cooldown: float = float(cooldown)
        self.last_call: float = 0.0

    def set_interval(self, cooldown: float) -> None:
        """Override the cooldown (used after an HTTP error to back off)."""
        self.cooldown = float(cooldown)

    async def wait(self) -> None:
        """Block until at least ``self.cooldown`` seconds have elapsed since last_call."""
        now = time.monotonic()
        delta = now - self.last_call
        if delta < self.cooldown:
            await asyncio.sleep(self.cooldown - delta)

    def stamp(self) -> None:
        """Mark *now* as the last call — caller is expected to invoke this
        immediately after issuing the request that the limiter was guarding.
        """
        self.last_call = time.monotonic()
