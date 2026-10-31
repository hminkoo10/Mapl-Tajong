"""자동 업데이트.

GitHub Releases에서 `MaplTajong-Setup-x.y.z.exe` 설치 파일을 찾아 받고(SHA-256 확인),
Inno Setup 설치 파일을 조용히 실행한다. 안드로이드 릴리스도 같은 저장소에 올라오므로
'최신 릴리스'가 아니라 설치 파일 이름으로 데스크톱 버전을 찾는다.
"""
import hashlib
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from app.core.paths import app_data_dir
from app.core.version import APP_VERSION

REPO = "hminkoo10/Mapl-Tajong"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
ASSET_RE = re.compile(r"^MaplTajong-Setup-(\d+(?:\.\d+){1,3})\.exe$", re.IGNORECASE)
ALLOWED_HOSTS = ("github.com", "githubusercontent.com")


class UpdateError(RuntimeError):
    pass


class Cancelled(UpdateError):
    pass


@dataclass
class UpdateInfo:
    version: str
    title: str
    notes: str
    page_url: str
    asset_name: str
    asset_url: str
    size: int
    sha256: str = None
    sha_url: str = None


def parse_version(s):
    nums = [int(x) for x in re.findall(r"\d+", str(s))[:4]]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums)


def is_newer(a, b):
    return parse_version(a) > parse_version(b)


def is_installed():
    """설치 파일로 설치된 실행 파일인지 (Inno Setup 제거 프로그램이 옆에 있음)."""
    if not getattr(sys, "frozen", False) or sys.platform != "win32":
        return False
    return any(Path(sys.executable).parent.glob("unins*.exe"))


def updates_dir():
    d = app_data_dir() / "updates"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _open(url, timeout, accept="*/*"):
    req = urllib.request.Request(url, headers={"User-Agent": f"MaplTajong/{APP_VERSION}", "Accept": accept})
    try:
        return urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context())
    except urllib.error.URLError as e:
        # 일부 PC는 인증서 저장소가 오래되어 실패한다 → certifi로 한 번 더
        if not isinstance(getattr(e, "reason", None), ssl.SSLError):
            raise
        try:
            import certifi
        except ImportError:
            raise e
        ctx = ssl.create_default_context(cafile=certifi.where())
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)


def _friendly(e):
    if isinstance(e, urllib.error.HTTPError):
        if e.code in (403, 429):
            return "업데이트 서버가 잠시 바빠요. 나중에 다시 확인할게요."
        return f"업데이트 정보를 가져오지 못했어요. (HTTP {e.code})"
    if isinstance(e, (urllib.error.URLError, TimeoutError, OSError)):
        return "인터넷에 연결되어 있지 않아 업데이트를 확인하지 못했어요."
    return f"업데이트를 확인하지 못했어요. ({e})"


def _check_host(url, allowed_hosts):
    host = (urlparse(url).hostname or "").lower()
    if not any(host == h or host.endswith("." + h) for h in allowed_hosts):
        raise UpdateError("알 수 없는 주소라서 받지 않았어요.")


def check(current=APP_VERSION, api_url=RELEASES_API, timeout=12):
    """새 버전이 있으면 UpdateInfo, 없으면 None."""
    try:
        with _open(api_url, timeout, "application/vnd.github+json") as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception as e:
        raise UpdateError(_friendly(e))

    best = None
    for rel in data if isinstance(data, list) else []:
        if rel.get("draft") or rel.get("prerelease"):
            continue
        assets = rel.get("assets") or []
        by_name = {a.get("name", ""): a for a in assets}
        for a in assets:
            m = ASSET_RE.match(a.get("name", ""))
            if not m:
                continue
            ver = m.group(1)
            if best is not None and not is_newer(ver, best.version):
                continue
            digest = str(a.get("digest") or "")
            side = by_name.get(a["name"] + ".sha256")
            best = UpdateInfo(
                version=ver,
                title=rel.get("name") or ver,
                notes=rel.get("body") or "",
                page_url=rel.get("html_url") or RELEASES_PAGE,
                asset_name=a["name"],
                asset_url=a.get("browser_download_url") or "",
                size=int(a.get("size") or 0),
                sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else None,
                sha_url=side.get("browser_download_url") if side else None,
            )
    if best is not None and is_newer(best.version, current):
        return best
    return None


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download(info: UpdateInfo, progress_cb=None, cancel_event=None, allowed_hosts=ALLOWED_HOSTS, timeout=30):
    """설치 파일을 받아 SHA-256을 확인한 뒤 경로를 반환."""
    _check_host(info.asset_url, allowed_hosts)
    expected = info.sha256
    if not expected and info.sha_url:
        _check_host(info.sha_url, allowed_hosts)
        try:
            with _open(info.sha_url, timeout) as r:
                m = re.search(r"\b([0-9a-fA-F]{64})\b", r.read(4096).decode("utf-8", "replace"))
            expected = m.group(1).lower() if m else None
        except Exception as e:
            raise UpdateError(_friendly(e))
    if not expected:
        raise UpdateError("설치 파일을 확인할 값(SHA-256)이 없어서 받지 않았어요.")

    dst = updates_dir() / Path(info.asset_name).name
    if dst.exists() and _sha256_file(dst) == expected:
        if progress_cb:
            progress_cb(1.0)
        return dst

    part = dst.with_name(dst.name + ".part")
    h = hashlib.sha256()
    done = 0
    try:
        with _open(info.asset_url, timeout) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.size or 0)
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise Cancelled("취소했어요.")
                chunk = r.read(1 << 18)
                if not chunk:
                    break
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if progress_cb and total:
                    progress_cb(min(0.99, done / total))
    except UpdateError:
        part.unlink(missing_ok=True)
        raise
    except Exception as e:
        part.unlink(missing_ok=True)
        raise UpdateError(_friendly(e))

    if h.hexdigest() != expected:
        part.unlink(missing_ok=True)
        raise UpdateError("받은 파일이 올바르지 않아요. 다음에 다시 받을게요.")
    os.replace(part, dst)
    if progress_cb:
        progress_cb(1.0)
    return dst


def launch_installer(path):
    """설치 파일을 조용히 실행. 설치가 끝나면 설치 파일이 프로그램을 다시 켠다."""
    if sys.platform != "win32":
        raise UpdateError("Windows에서만 설치할 수 있어요.")
    log = updates_dir() / "install.log"
    args = [str(path), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS", f"/LOG={log}"]
    flags = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen(args, creationflags=flags, close_fds=True, cwd=str(Path(path).parent))


def cleanup(keep=None):
    """지난 설치 파일 정리."""
    for f in updates_dir().glob("MaplTajong-Setup-*"):
        if keep is not None and f.name == Path(keep).name:
            continue
        try:
            f.unlink()
        except OSError:
            pass


def notes_to_text(md, max_lines=14):
    """릴리스 노트(마크다운)를 대화상자에 보여줄 평문으로."""
    out = []
    for line in (md or "").splitlines():
        s = line.strip()
        if not s:
            continue
        s = re.sub(r"^#+\s*", "", s)
        s = re.sub(r"^[-*]\s+", "· ", s)
        s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
        s = re.sub(r"`([^`]+)`", r"\1", s)
        s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
        out.append(s)
    if len(out) > max_lines:
        out = out[:max_lines] + ["…"]
    return "\n".join(out)
