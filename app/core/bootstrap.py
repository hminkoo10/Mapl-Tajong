import shutil
from app.core.paths import sounds_dir, asset_path

def seed_if_empty(conn):
    src_dir = asset_path("sounds")
    dst_dir = sounds_dir()

    if not src_dir.exists():
        return

    existing = {
        r["file_name"]
        for r in conn.execute("SELECT file_name FROM sounds").fetchall()
    }

    for p in src_dir.iterdir():
        if not p.is_file():
            continue

        if p.suffix.lower() not in [".wav", ".mp3"]:
            continue

        if p.name in existing:
            continue

        dst = dst_dir / p.name
        if not dst.exists():
            shutil.copy2(p, dst)

        conn.execute(
            "INSERT INTO sounds(name, file_name, volume) VALUES (?,?,?)",
            (p.stem, p.name, 1.0)
        )

    conn.commit()