"""전체 백업/복원과 CSV 내보내기."""
import csv
import json
import logging
import math
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from app.core import data_sign
from app.core.paths import app_data_dir, sounds_dir
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
TAMPERED_MSG = "이 백업 파일은 프로그램 밖에서 바뀌었거나 예전 형식이라 불러올 수 없어요."


class BackupError(RuntimeError):
    pass


MAX_ID = 2 ** 31 - 1
MAX_NAME = 200
MAX_ROWS = {"sounds": 256, "schedule_sets": 128, "schedules": 2000}


def _validation_log(detail):
    logging.getLogger("tajong.validation").warning(detail)
    try:
        path = app_data_dir() / "validation.log"
        lines = path.read_text(encoding="utf-8").splitlines()[-199:] if path.exists() else []
        lines.append(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {detail[:1000]}")
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except (OSError, ValueError):
        pass


def _clean_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if abs(value) <= MAX_ID else None
    if isinstance(value, float) and math.isfinite(value) and value.is_integer() and abs(value) <= MAX_ID:
        return int(value)
    return None


def _setting_id(value):
    if isinstance(value, str) and len(value) <= 10 and re.fullmatch(r"[0-9]+", value):
        return _clean_int(int(value))
    return _clean_int(value)


def _json_int(value):
    """너무 긴 정수 하나 때문에 다른 JSON 항목까지 읽지 못하지 않게 한다."""
    return int(value) if len(value.lstrip("-")) <= 19 else None


def _clean_float(value):
    if type(value) not in (int, float):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if math.isfinite(value) else None


def _clean_text(value, limit=MAX_NAME, required=True):
    if not isinstance(value, str):
        return None
    value = value.strip()
    if (required and not value) or len(value) > limit or any(ord(c) < 32 for c in value):
        return None
    try:
        value.encode("utf-8")
    except UnicodeError:
        return None
    return value


def _clean_file_name(value):
    if not isinstance(value, str):
        return None
    if value.startswith("sounds/"):
        value = value[7:]
    try:
        if len(value.encode("utf-8")) > 255:
            return None
    except UnicodeError:
        return None
    if (not value or value in (".", "..") or re.search(r'[\\/:*?"<>|]', value) or
            len(value) > MAX_NAME or value.endswith((".", " ")) or
            any(ord(c) < 32 for c in value) or
            re.fullmatch(r"(?i:CON|CONIN\$|CONOUT\$|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])", value.split(".")[0])):
        return None
    return value


def _clean_time(value):
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"([0-9]{2}):([0-9]{2})", value)
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        return None
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _clean_bool(value, default=1):
    if isinstance(value, bool):
        return int(value)
    if type(value) in (int, float) and value in (0, 1):
        return int(value)
    return default


def sanitize_tables(data, logger=None):
    """백업/config 표를 안전한 SQLite 입력 형태로 보정한다."""
    logger = logger or _validation_log
    fixed = []

    def note(detail):
        if detail not in fixed:
            fixed.append(detail)

    raw_tables = data if isinstance(data, dict) else {}
    out = {}
    for table in _TABLES:
        raw = raw_tables.get(table)
        if not isinstance(raw, list):
            out[table] = []
            note(f"{table}: 목록이 아니어서 기본값 사용")
            continue
        if len(raw) > MAX_ROWS[table]:
            raw = raw[:MAX_ROWS[table]]
            note(f"{table}: 최대 개수 초과 항목 삭제")
        clean = []
        ids = set()
        names = set()
        for row in raw:
            if not isinstance(row, dict):
                note(f"{table}: 객체가 아닌 항목 삭제")
                continue
            rid = _clean_int(row.get("id"))
            if rid is None or not 0 < rid <= MAX_ID or rid in ids:
                note(f"{table}: 잘못된/중복 id 항목 삭제")
                continue
            item = {"id": rid}
            if table == "sounds":
                name = _clean_text(row.get("name"))
                fn = _clean_file_name(row.get("file_name"))
                if name is None or fn is None:
                    note("sounds: 이름 또는 파일명 오류 항목 삭제")
                    continue
                volume = _clean_float(row.get("volume", 1.0))
                if volume is None or not 0 <= volume <= 2:
                    volume = 1.0
                    note("sounds.volume: 기본값으로 보정")
                item.update(name=name, file_name=fn, volume=volume)
            elif table == "schedule_sets":
                name = _clean_text(row.get("name"))
                if name is None or name in names:
                    note("schedule_sets: 이름 오류 항목 삭제")
                    continue
                names.add(name)
                item["name"] = name
            else:
                # 세트가 생기기 전 백업에는 set_id 가 없다 (불러온 뒤 지금 세트로 옮겨짐)
                set_id = None if row.get("set_id") is None else _clean_int(row.get("set_id"))
                name = _clean_text(row.get("name"))
                mask = _clean_int(row.get("weekday_mask"))
                hhmm = _clean_time(row.get("time_hhmm"))
                sound_id = _clean_int(row.get("sound_id"))
                if ((row.get("set_id") is not None and (set_id is None or not 0 < set_id <= MAX_ID)) or name is None or
                        mask is None or not 1 <= mask <= 127 or hhmm is None or
                        sound_id is None or not 0 < sound_id <= MAX_ID):
                    note("schedules: 필수 값 오류 항목 삭제")
                    continue
                item.update(set_id=set_id, name=name, weekday_mask=mask, time_hhmm=hhmm, sound_id=sound_id)
                volume = row.get("volume_override")
                if volume is not None:
                    volume = _clean_float(volume)
                    if volume is None or not 0 <= volume <= 2:
                        volume = None
                        note("schedules.volume_override: 기본값으로 보정")
                    item["volume_override"] = volume
                item["enabled"] = _clean_bool(row.get("enabled", 1))
                if row.get("enabled", 1) not in (True, False, 0, 1):
                    note("schedules.enabled: 기본값으로 보정")
                sort_order = _clean_int(row.get("sort_order", 0))
                item["sort_order"] = sort_order if sort_order is not None and sort_order >= 0 else 0
                if sort_order is None or sort_order < 0:
                    note("schedules.sort_order: 기본값으로 보정")
            for col in (c for c in _TABLES[table] if c.endswith("_at")):
                if col not in row or row[col] is None:
                    continue
                text = _clean_text(row.get(col), 64, required=False)
                if text and _clean_timestamp(text):
                    item[col] = text
                else:
                    note(f"{table}.{col}: 기본값으로 보정")
            ids.add(rid)
            clean.append(item)
        out[table] = clean
    sounds = {r["id"] for r in out["sounds"]}
    sets = {r["id"] for r in out["schedule_sets"]}
    if out.get("schedules") is not None:
        valid = [r for r in out["schedules"] if r["sound_id"] in sounds and (r["set_id"] is None or r["set_id"] in sets)]
        if len(valid) != len(out["schedules"]):
            note("schedules: 존재하지 않는 소리/세트를 참조한 항목 삭제")
        out["schedules"] = valid
    settings = raw_tables.get("settings")
    if isinstance(settings, dict):
        active = _setting_id(settings.get("active_set_id"))
        out["settings"] = {"active_set_id": str(active)} if active in sets else {}
        if "active_set_id" in settings and active not in sets:
            note("settings.active_set_id: 기본값으로 보정")
    else:
        out["settings"] = {}
        if settings is not None:
            note("settings: 객체가 아니어서 기본값 사용")
    if fixed:
        logger("값 검증 보정: " + ", ".join(fixed[:20]) + (" 외" if len(fixed) > 20 else ""))
    return out


