"""YouTube 받기 경로 시험 (CI 진단용, 앱에는 들어가지 않음).

로그인 없이 쓸 수 있는 경로를 하나씩 시험해 결과를 표로 보여 준다.
  1) yt-dlp 접속 방식(client)별 + PO 토큰
  2) Invidious 공개 서버 (서버가 대신 받아 줌)
  3) Piped 공개 서버
  4) SoundCloud
"""
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

VID = os.environ.get("PROBE_VIDEO", "jNQXAC9IVRw")
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
results = []


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'OK ' if ok else 'NO '}] {name}: {detail}"[:400], flush=True)


def http_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def first_bytes(url, n=65536, timeout=15, headers=None):
    h = {"User-Agent": UA, **(headers or {}), "Range": f"bytes=0-{n - 1}"}
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return len(r.read(n)), r.headers.get("Content-Type", "")


class L:
    def __init__(self):
        self.pot = []

    def debug(self, m):
        if "[pot" in str(m) or "PO Token" in str(m):
            self.pot.append(str(m)[:160])

    info = debug

    def warning(self, m):
        self.debug(m)

    def error(self, m):
        pass


def ytdlp_clients():
    import yt_dlp
    from app.core import youtube, ytpot
    pot = ytpot.register()
    print("yt-dlp", yt_dlp.version.__version__, "pot provider:", pot, ytpot.cli_version(), flush=True)
    cases = [("default", None, None)]
    for c in ("web", "web_safari", "mweb", "web_embedded", "tv", "tv_simply", "tv_samsung", "visionos",
              "android_vr", "ios", "web_music"):
        cases.append((c, [c], None))
        if pot and c in ("web", "web_safari", "mweb", "web_embedded", "tv", "tv_simply"):
            cases.append((c + "+pot", [c], "always"))
    for name, clients, fetch in cases:
        lg = L()
        opts = {"quiet": True, "no_warnings": True, "skip_download": True, "logger": lg, "noplaylist": True,
                "format": "bestaudio/best", "js_runtimes": youtube._js_runtimes(), "socket_timeout": 15}
        ya = {}
        if clients:
            ya["player_client"] = clients
        if fetch:
            ya["fetch_pot"] = [fetch]
        if ya:
            opts["extractor_args"] = {"youtube": ya}
        t = time.monotonic()
        try:
            with yt_dlp.YoutubeDL(opts) as y:
                info = y.extract_info(f"https://www.youtube.com/watch?v={VID}", download=False)
            url = info.get("url") or ""
            got = ""
            if url:
                try:
                    n, ct = first_bytes(url, 4096, headers=info.get("http_headers"))
                    got = f"stream {n}B {ct}"
                except Exception as e:
                    got = f"stream fetch fail {e}"
            rec(f"yt-dlp {name}", bool(url) and "fail" not in got,
                f"{time.monotonic() - t:.1f}s fmt={info.get('format_id')} {got} pot={len(lg.pot)}")
        except Exception as e:
            msg = str(e).replace("\n", " ")
            rec(f"yt-dlp {name}", False, f"{time.monotonic() - t:.1f}s pot={len(lg.pot)} {msg[:180]}")


def invidious():
    try:
        data = http_json("https://api.invidious.io/instances.json?sort_by=health")
    except Exception as e:
        rec("invidious list", False, str(e))
        return
    hosts = []
    for name, meta in data:
        if meta.get("type") == "https" and meta.get("api"):
            hosts.append(meta.get("uri") or f"https://{name}")
    rec("invidious list", bool(hosts), f"{len(hosts)} api instances: {hosts[:12]}")
    for h in hosts[:12]:
        t = time.monotonic()
        try:
            d = http_json(f"{h}/api/v1/videos/{VID}?local=true", timeout=15)
            fmts = [f for f in d.get("adaptiveFormats", []) if str(f.get("type", "")).startswith("audio")]
            if not fmts:
                rec(f"invidious {h}", False, f"no audio formats keys={list(d)[:6]} err={d.get('error')}")
                continue
            u = fmts[0]["url"]
            if u.startswith("/"):
                u = h + u
            n, ct = first_bytes(u)
            rec(f"invidious {h}", n > 1000, f"{time.monotonic() - t:.1f}s {n}B {ct}")
        except Exception as e:
            rec(f"invidious {h}", False, f"{time.monotonic() - t:.1f}s {str(e)[:150]}")


def piped():
    apis = []
    try:
        lst = http_json("https://piped-instances.kavin.rocks/")
        apis = [x.get("api_url") for x in lst if x.get("api_url")]
    except Exception as e:
        rec("piped list", False, str(e))
    apis = apis or ["https://pipedapi.kavin.rocks", "https://api.piped.private.coffee", "https://pipedapi.adminforge.de"]
    rec("piped list", bool(apis), f"{len(apis)}: {apis[:10]}")
    for a in apis[:10]:
        t = time.monotonic()
        try:
            d = http_json(f"{a}/streams/{VID}", timeout=15)
            aus = d.get("audioStreams") or []
            if not aus:
                rec(f"piped {a}", False, f"no audio: {str(d.get('error') or d.get('message'))[:150]}")
                continue
            n, ct = first_bytes(aus[0]["url"])
            rec(f"piped {a}", n > 1000, f"{time.monotonic() - t:.1f}s {n}B {ct}")
        except Exception as e:
            rec(f"piped {a}", False, f"{time.monotonic() - t:.1f}s {str(e)[:150]}")


def soundcloud():
    import yt_dlp
    t = time.monotonic()
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": "in_playlist",
                               "skip_download": True}) as y:
            info = y.extract_info("scsearch5:school bell sound", download=False)
        ents = [e for e in info.get("entries") or [] if e]
        rec("soundcloud search", bool(ents), f"{len(ents)} {[e.get('title') for e in ents][:3]}")
        if ents:
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True,
                                   "format": "bestaudio/best"}) as y:
                i2 = y.extract_info(ents[0].get("url") or ents[0].get("webpage_url"), download=False)
            n, ct = first_bytes(i2["url"]) if i2.get("url") else (0, "")
            rec("soundcloud stream", n > 1000, f"{time.monotonic() - t:.1f}s {n}B {ct} proto={i2.get('protocol')}")
    except Exception as e:
        rec("soundcloud", False, str(e)[:200])


if __name__ == "__main__":
    for fn in (ytdlp_clients, invidious, piped, soundcloud):
        try:
            fn()
        except Exception as e:
            rec(fn.__name__, False, f"crashed: {e}")
    print("\n===== 요약 =====")
    for name, ok, detail in results:
        print(f"{'OK ' if ok else 'NO '} {name}")
