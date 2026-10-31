"""종소리 파일 관리: 추가, 편집 저장, 원본 보관/복원, 길이 계산."""
import re
import shutil
import time
import wave
from pathlib import Path

from app.core import ffmpeg
from app.core.audio_edit import EditParams, render_edit
from app.core.paths import originals_dir, sounds_dir, temp_dir
from app.data import repo

AUDIO_EXTS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".opus", ".webm"}
PLAYABLE_EXTS = {".wav", ".mp3", ".ogg"}  # pygame이 바로 재생 가능한 형식

_bad = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


def safe_stem(name, fallback="sound"):
    s = _bad.sub("_", str(name or "")).strip(" .")
    return (s or fallback)[:60]


def unique_path(stem, ext):
    d = sounds_dir()
    ext = ext if ext.startswith(".") else "." + ext
    p = d / f"{stem}{ext}"
    n = 2
    while p.exists():
        p = d / f"{stem}_{n}{ext}"
        n += 1
    return p


def import_file(src):
    """파일을 종소리 폴더로 복사(필요하면 wav로 변환)하고 그 경로를 돌려준다. 오래 걸릴 수 있어 작업 스레드용."""
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError("선택한 파일을 찾을 수 없습니다.")
    stem = safe_stem(src.stem)
    if src.suffix.lower() in PLAYABLE_EXTS:
        dst = unique_path(stem, src.suffix.lower())
        shutil.copy2(src, dst)
    else:
        if not ffmpeg.available():
            raise RuntimeError("이 형식은 변환이 필요한데 ffmpeg를 찾을 수 없습니다. wav/mp3/ogg 파일을 사용해 주세요.")
        dst = unique_path(stem, ".wav")
        try:
            ffmpeg.render(src, dst)
        except Exception:
            dst.unlink(missing_ok=True)
            raise
    return dst


def add_sound_from_file(conn, src, name, volume=1.0):
    """파일을 복사해 등록. pygame이 못 읽는 형식은 wav로 변환."""
    dst = import_file(src)
    return repo.insert_sound(conn, (name or Path(src).stem).strip(), dst.name, float(volume))


def render_edit_new(src, params: EditParams, duration, name):
    """편집 결과를 새 파일로 만든다 (작업 스레드용). 만든 경로를 돌려준다."""
    dst = unique_path(safe_stem(name), ".wav")
    try:
        render_edit(src, dst, params, duration)
    except Exception:
        dst.unlink(missing_ok=True)
        raise
    return dst


def save_edit_as_new(conn, src, params: EditParams, duration, name, volume=1.0):
    dst = render_edit_new(src, params, duration, name)
    return repo.insert_sound(conn, name, dst.name, float(volume))


def render_edit_temp(sound_row, params: EditParams, duration):
    """덮어쓰기용 편집 결과를 임시 파일로 만든다 (작업 스레드용)."""
    cur = sounds_dir() / str(sound_row["file_name"])
    tmp = temp_dir() / f"edit_{int(sound_row['id'])}_{int(time.time() * 1000)}.wav"
    try:
        render_edit(cur, tmp, params, duration)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    return tmp


def original_backup(sound_id):
    hits = sorted(originals_dir().glob(f"{int(sound_id)}__*"))
    return hits[0] if hits else None


def overwrite_with_edit(conn, player, sound_row, params: EditParams, duration):
    tmp = render_edit_temp(sound_row, params, duration)
    return commit_overwrite(conn, player, sound_row, tmp)


def commit_overwrite(conn, player, sound_row, tmp):
    """render_edit_temp 결과로 원래 파일을 바꾼다 (원본은 한 번만 보관). 화면 스레드에서 호출."""
    sid = int(sound_row["id"])
    cur = sounds_dir() / str(sound_row["file_name"])
    tmp = Path(tmp)

    if original_backup(sid) is None and cur.exists():
        shutil.copy2(cur, originals_dir() / f"{sid}__{cur.name}")

    player.release(str(cur))
    if cur.suffix.lower() == ".wav":
        shutil.move(str(tmp), str(cur))
    else:
        new = unique_path(safe_stem(cur.stem), ".wav")
        shutil.move(str(tmp), str(new))
        repo.update_sound_file(conn, sid, new.name)
        try:
            cur.unlink()
        except OSError:
            pass
    clear_duration_cache()
    return sid


def restore_original(conn, player, sound_row):
    sid = int(sound_row["id"])
    bak = original_backup(sid)
    if bak is None:
        return False
    orig_name = bak.name.split("__", 1)[1]
    cur = sounds_dir() / str(sound_row["file_name"])
    player.release(str(cur))
    target = sounds_dir() / orig_name
    if cur.exists() and cur.name != orig_name:
        try:
            cur.unlink()
        except OSError:
            pass
    shutil.copy2(bak, target)
    if orig_name != str(sound_row["file_name"]):
        repo.update_sound_file(conn, sid, orig_name)
    bak.unlink()
    clear_duration_cache()
    return True


def remove_sound_files(sound_row):
    p = sounds_dir() / str(sound_row["file_name"])
    try:
        if p.exists():
            p.unlink()
    except OSError:
        pass
    bak = original_backup(int(sound_row["id"]))
    if bak:
        try:
            bak.unlink()
        except OSError:
            pass


_dur_cache = {}
_dur_loaded = False


def _dur_file():
    from app.core.paths import ui_cache_dir
    return ui_cache_dir() / "durations.json"


def _load_durations():
    global _dur_loaded
    if _dur_loaded:
        return
    _dur_loaded = True
    try:
        import json
        for k, v in json.loads(_dur_file().read_text(encoding="utf-8")).items():
            path, mt, size = k.rsplit("|", 2)
            _dur_cache[(path, int(mt), int(size))] = v
    except Exception:
        pass


def _save_durations():
    try:
        import json
        data = {f"{k[0]}|{k[1]}|{k[2]}": v for k, v in list(_dur_cache.items())[-500:] if v is not None}
        _dur_file().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def clear_duration_cache():
    """파일이 바뀌면 (경로, 수정 시각, 크기) 키가 달라지므로 따로 지울 필요가 없다."""


def _dur_key(p):
    try:
        st = p.stat()
    except OSError:
        return None
    return (str(p), st.st_mtime_ns, st.st_size)


def cached_duration(path):
    """바로 알 수 있는 길이만 돌려준다 (wav 머리말, 저장된 기록). 모르면 None — 화면 스레드용."""
    _load_durations()
    p = Path(path)
    key = _dur_key(p)
    if key is None:
        return None
    if key in _dur_cache:
        return _dur_cache[key]
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as wf:
                d = wf.getnframes() / float(wf.getframerate())
            _dur_cache[key] = d
            return d
        except Exception:
            return None
    return None


def sound_duration(path):
    """길이(초). mp3 등은 ffmpeg로 읽으므로 오래 걸릴 수 있다 — 작업 스레드에서 부를 것."""
    d = cached_duration(path)
    if d is not None:
        return d
    p = Path(path)
    key = _dur_key(p)
    if key is None:
        return None
    d = ffmpeg.probe_duration(p)
    _dur_cache[key] = d
    _save_durations()
    return d


def format_duration(sec):
    if sec is None:
        return "-"
    if sec < 60:
        return f"{sec:.1f}초"
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"
