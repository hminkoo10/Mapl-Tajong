"""YouTube 검색 / 미리 듣기 / 오디오 다운로드 (yt-dlp)."""
import re
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

from app.core import ffmpeg
from app.core.paths import app_data_dir, temp_dir


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
        self.warnings = []

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        self.warnings.append(str(msg))

    def error(self, msg):
        self.errors.append(str(msg))


def _log(kind, detail):
    """원인 파악용 기록 (데이터 폴더의 youtube.log, 최근 300줄만 유지)."""
    try:
        p = app_data_dir() / "youtube.log"
        lines = p.read_text(encoding="utf-8").splitlines()[-300:] if p.exists() else []
        lines.append(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {kind}: {str(detail).strip()[:1500]}")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


def deno_path():
    """함께 넣은 deno(자바스크립트 실행기)의 위치. YouTube가 요구하는 계산에 필요하다."""
    name = "deno.exe" if sys.platform == "win32" else "deno"
    cands = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        cands += [meipass / name, meipass / "deno" / name, exe_dir / name]
    for c in cands:
        if c.exists():
            return str(c)
    try:
        import deno as _deno
        p = _deno.find_deno_bin()
        if p and Path(p).exists():
            return str(p)
    except Exception:
        pass
    return shutil.which("deno")


def _js_runtimes():
    rt = {}
    d = deno_path()
    if d:
        rt["deno"] = {"path": d}
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
        "extractor_retries": 2,
        "js_runtimes": _js_runtimes(),
    }


# 기본 방식이 막히면 차례로 시도할 YouTube 접속 방식
_CLIENT_FALLBACKS = [None, ["tv_simply", "tv"], ["web_embedded", "mweb"], ["android_vr"]]


def _is_blocked(msg):
    low = msg.lower()
    return any(k in low for k in ("sign in", "not a bot", "confirm you", "po token", "requested format is not available",
                                  "only images are available", "http error 403", "login required"))


def _friendly(e, logger):
    msg = str(e) or (logger.errors[-1] if logger.errors else "")
    low = msg.lower()
    if "not a bot" in low or ("confirm you" in low and "bot" in low):
        return "YouTube가 자동 다운로드를 잠깐 막았어요. 잠시 뒤 다시 해 보거나 다른 영상을 골라 주세요."
    if "confirm your age" in low or "age-restricted" in low or "inappropriate for some users" in low:
        return "연령 제한이 있는 영상이라 받을 수 없어요."
    if "members-only" in low or "join this channel" in low:
        return "채널 회원 전용 영상이라 받을 수 없어요."
    if "private video" in low or "video unavailable" in low or "has been removed" in low:
        return "볼 수 없는 영상이에요. (비공개·삭제·지역 제한)"
    if "live event" in low or "is live" in low or "premieres in" in low:
        return "실시간 방송이나 예정된 영상은 받을 수 없어요."
    if "timed out" in low or "getaddrinfo" in low or "network is unreachable" in low or "connection" in low:
        return "인터넷 연결을 확인해 주세요."
    if "max_filesize" in low or "larger than max" in low:
        return "파일이 너무 커요. 더 짧은 영상을 골라 주세요."
    if "sign in" in low:
        return "로그인해야 볼 수 있는 영상이라 받을 수 없어요."
    return "YouTube에서 가져오지 못했어요. 잠시 뒤 다시 해 보세요."


def _run_with_fallback(m, base, logger, work, cancel_event=None):
    """work(opts) 를 기본 방식으로 해 보고, 막히면 다른 접속 방식으로 다시 시도."""
    last = None
    for clients in _CLIENT_FALLBACKS:
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled("취소했어요.")
        opts = dict(base)
        if clients:
            opts["extractor_args"] = {"youtube": {"player_client": clients}}
        try:
            return work(opts)
        except m.utils.DownloadCancelled:
            raise Cancelled("취소했어요.")
        except Exception as e:
            if cancel_event is not None and cancel_event.is_set():
                raise Cancelled("취소했어요.")
            last = e
            _log("실패" + (f"({','.join(clients)})" if clients else "(기본)"), e)
            if not _is_blocked(str(e)):
                break
    raise YoutubeError(_friendly(last, logger))


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


def _entry(e, fallback_url=""):
    vid = e.get("id") or ""
    dur = e.get("duration")
    url = e.get("webpage_url") or (e.get("url") if str(e.get("url", "")).startswith("http") else "")
    return {
        "id": vid,
        "title": e.get("title") or vid or fallback_url,
        "channel": e.get("channel") or e.get("uploader") or "",
        "duration": float(dur) if dur else None,
        "url": url or (f"https://www.youtube.com/watch?v={vid}" if vid else fallback_url),
        "thumbnail": _thumb(e),
        "views": e.get("view_count"),
        "live": e.get("live_status") in ("is_live", "is_upcoming"),
    }


