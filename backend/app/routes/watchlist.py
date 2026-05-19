"""Watchlist router — a user-pinned list of weapons + latest price snapshot.

Storage: single ``AppSetting`` row keyed by ``watchlist`` (list[str]).
The GET endpoint enriches each entry with the most recent price sample so the
UI can render it in one round-trip.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories, settings_store
from app.db import get_session

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAddBody(BaseModel):
    weapon: str


class WatchlistEntry(BaseModel):
    weapon: str
    latest_ts: int | None = None
    p1: int | None = None
    p2: int | None = None
    p3: int | None = None


@router.get("", response_model=list[WatchlistEntry])
async def list_watchlist(
    session: AsyncSession = Depends(get_session),
) -> list[WatchlistEntry]:
    weapons = await settings_store.get_watchlist(session)
    out: list[WatchlistEntry] = []
    for w in weapons:
        latest = await repositories.get_latest_price_sample(session, w)
        if latest is None:
            out.append(WatchlistEntry(weapon=w))
        else:
            ts, p1, p2, p3 = latest
            out.append(
                WatchlistEntry(weapon=w, latest_ts=ts, p1=p1, p2=p2, p3=p3)
            )
    return out


@router.post("")
async def add_watchlist(
    body: WatchlistAddBody,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool | str]:
    weapon = body.weapon.strip()
    if not weapon:
        raise HTTPException(status_code=400, detail="weapon is required")
    added = await settings_store.add_to_watchlist(session, weapon)
    return {"weapon": weapon, "added": added}


@router.delete("/{weapon}")
async def remove_watchlist(
    weapon: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, bool | str]:
    removed = await settings_store.remove_from_watchlist(session, weapon)
    return {"weapon": weapon, "removed": removed}
