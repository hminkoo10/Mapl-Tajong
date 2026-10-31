"""날씨 예보 (노르웨이 기상청 MET Norway Locationforecast 2.0, 키 없이 무료, CC BY 4.0).

- 요청 간격과 캐시는 서버가 알려 주는 Expires / Last-Modified 를 따른다 (MET 이용 규칙).
- 받은 내용은 파일로 보관해 인터넷이 잠깐 끊겨도 마지막 예보를 보여 준다.
"""
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime

from app.core import net
from app.core.paths import app_data_dir, ui_cache_dir
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


def place_of(value):
    """설정값(도시 이름 또는 {'name','lat','lon'} JSON)을 (이름, 위도, 경도)로."""
    if isinstance(value, dict):
        try:
            return str(value["name"]), float(value["lat"]), float(value["lon"])
        except (KeyError, TypeError, ValueError):
            return city(DEFAULT_CITY)
    text = str(value or "").strip()
    if text.startswith("{"):
        try:
            return place_of(json.loads(text))
        except ValueError:
            pass
    return city(text or DEFAULT_CITY)


def _log(kind, detail):
    try:
        p = app_data_dir() / "weather.log"
        lines = p.read_text(encoding="utf-8").splitlines()[-200:] if p.exists() else []
        lines.append(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {kind}: {str(detail)[:500]}")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except Exception:
        pass


# ---------------- 지역 검색 (OpenStreetMap Nominatim) ----------------
GEO_URL = "https://nominatim.openstreetmap.org/search"
GEO_CREDIT = "지역 검색: © OpenStreetMap 기여자"
_geo_lock = threading.Lock()
_geo_last = [0.0]


def search_places(query, limit=8):
    """동네·도시 이름으로 위치를 찾는다. [{'name','label','lat','lon'}]
    (Nominatim 이용 규칙: 1초에 한 번 이하, 입력할 때마다가 아니라 검색을 누를 때만)"""
    q = (query or "").strip()
    if not q:
        return []
    with _geo_lock:
        wait = 1.1 - (time.monotonic() - _geo_last[0])
        if wait > 0:
            time.sleep(wait)
        _geo_last[0] = time.monotonic()
    url = (f"{GEO_URL}?format=jsonv2&addressdetails=1&limit={int(limit)}&countrycodes=kr&accept-language=ko&q="
           + urllib.parse.quote(q))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with net.urlopen(req, timeout=12) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        _log("지역 검색 실패", f"{q}: {e!r}")
        raise
    out, seen = [], set()
    for x in data:
        a = x.get("address") or {}
        name = x.get("name") or a.get("suburb") or a.get("city") or q
        area = [a.get(k) for k in ("state", "city", "county", "borough", "city_district", "town") if a.get(k)]
        area = [v for i, v in enumerate(area) if v != name and v not in area[:i]]
        label = f"{name} ({' '.join(area[:2])})" if area else name
        key = (round(float(x["lat"]), 3), round(float(x["lon"]), 3))
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": name, "label": label, "lat": float(x["lat"]), "lon": float(x["lon"])})
    return out


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


def get(place=DEFAULT_CITY, force=False, timeout=10):
    """예보를 돌려준다 (작업 스레드에서 호출). 실패하면 보관해 둔 마지막 예보, 그것도 없으면 None.
    place: 도시 이름, 또는 {'name','lat','lon'} (설정에 저장한 JSON 문자열도 됨)"""
    name, lat, lon = place_of(place)
    cache = _read_cache()
    key = f"{name}|{lat:.3f}|{lon:.3f}"
    same = cache.get("key") == key
    now_ts = time.time()
    if same and not force and cache.get("doc") and now_ts < max(cache.get("expires") or 0,
                                                                  (cache.get("fetched") or 0) + MIN_INTERVAL):
        return _result(cache)
    req = urllib.request.Request(f"{API}?lat={lat:.4f}&lon={lon:.4f}",
                                 headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    if same and cache.get("last_modified") and cache.get("doc"):
        req.add_header("If-Modified-Since", cache["last_modified"])
    try:
        with net.urlopen(req, timeout=timeout) as r:
            doc = json.loads(r.read().decode("utf-8"))
            cache = {"key": key, "city": name, "doc": doc, "fetched": now_ts,
                     "expires": _http_time(r.headers.get("Expires")) or now_ts + 1800,
                     "last_modified": r.headers.get("Last-Modified") or ""}
            _write_cache(cache)
    except urllib.error.HTTPError as e:
        if e.code == 304 and same:
            cache["fetched"] = now_ts
            cache["expires"] = _http_time(e.headers.get("Expires")) or now_ts + 1800
            _write_cache(cache)
        else:
            _log("예보 받기 실패", f"{name}: HTTP {e.code}")
            if not same:
                return None
    except Exception as e:
        _log("예보 받기 실패", f"{name}: {e!r}")
        if not same:
            return None
    return _result(cache) if cache.get("doc") else None


def _result(cache):
    try:
        out = parse(cache["doc"])
    except Exception as e:
        _log("예보 읽기 실패", repr(e))
        return None
    if out:
        out["city"] = cache.get("city")
        out["fetched"] = cache.get("fetched")
    return out


def setting_value(get_setting):
    """설정에서 지역 값을 읽는다 (예전 'weather_city' 도 그대로 쓴다)."""
    return get_setting("weather_place", "") or get_setting("weather_city", DEFAULT_CITY)
