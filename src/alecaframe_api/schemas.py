"""Pydantic response schemas for the public API."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Currencies(BaseModel):
    platinum: int = Field(description="Tradeable platinum balance")
    platinum_free: int = Field(description="Non-tradeable platinum (from gifts/promos)")
    credits: int
    endo: int
    ducats: int
    trades_remaining: int
    gifts_remaining: int


class Standing(BaseModel):
    syndicate: str
    earned_today: int
    note: str | None = None


class StandingsResponse(BaseModel):
    cap_seems_to_be: int | None = None
    items: list[Standing]


class SummaryResponse(BaseModel):
    wfm_username: str | None = None
    currencies: Currencies
    section_counts: dict[str, int]
    standing_summary: dict[str, int]
    mastery_rank: int | None = None
    aleca_version: str | None = None
    cache: dict[str, Any]


class ItemEntry(BaseModel):
    unique_name: str
    name: str
    category: str | None = None
    count: int | None = None
    xp: int | None = None
    item_id: str | None = None
    extra: dict[str, Any] | None = None


class ItemListResponse(BaseModel):
    total: int
    returned: int
    items: list[ItemEntry]


class PrimePartRow(BaseModel):
    unique_name: str
    name: str
    count: int
    ducats: int | None = None
    is_blueprint: bool = False


class PrimePartsResponse(BaseModel):
    unique_items: int
    total_count: int
    total_ducat_value: int | None = None
    items: list[PrimePartRow]


class FoundryItem(BaseModel):
    unique_name: str
    name: str
    completion_date: str | None = None
    skipped: bool | None = None


class FoundryResponse(BaseModel):
    pending: list[FoundryItem]


class HealthResponse(BaseModel):
    ok: bool
    wfm_username: str | None = None
    aleca_version: str | None = None
    cache: dict[str, Any]


class RefreshResponse(BaseModel):
    ok: bool
    files: dict[str, Any]
    meta: dict[str, Any]
    elapsed_ms: int | None = None


class ApiInfo(BaseModel):
    name: str = "alecaframe-api"
    version: str
    docs_url: str = "/docs"
    endpoints: list[str]
