"""Settings router — read/write the two K/V rows backing the UI."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app import seed as seed_module
from app import settings_store
from app.db import get_session
from app.schemas import SettingsPayload

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=SettingsPayload)
async def get_settings(
    session: AsyncSession = Depends(get_session),
) -> SettingsPayload:
    good = await settings_store.get_good_weapons(session)
    fast = await settings_store.get_fast_weapons_list(session)
    return SettingsPayload(good_weapons=good, fast_weapons_list=fast)


@router.put("", response_model=SettingsPayload)
async def put_settings(
    payload: SettingsPayload,
    session: AsyncSession = Depends(get_session),
) -> SettingsPayload:
    await settings_store.set_good_weapons(session, payload.good_weapons)
    await settings_store.set_fast_weapons_list(session, payload.fast_weapons_list)
    return payload


@router.post("/reset-to-defaults", response_model=SettingsPayload)
async def reset_settings_to_defaults(
    session: AsyncSession = Depends(get_session),
) -> SettingsPayload:
    """Re-seed ``good_weapons`` + ``fast_weapons_list`` from the bundled
    ``settings.json``. Mirrors ``python -m app.seed`` but stays in-process so
    the UI can wire it to a button. ``watchlist`` is untouched.
    """
    path = seed_module._default_settings_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        raise HTTPException(
            status_code=500, detail=f"defaults file not found: {path}"
        )

    good = {str(k): int(v) for k, v in (data.get("good_weapons") or {}).items()}
    fast = [str(w) for w in (data.get("fast_weapons_list") or [])]
    await settings_store.set_good_weapons(session, good)
    await settings_store.set_fast_weapons_list(session, fast)
    return SettingsPayload(good_weapons=good, fast_weapons_list=fast)
