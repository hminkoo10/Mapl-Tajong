"""마고에듀 통합 클라우드 동기화 (형식: docs/cloud-sync.md)

함께 쓰는 데이터를 동기화 폴더(MAGOEDU_DATA_DIR)에 JSON 으로 내보내고, 다른 기기에서 바뀐 파일이 오면 바로 적용한다.
서버와 주고받는 일은 통합 클라우드(런처)가 한다.

    config.json           시간표·세트·종소리 목록·지금 쓰는 세트
    state.json            잠시 멈춤, 오늘 쉬기, 다음 종 건너뛰기, 울리기 요청
    sounds/<파일>          종소리 파일 (sound_files 가 직접 씀)
    logs/<기기 ID>.json    그 기기가 남긴 기록 (자기 파일만 씀)

파일마다 두 가지를 기억해서 주고받기가 되풀이되지 않게 한다.
    _seen[파일]   : 마지막으로 읽거나 쓴 파일 내용 (meta 제외)
    _synced[파일] : 그때 이 기기 DB 로 만든 내용 → 이것과 다를 때만 쓴다

SQLite 는 화면 스레드에서만 쓰므로 이 모듈도 모두 화면 스레드(QTimer, QFileSystemWatcher)에서 돈다.
"""
import json
import os
import platform
import re
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer, pyqtSignal

from app.core import backup
from app.core.sound_files import copy_atomic, remove_leftover_tmp
from app.core.paths import asset_path, backups_dir, db_path, legacy_data_dir, sound_file_path, sync_dir
from app.data import repo

APP = "MaplTajong"
FORMAT = 1
CONFIG = "config.json"
STATE = "state.json"
LOGS = "logs"
SOUNDS = "sounds"

SHARED_ACTIONS = ("SKIP_ONCE", "PAUSE_DAY")   # state.json 에 넣는 오늘만 적용 (FIRED_ONCE 는 기기마다 따로)
LOG_DAYS = 60
LOG_MAX = 5000
REQUEST_KEEP_SEC = 10 * 60    # 쓸 때 이보다 오래된 울리기 요청은 지운다
REQUEST_WINDOW_SEC = 2 * 60   # 지금 ±2분 안의 요청만 울린다
HANDLED_KEEP_SEC = 24 * 60 * 60

EXPORT_DELAY_MS = 1000        # 바꾼 뒤 1초쯤 모아서 쓴다
LOG_EXPORT_DELAY_MS = 5000    # 기록은 5초쯤 모아서
CHECK_DELAY_MS = 300          # 파일이 바뀌었다는 알림 뒤 잠깐 기다렸다 읽는다
RETRY_MS = 1500               # 읽을 수 없는 파일(쓰는 중 등)은 조금 뒤 다시
MAX_TRIES = 5
POLL_MS = 30 * 1000           # 알림을 놓쳐도 30초마다 한 번 확인

OLD_SETTING_KEYS = ("update_auto", "update_notified", "update_pending_version", "update_pending_notes")


# ---------------------------------------------------------------------------
# 도움 함수
# ---------------------------------------------------------------------------
def utc_now():
    return datetime.now(timezone.utc)


