-- WAL pragmas are applied programmatically in repo.py; this file is pure DDL.

CREATE TABLE IF NOT EXISTS order_snapshots (
  slug          TEXT NOT NULL,
  ts            INTEGER NOT NULL,
  side          TEXT NOT NULL,
  online_only   INTEGER NOT NULL,
  count_orders  INTEGER NOT NULL,
  min_price     INTEGER,
  p10           INTEGER, p25 INTEGER, median INTEGER, p75 INTEGER, p90 INTEGER,
  max_price     INTEGER,
  volume_qty    INTEGER NOT NULL,
  top5_json     TEXT,
  PRIMARY KEY (slug, ts, side, online_only)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_snapshots_slug_ts ON order_snapshots(slug, ts DESC);

CREATE TABLE IF NOT EXISTS live_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  slug TEXT,
  event_type TEXT,
  payload_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_live_events_ts ON live_events(ts DESC);

CREATE TABLE IF NOT EXISTS signal_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  slug TEXT,
  signal_type TEXT,
  payload_json TEXT,
  dedup_key TEXT UNIQUE
);
CREATE INDEX IF NOT EXISTS idx_signal_events_ts ON signal_events(ts DESC);

CREATE TABLE IF NOT EXISTS wfm_items (
  slug TEXT PRIMARY KEY,
  url_name TEXT,
  item_name TEXT,
  thumb_url TEXT,
  mastery_req INTEGER,
  tags TEXT,
  vaulted INTEGER,
  unique_name TEXT,
  updated_at INTEGER
);

CREATE TABLE IF NOT EXISTS set_compositions (
  set_slug TEXT,
  part_slug TEXT,
  qty INTEGER,
  PRIMARY KEY (set_slug, part_slug)
);

-- Rivens: per-weapon watchlist + auction tracking + tier snapshots.

CREATE TABLE IF NOT EXISTS riven_watchlist (
  weapon_slug TEXT PRIMARY KEY,
  added_at    INTEGER NOT NULL,
  notes       TEXT
);

CREATE TABLE IF NOT EXISTS riven_snapshot (
  weapon_slug TEXT NOT NULL,
  ts          INTEGER NOT NULL,
  tier        TEXT NOT NULL,         -- 'god' | 'mid' | 'low' | 'all'
  count       INTEGER NOT NULL,
  min_price   INTEGER,
  p25         INTEGER,
  median      INTEGER,
  p75         INTEGER,
  max_price   INTEGER,
  PRIMARY KEY (weapon_slug, ts, tier)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_riven_snapshot_weapon_ts ON riven_snapshot(weapon_slug, ts DESC);

CREATE TABLE IF NOT EXISTS riven_auction (
  auction_id      TEXT PRIMARY KEY,
  weapon_slug     TEXT NOT NULL,
  first_seen      INTEGER NOT NULL,
  last_seen       INTEGER NOT NULL,
  buyout_price    INTEGER,
  starting_price  INTEGER,
  top_bid         INTEGER,
  re_rolls        INTEGER,
  mod_rank        INTEGER,
  polarity        TEXT,
  attributes_json TEXT,                -- [{name, value, positive}, ...]
  owner_name      TEXT,
  owner_status    TEXT,                -- 'ingame' | 'online' | 'offline'
  tier            TEXT,                -- our classification at last_seen
  status          TEXT NOT NULL,       -- 'active' | 'gone'
  gone_at         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_riven_auction_weapon ON riven_auction(weapon_slug, status);
CREATE INDEX IF NOT EXISTS idx_riven_auction_last_seen ON riven_auction(last_seen DESC);

-- Void Fissure subscriptions + Telegram chats + notification dedup ledger.

CREATE TABLE IF NOT EXISTS fissure_subscription (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  era          TEXT,            -- NULL = any
  mission_type TEXT,            -- NULL = any
  is_hard      INTEGER,         -- 0 | 1 | NULL(any)
  is_storm     INTEGER,         -- 0 | 1 | NULL(any)
  enabled      INTEGER NOT NULL DEFAULT 1,
  created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS telegram_chat (
  chat_id       INTEGER PRIMARY KEY,
  username      TEXT,
  registered_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS fissure_notification (
  subscription_id INTEGER NOT NULL,
  fissure_id      TEXT NOT NULL,
  notified_at     INTEGER NOT NULL,
  PRIMARY KEY (subscription_id, fissure_id)
) WITHOUT ROWID;
CREATE INDEX IF NOT EXISTS idx_fissure_notif_at ON fissure_notification(notified_at);
