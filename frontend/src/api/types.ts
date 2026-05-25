/** Mirror of `src/alecaframe_api/schemas.py` Pydantic models, hand-maintained.
 *
 * Keep alphabetical by export to make additions easy to spot in diffs.
 */

export type ApiInfo = {
  name: string;
  version: string;
  docs_url: string;
  endpoints: string[];
};

export type HealthResponse = {
  ok: boolean;
  wfm_username: string | null;
  aleca_version: string | null;
  cache: Record<string, unknown>;
};

export type OrderRow = {
  side: "sell" | "buy" | string;
  price: number;
  qty: number;
  user: string;
  status: string;
  reputation: number;
  platform: string;
};

export type OrderBookStats = {
  side: "sell" | "buy" | string;
  online_only: boolean;
  count_orders: number;
  volume_qty: number;
  min_price: number | null;
  p10: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  p90: number | null;
  max_price: number | null;
  top5: number[];
};

export type OrderBookResponse = {
  slug: string;
  item_name: string;
  fetched_at: string;
  stale: boolean;
  sell: OrderBookStats;
  buy: OrderBookStats;
  top_orders: OrderRow[];
};

export type ItemUse = {
  name: string;
  unique_name: string;
  count: number;
};

export type PricedItem = {
  unique_name: string;
  name: string;
  slug: string | null;
  count: number | null;
  vaulted: boolean | null;
  sell_min: number | null;
  sell_median: number | null;
  sell_spread: number | null;
  buy_max: number | null;
  estimated_value: number | null;
  stale: boolean;
  used_in: ItemUse[];
};

export type PricedItemListResponse = {
  total: number;
  returned: number;
  items: PricedItem[];
};

export type RefreshResponse = {
  ok: boolean;
  files: Record<string, unknown>;
  meta: Record<string, unknown>;
  elapsed_ms: number | null;
};

export type RelistNudge = {
  slug: string;
  item_name: string;
  your_price: number;
  median: number | null;
  top5: number[];
  suggestion: string;
};

export type RelistNudgeResponse = { total: number; items: RelistNudge[] };

export type SetProfitRow = {
  set_slug: string;
  set_name: string;
  set_price: number;
  parts_cost: number;
  tax_estimate: number;
  profit: number;
  missing_parts: Record<string, number>;
  owned_parts: Record<string, number>;
};

export type SetProfitResponse = { total: number; returned: number; items: SetProfitRow[] };

export type WFMItemRef = {
  slug: string;
  item_name: string;
  thumb_url: string | null;
  // v2 listing omits vaulted; only the per-item endpoint exposes it.
  vaulted: boolean | null;
  wfm_id: string;
};

export type WFMItemsResponse = { total: number; items: WFMItemRef[] };

export type PriceStats = {
  slug: string;
  sell_min: number | null;
  sell_median: number | null;
  sell_spread: number | null;
  buy_max: number | null;
  fetched_at: number;
  stale: boolean;
};

export type PricesSnapshotResponse = {
  total: number;
  prices: Record<string, PriceStats>;
};

// ---------------------------------------------------------------- Rivens

export type RivenAuctionAttribute = {
  name: string;
  value: number;
  positive: boolean;
};

export type RivenAuctionRow = {
  auction_id: string;
  weapon_slug: string;
  buyout_price: number | null;
  starting_price: number | null;
  top_bid: number | null;
  re_rolls: number | null;
  mod_rank: number | null;
  polarity: string | null;
  owner_name: string | null;
  owner_status: string | null;       // 'ingame' | 'online' | 'offline'
  tier: string;
  attributes: RivenAuctionAttribute[];
};

export type RivenTierStats = {
  tier: string;
  count: number;
  min_price: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  max_price: number | null;
};

export type RivenOutlier = {
  auction_id: string;
  tier: string;
  price: number;
  historical_median: number;
  discount_pct: number;
};

export type RivenStrategyTip = {
  kind: string;
  severity: "info" | "warn" | "good" | string;
  ru: string;
  en: string;
};

export type RivenTopAttribute = {
  name: string;
  count: number;
  share: number;
};

export type RivenAuctionsResponse = {
  weapon_slug: string;
  fetched_at: string;
  stale: boolean;
  tiers: { god: RivenAuctionRow[]; mid: RivenAuctionRow[]; low: RivenAuctionRow[] };
  stats: RivenTierStats[];
  outliers: RivenOutlier[];
  top_attributes: RivenTopAttribute[];
  strategies: RivenStrategyTip[];
};

export type RivenWatchEntry = {
  weapon_slug: string;
  added_at: number;
  notes: string | null;
};

export type RivenWatchlistResponse = { total: number; items: RivenWatchEntry[] };

export type RivenSnapshotRow = {
  weapon_slug: string;
  ts: number;
  tier: string;
  count: number;
  min_price: number | null;
  p25: number | null;
  median: number | null;
  p75: number | null;
  max_price: number | null;
};

export type RivenHistoryResponse = {
  weapon_slug: string;
  tier: string;
  items: RivenSnapshotRow[];
};

export type RivenWeapon = {
  slug: string;
  item_name: string;
  icon: string | null;
  disposition: number | null;
  riven_type: string | null;
  group: string | null;
};

export type RivenWeaponsResponse = { total: number; items: RivenWeapon[] };

export type WtbMatch = {
  slug: string;
  item_name: string;
  your_qty: number;
  buyer: string;
  buyer_status: string;
  buyer_reputation: number;
  offer_price: number;
};

export type WtbMatchResponse = { total: number; items: WtbMatch[] };
