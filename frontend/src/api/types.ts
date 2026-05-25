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
