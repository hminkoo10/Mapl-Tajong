"""YouTube 검색/오디오 다운로드 (yt-dlp)."""
import shutil
import sys
import threading
from pathlib import Path

from app.core import ffmpeg


class YoutubeError(RuntimeError):
    pass


class Cancelled(YoutubeError):
    pass


def _yt_dlp():
    try:
        import yt_dlp
        return yt_dlp
    except Exception:
        return None


def available():
    return _yt_dlp() is not None


def version():
    m = _yt_dlp()
    if not m:
        return None
    try:
        return m.version.__version__
    except Exception:
        return "unknown"


class _Logger:
    """windowed exe에서는 stdout이 없으므로 yt-dlp 출력을 여기로 받는다."""

    def __init__(self):
        self.errors = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.errors.append(str(msg))


def _js_runtimes():
    """deno가 exe 옆이나 PATH에 있으면 사용 (YouTube 호환성 향상). 없어도 동작은 함."""
    rt = {}
    name = "deno.exe" if sys.platform == "win32" else "deno"
    cands = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        cands += [exe_dir / name, exe_dir / "deno" / name, Path(getattr(sys, "_MEIPASS", exe_dir)) / name]
    for c in cands:
        if c.exists():
            rt["deno"] = {"path": str(c)}
            break
    if "deno" not in rt and shutil.which("deno"):
        rt["deno"] = {}
    if shutil.which("node"):
        rt["node"] = {}
    return rt or {"deno": {}}


def _base_opts(logger):
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "logger": logger,
        "socket_timeout": 15,
        "js_runtimes": _js_runtimes(),
    }


def _friendly(e, logger):
    msg = str(e) or (logger.errors[-1] if logger.errors else "")
    low = msg.lower()
    if "sign in" in low or "confirm your age" in low:
        return "로그인이 필요한(연령 제한 등) 영상이라 받을 수 없습니다."
    if "unavailable" in low or "private" in low:
        return "재생할 수 없는 영상입니다(비공개/삭제/지역 제한)."
    if "timed out" in low or "network" in low or "connection" in low or "getaddrinfo" in low:
        return "인터넷 연결을 확인해 주세요."
    if "max_filesize" in low or "larger than max" in low:
        return "파일이 너무 큽니다. 더 짧은 영상을 골라 주세요."
    return "YouTube 처리 중 오류가 발생했습니다.\n" + msg.replace("ERROR: ", "")[-400:]


def _thumb(entry):
    vid = entry.get("id") or ""
    thumbs = entry.get("thumbnails") or []
    for t in thumbs:
        url = t.get("url") or ""
        if "mqdefault" in url or "hqdefault" in url:
            return url
    if vid:
        return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
    return thumbs[-1].get("url") if thumbs else ""


def search(query, limit=15):
    m = _yt_dlp()
    if not m:
        raise YoutubeError("yt-dlp가 설치되어 있지 않습니다.")
    query = (query or "").strip()
    if not query:
        return []
    logger = _Logger()
    opts = _base_opts(logger)
    opts.update({"skip_download": True, "extract_flat": "in_playlist"})
    try:
        with m.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"ytsearch{int(limit)}:{query}", download=False)
    except Exception as e:
        raise YoutubeError(_friendly(e, logger))

    out = []
    for e in (info or {}).get("entries") or []:
        if not e:
            continue
        vid = e.get("id")
        if not vid:
            continue
        dur = e.get("duration")
        out.append({
            "id": vid,
            "title": e.get("title") or vid,
            "channel": e.get("channel") or e.get("uploader") or "",
            "duration": float(dur) if dur else None,
            "url": e.get("url") if str(e.get("url", "")).startswith("http") else f"https://www.youtube.com/watch?v={vid}",
            "thumbnail": _thumb(e),
            "views": e.get("view_count"),
        })
    return out


def looks_like_url(text):
    t = (text or "").strip().lower()
    return t.startswith(("http://", "https://", "www.", "youtu.be/", "youtube.com/", "m.youtube.com/"))


def probe(url):
    """URL 하나의 정보를 검색 결과와 같은 형태로 반환."""
    m = _yt_dlp()
    if not m:
        raise YoutubeError("yt-dlp가 설치되어 있지 않습니다.")
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    logger = _Logger()
    opts = _base_opts(logger)
    opts.update({"skip_download": True, "extract_flat": True})
    try:
        with m.YoutubeDL(opts) as ydl:
            e = ydl.extract_info(url, download=False)
    except Exception as ex:
        raise YoutubeError(_friendly(ex, logger))
    if not e:
        return []
    if e.get("entries"):
        e = next((x for x in e["entries"] if x), None) or {}
    vid = e.get("id") or ""
    dur = e.get("duration")
    return [{
        "id": vid,
        "title": e.get("title") or vid or url,
        "channel": e.get("channel") or e.get("uploader") or "",
        "duration": float(dur) if dur else None,
        "url": e.get("webpage_url") or url,
        "thumbnail": _thumb(e),
        "views": e.get("view_count"),
    }]


def download_audio(url, out_dir, progress_cb=None, cancel_event: threading.Event = None):
    """오디오만 받아 mp3로 변환. 최종 파일 경로를 반환."""
    m = _yt_dlp()
    if not m:
        raise YoutubeError("yt-dlp가 설치되어 있지 않습니다.")
    ff = ffmpeg.ffmpeg_exe()
    if not ff:
        raise YoutubeError("ffmpeg를 찾을 수 없어 변환할 수 없습니다.")

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    logger = _Logger()

    def hook(d):
        if cancel_event is not None and cancel_event.is_set():
            raise m.utils.DownloadCancelled("cancelled")
        if not progress_cb:
            return
        st = d.get("status")
        if st == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes") or 0
            frac = (done / total) if total else 0.0
            progress_cb(min(0.95, frac * 0.95), "받는 중")
        elif st == "finished":
            progress_cb(0.96, "변환하는 중")

    opts = _base_opts(logger)
    opts.update({
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "ffmpeg_location": ff,
        "max_filesize": 300 * 1024 * 1024,
        "progress_hooks": [hook],
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
    })

    try:
        with m.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except m.utils.DownloadCancelled:
        raise Cancelled("취소되었습니다.")
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled("취소되었습니다.")
        raise YoutubeError(_friendly(e, logger))

    path = None
    for rd in (info or {}).get("requested_downloads") or []:
        fp = rd.get("filepath")
        if fp and Path(fp).exists():
            path = Path(fp)
    if path is None and info and info.get("id"):
        hits = sorted(out_dir.glob(f"{info['id']}.mp3")) or sorted(out_dir.glob(f"{info['id']}.*"))
        path = hits[0] if hits else None
    if path is None:
        raise YoutubeError("다운로드한 파일을 찾을 수 없습니다.")
    if progress_cb:
        progress_cb(1.0, "완료")
    return path, (info or {}).get("title") or path.stem
