"""Pydantic DTOs used by the HTTP routes.

Phase 1 only needs a minimal surface so the route modules can import without
errors. Phase 2 will flesh these out (alerts, WS payloads, etc.).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = "ok"


class SettingsPayload(BaseModel):
    """The two K/V rows surfaced together for the Settings page."""

    good_weapons: dict[str, int] = Field(default_factory=dict)
    fast_weapons_list: list[str] = Field(default_factory=list)


class SavedGrollOut(BaseModel):
    auction_id: str
    payload: dict[str, Any]
    saved_at: datetime


class WeaponPricePoint(BaseModel):
    t: int  # unix seconds
    p1: int
    p2: int
    p3: int
