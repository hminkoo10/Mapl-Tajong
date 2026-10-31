"""YouTube·SoundCloud 검색 / 미리 듣기 / 오디오 다운로드 (yt-dlp)."""
import os
import re
import shutil
import sys
import threading
from datetime import datetime
from pathlib import Path

from app.core import ffmpeg, google_login, ytpot
from app.core.paths import app_data_dir, temp_dir


class YoutubeError(RuntimeError):
    pass


class Cancelled(YoutubeError):
    pass


class Blocked(YoutubeError):
    """이 컴퓨터에서 YouTube에 직접 접속하는 길이 막힘 (우회 경로를 써 볼 수 있음)."""


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
        self.pot = []

    def debug(self, msg):
        m = str(msg)
        if "[pot" in m and len(self.pot) < 30:
            self.pot.append(m[:200])

    def info(self, msg):
        self.debug(msg)

    def warning(self, msg):
        self.warnings.append(str(msg))
        self.debug(msg)

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


def _cache_dir():
    d = app_data_dir() / "ytcache"
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def _base_opts(logger):
    return {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "noplaylist": True,
        "logger": logger,
        "socket_timeout": 15,
        "extractor_retries": 2,
        "cachedir": _cache_dir(),
        "js_runtimes": _js_runtimes(),
    }


# ---------------- 막혔을 때 다시 시도 ----------------
BLOCKED_MSG = "YouTube가 이 컴퓨터의 자동 다운로드를 막았어요."
BLOCKED_HINT = "구글 로그인을 하면 받을 수 있어요."
EXPIRED_HINT = "구글 로그인 정보로도 받지 못했어요. 다시 로그인해 보세요."


def is_blocked_message(msg):
    return str(msg or "").startswith(BLOCKED_MSG)


def _is_blocked(msg):
    low = msg.lower()
    if any(k in low for k in ("private video", "video unavailable", "has been removed", "confirm your age",
                              "age-restricted", "members-only", "join this channel")):
        return False
    return any(k in low for k in ("sign in", "not a bot", "confirm you", "po token", "requested format is not available",
                                  "only images are available", "http error 403", "login required"))


def _friendly(e, logger):
    msg = str(e) or (logger.errors[-1] if logger.errors else "")
    low = msg.lower()
    if "not a bot" in low or ("confirm you" in low and "bot" in low):
        return f"{BLOCKED_MSG} {BLOCKED_HINT}"
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
    if _is_blocked(msg):
        return f"{BLOCKED_MSG} {BLOCKED_HINT}"
    return "YouTube에서 가져오지 못했어요. 잠시 뒤 다시 해 보세요."


def _strategies(cookiefile=None):
    """로그인했으면 로그인 정보로 먼저, 아니면 기본 → 증명값(PO 토큰)을 붙인 웹 접속 → TV 접속."""
    pot = ytpot.register()
    out = []
    if cookiefile:
        out.append(("구글 로그인", {"fetch_pot": ["always"]} if pot else None, cookiefile))
    out.append(("기본", None, None))
    if pot:
        out.append(("증명값-web", {"player_client": ["web_safari", "web"], "fetch_pot": ["always"]}, None))
        out.append(("증명값-mweb", {"player_client": ["mweb"], "fetch_pot": ["always"]}, None))
    out.append(("tv", {"player_client": ["tv", "web_embedded"]}, None))
    return out


