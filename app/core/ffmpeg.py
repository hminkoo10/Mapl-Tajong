"""ffmpeg 위치 탐색과 오디오 처리 헬퍼.

우선순위: exe 옆/번들 폴더 → imageio-ffmpeg 패키지 → PATH
"""
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from array import array
from functools import lru_cache
from pathlib import Path

_IS_WIN = sys.platform == "win32"
_NO_WINDOW = 0x08000000 if _IS_WIN else 0
_BELOW_NORMAL = 0x00004000 if _IS_WIN else 0   # 종소리 재생보다 뒤에 돌도록 (BELOW_NORMAL_PRIORITY_CLASS)


class FfmpegError(RuntimeError):
    pass


class Cancelled(Exception):
    """사용자가 취소함"""


@lru_cache(maxsize=1)
def ffmpeg_exe():
    name = "ffmpeg.exe" if _IS_WIN else "ffmpeg"
    env = os.environ.get("MAPL_FFMPEG")   # 시험용으로 다른 ffmpeg를 쓸 때
    if env and Path(env).exists():
        return env
    cands = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        cands += [exe_dir / name, exe_dir / "ffmpeg" / name, meipass / name, meipass / "ffmpeg" / name]
    for c in cands:
        if c.exists():
            return str(c)
    try:
        import imageio_ffmpeg
        p = imageio_ffmpeg.get_ffmpeg_exe()
        if p and Path(p).exists():
            return str(p)
    except Exception:
        pass
    return shutil.which("ffmpeg")


def available():
    return ffmpeg_exe() is not None


def _run(args, timeout=300, capture_stdout=True):
    exe = ffmpeg_exe()
    if not exe:
        raise FfmpegError("소리를 변환하는 데 필요한 도구(ffmpeg)를 찾을 수 없어요.")
    cmd = [exe, "-hide_banner", "-nostdin", *args]
    try:
        r = subprocess.run(
            cmd,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL,
            timeout=timeout,
            creationflags=_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise FfmpegError("소리를 변환하는 데 너무 오래 걸려 멈췄어요.")
    return r


def _tail(stderr_bytes, n=4):
    text = (stderr_bytes or b"").decode("utf-8", "replace").strip().splitlines()
    return "\n".join(text[-n:])


_DUR_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def probe_duration(path):
    """초 단위 길이. 실패하면 None."""
    try:
        r = _run(["-i", str(path)], timeout=20, capture_stdout=False)
    except FfmpegError:
        return None
    m = _DUR_RE.search((r.stderr or b"").decode("utf-8", "replace"))
    if not m:
        return None
    h, mi, s = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(s)


def decode_mono(path, rate=8000):
    """파형 표시용: 모노 16bit PCM 샘플 배열."""
    r = _run(["-i", str(path), "-vn", "-ac", "1", "-ar", str(rate), "-f", "s16le", "-acodec", "pcm_s16le", "-"],
             timeout=180)
    if r.returncode != 0:
        raise FfmpegError("종소리 파일을 읽을 수 없어요.\n" + _tail(r.stderr))
    data = array("h")
    raw = r.stdout or b""
    if len(raw) % 2:
        raw = raw[:-1]
    data.frombytes(raw)
    if sys.byteorder != "little":
        data.byteswap()
    return data


def render(src, dst, audio_filter=None, rate=44100, channels=2):
    """src를 필터 적용 후 16bit WAV로 저장. (dst 가 .tmp 여도 WAV 가 되도록 형식을 직접 정한다)"""
    args = ["-y", "-i", str(src), "-vn"]
    if audio_filter:
        args += ["-af", audio_filter]
    args += ["-ar", str(rate), "-ac", str(channels), "-c:a", "pcm_s16le", "-f", "wav", str(dst)]
    r = _run(args, timeout=600, capture_stdout=False)
    if r.returncode != 0 or not Path(dst).exists():
        raise FfmpegError("종소리 파일을 변환하지 못했어요.\n" + _tail(r.stderr))
    return Path(dst)


def amplify(src, dst, gain):
    return render(src, dst, f"volume={float(gain):.3f}")


def _seconds(m):
    h, mi, sec = m.groups()
    return int(h) * 3600 + int(mi) * 60 + float(sec)


def _run_watched(args, on_progress=None, cancel=None, timeout=600):
    """ffmpeg 를 낮은 우선순위로 돌리며 진행 정도(0..1)를 on_progress 로 알린다 (작업 스레드용).
    cancel(threading.Event)이 켜지면 바로 멈추고 Cancelled 를 낸다. 돌려주는 값: (종료 코드, stderr)"""
    exe = ffmpeg_exe()
    if not exe:
        raise FfmpegError("소리를 변환하는 데 필요한 도구(ffmpeg)를 찾을 수 없어요.")
    cmd = [exe, "-hide_banner", "-nostdin", "-nostats", "-progress", "pipe:1", *args]
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                         creationflags=_NO_WINDOW | _BELOW_NORMAL)
    err = []
    total = []
    stopped = []
    finished = threading.Event()

    def read_err():
        for line in p.stderr:
            err.append(line)
            if not total:
                m = _DUR_RE.search(line.decode("utf-8", "replace"))
                if m and _seconds(m) > 0:
                    total.append(_seconds(m))

    def watch():
        end = time.monotonic() + timeout
        while not finished.wait(0.1):
            late = time.monotonic() > end
            if late or (cancel is not None and cancel.is_set()):
                stopped.append("timeout" if late else "cancel")
                p.kill()
                return

    threads = [threading.Thread(target=read_err, daemon=True), threading.Thread(target=watch, daemon=True)]
    for t in threads:
        t.start()
    try:
        for line in p.stdout:
            key, _, val = line.decode("ascii", "replace").strip().partition("=")
            if on_progress is None:
                continue
            if key == "progress" and val == "end":
                on_progress(1.0)
            elif key == "out_time_us" and val.isdigit() and total:
                on_progress(min(1.0, int(val) / 1e6 / total[0]))
    except BaseException:
        p.kill()
        raise
    finally:
        p.wait()
        finished.set()
        for t in threads:
            t.join()
        p.stdout.close()
        p.stderr.close()
    if stopped == ["cancel"]:
        raise Cancelled()
    if stopped:
        raise FfmpegError("소리를 변환하는 데 너무 오래 걸려 멈췄어요.")
    return p.returncode, b"".join(err)


def encode_mp3(src, dst, bitrate="192k", on_progress=None, cancel=None):
    """src를 MP3로 저장. (dst 가 .tmp 여도 MP3 가 되도록 형식을 직접 정한다)
    on_progress(0..1) 로 진행 정도를 알리고, cancel 이 켜지면 멈추고 Cancelled 를 낸다."""
    args = ["-y", "-i", str(src), "-vn", "-c:a", "libmp3lame", "-b:a", bitrate, "-f", "mp3", str(dst)]
    rc, err = _run_watched(args, on_progress, cancel, timeout=600)
    if rc != 0 or not Path(dst).exists():
        raise FfmpegError("MP3로 바꾸지 못했어요.\n" + _tail(err))
    return Path(dst)
