import sqlite3
from app.core.paths import db_path

print("DB PATH:", db_path())

conn = sqlite3.connect(db_path())
rows = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()

print("TABLES:", [r[0] for r in rows])
