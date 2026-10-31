"""ffmpeg 위치 탐색과 오디오 처리 헬퍼.

우선순위: exe 옆/번들 폴더 → imageio-ffmpeg 패키지 → PATH
"""
import os
import re
import shutil
import subprocess
import sys
from array import array
from functools import lru_cache
from pathlib import Path

_IS_WIN = sys.platform == "win32"
_NO_WINDOW = 0x08000000 if _IS_WIN else 0


class FfmpegError(RuntimeError):
    pass


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
        raise FfmpegError("ffmpeg를 찾을 수 없습니다.")
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
        raise FfmpegError("ffmpeg 처리 시간이 초과되었습니다.")
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
        raise FfmpegError("오디오를 읽을 수 없습니다.\n" + _tail(r.stderr))
    data = array("h")
    raw = r.stdout or b""
    if len(raw) % 2:
        raw = raw[:-1]
    data.frombytes(raw)
    if sys.byteorder != "little":
        data.byteswap()
    return data


def render(src, dst, audio_filter=None, rate=44100, channels=2):
    """src를 필터 적용 후 16bit WAV로 저장."""
    args = ["-y", "-i", str(src), "-vn"]
    if audio_filter:
        args += ["-af", audio_filter]
    args += ["-ar", str(rate), "-ac", str(channels), "-c:a", "pcm_s16le", str(dst)]
    r = _run(args, timeout=600, capture_stdout=False)
    if r.returncode != 0 or not Path(dst).exists():
        raise FfmpegError("오디오 변환에 실패했습니다.\n" + _tail(r.stderr))
    return Path(dst)


def amplify(src, dst, gain):
    return render(src, dst, f"volume={float(gain):.3f}")
