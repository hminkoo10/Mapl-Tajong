"""인터넷 요청 공통 설정.

Windows는 일부 인증서(루트 CA)를 브라우저가 처음 쓸 때 내려받아 두기 때문에, 그 사이트를 브라우저로 연 적이 없는
컴퓨터에서는 파이썬이 인증서를 찾지 못해 접속을 거부할 수 있다. 그래서 Windows 인증서 저장소와 함께
certifi(모질라 인증서 목록)도 믿도록 한다. 학원·학교 방화벽이 쓰는 인증서는 Windows 저장소 쪽에서 통과한다.
"""
import ssl
import urllib.request
from functools import lru_cache


@lru_cache(maxsize=1)
def ssl_context():
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except Exception:
        pass
    return ctx


def urlopen(req, timeout=15):
    if isinstance(req, str):
        req = urllib.request.Request(req)
    return urllib.request.urlopen(req, timeout=timeout, context=ssl_context())
