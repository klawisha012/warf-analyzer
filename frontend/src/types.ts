// Minimal frontend types — only what components destructure. Backend is the
// source of truth; we don't redeclare every field that ships in the JSON, just
// the ones we read.

export interface RivenAttribute {
  url_name: string
  value: number
  positive: boolean
}

export interface RivenItem {
  name?: string
  weapon_url_name: string
  re_rolls?: number
  mod_rank?: number
  attributes: RivenAttribute[]
  type?: string
}

export interface AuctionOwner {
  ingame_name: string
  status?: string
}

export interface Auction {
  id: string
  buyout_price: number | null
  starting_price?: number | null
  top_bid?: number | null
  updated: string
  owner: AuctionOwner
  item: RivenItem
}

export type AlertReason = 'good stats' | 'endo' | 'pod roll'

export interface AlertItem {
  type?: 'alert'
  auction: Auction
  reason: AlertReason
  ts?: number
}

export interface WsStatsMessage {
  type: 'stats'
  api_updates: number
}

export interface WeaponPricePoint {
  t: number // unix seconds
  p1: number
  p2: number
  p3: number
}

export interface Settings {
  good_weapons: Record<string, number>
  fast_weapons_list: string[]
}

export interface SavedGroll {
  auction_id: string
  payload: Auction
  saved_at?: string
}

export interface WatchlistEntry {
  weapon: string
  latest_ts: number | null
  p1: number | null
  p2: number | null
  p3: number | null
}
