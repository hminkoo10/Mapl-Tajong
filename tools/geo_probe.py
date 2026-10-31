"""도로명주소 검색 방식 비교 (CI 진단용, 앱에는 들어가지 않음)."""
import json
import re
import sys
import time
import urllib.parse
import urllib.request

for s in (sys.stdout, sys.stderr):
    try:
        s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

UA = "MaplTajong/2.1 (+https://github.com/hminkoo10/Mapl-Tajong)"
ADDRS = [
    "서울특별시 강남구 테헤란로 152",
    "서울 강남구 테헤란로 152",
    "경기도 성남시 분당구 정자일로 95",
    "부산광역시 해운대구 해운대해변로 264",
    "서울특별시 종로구 세종대로 175",
    "대구광역시 중구 동성로2길 80",
    "서울특별시 서초구 강남대로 465",
    "경기도 수원시 팔달구 효원로 241",
]
ROAD = re.compile(r"^(.+?(?:대로|로|길))$")


def get(url):
    time.sleep(1.2)
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def split(addr):
    parts = addr.split()
    road_i = next((i for i, p in enumerate(parts) if ROAD.match(p) and i + 1 < len(parts)
                   and re.fullmatch(r"\d+(-\d+)?", parts[i + 1])), None)
    if road_i is None:
        return None
    return parts[:road_i], parts[road_i], parts[road_i + 1]


def show(tag, data):
    if not data:
        print(f"   {tag:10} -> (없음)")
        return
    x = data[0]
    a = x.get("address") or {}
    print(f"   {tag:10} -> {x.get('addresstype') or x.get('type')} hn={a.get('house_number')} "
          f"{x.get('lat')},{x.get('lon')} | {x.get('display_name', '')[:70]}")


def main():
    base = "https://nominatim.openstreetmap.org/search?format=jsonv2&addressdetails=1&limit=3&countrycodes=kr&accept-language=ko"
    for addr in ADDRS:
        print(f"== {addr}")
        try:
            show("자유형", get(base + "&q=" + urllib.parse.quote(addr)))
            sp = split(addr)
            if sp:
                region, road, num = sp
                rev = f"{num} {road}, " + ", ".join(reversed(region))
                show("역순", get(base + "&q=" + urllib.parse.quote(rev)))
                q = {"street": f"{num} {road}"}
                if region:
                    q["city"] = region[-1] if len(region) >= 2 else region[0]
                    if len(region) >= 2:
                        q["state"] = region[0]
                show("구조화", get(base + "&" + urllib.parse.urlencode(q)))
                show("도로+번호", get(base + "&q=" + urllib.parse.quote(f"{road} {num}")))
            ph = get("https://photon.komoot.io/api/?limit=3&q=" + urllib.parse.quote(addr))
            feats = ph.get("features") or []
            if feats:
                pr = feats[0]["properties"]
                c = feats[0]["geometry"]["coordinates"]
                print(f"   {'photon':10} -> {pr.get('type')} hn={pr.get('housenumber')} {c[1]},{c[0]} | "
                      f"{pr.get('name')} {pr.get('street')} {pr.get('city')} {pr.get('district')}")
            else:
                print(f"   {'photon':10} -> (없음)")
        except Exception as e:
            print("   오류:", e)


if __name__ == "__main__":
    main()
