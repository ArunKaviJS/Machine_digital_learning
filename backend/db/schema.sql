-- Arun initial schema (migration 1). ISO-8601 timestamps + local date (YYYY-MM-DD).

CREATE TABLE IF NOT EXISTS usage_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    application TEXT NOT NULL,
    website TEXT,
    window_title TEXT,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    duration_seconds INTEGER NOT NULL,
    date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS water_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('reminder_shown','drank','snoozed','dismissed'))
);

CREATE TABLE IF NOT EXISTS tidy_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    folder TEXT NOT NULL,
    created_at TEXT NOT NULL,
    confirmed INTEGER NOT NULL DEFAULT 0,
    undone INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tidy_moves (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id INTEGER NOT NULL REFERENCES tidy_batches(id),
    original_path TEXT NOT NULL,
    new_path TEXT NOT NULL,
    moved_at TEXT NOT NULL,
    undone INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS guard_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    site TEXT,
    type TEXT NOT NULL CHECK(type IN ('nag','countdown_start','tab_closed','cancelled','snoozed'))
);

CREATE TABLE IF NOT EXISTS ai_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    intent TEXT,
    latency_ms INTEGER,
    success INTEGER NOT NULL DEFAULT 0,
    prompt TEXT            -- stored only when ai.logPrompts=true
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_usage_date ON usage_sessions(date);
CREATE INDEX IF NOT EXISTS idx_usage_site_date ON usage_sessions(website, date);
CREATE INDEX IF NOT EXISTS idx_water_date ON water_events(date);
CREATE INDEX IF NOT EXISTS idx_guard_date ON guard_events(date);
CREATE INDEX IF NOT EXISTS idx_moves_batch ON tidy_moves(batch_id);