def search(query, limit=15):
    m = _yt_dlp()
    if not m:
        raise YoutubeError("YouTube 기능을 쓸 수 없어요. (yt-dlp 없음)")
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
        _log("검색 실패", e)
        raise YoutubeError(_friendly(e, logger))
    return [_entry(e) for e in (info or {}).get("entries") or [] if e and e.get("id")]


def looks_like_url(text):
    t = (text or "").strip().lower()
    return t.startswith(("http://", "https://", "www.", "youtu.be/", "youtube.com/", "m.youtube.com/"))


def probe(url):
    """URL 하나의 정보를 검색 결과와 같은 형태로 반환."""
    m = _yt_dlp()
    if not m:
        raise YoutubeError("YouTube 기능을 쓸 수 없어요. (yt-dlp 없음)")
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
        _log("주소 확인 실패", ex)
        raise YoutubeError(_friendly(ex, logger))
    if not e:
        return []
    if e.get("entries"):
        e = next((x for x in e["entries"] if x), None) or {}
    return [_entry(e, url)]


def preview_clip(url, seconds=30, cancel_event: threading.Event = None):
    """미리 듣기: 영상 소리의 앞부분만 받아 wav로. 같은 영상은 다시 받지 않는다."""
    m = _yt_dlp()
    if not m:
        raise YoutubeError("YouTube 기능을 쓸 수 없어요. (yt-dlp 없음)")
    if not ffmpeg.available():
        raise YoutubeError("소리를 변환할 도구(ffmpeg)가 없어요.")
    vid = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{6,})", url)
    out = temp_dir() / f"yt_preview_{vid.group(1) if vid else abs(hash(url))}.wav"
    if out.exists() and out.stat().st_size > 1000:
        return out

    logger = _Logger()
    base = _base_opts(logger)
    base.update({"format": "bestaudio/best", "skip_download": True})

    def work(opts):
        with m.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        stream = info.get("url") or next((f.get("url") for f in info.get("requested_formats") or [] if f.get("url")), None)
        if not stream:
            raise YoutubeError("requested format is not available")
        return stream, info.get("http_headers") or {}

    stream, headers = _run_with_fallback(m, base, logger, work, cancel_event)
    if cancel_event is not None and cancel_event.is_set():
        raise Cancelled("취소했어요.")
    hdr = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    tmp = out.with_name(out.stem + ".part.wav")
    args = ["-y"]
    if hdr:
        args += ["-headers", hdr]
    args += ["-i", stream, "-t", str(int(seconds)), "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(tmp)]
    try:
        r = ffmpeg._run(args, timeout=90, capture_stdout=False)
    except ffmpeg.FfmpegError as e:
        raise YoutubeError(str(e))
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size < 1000:
        _log("미리 듣기 변환 실패", ffmpeg._tail(r.stderr, 6))
        tmp.unlink(missing_ok=True)
        raise YoutubeError("미리 듣기를 준비하지 못했어요. 잠시 뒤 다시 해 보세요.")
    tmp.replace(out)
    return out


def download_audio(url, out_dir, progress_cb=None, cancel_event: threading.Event = None):
    """오디오만 받아 mp3로 변환. (최종 파일 경로, 제목)을 반환."""
    m = _yt_dlp()
    if not m:
        raise YoutubeError("YouTube 기능을 쓸 수 없어요. (yt-dlp 없음)")
    ff = ffmpeg.ffmpeg_exe()
    if not ff:
        raise YoutubeError("소리를 변환할 도구(ffmpeg)가 없어요.")

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
            progress_cb(min(0.95, (done / total) * 0.95 if total else 0.0), "받는 중")
        elif st == "finished":
            progress_cb(0.96, "변환하는 중")

    base = _base_opts(logger)
    base.update({
        "format": "bestaudio/best",
        "outtmpl": str(out_dir / "%(id)s.%(ext)s"),
        "ffmpeg_location": ff,
        "max_filesize": 300 * 1024 * 1024,
        "progress_hooks": [hook],
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
    })

    def work(opts):
        with m.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    info = _run_with_fallback(m, base, logger, work, cancel_event)

    path = None
    for rd in (info or {}).get("requested_downloads") or []:
        fp = rd.get("filepath")
        if fp and Path(fp).exists():
            path = Path(fp)
    if path is None and info and info.get("id"):
        hits = sorted(out_dir.glob(f"{info['id']}.mp3")) or sorted(out_dir.glob(f"{info['id']}.*"))
        path = hits[0] if hits else None
    if path is None:
        raise YoutubeError("받은 파일을 찾지 못했어요.")
    if progress_cb:
        progress_cb(1.0, "완료")
    return path, (info or {}).get("title") or path.stem
