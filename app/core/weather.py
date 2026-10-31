"""날씨 예보 (노르웨이 기상청 MET Norway Locationforecast 2.0, 키 없이 무료, CC BY 4.0).

- 요청 간격과 캐시는 서버가 알려 주는 Expires / Last-Modified 를 따른다 (MET 이용 규칙).
- 받은 내용은 파일로 보관해 인터넷이 잠깐 끊겨도 마지막 예보를 보여 준다.
"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from app.core.paths import ui_cache_dir
from app.core.version import APP_VERSION

API = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
USER_AGENT = f"MaplTajong/{APP_VERSION} (+https://github.com/hminkoo10/Mapl-Tajong)"
CREDIT = "날씨 정보: 노르웨이 기상청(MET Norway)"
MIN_INTERVAL = 15 * 60

# 학원·학교가 많은 곳 위주. (이름, 위도, 경도)
CITIES = [
    ("서울", 37.5665, 126.9780), ("인천", 37.4563, 126.7052), ("수원", 37.2636, 127.0286),
    ("성남", 37.4200, 127.1267), ("고양", 37.6584, 126.8320), ("용인", 37.2411, 127.1776),
    ("부천", 37.5034, 126.7660), ("안산", 37.3219, 126.8309), ("안양", 37.3943, 126.9568),
    ("남양주", 37.6360, 127.2165), ("화성", 37.1995, 126.8312), ("평택", 36.9921, 127.1129),
    ("의정부", 37.7381, 127.0337), ("파주", 37.7600, 126.7800), ("김포", 37.6153, 126.7156),
    ("광명", 37.4786, 126.8646), ("하남", 37.5393, 127.2149), ("시흥", 37.3800, 126.8029),
    ("춘천", 37.8813, 127.7298), ("원주", 37.3422, 127.9202), ("강릉", 37.7519, 128.8761),
    ("청주", 36.6424, 127.4890), ("천안", 36.8151, 127.1139), ("세종", 36.4800, 127.2890),
    ("대전", 36.3504, 127.3845), ("전주", 35.8242, 127.1480), ("군산", 35.9676, 126.7366),
    ("광주", 35.1595, 126.8526), ("목포", 34.8118, 126.3922), ("여수", 34.7604, 127.6622),
    ("순천", 34.9506, 127.4872), ("대구", 35.8714, 128.6014), ("포항", 36.0190, 129.3435),
    ("구미", 36.1195, 128.3446), ("안동", 36.5684, 128.7294), ("경주", 35.8562, 129.2247),
    ("부산", 35.1796, 129.0756), ("울산", 35.5384, 129.3114), ("창원", 35.2280, 128.6811),
    ("김해", 35.2285, 128.8894), ("진주", 35.1800, 128.1076), ("제주", 33.4996, 126.5312),
    ("서귀포", 33.2541, 126.5600),
]
DEFAULT_CITY = "서울"

# MET 기호 → (그림 종류, 한국어)
_SYMBOLS = {
    "clearsky": ("clear", "맑음"),
    "fair": ("fair", "대체로 맑음"),
    "partlycloudy": ("partly", "구름 조금"),
    "cloudy": ("cloudy", "흐림"),
    "fog": ("fog", "안개"),
    "lightrainshowers": ("rain", "약한 소나기"),
    "rainshowers": ("rain", "소나기"),
    "heavyrainshowers": ("rain", "강한 소나기"),
    "lightrain": ("rain", "약한 비"),
    "rain": ("rain", "비"),
    "heavyrain": ("rain", "강한 비"),
    "lightsleetshowers": ("sleet", "진눈깨비"),
    "sleetshowers": ("sleet", "진눈깨비"),
    "heavysleetshowers": ("sleet", "진눈깨비"),
    "lightsleet": ("sleet", "진눈깨비"),
    "sleet": ("sleet", "진눈깨비"),
    "heavysleet": ("sleet", "진눈깨비"),
    "lightsnowshowers": ("snow", "약한 눈"),
    "snowshowers": ("snow", "눈"),
    "heavysnowshowers": ("snow", "많은 눈"),
    "lightsnow": ("snow", "약한 눈"),
    "snow": ("snow", "눈"),
    "heavysnow": ("snow", "많은 눈"),
}


def city(name):
    for c in CITIES:
        if c[0] == name:
            return c
    return CITIES[0]


def describe(symbol_code):
    """'partlycloudy_night' → ('partly', '구름 조금', True)"""
    code = str(symbol_code or "")
    night = code.endswith("_night") or code.endswith("_polartwilight")
    base = code.split("_")[0]
    if "thunder" in base:
        return "thunder", "천둥번개", night
    kind, text = _SYMBOLS.get(base, ("cloudy", "흐림"))
    return kind, text, night


def _cache_path():
    return ui_cache_dir() / "weather.json"


def _read_cache():
    try:
        return json.loads(_cache_path().read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_cache(data):
    try:
        _cache_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def _http_time(text):
    try:
        return parsedate_to_datetime(text).timestamp()
    except Exception:
        return None


def _local(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().replace(tzinfo=None)


def parse(doc, now=None):
    """MET 응답(JSON)을 화면에 쓰기 좋은 모양으로."""
    now = now or datetime.now()
    series = (doc.get("properties") or {}).get("timeseries") or []
    rows = []
    for ts in series:
        try:
            t = _local(ts["time"])
        except Exception:
            continue
        data = ts.get("data") or {}
        temp = ((data.get("instant") or {}).get("details") or {}).get("air_temperature")
        nxt = data.get("next_1_hours") or data.get("next_6_hours") or data.get("next_12_hours") or {}
        sym = (nxt.get("summary") or {}).get("symbol_code")
        rain = (nxt.get("details") or {}).get("precipitation_amount")
        rows.append((t, temp, sym, rain))
    if not rows:
        return None
    cur = None
    for r in rows:
        if r[0] <= now + timedelta(minutes=30):
            cur = r
        else:
            break
    cur = cur or rows[0]
    hours = [r for r in rows if r[0] > now and r[1] is not None and r[2]][:12]
    today = [r[1] for r in rows if r[0].date() == now.date() and r[1] is not None]
    tomorrow_d = (now + timedelta(days=1)).date()
    tomorrow = [r for r in rows if r[0].date() == tomorrow_d and r[1] is not None]
    t_sym = next((r[2] for r in tomorrow if r[0].hour >= 9 and r[2]), tomorrow[0][2] if tomorrow else None)
    kind, text, night = describe(cur[2])
    return {
        "now": {"temp": cur[1], "kind": kind, "text": text, "night": night},
        "today": {"max": max(today) if today else None, "min": min(today) if today else None},
        "tomorrow": {"max": max(r[1] for r in tomorrow) if tomorrow else None,
                     "min": min(r[1] for r in tomorrow) if tomorrow else None,
                     "text": describe(t_sym)[1] if t_sym else "", "kind": describe(t_sym)[0] if t_sym else ""},
        "hours": [{"time": r[0].strftime("%Y-%m-%dT%H:%M"), "temp": r[1], "kind": describe(r[2])[0],
                   "night": describe(r[2])[2], "rain": r[3]} for r in hours],
    }


def get(city_name=DEFAULT_CITY, force=False, timeout=10):
    """예보를 돌려준다 (작업 스레드에서 호출). 실패하면 보관해 둔 마지막 예보, 그것도 없으면 None."""
    name, lat, lon = city(city_name)
    cache = _read_cache()
    same = cache.get("city") == name
    now_ts = time.time()
    if same and not force and cache.get("doc") and now_ts < max(cache.get("expires") or 0,
                                                                  (cache.get("fetched") or 0) + MIN_INTERVAL):
        return _result(cache)
    req = urllib.request.Request(f"{API}?lat={lat:.4f}&lon={lon:.4f}",
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    if same and cache.get("last_modified") and cache.get("doc"):
        req.add_header("If-Modified-Since", cache["last_modified"])
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            doc = json.loads(r.read().decode("utf-8"))
            cache = {"city": name, "doc": doc, "fetched": now_ts,
                     "expires": _http_time(r.headers.get("Expires")) or now_ts + 1800,
                     "last_modified": r.headers.get("Last-Modified") or ""}
            _write_cache(cache)
    except urllib.error.HTTPError as e:
        if e.code == 304 and same:
            cache["fetched"] = now_ts
            cache["expires"] = _http_time(e.headers.get("Expires")) or now_ts + 1800
            _write_cache(cache)
        elif not same:
            return None
    except Exception:
        if not same:
            return None
    return _result(cache) if cache.get("doc") else None


def _result(cache):
    out = parse(cache["doc"])
    if out:
        out["city"] = cache.get("city")
        out["fetched"] = cache.get("fetched")
    return out
