"""전체 백업/복원과 CSV 내보내기."""
import csv
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from app.core.paths import sounds_dir
from app.core.sound_files import write_atomic
from app.core.version import APP_VERSION

FORMAT = 1
_TABLES = {
    "sounds": ["id", "name", "file_name", "volume", "created_at"],
    "schedule_sets": ["id", "name", "created_at"],
    "schedules": ["id", "set_id", "name", "weekday_mask", "time_hhmm", "sound_id", "volume_override",
                  "enabled", "sort_order", "created_at", "updated_at"],
}
_SETTING_KEYS = ["active_set_id"]


class BackupError(RuntimeError):
    pass


def default_backup_name():
    return f"마고타종_백업_{datetime.now().strftime('%Y%m%d_%H%M')}.zip"


def export_backup(conn, dst, sounds_from=None):
    """sounds_from: 종소리 파일이 있는 폴더 (없으면 지금 종소리 폴더)"""
    dst = Path(dst)
    data = {}
    for table, cols in _TABLES.items():
        rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY id").fetchall()
        data[table] = [dict(zip(cols, tuple(r))) for r in rows]
    data["settings"] = {}
    for k in _SETTING_KEYS:
        r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
        if r:
            data["settings"][k] = r[0]

    manifest = {
        "app": "MaplTajong",
        "format": FORMAT,
        "app_version": APP_VERSION,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "counts": {t: len(v) for t, v in data.items() if isinstance(v, list)},
    }

    tmp = dst.with_suffix(dst.suffix + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        z.writestr("data.json", json.dumps(data, ensure_ascii=False, indent=2))
        sd = Path(sounds_from) if sounds_from else sounds_dir()
        for s in data["sounds"]:
            f = sd / s["file_name"]
            if f.exists():
                z.write(f, f"sounds/{s['file_name']}")
    tmp.replace(dst)
    return manifest


def _extract(z, member, path):
    with z.open(member) as fsrc, open(path, "wb") as fdst:
        shutil.copyfileobj(fsrc, fdst)


def read_manifest(src):
    try:
        with zipfile.ZipFile(src) as z:
            m = json.loads(z.read("manifest.json").decode("utf-8"))
    except Exception:
        raise BackupError("타종 프로그램 백업 파일이 아닙니다.")
    if m.get("app") != "MaplTajong":
        raise BackupError("타종 프로그램 백업 파일이 아닙니다.")
    if int(m.get("format", 0)) > FORMAT:
        raise BackupError("더 최신 버전에서 만든 백업입니다. 프로그램을 업데이트해 주세요.")
    return m


def import_backup(conn, src, before_replace_files=None):
    """현재 시간표/종소리를 백업 내용으로 교체한다. (로그는 유지)"""
    read_manifest(src)
    with zipfile.ZipFile(src) as z:
        data = json.loads(z.read("data.json").decode("utf-8"))
        names = set(z.namelist())

        if before_replace_files:
            before_replace_files()

        sd = sounds_dir()
        for s in data.get("sounds", []):
            fn = Path(str(s["file_name"])).name  # 경로 조작 방지
            s["file_name"] = fn
            member = f"sounds/{fn}"
            if member in names:
                write_atomic(sd / fn, lambda tmp, m=member: _extract(z, m, tmp))

    try:
        conn.commit()
        conn.execute("BEGIN")
        conn.execute("DELETE FROM schedules")
        conn.execute("DELETE FROM schedule_sets")
        conn.execute("DELETE FROM sounds")
        conn.execute("DELETE FROM overrides WHERE action IN ('SKIP_ONCE','FIRED_ONCE')")
        for table in ("sounds", "schedule_sets", "schedules"):
            cols = _TABLES[table]
            for row in data.get(table, []):
                present = [c for c in cols if c in row]
                conn.execute(
                    f"INSERT INTO {table} ({', '.join(present)}) VALUES ({', '.join('?' for _ in present)})",
                    tuple(row[c] for c in present),
                )
        if not data.get("schedule_sets"):
            conn.execute("INSERT INTO schedule_sets(name) VALUES('기본')")
        for k, v in (data.get("settings") or {}).items():
            if k in _SETTING_KEYS:
                conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (k, str(v)))
        valid = conn.execute(
            "SELECT 1 FROM schedule_sets WHERE id=(SELECT CAST(value AS INTEGER) FROM settings WHERE key='active_set_id')"
        ).fetchone()
        if not valid:
            first = conn.execute("SELECT id FROM schedule_sets ORDER BY id LIMIT 1").fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('active_set_id', ?)", (str(first),))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise BackupError(f"복원 중 오류가 발생했습니다: {e}")
    return {t: len(data.get(t, [])) for t in _TABLES}


def _write_csv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


RESULT_LABELS = {
    "PLAYED": "울림", "SKIPPED": "건너뜀", "FAILED": "실패", "MISSED": "놓침",
}


def export_logs_csv(rows, path):
    """rows: 기록 화면의 줄 (device_name 이 없으면 이 컴퓨터 기록)"""
    _write_csv(path, ["시간", "결과", "이벤트", "종소리", "기기", "상세"], [
        (r["occurred_at"], RESULT_LABELS.get(r["result"], r["result"]), r["schedule_name"] or "",
         r["sound_name"] or "", dict(r).get("device_name") or "이 컴퓨터", r["detail"] or "")
        for r in rows
    ])


def export_schedules_csv(conn, path):
    from app.core.timeutil import mask_to_days
    rows = conn.execute("""
        SELECT ss.name AS set_name, s.time_hhmm, s.name, s.weekday_mask, so.name AS sound_name,
               s.volume_override, so.volume AS sound_volume, s.enabled
        FROM schedules s
        JOIN schedule_sets ss ON ss.id = s.set_id
        JOIN sounds so ON so.id = s.sound_id
        ORDER BY ss.id, s.time_hhmm, s.id
    """).fetchall()
    out = []
    for r in rows:
        v = r["volume_override"] if r["volume_override"] is not None else r["sound_volume"]
        out.append((r["set_name"], r["time_hhmm"], r["name"], mask_to_days(r["weekday_mask"]),
                    r["sound_name"], f"{int(round(float(v) * 100))}%", "ON" if int(r["enabled"]) else "OFF"))
    _write_csv(path, ["세트", "시간", "이벤트", "요일", "종소리", "음량", "활성"], out)
    return len(out)
