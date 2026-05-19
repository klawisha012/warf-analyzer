"""Weapons router — list + per-weapon price history."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories, settings_store
from app.db import get_session

router = APIRouter(prefix="/api/weapons", tags=["weapons"])


@router.get("")
async def list_weapons(
    session: AsyncSession = Depends(get_session),
) -> dict[str, object]:
    """Returns ``good_weapons`` (full dict) + ``fast_weapons_list``."""
    good = await settings_store.get_good_weapons(session)
    fast = await settings_store.get_fast_weapons_list(session)
    return {"good_weapons": good, "fast_weapons_list": fast}


@router.get("/{weapon}/prices")
async def weapon_prices(
    weapon: str,
    session: AsyncSession = Depends(get_session),
) -> list[dict[str, int]]:
    """Top-3 price samples over time for one weapon."""
    rows = await repositories.get_price_history(session, weapon)
    return [{"t": ts, "p1": p1, "p2": p2, "p3": p3} for ts, p1, p2, p3 in rows]