def _run_with_fallback(m, base, logger, work, cancel_event=None, status_cb=None):
    """work(opts) 를 차례로 시도한다. 막히면 다음 방식으로."""
    last = None
    cookiefile = str(google_login.cookie_file()) if google_login.is_logged_in() else None
    plan = _strategies(cookiefile)
    for i, (label, yt_args, cookies) in enumerate(plan):
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled("취소했어요.")
        if i and status_cb:
            status_cb(f"다른 방법으로 다시 시도하는 중 ({i + 1}/{len(plan)})")
        opts = dict(base)
        if yt_args:
            opts["extractor_args"] = {"youtube": yt_args}
        if cookies:
            opts["cookiefile"] = cookies
        logger.errors.clear()
        logger.pot.clear()
        try:
            result = work(opts)
            if i:
                _log("성공", label)
            return result
        except m.utils.DownloadCancelled:
            raise Cancelled("취소했어요.")
        except Cancelled:
            raise
        except Exception as e:
            if cancel_event is not None and cancel_event.is_set():
                raise Cancelled("취소했어요.")
            pot = [m for m in logger.pot if "mapl-bgutil" in m or "PO" in m]
            _log(f"실패({label})", f"{e}" + (f" | 증명값: {pot[-1]}" if pot else ""))
            last = e
            if not _is_blocked(str(e)):
                break
    msg = _friendly(last, logger)
    if is_blocked_message(msg) or (last is not None and _is_blocked(str(last))):
        raise Blocked(f"{BLOCKED_MSG} {EXPIRED_HINT if cookiefile else BLOCKED_HINT}")
    raise YoutubeError(msg)


SOURCES = ("youtube", "soundcloud")
SOURCE_LABEL = {"youtube": "YouTube", "soundcloud": "SoundCloud"}


def source_of(url):
    return "soundcloud" if "soundcloud.com" in str(url or "").lower() else "youtube"


def _thumb(entry, source="youtube"):
    vid = entry.get("id") or ""
    thumbs = entry.get("thumbnails") or []
    if source == "soundcloud":
        best = None
        for t in thumbs:
            url = t.get("url") or ""
            w = t.get("width") or 0
            if "t300x300" in url or "t500x500" in url:
                return url
            if url and (best is None or 0 < w <= 500):
                best = url
        return best or entry.get("thumbnail") or ""
    for t in thumbs:
        url = t.get("url") or ""
        if "mqdefault" in url or "hqdefault" in url:
            return url
    if vid:
        return f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg"
    return thumbs[-1].get("url") if thumbs else ""


def _entry(e, fallback_url="", source="youtube"):
    vid = str(e.get("id") or "")
    dur = e.get("duration")
    url = e.get("webpage_url") or (e.get("url") if str(e.get("url", "")).startswith("http") else "")
    if not url and source == "youtube" and vid:
        url = f"https://www.youtube.com/watch?v={vid}"
    return {
        "id": vid,
        "source": source,
        "title": e.get("title") or vid or fallback_url,
        "channel": e.get("channel") or e.get("uploader") or "",
        "duration": float(dur) if dur else None,
        "url": url or fallback_url,
        "thumbnail": _thumb(e, source),
        "views": e.get("view_count"),
        "live": e.get("live_status") in ("is_live", "is_upcoming"),
    }


def _source_error(e, logger, source):
    if source == "youtube":
        return _friendly(e, logger)
    low = (str(e) or "").lower()
    if "timed out" in low or "getaddrinfo" in low or "network is unreachable" in low or "connection" in low:
        return "인터넷 연결을 확인해 주세요."
    if "404" in low or "not found" in low or "unavailable" in low:
        return "SoundCloud에서 찾을 수 없는 소리예요. (삭제·비공개)"
    if "max_filesize" in low or "larger than max" in low:
        return "파일이 너무 커요. 더 짧은 소리를 골라 주세요."
    return "SoundCloud에서 가져오지 못했어요. 잠시 뒤 다시 해 보세요."


def search(query, limit=15, source="youtube"):
    m = _yt_dlp()
    if not m:
        raise YoutubeError("검색 기능을 쓸 수 없어요. (yt-dlp 없음)")
    query = (query or "").strip()
    if not query:
        return []
    logger = _Logger()
    opts = _base_opts(logger)
    opts.update({"skip_download": True, "extract_flat": "in_playlist"})
    prefix = "scsearch" if source == "soundcloud" else "ytsearch"
    try:
        with m.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(f"{prefix}{int(limit)}:{query}", download=False)
    except Exception as e:
        _log(f"검색 실패({SOURCE_LABEL.get(source, source)})", e)
        raise YoutubeError(_source_error(e, logger, source))
    return [_entry(e, source=source) for e in (info or {}).get("entries") or [] if e and e.get("id")]


