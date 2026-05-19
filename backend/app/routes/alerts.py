"""Alerts router — recent in-memory feed.

The deque lives on ``app.state.recent_alerts`` (bounded by
``ALERTS_DEQUE_MAXLEN`` in ``main.py``). Worker fills it; this route only
reads. Newest entries are at the *left* of the deque.

The WebSocket endpoint is mounted in ``main.py`` directly because
``APIRouter.websocket`` is constrained in older FastAPI versions — keep all
WS surface in one place.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


def purge_auction_from_deque(deque_obj, auction_id: str) -> bool:
    """Drop every entry whose auction.id matches. Preserves the deque maxlen.
    Returns True if at least one entry was removed.
    """
    if deque_obj is None:
        return False
    kept = [
        item for item in deque_obj
        if (item.get("auction") or {}).get("id") != auction_id
    ]
    if len(kept) == len(deque_obj):
        return False
    deque_obj.clear()
    deque_obj.extend(kept)
    return True


@router.get("")
async def list_alerts(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    """Recent alerts feed (newest first)."""
    deque_ = getattr(request.app.state, "recent_alerts", None)
    if deque_ is None:
        return []
    # Deque has newest-first; just slice.
    return list(deque_)[:limit]


@router.delete("/{auction_id}")
async def dismiss_alert(
    auction_id: str,
    request: Request,
) -> dict[str, Any]:
    """Permanently dismiss one alert.

    Drops it from the in-memory ``recent_alerts`` deque AND records the id in
    ``alerted_ids`` so the worker won't re-emit it later. In-memory only —
    survives until backend restart (the deque has the same lifetime, so the
    two stay consistent).
    """
    deque_ = getattr(request.app.state, "recent_alerts", None)
    removed = purge_auction_from_deque(deque_, auction_id)

    alerted: set[str] | None = getattr(request.app.state, "alerted_ids", None)
    if alerted is not None:
        alerted.add(auction_id)

    return {"auction_id": auction_id, "dismissed": removed}


# Re-exported for the groll router so saving a groll also clears the card
# from the feed (same pattern as dismiss).
__all__ = ["router", "purge_auction_from_deque"]
