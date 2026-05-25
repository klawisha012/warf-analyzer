import { api } from "./client";
import type {
  ApiInfo, HealthResponse,
  OrderBookResponse,
  PricedItemListResponse,
  PricesSnapshotResponse,
  RefreshResponse,
  RelistNudgeResponse,
  RivenAuctionsResponse,
  RivenHistoryResponse,
  RivenWatchlistResponse,
  RivenWeaponsResponse,
  SetProfitResponse,
  WFMItemsResponse,
  WtbMatchResponse,
} from "./types";

/** Query-key factory — keep all keys here so devtools / invalidations are predictable. */
export const keys = {
  info:           () => ["info"] as const,
  healthz:        () => ["healthz"] as const,
  wfmItems:       () => ["wfm", "items"] as const,
  wfmOrders:      (slug: string, opts: { includeOffline: boolean }) =>
    ["wfm", "orders", slug, opts] as const,
  meListings:     () => ["me", "listings"] as const,
  meInventory:    (slot: string, limit: number) => ["me", "inventory-priced", slot, limit] as const,
  mePrimeParts:   (min_count: number) => ["me", "prime-parts-priced", min_count] as const,
  meSetsProfit:   (min_margin: number) => ["me", "sets-profit", min_margin] as const,
  meWtbMatches:   (min_offer: number) => ["me", "wtb-matches", min_offer] as const,
  meRelistNudges: () => ["me", "relist-nudges"] as const,
  rivenAuctions:  (slug: string) => ["rivens", "auctions", slug] as const,
  rivenWatchlist: () => ["rivens", "watchlist"] as const,
  rivenHistory:   (slug: string, tier: string, days: number) => ["rivens", "history", slug, tier, days] as const,
  rivenWeapons:   () => ["rivens", "weapons"] as const,
};

export const fetchers = {
  info: () => api<ApiInfo>("/"),
  healthz: () => api<HealthResponse>("/healthz"),
  wfmItems: () => api<WFMItemsResponse>("/wfm/items"),
  wfmOrders: (slug: string, includeOffline: boolean) =>
    api<OrderBookResponse>(`/wfm/orders/${encodeURIComponent(slug)}?include_offline=${includeOffline ? 1 : 0}`),
  meListings: () => api<unknown>("/me/listings"),
  meInventory: (slot: string, limit: number) =>
    api<PricedItemListResponse>(`/me/inventory-priced?slot=${slot}&limit=${limit}`),
  mePrimeParts: (min_count: number) =>
    api<PricedItemListResponse>(`/me/prime-parts-priced?min_count=${min_count}`),
  meSetsProfit: (min_margin: number) =>
    api<SetProfitResponse>(`/me/sets-profit?min_margin=${min_margin}`),
  meWtbMatches: (min_offer: number) =>
    api<WtbMatchResponse>(`/me/wtb-matches?min_offer=${min_offer}`),
  meRelistNudges: () => api<RelistNudgeResponse>("/me/relist-nudges"),
  refresh: () => api<RefreshResponse>("/refresh", { method: "POST" }),
  prices: (slugs: string[]) =>
    api<PricesSnapshotResponse>(`/prices?slugs=${encodeURIComponent(slugs.join(","))}`),
  rivenAuctions: (slug: string, fresh = false) =>
    api<RivenAuctionsResponse>(`/rivens/auctions/${encodeURIComponent(slug)}${fresh ? "?fresh=1" : ""}`),
  rivenWatchlist: () => api<RivenWatchlistResponse>("/rivens/watchlist"),
  rivenWatchAdd: (slug: string, notes?: string) =>
    api<RivenWatchlistResponse>("/rivens/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ weapon_slug: slug, notes }),
    }),
  rivenWatchRemove: (slug: string) =>
    api<{ removed: string }>(`/rivens/watchlist/${encodeURIComponent(slug)}`, { method: "DELETE" }),
  rivenHistory: (slug: string, tier = "all", days = 7) =>
    api<RivenHistoryResponse>(`/rivens/history/${encodeURIComponent(slug)}?tier=${tier}&days=${days}`),
  rivenWeapons: () => api<RivenWeaponsResponse>("/rivens/weapons"),
};