def _clean_timestamp(value):
    if not isinstance(value, str) or len(value) > 40 or not re.match(r"[0-9]{4}-[0-9]{2}-[0-9]{2}[T ]", value):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _check_sig(raw):
    """통합 클라우드가 키를 주면(서명을 씀) 서명이 맞는 data.json 만 받는다."""
    key = data_sign.data_key()
    if key and not data_sign.verify_bytes(raw, key):
        raise BackupError(TAMPERED_MSG)


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

    key = data_sign.data_key()
    tmp = dst.with_suffix(dst.suffix + ".part")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        if key:
            z.writestr("data.json", data_sign.dumps_signed(data, key, ensure_ascii=False, indent=2))
        else:
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
            m = json.loads(z.read("manifest.json").decode("utf-8"), parse_int=_json_int)
    except Exception:
        raise BackupError("타종 프로그램 백업 파일이 아닙니다.")
    if not isinstance(m, dict) or m.get("app") != "MaplTajong":
        raise BackupError("타종 프로그램 백업 파일이 아닙니다.")
    fmt = _clean_int(m.get("format", FORMAT))
    if fmt is None or fmt < 1:
        raise BackupError("타종 프로그램 백업 파일이 아닙니다.")
    if fmt > FORMAT:
        raise BackupError("더 최신 버전에서 만든 백업입니다. 프로그램을 업데이트해 주세요.")
    counts = m.get("counts")
    m["counts"] = {t: n if n is not None and 0 <= n <= MAX_ROWS[t] else 0
                   for t in _TABLES for n in [_clean_int(counts.get(t)) if isinstance(counts, dict) else None]}
    if counts is not None and counts != m["counts"]:
        _validation_log("manifest.counts: 기본값으로 보정")
    for field in ("app_version", "created_at"):
        value = _clean_text(m.get(field, ""), 64, required=False)
        if value is None:
            _validation_log(f"manifest.{field}: 기본값으로 보정")
        m[field] = value or ""
    if data_sign.data_key():   # 불러오기 전 확인 창에서 바로 알리게
        with zipfile.ZipFile(src) as z:
            _check_sig(z.read("data.json") if "data.json" in z.namelist() else b"")
    return m


def import_backup(conn, src, before_replace_files=None):
    """현재 시간표/종소리를 백업 내용으로 교체한다. (로그는 유지)"""
    read_manifest(src)
    with zipfile.ZipFile(src) as z:
        raw = z.read("data.json")
        _check_sig(raw)
        try:
            data = json.loads(raw.decode("utf-8"), parse_int=_json_int)
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            raise BackupError("백업 데이터 형식이 올바르지 않아요.") from e
        if not isinstance(data, dict):
            raise BackupError("백업 데이터 형식이 올바르지 않아요.")
        data = sanitize_tables(data)
        names = set(z.namelist())

        if before_replace_files:
            before_replace_files()

        sd = sounds_dir()
        for s in data["sounds"]:
            fn = s["file_name"]
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
            for row in data[table]:
                present = [c for c in cols if c in row]
                conn.execute(
                    f"INSERT INTO {table} ({', '.join(present)}) VALUES ({', '.join('?' for _ in present)})",
                    tuple(row[c] for c in present),
                )
        if not data["schedule_sets"]:
            conn.execute("INSERT INTO schedule_sets(name) VALUES('기본')")
        for k, v in data["settings"].items():
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
    return {t: len(data[t]) for t in _TABLES}


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
