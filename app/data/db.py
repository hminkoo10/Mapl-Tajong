import sqlite3
from app.core.paths import db_path

def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_schema(conn, schema_sql):
    conn.executescript(schema_sql)

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
