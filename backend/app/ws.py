"""WebSocket connection manager — hardened against per-client failures.

Follows the FastAPI ``advanced/websockets`` "Multiple clients" pattern, with
the documented hardening: ``broadcast`` MUST not let one broken socket break
the whole loop, so each send is wrapped in try/except and dead connections
are evicted from ``active_connections`` afterwards.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Tracks live WebSocket clients and fans messages out."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self.active_connections.append(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._lock:
            if websocket in self.active_connections:
                self.active_connections.remove(websocket)

    async def broadcast_json(self, payload: dict[str, Any]) -> None:
        """Send ``payload`` as JSON to every connected client.

        Per-client failures are swallowed and the offending socket dropped
        from ``active_connections`` — one dead client must never crash the
        worker loop.
        """
        # Snapshot under the lock so we can iterate without holding it.
        async with self._lock:
            connections = list(self.active_connections)

        dead: list[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(payload)
            except Exception as exc:  # noqa: BLE001 — broad on purpose
                logger.debug("ws send failed, dropping client: %s", exc)
                dead.append(ws)

        if dead:
            async with self._lock:
                for ws in dead:
                    if ws in self.active_connections:
                        self.active_connections.remove(ws)
