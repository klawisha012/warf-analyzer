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
