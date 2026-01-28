PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS sounds (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  file_name TEXT NOT NULL,
  volume REAL NOT NULL DEFAULT 1.0,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS schedules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  weekday_mask INTEGER NOT NULL,
  time_hhmm TEXT NOT NULL,
  sound_id INTEGER NOT NULL,
  volume_override REAL,
  enabled INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now')),
  FOREIGN KEY(sound_id) REFERENCES sounds(id)
);

CREATE TABLE IF NOT EXISTS logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL,
  schedule_id INTEGER,
  schedule_name TEXT,
  sound_name TEXT,
  result TEXT NOT NULL,
  detail TEXT
);

CREATE TABLE IF NOT EXISTS overrides (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date_yyyymmdd TEXT NOT NULL,
  schedule_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT (datetime('now')),
  note TEXT
);