def utc_iso(dt=None):
    return (dt or utc_now()).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(s):
    try:
        s = str(s).strip()
        if s.endswith("Z") or s.endswith("z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def safe_device_id(s):
    """파일 이름에 쓰므로 A-Z a-z 0-9 _ - 만 남긴다."""
    return re.sub(r"[^A-Za-z0-9_-]", "", str(s or ""))[:80]


def computer_name():
    return (os.environ.get("COMPUTERNAME") or platform.node() or "PC").strip() or "PC"


def device_identity(conn, session):
    """(기기 ID, 기기 이름). PC 의 기기 ID 는 실행 허가증의 dev. 없으면(개발 실행) 이 기기에 하나 만들어 둔다."""
    dev = safe_device_id((getattr(session, "payload", None) or {}).get("dev"))
    if not dev:
        dev = safe_device_id(repo.get_setting(conn, "device_id", ""))
        if not dev:
            dev = "pc-" + uuid.uuid4().hex[:12]
            repo.set_setting(conn, "device_id", dev)
    return dev, computer_name()


def content_key(doc):
    """meta 를 뺀 내용 (바뀌었는지 비교용)."""
    if not isinstance(doc, dict):
        return None
    body = {k: v for k, v in doc.items() if k != "meta"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def read_json(path):
    """없으면 None. 읽을 수 없거나(쓰는 중·잠김) 올바른 JSON 이 아니면 ValueError."""
    try:
        raw = Path(path).read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise ValueError(str(e))
    try:
        return json.loads(raw.decode("utf-8-sig"))
    except Exception as e:
        raise ValueError(f"JSON 이 아니에요: {e}")


def write_json_atomic(path, doc, compact=False):
    """.tmp 에 쓴 뒤 이름을 바꾼다 (원자적 저장)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    if compact:
        text = json.dumps(doc, ensure_ascii=False, separators=(",", ":"))
    else:
        text = json.dumps(doc, ensure_ascii=False, indent=1)
    with open(tmp, "wb") as f:
        f.write(text.encode("utf-8"))
        f.flush()
        os.fsync(f.fileno())
    err = None
    for i in range(4):
        try:
            os.replace(tmp, path)
            return
        except PermissionError as e:   # 통합 클라우드가 올리려고 읽는 중일 수 있음
            err = e
            time.sleep(0.05 * (i + 1))
    try:
        tmp.unlink()
    except OSError:
        pass
    raise err


def _sig(path):
    try:
        st = os.stat(path)
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size)


def _meta(device_id, device_name):
    return {"device_id": device_id, "device_name": device_name, "at": utc_iso()}


def _today():
    return datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# config.json
# ---------------------------------------------------------------------------
def build_config(conn):
    """백업 파일의 data.json 과 같은 내용 + 머리말 (meta 는 쓸 때 붙인다)."""
    doc = {"app": APP, "kind": "config", "format": FORMAT}
    for table, cols in backup._TABLES.items():
        rows = conn.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY id").fetchall()
        doc[table] = [dict(zip(cols, tuple(r))) for r in rows]
    doc["settings"] = {}
    for k in backup._SETTING_KEYS:
        r = conn.execute("SELECT value FROM settings WHERE key=?", (k,)).fetchone()
        if r:
            doc["settings"][k] = str(r[0])
    return doc


def _int(v):
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, float) and v.is_integer():
        return int(v)
    if isinstance(v, int):
        return v
    if isinstance(v, str) and re.fullmatch(r"-?\d+", v.strip()):
        return int(v.strip())
    raise ValueError(f"정수가 아니에요: {v!r}")


def _opt_int(v):
    return None if v is None else _int(v)


def _float(v):
    if isinstance(v, bool) or v is None:
        raise ValueError(f"숫자가 아니에요: {v!r}")
    return float(v)


def _opt_float(v):
    return None if v is None else _float(v)


def _text(v):
    if v is None or isinstance(v, (dict, list)):
        raise ValueError(f"글자가 아니에요: {v!r}")
    return str(v)


def _file_name(v):
    name = Path(_text(v)).name   # 경로 조작 방지
    if not name or name in (".", ".."):
        raise ValueError(f"파일 이름이 올바르지 않아요: {v!r}")
    return name


def _hhmm(v):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", _text(v).strip())
    if not m or int(m.group(1)) > 23 or int(m.group(2)) > 59:
        raise ValueError(f"시각이 올바르지 않아요: {v!r}")
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def _bool_int(v):
    return 1 if (v is True or (not isinstance(v, bool) and _int(v) != 0)) else 0


# 표마다: 열 → (바꾸는 함수, 꼭 있어야 하는지)
_COLUMNS = {
    "sounds": {"id": (_int, True), "name": (_text, True), "file_name": (_file_name, True),
               "volume": (_float, False), "created_at": (_text, False)},
    "schedule_sets": {"id": (_int, True), "name": (_text, True), "created_at": (_text, False)},
    "schedules": {"id": (_int, True), "set_id": (_opt_int, False), "name": (_text, True),
                  "weekday_mask": (_int, True), "time_hhmm": (_hhmm, True), "sound_id": (_int, True),
                  "volume_override": (_opt_float, False), "enabled": (_bool_int, False),
                  "sort_order": (_int, False), "created_at": (_text, False), "updated_at": (_text, False)},
}


def _check_head(doc, kind):
    if not isinstance(doc, dict) or doc.get("app") != APP or doc.get("kind") != kind:
        raise ValueError(f"{kind} 파일이 아니에요")
    try:
        fmt = _int(doc.get("format", 1))
    except ValueError:
        raise ValueError("format 이 올바르지 않아요")
    if fmt > FORMAT:
        raise ValueError("더 새로운 버전에서 만든 파일이에요")


def _validated_config(doc):
    _check_head(doc, "config")
    out = {}
    for table, cols in _COLUMNS.items():
        rows = doc.get(table)
        if not isinstance(rows, list):
            raise ValueError(f"{table} 이 없어요")
        clean = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{table} 줄이 올바르지 않아요")
            r = {}
            for col, (conv, required) in cols.items():
                if col not in row or (row[col] is None and conv not in (_opt_int, _opt_float)):
                    if required:
                        raise ValueError(f"{table}.{col} 이 없어요")
                    continue
                r[col] = conv(row[col])
            clean.append(r)
        out[table] = sorted(clean, key=lambda r: r["id"])
    settings = doc.get("settings") or {}
    if not isinstance(settings, dict):
        raise ValueError("settings 가 올바르지 않아요")
    out["settings"] = {k: str(settings[k]) for k in backup._SETTING_KEYS if settings.get(k) is not None}
    return out


def apply_config(conn, doc):
    """시간표·세트·종소리 줄을 파일 내용으로 바꾼다 (ID 그대로). 종소리 파일·기록·이 기기 설정은 건드리지 않는다.
    없어졌거나 시각이 바뀐 일정의 FIRED_ONCE·SKIP_ONCE 만 지운다. 지운 일정 ID 목록을 돌려준다."""
    data = _validated_config(doc)
    old_times = {int(r[0]): str(r[1]) for r in conn.execute("SELECT id, time_hhmm FROM schedules").fetchall()}
    try:
        conn.commit()
        conn.execute("BEGIN")
        conn.execute("DELETE FROM schedules")
        conn.execute("DELETE FROM schedule_sets")
        conn.execute("DELETE FROM sounds")
        for table in ("sounds", "schedule_sets", "schedules"):
            for row in data[table]:
                cols = list(row)
                conn.execute(f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                             tuple(row[c] for c in cols))
        if not data["schedule_sets"]:
            conn.execute("INSERT INTO schedule_sets(name) VALUES('기본')")
        for k, v in data["settings"].items():
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES(?, ?)", (k, v))
        valid = conn.execute(
            "SELECT 1 FROM schedule_sets WHERE id=(SELECT CAST(value AS INTEGER) FROM settings WHERE key='active_set_id')"
        ).fetchone()
        if not valid:
            first = conn.execute("SELECT id FROM schedule_sets ORDER BY id LIMIT 1").fetchone()[0]
            conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('active_set_id', ?)", (str(first),))
        new_times = {int(r["id"]): r["time_hhmm"] for r in data["schedules"]}
        gone = sorted(sid for sid, t in old_times.items() if new_times.get(sid) != t)
        if gone:
            q = ",".join("?" for _ in gone)
            conn.execute(f"DELETE FROM overrides WHERE schedule_id IN ({q}) AND action IN ('SKIP_ONCE','FIRED_ONCE')",
                         gone)
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise ValueError(f"적용하지 못했어요: {e}")
    return gone


# ---------------------------------------------------------------------------
# state.json
# ---------------------------------------------------------------------------
def build_state(conn, requests=(), today=None):
    today = today or _today()
    rows = conn.execute(
        "SELECT date_yyyymmdd, schedule_id, action, note FROM overrides "
        "WHERE action IN ('SKIP_ONCE','PAUSE_DAY') AND date_yyyymmdd >= ? "
        "ORDER BY date_yyyymmdd, schedule_id, action, id", (today,)).fetchall()
    seen = set()
    overrides = []
    for r in rows:
        key = (str(r[0]), int(r[1]), str(r[2]))
        if key in seen:
            continue
        seen.add(key)
        overrides.append({"date": key[0], "schedule_id": key[1], "action": key[2], "note": str(r[3] or "")})
    return {
        "app": APP, "kind": "state", "format": FORMAT,
        "paused": repo.get_setting(conn, "paused", "0") == "1",
        "overrides": overrides,
        "ring_requests": [dict(r) for r in requests],
    }


def _clean_request(r):
    if not isinstance(r, dict):
        return None
    rid = str(r.get("id") or "").strip()
    if not rid or parse_utc(r.get("at")) is None:
        return None
    try:
        sid = _opt_int(r.get("schedule_id"))
        snd = _opt_int(r.get("sound_id"))
    except ValueError:
        return None
    if sid is None and snd is None:
        return None
    return {"id": rid, "schedule_id": sid, "sound_id": snd, "at": str(r.get("at")),
            "by": str(r.get("by") or ""), "by_name": str(r.get("by_name") or "")}


def _validated_state(doc, today):
    _check_head(doc, "state")
    ov = doc.get("overrides", [])
    reqs = doc.get("ring_requests", [])
    if not isinstance(ov, list) or not isinstance(reqs, list):
        raise ValueError("state 가 올바르지 않아요")
    overrides = []
    seen = set()
    for o in ov:
        if not isinstance(o, dict):
            continue
        date = str(o.get("date") or "")
        action = str(o.get("action") or "")
        try:
            sid = _int(o.get("schedule_id", 0))
        except ValueError:
            continue
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or action not in SHARED_ACTIONS or date < today:
            continue
        if action == "PAUSE_DAY":
            sid = 0
        if (date, sid, action) in seen:
            continue
        seen.add((date, sid, action))
        overrides.append((date, sid, action, str(o.get("note") or "")))
    requests = [c for c in (_clean_request(r) for r in reqs) if c]
    return bool(doc.get("paused")), overrides, requests


def apply_state(conn, doc, today=None):
    """멈춤과 오늘·뒤 날짜의 SKIP_ONCE·PAUSE_DAY 를 파일 내용으로 바꾼다. (paused, 울리기 요청 목록) 을 돌려준다."""
    today = today or _today()
    paused, overrides, requests = _validated_state(doc, today)
    try:
        conn.commit()
        conn.execute("BEGIN")
        conn.execute("DELETE FROM overrides WHERE action IN ('SKIP_ONCE','PAUSE_DAY') AND date_yyyymmdd >= ?", (today,))
        for date, sid, action, note in overrides:
            conn.execute("INSERT INTO overrides(date_yyyymmdd, schedule_id, action, note) VALUES(?,?,?,?)",
                         (date, sid, action, note))
        conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('paused', ?)", ("1" if paused else "0",))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise ValueError(f"적용하지 못했어요: {e}")
    return paused, requests


# ---------------------------------------------------------------------------
# logs/<기기 ID>.json
# ---------------------------------------------------------------------------
def build_logs(conn, device_id, device_name, now=None):
    now = now or datetime.now()
    since = (now - timedelta(days=LOG_DAYS)).strftime("%Y-%m-%d 00:00:00")
    rows = conn.execute(
        "SELECT occurred_at, schedule_id, schedule_name, sound_name, result, detail FROM logs "
        "WHERE occurred_at >= ? ORDER BY id DESC LIMIT ?", (since, LOG_MAX)).fetchall()
    logs = [{"occurred_at": str(r[0]), "schedule_id": r[1], "schedule_name": r[2] or "", "sound_name": r[3] or "",
             "result": str(r[4]), "detail": r[5] or ""} for r in reversed(rows)]
    return {"app": APP, "kind": "logs", "format": FORMAT, "device_id": device_id, "device_name": device_name,
            "logs": logs}


def parse_logs(doc, fallback_id=""):
    """다른 기기의 기록 파일 → (기기 ID, 기기 이름, 줄 목록)."""
    if not isinstance(doc, dict) or doc.get("app") != APP or doc.get("kind") != "logs" \
            or not isinstance(doc.get("logs"), list):
        raise ValueError("기록 파일이 아니에요")
    dev = safe_device_id(doc.get("device_id")) or safe_device_id(fallback_id)
    name = str(doc.get("device_name") or dev or "다른 기기")
    rows = []
    for r in doc["logs"]:
        if not isinstance(r, dict):
            continue
        occ = str(r.get("occurred_at") or "")
        res = str(r.get("result") or "")
        if not re.match(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}", occ) or not res:
            continue
        try:
            sid = _opt_int(r.get("schedule_id"))
        except ValueError:
            sid = None
        rows.append({"id": None, "occurred_at": occ, "schedule_id": sid,
                     "schedule_name": str(r.get("schedule_name") or ""), "sound_name": str(r.get("sound_name") or ""),
                     "result": res, "detail": str(r.get("detail") or ""), "device_id": dev, "device_name": name})
    return dev, name, rows


def _log_matches(r, start, end, result, keyword):
    if start and r["occurred_at"] < start + " 00:00:00":
        return False
    if end and r["occurred_at"] > end + " 23:59:59":
        return False
    if result and result != "ALL" and r["result"] != result:
        return False
    if keyword:
        k = keyword.lower()
        if not any(k in str(r.get(c) or "").lower() for c in ("schedule_name", "sound_name", "detail")):
            return False
    return True


def list_logs(conn, remote_rows, start, end, result, keyword, limit):
    """기록 화면: 이 기기 기록 + 다른 기기 기록을 시간 순(최근 먼저)으로. device_name 이 None 이면 이 기기."""
    rows = []
    for r in repo.list_logs(conn, start, end, result, keyword, limit):
        d = dict(r)
        d["device_id"] = None
        d["device_name"] = None
        rows.append(d)
    rows += [r for r in remote_rows if _log_matches(r, start, end, result, keyword)]
    rows.sort(key=lambda r: (r["occurred_at"], r["id"] or 0), reverse=True)
    return rows[:int(limit)]


# ---------------------------------------------------------------------------
# 처음 연결할 때
# ---------------------------------------------------------------------------
def _compare_key(doc):
    """처음 연결할 때 '둘이 같은지' 볼 때 쓰는 내용 (meta·만든 시각 제외)."""
    if not isinstance(doc, dict):
        return None
    out = {}
    for table in ("sounds", "schedule_sets", "schedules"):
        out[table] = sorted(({k: v for k, v in r.items() if k not in ("created_at", "updated_at")}
                             for r in (doc.get(table) or []) if isinstance(r, dict)),
                            key=lambda r: str(r.get("id")))
    out["settings"] = {k: str(v) for k, v in (doc.get("settings") or {}).items()}
    return json.dumps(out, ensure_ascii=False, sort_keys=True, default=str)


def is_default_data(conn):
    """처음 설치한 그대로인지 (일정 없음, 세트 하나, 기본 종소리만)."""
    if conn.execute("SELECT COUNT(*) FROM schedules").fetchone()[0]:
        return False
    if conn.execute("SELECT COUNT(*) FROM schedule_sets").fetchone()[0] > 1:
        return False
    src = asset_path("sounds")
    bundled = {p.name for p in src.iterdir()} if src.exists() else set()
    return all(str(r[0]) in bundled for r in conn.execute("SELECT file_name FROM sounds").fetchall())


def _copy_sqlite(src, dst):
    """켜져 있는 예전 프로그램이 쓰는 중이어도 깨지지 않게 SQLite 백업 기능으로 복사한다."""
    s = sqlite3.connect(f"{Path(src).resolve().as_uri()}?mode=ro", uri=True)
    try:
        d = sqlite3.connect(str(dst))
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def copy_sound_files(src_dir, dst_dir, overwrite=False):
    src_dir, dst_dir = Path(src_dir), Path(dst_dir)
    if not src_dir.is_dir():
        return 0
    dst_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in src_dir.iterdir():
        if not p.is_file() or p.suffix.lower() == ".tmp":
            continue
        dst = dst_dir / p.name
        if dst.exists() and not overwrite:
            continue
        try:
            copy_atomic(p, dst)
            n += 1
        except OSError:
            pass
    return n


def open_database(schema_sql, ask_choice=None):
    """이 기기의 DB 를 연다 → (conn, prefer_local).

    처음 연결(이 기기에 tajong.db 가 없음)일 때:
      - 클라우드에 config.json 이 없으면: 예전에 따로 설치해 쓰던 데이터(%APPDATA%\\MaplTajong)가 있으면 그것을,
        없으면 기본 종소리로 시작한다. (내보내기는 CloudSync.start 가 한다)
      - 클라우드에 있고 예전 데이터가 기본값이 아니며 둘이 다르면 ask_choice() 로 고른다.
        'cloud'(기본): 예전 데이터는 백업 파일로 남기고 클라우드 것을 쓴다.
        'local': 예전 데이터로 클라우드를 바꾼다 → prefer_local=True
    통합 클라우드는 켜기 전에 동기화하므로, 이때 동기화 폴더에 있는 파일은 클라우드의 것이다.
    """
    from app.core.bootstrap import seed_if_empty
    from app.data.db import connect, init_schema

    db = db_path()
    fresh = not db.exists()
    legacy = legacy_data_dir()
    use_legacy = fresh and (legacy / "tajong.db").is_file()
    if use_legacy:
        try:
            _copy_sqlite(legacy / "tajong.db", db)
        except Exception:
            use_legacy = False
            for p in (db, db.with_name(db.name + "-journal")):
                try:
                    p.unlink()
                except OSError:
                    pass

    conn = connect()
    init_schema(conn, schema_sql)
    conn.execute(f"DELETE FROM settings WHERE key IN ({','.join('?' for _ in OLD_SETTING_KEYS)})", OLD_SETTING_KEYS)
    conn.commit()

    prefer_local = False
    if not fresh:
        return conn, prefer_local
    cfg = sync_dir() / CONFIG
    if not cfg.exists():
        if use_legacy:
            copy_sound_files(legacy / SOUNDS, sync_dir() / SOUNDS)
        else:
            seed_if_empty(conn)
        return conn, prefer_local
    if not use_legacy or is_default_data(conn):
        return conn, prefer_local
    try:
        cloud = read_json(cfg)
    except ValueError:
        cloud = None
    if cloud is None or _compare_key(build_config(conn)) == _compare_key(cloud):
        return conn, prefer_local
    choice = ask_choice() if ask_choice else "cloud"
    if choice == "local":
        copy_sound_files(legacy / SOUNDS, sync_dir() / SOUNDS, overwrite=True)
        prefer_local = True
    else:
        try:
            backup.export_backup(conn, backups_dir() / backup.default_backup_name(), sounds_from=legacy / SOUNDS)
        except Exception:
            pass
    return conn, prefer_local


# ---------------------------------------------------------------------------
# 동기화
# ---------------------------------------------------------------------------
class CloudSync(QObject):
    remote_applied = pyqtSignal(str)   # 'all'(config) | 'state' | 'logs' | 'sounds' — 다른 기기 것을 적용함
    notice = pyqtSignal(str, str)      # (알림 글, 종류)

    def __init__(self, conn, data_dir, device_id, device_name, scheduler=None, parent=None):
        super().__init__(parent)
        self.conn = conn
        self.dir = Path(data_dir)
        self.device_id = safe_device_id(device_id) or "pc"
        self.device_name = device_name
        self.scheduler = scheduler
        self.logs_dir = self.dir / LOGS
        self.sounds_dir = self.dir / SOUNDS
        self.own_logs = self.logs_dir / f"{self.device_id}.json"
        self._paths = {"config": self.dir / CONFIG, "state": self.dir / STATE}
        self._seen = {}
        self._synced = {}
        self._sig = {}
        self._tries = {}
        self._requests = []
        self._unsent = set()
        self._handled = self._load_handled()
        self._remote_logs = {}     # 파일 이름 → {"sig", "device_id", "name", "rows"}
        self._sounds_sig = None
        self.watcher = None

        self._export_timer = QTimer(self)
        self._export_timer.setSingleShot(True)
        self._export_timer.setInterval(EXPORT_DELAY_MS)
        self._export_timer.timeout.connect(self.export_now)
        self._logs_timer = QTimer(self)
        self._logs_timer.setSingleShot(True)
        self._logs_timer.setInterval(LOG_EXPORT_DELAY_MS)
        self._logs_timer.timeout.connect(self.export_logs)
        self._check_timer = QTimer(self)
        self._check_timer.setSingleShot(True)
        self._check_timer.timeout.connect(self.check_files)
        self._poll = QTimer(self)
        self._poll.setInterval(POLL_MS)
        self._poll.timeout.connect(self.check_files)

    # ---------- 시작 ----------
    def start(self, prefer_local=False, watch=True):
        """켤 때 한 번: 클라우드 파일을 적용하거나(있으면) 이 기기 것을 내보낸다(없으면)."""
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.sounds_dir.mkdir(parents=True, exist_ok=True)
        for d in (self.dir, self.sounds_dir, self.logs_dir):
            remove_leftover_tmp(d)   # 갑자기 꺼져서 남은 임시 파일 (동기화하지 않는 이름)
        for kind in ("config", "state"):
            self._initial(kind, prefer_local)
        self.export_logs()
        self._load_remote_logs()
        self._sounds_sig = self._sounds_listing()
        if watch:
            self.watcher = QFileSystemWatcher(self)
            self.watcher.directoryChanged.connect(self._on_fs)
            self.watcher.fileChanged.connect(self._on_fs)
            self._rewatch()
            self._poll.start()

    def _initial(self, kind, prefer_local):
        path = self._paths[kind]
        try:
            doc = read_json(path)
        except ValueError:
            self._schedule_check(RETRY_MS)   # 받는 중일 수 있음 → 조금 뒤 다른 기기 것으로 적용
            return
        if doc is None or prefer_local:
            self._export(kind, force=True)
            return
        self._sig[str(path)] = _sig(path)
        try:
            self._apply(kind, doc)
        except ValueError:
            pass

    # ---------- 이 기기에서 바뀜 → 내보내기 ----------
    def local_changed(self, what="all"):
        """함께 쓰는 데이터(시간표·세트·종소리·지금 세트·멈춤·건너뛰기·오늘 쉬기)를 바꾼 뒤 부른다."""
        self._export_timer.start()

    def log_added(self):
        if not self._logs_timer.isActive():
            self._logs_timer.start()

    def request_ring(self, schedule_id=None, sound_id=None):
        """이 기기에서 종을 울리지 않을 때 '지금 울리기': 종을 울리는 기기에 요청한다."""
        req = {"id": uuid.uuid4().hex, "schedule_id": None if schedule_id is None else int(schedule_id),
               "sound_id": None if sound_id is None else int(sound_id), "at": utc_iso(),
               "by": self.device_id, "by_name": self.device_name}
        self._requests.append(req)
        self._unsent.add(req["id"])
        self._export_timer.start()
        return req

    def export_now(self):
        self._export_timer.stop()
        self._export("config")
        self._export("state")

    def flush(self):
        """끄기 전에: 모아 둔 것을 바로 쓴다."""
        if self._export_timer.isActive():
            self.export_now()
        if self._logs_timer.isActive():
            self._logs_timer.stop()
            self.export_logs()

    def _build(self, kind, requests=None):
        if kind == "config":
            return build_config(self.conn)
        return build_state(self.conn, self._requests if requests is None else requests)

    def _export(self, kind, force=False):
        doc = self._build(kind)
        key = content_key(doc)
        if not force and key == self._synced.get(kind):
            return False
        path = self._paths[kind]
        if not force:
            # 받아 두고 아직 적용하지 않은 다른 기기 변경이 있으면 그쪽이 먼저 (서버에 먼저 올라간 것이 이김)
            try:
                disk = read_json(path)
            except ValueError:
                disk = None
            if disk is not None and content_key(disk) != self._seen.get(kind):
                try:
                    self._sig[str(path)] = _sig(path)
                    applied = self._apply(kind, disk)
                except ValueError:
                    pass
                else:
                    doc = self._build(kind)
                    key = content_key(doc)
                    if key == self._synced.get(kind):
                        if applied:
                            self.notice.emit("다른 기기에서 먼저 바뀌어서 그 내용으로 맞췄어요", "info")
                        return False
        if kind == "state":
            self._prune_requests()
            doc = self._build(kind)
            key = content_key(doc)
        doc["meta"] = _meta(self.device_id, self.device_name)
        try:
            write_json_atomic(path, doc)
        except OSError:
            QTimer.singleShot(RETRY_MS, self.local_changed)
            return False
        self._seen[kind] = key
        self._synced[kind] = key
        self._sig[str(path)] = _sig(path)
        if kind == "state":
            self._unsent.clear()
        return True

    def _prune_requests(self):
        now = utc_now()
        keep = []
        for r in self._requests:
            at = parse_utc(r.get("at"))
            if at is not None and (now - at).total_seconds() <= REQUEST_KEEP_SEC:
                keep.append(r)
        self._requests = keep

    def export_logs(self):
        self._logs_timer.stop()
        doc = build_logs(self.conn, self.device_id, self.device_name)
        key = content_key(doc)
        if key == self._seen.get("logs"):
            return False
        if "logs" not in self._seen:
            try:
                if content_key(read_json(self.own_logs)) == key:
                    self._seen["logs"] = key
                    return False
            except ValueError:
                pass
        try:
            write_json_atomic(self.own_logs, doc, compact=True)
        except OSError:
            QTimer.singleShot(RETRY_MS, self.log_added)
            return False
        self._seen["logs"] = key
        return True

    # ---------- 다른 기기에서 바뀜 → 적용 ----------
    def _apply(self, kind, doc):
        """파일 내용을 이 기기에 적용한다. 바뀐 것이 있으면 True. 올바르지 않으면 ValueError."""
        key = content_key(doc)
        if kind == "config":
            if key == self._seen.get(kind):
                return False
            if content_key(build_config(self.conn)) == key:
                self._seen[kind] = self._synced[kind] = key
                return False
            if self._export_timer.isActive():
                self.notice.emit("다른 기기에서 먼저 바뀌어서 그 내용으로 맞췄어요", "info")
            apply_config(self.conn, doc)
            self._seen[kind] = key
            self._synced[kind] = content_key(build_config(self.conn))
            self.remote_applied.emit("all")
            return True

        if key == self._seen.get(kind):
            return False
        paused, requests = apply_state(self.conn, doc)
        ids = {r["id"] for r in requests}
        unsent = [r for r in self._requests if r["id"] in self._unsent and r["id"] not in ids]
        self._unsent = {r["id"] for r in unsent}
        self._requests = requests + unsent
        self._seen[kind] = key
        self._synced[kind] = content_key(build_state(self.conn, requests))
        if self.scheduler is not None:
            self.scheduler.paused = paused
        self.remote_applied.emit("state")
        self.handle_requests()
        return True

    def _on_fs(self, _path=""):
        self._schedule_check(CHECK_DELAY_MS)

    def _schedule_check(self, ms):
        if not self._check_timer.isActive() or self._check_timer.remainingTime() > ms:
            self._check_timer.start(ms)

    def _failed(self, path, sig):
        n = self._tries.get(path, (None, 0))
        n = n[1] + 1 if n[0] == sig else 1
        self._tries[path] = (sig, n)
        if n < MAX_TRIES:
            self._schedule_check(RETRY_MS)
        else:
            self._sig[path] = sig   # 계속 올바르지 않으면 파일이 다시 바뀔 때까지 두고 본다

    def check_files(self):
        for kind in ("config", "state"):
            path = self._paths[kind]
            sp = str(path)
            sig = _sig(path)
            if sig == self._sig.get(sp):
                continue
            if sig is None:
                self._sig[sp] = None
                continue
            try:
                doc = read_json(path)
                if doc is None:
                    continue
                _check_head(doc, kind)
            except ValueError:
                self._failed(sp, sig)
                continue
            self._sig[sp] = sig
            self._tries.pop(sp, None)
            try:
                self._apply(kind, doc)
            except ValueError:
                pass
        self._load_remote_logs()
        snd = self._sounds_listing()
        if snd != self._sounds_sig:
            self._sounds_sig = snd
            self.remote_applied.emit("sounds")
        self._rewatch()

    def _rewatch(self):
        if self.watcher is None:
            return
        want = [str(p) for p in (self.dir, self.logs_dir, self.sounds_dir) if p.is_dir()]
        want += [str(p) for p in self._paths.values() if p.is_file()]
        have = set(self.watcher.directories()) | set(self.watcher.files())
        add = [p for p in want if p not in have]
        if add:
            self.watcher.addPaths(add)

    def _sounds_listing(self):
        try:
            return tuple(sorted((p.name, _sig(p)) for p in self.sounds_dir.iterdir() if p.suffix.lower() != ".tmp"))
        except OSError:
            return None

    # ---------- 다른 기기의 기록 ----------
    def _load_remote_logs(self):
        found = {}
        changed = False
        try:
            files = [p for p in self.logs_dir.glob("*.json") if p.name != self.own_logs.name]
        except OSError:
            files = []
        for p in files:
            sig = _sig(p)
            old = self._remote_logs.get(p.name)
            if old and old["sig"] == sig:
                found[p.name] = old
                continue
            try:
                dev, name, rows = parse_logs(read_json(p), p.stem)
            except ValueError:
                if old:
                    found[p.name] = old
                self._failed(str(p), sig)
                continue
            if dev == self.device_id:
                continue
            found[p.name] = {"sig": sig, "device_id": dev, "name": name, "rows": rows}
            changed = True
        if set(found) != set(self._remote_logs):
            changed = True
        self._remote_logs = found
        if changed:
            self.remote_applied.emit("logs")

    def remote_rows(self):
        out = []
        for v in self._remote_logs.values():
            out.extend(v["rows"])
        return out

    def remote_logs_on(self, date_yyyymmdd):
        return [r for r in self.remote_rows() if r["occurred_at"].startswith(date_yyyymmdd)]

    # ---------- 울리기 요청 ----------
    def _load_handled(self):
        try:
            data = json.loads(repo.get_setting(self.conn, "ring_handled", "{}") or "{}")
            return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save_handled(self):
        now = utc_now()
        keep = {}
        for k, v in self._handled.items():
            at = parse_utc(v)
            if at is not None and (now - at).total_seconds() <= HANDLED_KEEP_SEC:
                keep[k] = v
        self._handled = keep
        repo.set_setting(self.conn, "ring_handled", json.dumps(keep))

    def handle_requests(self):
        """종을 울리는 기기: 처음 보는 요청 중 지금 ±2분 안의 것만 한 번 울린다."""
        sch = self.scheduler
        if sch is None or not sch.ring_enabled:
            return 0
        now = utc_now()
        todo = []
        for r in self._requests:
            if r["id"] in self._handled or r["by"] == self.device_id:
                continue
            at = parse_utc(r["at"])
            if at is None or abs((now - at).total_seconds()) > REQUEST_WINDOW_SEC:
                continue
            self._handled[r["id"]] = r["at"]
            todo.append(r)
        if not todo:
            return 0
        self._save_handled()   # 울리다 꺼져도 다시 울리지 않게 먼저 기억
        for r in todo:
            who = r["by_name"] or "다른 기기"
            if r["schedule_id"] is not None:
                ev = sch.ring_schedule_now(r["schedule_id"], detail=f"forced · {who}")
                if ev is not None:
                    self.notice.emit(f"{who}에서 요청해서 {ev.name} 종을 울렸어요", "bell")
            else:
                s = repo.get_sound(self.conn, r["sound_id"])
                if s is None:
                    continue
                try:
                    sch.player.play(str(sound_file_path(str(s["file_name"]))), float(s["volume"]), str(s["name"]))
                    self.notice.emit(f"{who}에서 요청해서 {s['name']} 종소리를 울렸어요", "bell")
                except Exception as e:
                    self.notice.emit(f"{who}의 요청을 울리지 못했어요: {e}", "error")
        return len(todo)
