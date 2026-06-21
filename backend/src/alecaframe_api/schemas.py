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
    # DE imageName (from cachedData) → warframestat CDN. Lets the UI show art
    # for items WFM has no thumbnail for (e.g. whole warframes, slug=None).
    image_name: str | None = None
    count: int | None = None
    vaulted: bool | None = None
    sell_min: int | None = None
    sell_median: int | None = None
    sell_spread: int | None = None
    buy_max: int | None = None
    estimated_value: int | None = None
    sell_min_max_rank: int | None = None
    buy_max_max_rank: int | None = None
    max_rank: int | None = None
    stale: bool = False
    used_in: list[ItemUseRef] = []


class PricedItemListResponse(BaseModel):
    total: int
    returned: int
    items: list[PricedItemEntry]


class ItemBaseStats(BaseModel):
    """Base (unmodded) reference stats for one item/warframe, from WFCD."""
    unique_name: str
    category: str | None = None
    name: str | None = None
    mastery_req: int | None = None
    disposition: float | None = None
    stats: dict[str, Any] = Field(default_factory=dict)
    source: str | None = None
    updated_at: int | None = None


class ItemBaseStatsListResponse(BaseModel):
    total: int
    items: list[ItemBaseStats]


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


# ---------------------------------------------------------------- Rivens


class RivenAuctionAttribute(BaseModel):
    name: str
    value: float | int
    positive: bool


class RivenAuctionRow(BaseModel):
    auction_id: str
    weapon_slug: str
    buyout_price: int | None = None
    starting_price: int | None = None
    top_bid: int | None = None
    re_rolls: int | None = None
    mod_rank: int | None = None
    polarity: str | None = None
    owner_name: str | None = None
    owner_status: str | None = None         # 'ingame' | 'online' | 'offline'
    tier: str
    attributes: list[RivenAuctionAttribute] = []


class RivenTierStats(BaseModel):
    tier: str
    count: int
    min_price: int | None = None
    p25: int | None = None
    median: int | None = None
    p75: int | None = None
    max_price: int | None = None


class RivenOutlier(BaseModel):
    auction_id: str
    tier: str
    price: int
    historical_median: int
    discount_pct: int


class RivenStrategyTip(BaseModel):
    kind: str
    severity: str
    ru: str
    en: str


class RivenTopAttribute(BaseModel):
    name: str
    count: int
    share: float


class RivenAuctionsResponse(BaseModel):
    weapon_slug: str
    fetched_at: str
    stale: bool = False
    tiers: dict[str, list[RivenAuctionRow]]      # 'god' | 'mid' | 'low'
    stats: list[RivenTierStats]                  # one per tier + 'all'
    outliers: list[RivenOutlier]
    top_attributes: list[RivenTopAttribute]
    strategies: list[RivenStrategyTip]
    avoid_negatives: list[str] = []
    harmless_negatives: list[str] = []


class RivenWatchEntry(BaseModel):
    weapon_slug: str
    added_at: int
    notes: str | None = None


class RivenWatchlistResponse(BaseModel):
    total: int
    items: list[RivenWatchEntry]


class RivenWatchAddRequest(BaseModel):
    weapon_slug: str
    notes: str | None = None


class RivenSnapshotRow(BaseModel):
    weapon_slug: str
    ts: int
    tier: str
    count: int
    min_price: int | None = None
    p25: int | None = None
    median: int | None = None
    p75: int | None = None
    max_price: int | None = None


class RivenHistoryResponse(BaseModel):
    weapon_slug: str
    tier: str
    items: list[RivenSnapshotRow]


# ----- void fissures -------------------------------------------------------


class FissureRow(BaseModel):
    id: str
    era: str
    mission_type: str
    node: str
    planet: str | None = None
    enemy: str | None = None
    is_hard: bool
    is_storm: bool
    expiry: str | None = None
    eta_seconds: int | None = None


class FissuresResponse(BaseModel):
    total: int
    items: list[FissureRow]


class FissureMetaResponse(BaseModel):
    eras: list[str]
    mission_types: list[str]


class FissureSubscriptionRow(BaseModel):
    id: int
    era: str | None = None
    mission_type: str | None = None
    is_hard: bool | None = None
    is_storm: bool | None = None
    enabled: bool = True
    created_at: int


class FissureSubscriptionsResponse(BaseModel):
    total: int
    items: list[FissureSubscriptionRow]


class FissureSubscriptionCreate(BaseModel):
    era: str | None = None
    mission_type: str | None = None
    is_hard: bool | None = None
    is_storm: bool | None = None


class TelegramChatRow(BaseModel):
    chat_id: int
    username: str | None = None
    registered_at: int


class TelegramChatsResponse(BaseModel):
    bot_enabled: bool
    bot_username: str | None = None
    total: int
    items: list[TelegramChatRow]
