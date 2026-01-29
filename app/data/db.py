import sqlite3
from app.core.paths import db_path

def connect():
    conn = sqlite3.connect(db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def _has_table(conn, name):
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)
    ).fetchone()
    return row is not None

def _has_column(conn, table, col):
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    except:
        return False
    for r in rows:
        if r[1] == col:
            return True
    return False

def init_schema(conn, schema_sql):
    conn.executescript(schema_sql)
    conn.commit()

    if not _has_table(conn, "overrides"):
        conn.execute("""
        CREATE TABLE overrides (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          date_yyyymmdd TEXT NOT NULL,
          schedule_id INTEGER NOT NULL,
          action TEXT NOT NULL,
          applied_at TEXT NOT NULL DEFAULT (datetime('now')),
          note TEXT
        );
        """)
        conn.commit()

    if not _has_table(conn, "schedule_sets"):
        conn.execute("""
        CREATE TABLE schedule_sets (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL UNIQUE,
          created_at TEXT NOT NULL DEFAULT (datetime('now'))
        );
        """)
        conn.commit()

    if not _has_table(conn, "settings"):
        conn.execute("""
        CREATE TABLE settings (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );
        """)
        conn.commit()

    if _has_table(conn, "schedules") and (not _has_column(conn, "schedules", "set_id")):
        conn.execute("ALTER TABLE schedules ADD COLUMN set_id INTEGER")
        conn.commit()

    row = conn.execute("SELECT 1 FROM schedule_sets LIMIT 1").fetchone()
    if row is None:
        conn.execute("INSERT INTO schedule_sets(name) VALUES(?)", ("기본",))
        conn.commit()

    row = conn.execute("SELECT value FROM settings WHERE key='active_set_id'").fetchone()
    if row is None:
        sid = conn.execute("SELECT id FROM schedule_sets ORDER BY id ASC LIMIT 1").fetchone()[0]
        conn.execute(
            "INSERT OR REPLACE INTO settings(key,value) VALUES('active_set_id',?)",
            (str(int(sid)),)
        )
        conn.commit()

    sid = conn.execute("SELECT value FROM settings WHERE key='active_set_id'").fetchone()[0]
    try:
        sid = int(sid)
    except:
        sid = 0

    if sid != 0 and _has_table(conn, "schedules") and _has_column(conn, "schedules", "set_id"):
        conn.execute("UPDATE schedules SET set_id=? WHERE set_id IS NULL", (sid,))
        conn.commit()
