import sqlite3
from app.core.paths import db_path

conn = sqlite3.connect(db_path())

conn.execute("""
CREATE TABLE IF NOT EXISTS overrides (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  date_yyyymmdd TEXT NOT NULL,
  schedule_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  applied_at TEXT NOT NULL DEFAULT (datetime('now')),
  note TEXT
);
""")

conn.commit()
print("overrides table created")
