"""Saved-grolls router — replaces the Mongo collection.

POST also drops the auction_id from the worker's in-memory ``seen_ids`` /
``alerted_ids`` so re-saving the same groll later doesn't immediately fire
a duplicate alert.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories
from app.db import get_session
from app.routes.alerts import purge_auction_from_deque

router = APIRouter(prefix="/api/groll", tags=["groll"])


@router.get("")
async def list_grolls(
    session: AsyncSession = Depends(get_session),
) -> list[str]:
    """Return the list of saved auction IDs."""
    return await repositories.list_saved_groll_ids(session)


@router.post("", status_code=status.HTTP_201_CREATED)
async def save_groll(
    auction: dict[str, Any],
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    auction_id = auction.get("id") or auction.get("auction_id")
    if not auction_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="auction payload must contain 'id'",
        )

    inserted = await repositories.add_saved_groll(session, auction)

    # Tell the worker about it: track for de-dup, and drop from seen_ids /
    # alerted_ids so the next scan-pass treats it as known-saved.
    saved_ids: set[str] = getattr(request.app.state, "saved_groll_ids", set())
    saved_ids.add(auction_id)
    request.app.state.saved_groll_ids = saved_ids

    for attr in ("seen_ids", "alerted_ids"):
        bucket: set[str] | None = getattr(request.app.state, attr, None)
        if bucket is not None:
            bucket.discard(auction_id)

    # Also remove it from the live alerts deque so a page reload doesn't
    # re-render the card the user just saved off.
    purge_auction_from_deque(
        getattr(request.app.state, "recent_alerts", None),
        auction_id,
    )

    return {"ok": True, "auction_id": auction_id, "inserted": inserted}


@router.delete("/{auction_id}")
async def delete_groll(
    auction_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    deleted = await repositories.delete_saved_groll(session, auction_id)

    saved_ids: set[str] | None = getattr(request.app.state, "saved_groll_ids", None)
    if saved_ids is not None:
        saved_ids.discard(auction_id)

    return {"ok": True, "auction_id": auction_id, "deleted": deleted}
