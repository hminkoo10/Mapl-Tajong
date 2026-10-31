"""종소리 찾기 경로 시험 (CI 진단용, 앱에는 들어가지 않음).

앱 코드 그대로 SoundCloud 검색 → 미리 듣기 → 받기를 해 보고, YouTube 검색이 되는지도 확인한다.
"""
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from app.core import youtube  # noqa: E402
from app.core.paths import app_data_dir  # noqa: E402

results = []


def rec(name, ok, detail=""):
    results.append((name, ok))
    print(f"[{'OK ' if ok else 'NO '}] {name}: {detail}"[:500], flush=True)


def step(name, fn):
    t = time.monotonic()
    try:
        out = fn()
        rec(name, True, f"{time.monotonic() - t:.1f}s {out}")
        return out
    except Exception as e:
        rec(name, False, f"{time.monotonic() - t:.1f}s {type(e).__name__}: {e}")
        return None


def weather_checks():
    import json
    import urllib.request
    from app.core import weather
    for city in ("서울", "수원"):
        step(f"날씨 {city}", lambda c=city: (lambda d: f"{d['now']} today={d['today']} hours={len(d['hours'])}"
                                            if d else "None")(weather.get(c, force=True)))
    # 원본 응답 확인
    def raw():
        req = urllib.request.Request(f"{weather.API}?lat=37.5665&lon=126.9780",
                                     headers={"User-Agent": weather.USER_AGENT, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read()
            return f"status={r.status} bytes={len(body)} expires={r.headers.get('Expires')}"
    step("날씨 원본 응답", raw)

    def geo(q):
        url = ("https://nominatim.openstreetmap.org/search?format=jsonv2&limit=5&countrycodes=kr&accept-language=ko&q="
               + urllib.parse.quote(q))
        req = urllib.request.Request(url, headers={"User-Agent": weather.USER_AGENT})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read().decode("utf-8"))
        return [(x.get("display_name", "")[:50], x.get("lat"), x.get("lon"), x.get("addresstype")) for x in data[:3]]
    import urllib.parse
    for q in ("대치동", "분당구", "수원"):
        step(f"지역 검색 {q}", lambda q=q: geo(q))


def main():
    weather_checks()
    print("yt-dlp", youtube.version(), flush=True)
    for q in ("school bell", "학교 종소리"):
        res = step(f"SoundCloud 검색 '{q}'", lambda q=q: youtube.search(q, 8, "soundcloud"))
        if res:
            for r in res[:3]:
                print(f"   - {r['title']} | {r['channel']} | {r['duration']}s | {r['url']} | thumb={bool(r['thumbnail'])}")
    res = youtube.search("school bell", 8, "soundcloud")
    pick = next((r for r in res if r.get("duration") and r["duration"] < 600), res[0] if res else None)
    if pick:
        step("SoundCloud 주소 확인", lambda: youtube.probe(pick["url"])[0]["title"])
        step("SoundCloud 미리 듣기", lambda: youtube.preview_clip(pick["url"], 5).stat().st_size)
        d = tempfile.mkdtemp()
        step("SoundCloud 받기", lambda: (lambda p: f"{p[0].name} {p[0].stat().st_size}B {p[1]}")(
            youtube.download_audio(pick["url"], d, lambda f, s: None)))
    step("YouTube 검색", lambda: [r["title"] for r in youtube.search("학교 종소리", 3, "youtube")])
    log = app_data_dir() / "youtube.log"
    if log.exists():
        print("---- youtube.log ----")
        print(log.read_text(encoding="utf-8")[-2000:])
    print("\n===== 요약 =====")
    for name, ok in results:
        print(f"{'OK ' if ok else 'NO '} {name}")


if __name__ == "__main__":
    main()
