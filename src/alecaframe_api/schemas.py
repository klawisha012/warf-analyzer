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


# ---------------------------------------------------------------- WFM models


class OrderRow(BaseModel):
    side: str           # "sell" | "buy"
    price: int
    qty: int
    user: str
    status: str
    reputation: int
    platform: str = "pc"


class OrderBookStatsModel(BaseModel):
    side: str
    online_only: bool
    count_orders: int
    volume_qty: int
    min_price: int | None
    p10: int | None
    p25: int | None
    median: int | None
    p75: int | None
    p90: int | None
    max_price: int | None
    top5: list[int]


class OrderBookResponse(BaseModel):
    slug: str
    item_name: str
    fetched_at: str
    stale: bool = False
    sell: OrderBookStatsModel
    buy: OrderBookStatsModel
    top_orders: list[OrderRow] = Field(default_factory=list)


class ItemUseRef(BaseModel):
    """An item that uses some other item as a component in its recipe."""
    name: str
    unique_name: str
    count: int


class PricedItemEntry(BaseModel):
    unique_name: str
    name: str
    slug: str | None
    count: int | None = None
    vaulted: bool | None = None
    sell_min: int | None = None
    sell_median: int | None = None
    sell_spread: int | None = None
    buy_max: int | None = None
    estimated_value: int | None = None
    stale: bool = False
    used_in: list[ItemUseRef] = []


class PricedItemListResponse(BaseModel):
    total: int
    returned: int
    items: list[PricedItemEntry]


class SetProfitRowModel(BaseModel):
    set_slug: str
    set_name: str
    set_price: int
    parts_cost: int
    tax_estimate: int
    profit: int
    missing_parts: dict[str, int]
    owned_parts: dict[str, int]


class SetProfitResponse(BaseModel):
    total: int
    returned: int
    items: list[SetProfitRowModel]


class WtbMatchRow(BaseModel):
    slug: str
    item_name: str
    your_qty: int
    buyer: str
    buyer_status: str
    buyer_reputation: int
    offer_price: int


class WtbMatchResponse(BaseModel):
    total: int
    items: list[WtbMatchRow]


class RelistNudgeRow(BaseModel):
    slug: str
    item_name: str
    your_price: int
    median: int | None
    top5: list[int]
    suggestion: str   # e.g. "raise to 36" / "lower to 33"


class RelistNudgeResponse(BaseModel):
    total: int
    items: list[RelistNudgeRow]


class WFMItemRef(BaseModel):
    slug: str
    item_name: str
    thumb_url: str | None
    # v2 listing omits vaulted — only the per-item /v2/items/{slug} endpoint
    # carries it. Lifted to Optional so callers can distinguish "unknown" from "live".
    vaulted: bool | None = None
    wfm_id: str


class WFMItemsResponse(BaseModel):
    total: int
    items: list[WFMItemRef]


class PriceStatsModel(BaseModel):
    slug: str
    sell_min: int | None = None
    sell_median: int | None = None
    sell_spread: int | None = None
    buy_max: int | None = None
    fetched_at: float
    stale: bool = False


class PricesSnapshotResponse(BaseModel):
    total: int
    prices: dict[str, PriceStatsModel]
