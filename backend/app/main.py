"""FastAPI app entrypoint — Phase 2.

Lifespan owns:
    * the long-lived ``httpx.AsyncClient`` (stored on ``app.state.http``),
    * the ``ConnectionManager`` (``app.state.ws_manager``),
    * the bounded recent-alerts deque (``app.state.recent_alerts``),
    * counters for stats fan-out (``app.state.api_update_count``),
    * the background scanner task — created on startup, cancelled + awaited
      on shutdown.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import engine
from app.routes import alerts, groll, settings as settings_routes, watchlist, weapons
from app.worker import run_scanner
from app.ws import ConnectionManager

ALERTS_DEQUE_MAXLEN = 500


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(
        timeout=httpx.Timeout(10.0, connect=5.0),
        headers={"accept": "application/json", "platform": "pc"},
    )
    app.state.ws_manager = ConnectionManager()
    app.state.recent_alerts = deque(maxlen=ALERTS_DEQUE_MAXLEN)
    app.state.api_update_count = 0
    # Worker populates these on startup; pre-seed empty so routes can read
    # them safely before the first scanner iteration.
    app.state.seen_ids = set()
    app.state.alerted_ids = set()
    app.state.saved_groll_ids = set()

    scanner_task = asyncio.create_task(run_scanner(app), name="riven-scanner")

    try:
        yield
    finally:
        scanner_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await scanner_task
        await app.state.http.aclose()
        await engine.dispose()


app = FastAPI(title="Riven Scanner Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(alerts.router)
app.include_router(weapons.router)
app.include_router(settings_routes.router)
app.include_router(groll.router)
app.include_router(watchlist.router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# WebSocket endpoint — registered directly on the app so the path matches the
# ``WS_PATH`` setting (``/ws/alerts`` by default). Routers can't carry WS
# endpoints in older FastAPI versions, so we mount it here.
# ---------------------------------------------------------------------------

@app.websocket(settings.WS_PATH)
async def ws_alerts(websocket: WebSocket) -> None:
    manager: ConnectionManager = app.state.ws_manager
    await manager.connect(websocket)
    try:
        # Replay the most recent alerts on connect so a fresh tab has context.
        for payload in list(app.state.recent_alerts)[:50]:
            try:
                await websocket.send_json(payload)
            except Exception:
                break
        # Push current stats too.
        await websocket.send_json(
            {"type": "stats", "api_updates": app.state.api_update_count}
        )

        # Keep the connection alive; we don't expect inbound messages, but
        # awaiting receive_text() lets us detect disconnection cheaply.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(websocket)
