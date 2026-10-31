"""YouTube PO 토큰(접속 증명값) 공급.

YouTube는 요청이 '진짜 브라우저'에서 온 것인지 BotGuard 라는 검사로 확인하고, 증명값(PO 토큰)이 없으면
"Sign in to confirm you're not a bot" 으로 막는다. 디스코드 음악 봇들(yt-dlp, Lavalink)은 BotGuard를 직접 돌려
증명값을 만들어 붙이는 방식(bgutil)으로 이 문제를 피한다. 여기서도 같은 방식을 쓴다.

증명값은 함께 넣은 bgutil-pot 실행 파일(github.com/jim60105/bgutil-ytdlp-pot-provider-rs, GPL-3.0)이 만들고,
이 모듈은 yt-dlp의 PO 토큰 공급자 규격에 맞춰 그 실행 파일을 불러 주기만 한다.
"""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.core.paths import app_data_dir

_IS_WIN = sys.platform == "win32"
_NO_WINDOW = 0x08000000 if _IS_WIN else 0
_EXE = "bgutil-pot.exe" if _IS_WIN else "bgutil-pot"
TIMEOUT = 40.0

_registered = False


def cli_path():
    """함께 넣은 bgutil-pot 의 위치 (없으면 None)."""
    cands = []
    env = os.environ.get("MAPL_BGUTIL_POT")
    if env:
        cands.append(Path(env))
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        cands += [meipass / _EXE, meipass / "bgutil" / _EXE, exe_dir / _EXE]
    root = Path(__file__).resolve().parents[2]
    cands += [root / "build" / "bin" / _EXE]
    for c in cands:
        if c.is_file():
            return str(c)
    w = shutil.which("bgutil-pot")
    return w or None


def available():
    return cli_path() is not None


def _cache_dir():
    d = app_data_dir() / "potcache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def run_cli(args, timeout=TIMEOUT):
    exe = cli_path()
    if not exe:
        raise FileNotFoundError("bgutil-pot")
    env = os.environ.copy()
    env.setdefault("CACHE_DIR", str(_cache_dir()))
    env.setdefault("RUST_LOG", "warn")
    return subprocess.run([exe, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, env=env, creationflags=_NO_WINDOW, text=True,
                          encoding="utf-8", errors="replace")


def cli_version():
    try:
        r = run_cli(["--version"], timeout=10)
    except Exception:
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def register():
    """yt-dlp에 공급자를 등록한다. 실행 파일이 없거나 yt-dlp가 너무 오래됐으면 False."""
    global _registered
    if _registered:
        return True
    if not available():
        return False
    try:
        from yt_dlp.extractor.youtube.pot.provider import (
            ExternalRequestFeature,
            PoTokenContext,
            PoTokenProvider,
            PoTokenProviderError,
            PoTokenProviderRejectedRequest,
            PoTokenResponse,
            register_preference,
            register_provider,
        )
        from yt_dlp.extractor.youtube.pot.utils import WEBPO_CLIENTS, get_webpo_content_binding
    except Exception:
        return False

    @register_provider
    class MaplBgUtilPTP(PoTokenProvider):
        PROVIDER_NAME = "mapl-bgutil"
        PROVIDER_VERSION = "1.0.0"
        BUG_REPORT_LOCATION = "https://github.com/hminkoo10/Mapl-Tajong/issues"
        _SUPPORTED_CLIENTS = WEBPO_CLIENTS
        _SUPPORTED_CONTEXTS = (PoTokenContext.GVS, PoTokenContext.PLAYER, PoTokenContext.SUBS)
        _SUPPORTED_EXTERNAL_REQUEST_FEATURES = (
            ExternalRequestFeature.PROXY_SCHEME_HTTP,
            ExternalRequestFeature.PROXY_SCHEME_HTTPS,
            ExternalRequestFeature.PROXY_SCHEME_SOCKS4,
            ExternalRequestFeature.PROXY_SCHEME_SOCKS4A,
            ExternalRequestFeature.PROXY_SCHEME_SOCKS5,
            ExternalRequestFeature.PROXY_SCHEME_SOCKS5H,
            ExternalRequestFeature.SOURCE_ADDRESS,
            ExternalRequestFeature.DISABLE_TLS_VERIFICATION,
        )

        def is_available(self):
            return available()

        def _real_request_pot(self, request):
            binding = get_webpo_content_binding(request)[0]
            if not binding:
                raise PoTokenProviderRejectedRequest("content binding 없음")
            args = ["-c", binding]
            if request.request_proxy:
                args += ["-p", request.request_proxy]
            if request.bypass_cache:
                args.append("--bypass-cache")
            if request.request_source_address:
                args += ["--source-address", request.request_source_address]
            if request.request_verify_tls is False:
                args.append("--disable-tls-verification")
            self.logger.info(f"{request.context.value} PO 토큰을 만드는 중 ({request.internal_client_name})")
            try:
                r = run_cli(args)
            except subprocess.TimeoutExpired as e:
                raise PoTokenProviderError(f"bgutil-pot 시간 초과 ({e})")
            except Exception as e:
                raise PoTokenProviderError(f"bgutil-pot 실행 실패 ({e!r})") from e
            lines = (r.stdout or "").strip().splitlines()
            if r.returncode or not lines:
                tail = (r.stderr or "").strip().splitlines()[-3:]
                raise PoTokenProviderError(f"bgutil-pot 실패 ({r.returncode}): {' / '.join(tail)}")
            try:
                data = json.loads(lines[-1])
            except json.JSONDecodeError as e:
                raise PoTokenProviderError(f"bgutil-pot 응답을 읽지 못함 ({e})") from e
            token = data.get("poToken") if isinstance(data, dict) else None
            if not token:
                raise PoTokenProviderError("bgutil-pot 이 토큰을 주지 않음")
            return PoTokenResponse(po_token=token)

    @register_preference(MaplBgUtilPTP)
    def _prefer(provider, request):
        return 100

    _registered = True
    return True
