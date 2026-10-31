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


def add_sound_from_file(conn, src, name, volume=1.0):
    """파일을 복사해 등록. pygame이 못 읽는 형식은 wav로 변환."""
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError("선택한 파일을 찾을 수 없습니다.")
    name = (name or src.stem).strip()
    stem = safe_stem(src.stem)
    if src.suffix.lower() in PLAYABLE_EXTS:
        dst = unique_path(stem, src.suffix.lower())
        shutil.copy2(src, dst)
    else:
        if not ffmpeg.available():
            raise RuntimeError("이 형식은 변환이 필요한데 ffmpeg를 찾을 수 없습니다. wav/mp3/ogg 파일을 사용해 주세요.")
        dst = unique_path(stem, ".wav")
        ffmpeg.render(src, dst)
    return repo.insert_sound(conn, name, dst.name, float(volume))


def save_edit_as_new(conn, src, params: EditParams, duration, name, volume=1.0):
    dst = unique_path(safe_stem(name), ".wav")
    render_edit(src, dst, params, duration)
    return repo.insert_sound(conn, name, dst.name, float(volume))


def original_backup(sound_id):
    hits = sorted(originals_dir().glob(f"{int(sound_id)}__*"))
    return hits[0] if hits else None


def overwrite_with_edit(conn, player, sound_row, params: EditParams, duration):
    sid = int(sound_row["id"])
    cur = sounds_dir() / str(sound_row["file_name"])
    tmp = temp_dir() / f"edit_{sid}_{int(time.time() * 1000)}.wav"
    render_edit(cur, tmp, params, duration)

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


def clear_duration_cache():
    _dur_cache.clear()


def sound_duration(path):
    p = Path(path)
    try:
        st = p.stat()
    except OSError:
        return None
    key = (str(p), st.st_mtime_ns, st.st_size)
    if key in _dur_cache:
        return _dur_cache[key]
    d = None
    if p.suffix.lower() == ".wav":
        try:
            with wave.open(str(p), "rb") as wf:
                d = wf.getnframes() / float(wf.getframerate())
        except Exception:
            d = None
    if d is None:
        d = ffmpeg.probe_duration(p)
    _dur_cache[key] = d
    return d


def format_duration(sec):
    if sec is None:
        return "-"
    if sec < 60:
        return f"{sec:.1f}초"
    m, s = divmod(int(round(sec)), 60)
    return f"{m}:{s:02d}"
