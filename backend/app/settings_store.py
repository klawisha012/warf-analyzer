"""Typed accessors for the ``AppSetting`` K/V table.

Two keys are used by the application:
    * ``good_weapons``      — dict[str, int]  (weapon_url_name → max price)
    * ``fast_weapons_list`` — list[str]       (weapon_url_names to poll fast)

Wrap ``repositories.get_setting`` / ``set_setting`` so the rest of the code
doesn't need to remember the raw key names or default shapes.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app import repositories

GOOD_WEAPONS_KEY = "good_weapons"
FAST_WEAPONS_KEY = "fast_weapons_list"
WATCHLIST_KEY = "watchlist"


async def get_good_weapons(session: AsyncSession) -> dict[str, int]:
    raw = await repositories.get_setting(session, GOOD_WEAPONS_KEY)
    if not raw:
        return {}
    # JSON can come back with string values; coerce to int defensively.
    return {str(k): int(v) for k, v in dict(raw).items()}


async def set_good_weapons(session: AsyncSession, value: dict[str, int]) -> None:
    await repositories.set_setting(session, GOOD_WEAPONS_KEY, value)


async def get_fast_weapons_list(session: AsyncSession) -> list[str]:
    raw = await repositories.get_setting(session, FAST_WEAPONS_KEY)
    if not raw:
        return []
    return [str(w) for w in list(raw)]


async def set_fast_weapons_list(session: AsyncSession, value: list[str]) -> None:
    await repositories.set_setting(session, FAST_WEAPONS_KEY, value)


async def get_watchlist(session: AsyncSession) -> list[str]:
    raw = await repositories.get_setting(session, WATCHLIST_KEY)
    if not raw:
        return []
    return [str(w) for w in list(raw)]


async def set_watchlist(session: AsyncSession, value: list[str]) -> None:
    await repositories.set_setting(session, WATCHLIST_KEY, value)


async def add_to_watchlist(session: AsyncSession, weapon: str) -> bool:
    """Append ``weapon`` if not already present. Returns True iff added."""
    current = await get_watchlist(session)
    if weapon in current:
        return False
    current.append(weapon)
    await set_watchlist(session, current)
    return True


async def remove_from_watchlist(session: AsyncSession, weapon: str) -> bool:
    """Remove ``weapon`` if present. Returns True iff removed."""
    current = await get_watchlist(session)
    if weapon not in current:
        return False
    current.remove(weapon)
    await set_watchlist(session, current)
    return True