def looks_like_url(text):
    t = (text or "").strip().lower()
    return t.startswith(("http://", "https://", "www.", "youtu.be/", "youtube.com/", "m.youtube.com/",
                         "soundcloud.com/", "on.soundcloud.com/", "m.soundcloud.com/"))


def probe(url):
    """URL 하나의 정보를 검색 결과와 같은 형태로 반환."""
    m = _yt_dlp()
    if not m:
        raise YoutubeError("검색 기능을 쓸 수 없어요. (yt-dlp 없음)")
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    source = source_of(url)
    logger = _Logger()
    opts = _base_opts(logger)
    opts.update({"skip_download": True, "extract_flat": True})
    try:
        with m.YoutubeDL(opts) as ydl:
            e = ydl.extract_info(url, download=False)
    except Exception as ex:
        _log("주소 확인 실패", ex)
        raise YoutubeError(_source_error(ex, logger, source))
    if not e:
        return []
    if e.get("entries"):
        e = next((x for x in e["entries"] if x), None) or {}
    return [_entry(e, url, source)]


def _run(m, base, logger, work, source, cancel_event=None, status_cb=None):
    """YouTube는 막혔을 때를 대비해 여러 방식으로, SoundCloud는 한 번에."""
    if source == "youtube":
        return _run_with_fallback(m, base, logger, work, cancel_event, status_cb)
    try:
        return work(dict(base))
    except m.utils.DownloadCancelled:
        raise Cancelled("취소했어요.")
    except Cancelled:
        raise
    except Exception as e:
        if cancel_event is not None and cancel_event.is_set():
            raise Cancelled("취소했어요.")
        _log("실패(SoundCloud)", e)
        raise YoutubeError(_source_error(e, logger, source))


def preview_clip(url, seconds=30, cancel_event: threading.Event = None, status_cb=None):
    """미리 듣기: 소리의 앞부분만 받아 wav로. 같은 소리는 다시 받지 않는다."""
    m = _yt_dlp()
    if not m:
        raise YoutubeError("미리 듣기를 쓸 수 없어요. (yt-dlp 없음)")
    if not ffmpeg.available():
        raise YoutubeError("소리를 변환할 도구(ffmpeg)가 없어요.")
    source = source_of(url)
    if source == "youtube":
        vid = re.search(r"(?:v=|youtu\.be/|shorts/)([\w-]{6,})", url)
        key = vid.group(1) if vid else str(abs(hash(url)))
    else:
        key = "sc_" + re.sub(r"[^\w-]+", "_", url.split("soundcloud.com/", 1)[-1])[-80:]
    out = temp_dir() / f"yt_preview_{key}.wav"
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
        return stream, info.get("http_headers") or {}, f"{info.get('format_id')}/{info.get('protocol')}"

    stream, headers, fmt = _run(m, base, logger, work, source, cancel_event, status_cb)
    if cancel_event is not None and cancel_event.is_set():
        raise Cancelled("취소했어요.")
    tmp = out.with_name(out.stem + ".part.wav")
    ok, detail = _ffmpeg_clip(stream, headers, seconds, tmp)
    if not ok:
        # 조각으로 나뉜 스트림 등 ffmpeg가 바로 못 여는 경우: yt-dlp가 앞부분만 받아 오게 한다
        _log("미리 듣기 1차 실패", f"{fmt} {detail}")
        try:
            ok, detail = _clip_via_ytdlp(m, url, seconds, tmp, source, cancel_event, status_cb)
        except Cancelled:
            raise
        except Exception as e:
            ok, detail = False, str(e)
    if not ok:
        _log("미리 듣기 변환 실패", f"{fmt} {detail}")
        tmp.unlink(missing_ok=True)
        raise YoutubeError("미리 듣기를 준비하지 못했어요. 잠시 뒤 다시 해 보세요.")
    tmp.replace(out)
    return out


def _wav_ok(path):
    try:
        return path.exists() and path.stat().st_size > 1000
    except OSError:
        return False


