"""설정 파일 서명 (앱 밖에서 손으로 바꾼 설정은 적용하지 않으려고).

통합 클라우드(런처)는 magoedu-app.json 에 "dataSigning": true 인 프로그램에만 MAGOEDU_DATA_KEY 를 넘겨 준다.
키가 없으면(예전 통합 클라우드) 서명하지 않고 확인하지도 않는다 (예전 그대로).

안드로이드(core/DataSign.kt)와 바이트까지 같아야 해서 정규화 JSON 이 아니라 쓴 글자 그대로 다룬다.
    서명: 맨 위에 "sig": "000…0"(0 64개)을 넣어 평소처럼 직렬화 → UTF-8 바이트 B,
          sig = HMAC-SHA256(키 글자의 UTF-8 바이트, B) 의 소문자 16진수. B 의 그 0 자리만 sig 로 바꿔 쓴다 (길이 같음)
    확인: 파일 바이트 그대로(BOM·공백도 그대로) UTF-8 로 읽어 "sig"\\s*:\\s*"([0-9a-f]{64})" 가 꼭 하나 있어야 하고,
          그 64자를 0 으로 바꾼 바이트의 HMAC 과 같아야 한다 (상수 시간 비교)
"""
import hashlib
import hmac
import json
import os
import re

KEY_ENV = "MAGOEDU_DATA_KEY"
ZERO = "0" * 64
# \s 는 안드로이드(자바 정규식)와 같게 ASCII 공백만
_SIG = re.compile(r'"sig"\s*:\s*"([0-9a-f]{64})"', re.ASCII)


def data_key():
    """통합 클라우드가 준 키. 없으면 "" (서명을 쓰지 않음)."""
    return os.environ.get(KEY_ENV) or ""


def _mac(key, data):
    return hmac.new(key.encode("utf-8"), data, hashlib.sha256).hexdigest()


def sign_bytes(raw, key):
    """raw 에 "sig": "000…0" 이 하나만 있어야 한다. 그 자리에 서명을 넣은 바이트를 돌려준다."""
    text = raw.decode("utf-8")
    found = list(_SIG.finditer(text))
    if len(found) != 1 or found[0].group(1) != ZERO:
        raise ValueError("서명 자리가 없어요")
    a, b = found[0].span(1)
    return (text[:a] + _mac(key, raw) + text[b:]).encode("utf-8")


def dumps_signed(doc, key, **kwargs):
    """json.dumps(doc, **kwargs) 와 같게 쓰되 "sig" 를 넣어 서명한 UTF-8 바이트."""
    doc = dict(doc)
    doc["sig"] = ZERO
    return sign_bytes(json.dumps(doc, **kwargs).encode("utf-8"), key)


def verify_bytes(raw, key):
    """서명이 맞으면 True. 없거나, 둘 이상이거나, 틀리거나, UTF-8 이 아니면 False."""
    try:
        text = bytes(raw).decode("utf-8")
    except UnicodeDecodeError:
        return False
    found = list(_SIG.finditer(text))
    if len(found) != 1:
        return False
    a, b = found[0].span(1)
    blank = (text[:a] + ZERO + text[b:]).encode("utf-8")
    return hmac.compare_digest(_mac(key, blank), found[0].group(1))