def _ffmpeg_clip(stream, headers, seconds, tmp):
    hdr = "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items())
    args = ["-y"]
    if hdr:
        args += ["-headers", hdr]
    args += ["-i", stream, "-t", str(int(seconds)), "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(tmp)]
    try:
        r = ffmpeg._run(args, timeout=90, capture_stdout=False)
    except ffmpeg.FfmpegError as e:
        return False, str(e)
    if r.returncode == 0 and _wav_ok(tmp):
        return True, ""
    return False, f"rc={r.returncode} size={tmp.stat().st_size if tmp.exists() else 0} {ffmpeg._tail(r.stderr, 8)}"


def _clip_via_ytdlp(m, url, seconds, tmp, source, cancel_event=None, status_cb=None):
    """yt-dlp가 (조각 스트림이면 조각을 하나씩) 직접 받다가 앞부분이 모이면 멈추고, 받은 만큼을 wav로 바꾼다.
    ffmpeg는 이 컴퓨터에 받은 파일만 읽으므로 네트워크 스트림을 열다 생기는 문제를 피한다."""
    import shutil as _sh
    import tempfile as _tf
    work_dir = Path(_tf.mkdtemp(prefix="pv_", dir=str(temp_dir())))
    early = {"stop": False}
    need = int(seconds) + 12   # 받다 만 조각은 빠지므로 넉넉히

    def hook(d):
        if cancel_event is not None and cancel_event.is_set():
            raise m.utils.DownloadCancelled("cancelled")
        if d.get("status") != "downloading":
            return
        info = d.get("info_dict") or {}
        dur = info.get("duration") or 0
        idx, cnt = d.get("fragment_index") or 0, d.get("fragment_count") or 0
        got = d.get("downloaded_bytes") or 0
        rate = (info.get("abr") or info.get("tbr") or 160) * 1000 / 8   # 초당 바이트
        enough = (cnt and dur and idx / cnt * dur >= need) or got >= rate * need * 1.3
        if enough:
            early["stop"] = True
            raise m.utils.DownloadCancelled("enough")

    logger = _Logger()
    base = _base_opts(logger)
    base.update({
        "format": "bestaudio/best",
        "outtmpl": str(work_dir / "clip.%(ext)s"),
        "progress_hooks": [hook],
        "hls_prefer_native": True,
        "continuedl": False,
        "max_filesize": 120 * 1024 * 1024,
    })

    def work(opts):
        with m.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=True)

    try:
        try:
            _run(m, base, logger, work, source, cancel_event, status_cb)
        except Cancelled:
            if not early["stop"]:
                raise
        files = sorted((f for f in work_dir.iterdir() if f.is_file() and f.stat().st_size > 0),
                       key=lambda f: f.stat().st_size, reverse=True)
        if not files:
            return False, "yt-dlp 결과 파일 없음"
        r = ffmpeg._run(["-y", "-i", str(files[0]), "-t", str(int(seconds)), "-vn", "-ac", "2", "-ar", "44100",
                         "-c:a", "pcm_s16le", str(tmp)], timeout=90, capture_stdout=False)
        if r.returncode == 0 and _wav_ok(tmp):
            return True, ""
        return False, f"2차 rc={r.returncode} {ffmpeg._tail(r.stderr, 6)}"
    finally:
        _sh.rmtree(work_dir, ignore_errors=True)


def download_audio(url, out_dir, progress_cb=None, cancel_event: threading.Event = None):
    """소리만 받아 mp3로 변환. (최종 파일 경로, 제목)을 반환."""
    m = _yt_dlp()
    if not m:
        raise YoutubeError("받기 기능을 쓸 수 없어요. (yt-dlp 없음)")
    ff = ffmpeg.ffmpeg_exe()
    if not ff:
        raise YoutubeError("소리를 변환할 도구(ffmpeg)가 없어요.")
    source = source_of(url)

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
            if total:
                progress_cb(min(0.95, (done / total) * 0.95), "받는 중")
            else:
                frag = d.get("fragment_index") or 0
                nfrag = d.get("fragment_count") or 0
                progress_cb(min(0.95, frag / nfrag * 0.95) if nfrag else 0.0, "받는 중")
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

    status = (lambda text: progress_cb(0.0, text)) if progress_cb else None
    info = _run(m, base, logger, work, source, cancel_event, status)

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
