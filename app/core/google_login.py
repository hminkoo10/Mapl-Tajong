"""YouTube 받기용 구글 로그인.

이 컴퓨터의 Chrome(없으면 Edge·웨일)을 '이 프로그램 전용 프로필'로 열어 사용자가 직접 구글에 로그인하게 한다.
로그인이 끝나면 브라우저의 개발자 연결(DevTools, 이 컴퓨터 안에서만 열림)로 YouTube 로그인 정보(쿠키)만 읽어
파일로 저장하고 창을 닫는다. yt-dlp는 이 파일로 로그인한 상태로 받는다.

- 평소 쓰는 브라우저 프로필과는 완전히 분리되어 있다. 전용 프로필은 로그인 뒤 다시 열지 않으므로
  브라우저가 로그인 정보를 바꿔 버려(rotate) 금방 무효가 되는 문제도 없다.
- 로그인 정보는 이 컴퓨터의 데이터 폴더에만 저장되고 다른 곳으로 보내지 않는다.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from app.core.paths import app_data_dir

LOGIN_URL = ("https://accounts.google.com/ServiceLogin?service=youtube&uilel=3&passive=true&hl=ko"
             "&continue=https%3A%2F%2Fwww.youtube.com%2Fsignin%3Faction_handle_signin%3Dtrue%26app%3Ddesktop"
             "%26hl%3Dko%26next%3Dhttps%253A%252F%252Fwww.youtube.com%252F")
LOGIN_COOKIES = ("LOGIN_INFO", "SAPISID", "__Secure-3PAPISID")
KEEP_DOMAINS = ("youtube.com", "google.com")
_IS_WIN = sys.platform == "win32"


class LoginError(RuntimeError):
    pass


def profile_dir():
    return app_data_dir() / "google_login"


def cookie_file():
    return app_data_dir() / "youtube_cookies.txt"


def is_logged_in():
    p = cookie_file()
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return False
    return any(f"\t{name}\t" in text for name in LOGIN_COOKIES)


def logged_in_at():
    try:
        return cookie_file().stat().st_mtime
    except OSError:
        return None


def logout():
    try:
        cookie_file().unlink()
    except OSError:
        pass
    shutil.rmtree(profile_dir(), ignore_errors=True)


# ---------------- 브라우저 찾기 ----------------
def find_browser():
    """(이름, 실행 파일) — Chrome → Edge → 웨일 순. 없으면 None."""
    env = os.environ.get("MAPL_LOGIN_BROWSER")
    if env and Path(env).is_file():
        return ("브라우저", env)
    cands = []
    if _IS_WIN:
        pf = [os.environ.get(k) for k in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")]
        pf = [Path(x) for x in pf if x]
        for base in pf:
            cands.append(("Chrome", base / "Google" / "Chrome" / "Application" / "chrome.exe"))
        for base in pf:
            cands.append(("Edge", base / "Microsoft" / "Edge" / "Application" / "msedge.exe"))
        for base in pf:
            cands.append(("웨일", base / "Naver" / "Naver Whale" / "Application" / "whale.exe"))
        for label, exe in cands:
            if exe.is_file():
                return (label, str(exe))
        reg = _from_registry()
        if reg:
            return reg
        return None
    for label, name in (("Chrome", "google-chrome"), ("Chrome", "google-chrome-stable"), ("Chromium", "chromium"),
                        ("Chromium", "chromium-browser"), ("Edge", "microsoft-edge")):
        w = shutil.which(name)
        if w:
            return (label, w)
    return None


def _from_registry():
    try:
        import winreg
    except ImportError:
        return None
    for label, exe in (("Chrome", "chrome.exe"), ("Edge", "msedge.exe"), ("웨일", "whale.exe")):
        for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            try:
                with winreg.OpenKey(root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}") as k:
                    path, _ = winreg.QueryValueEx(k, "")
                    if path and Path(path).is_file():
                        return (label, path)
            except OSError:
                continue
    return None


# ---------------- 로그인 창 ----------------
def _write_cookies(cookies, path: Path):
    lines = ["# Netscape HTTP Cookie File",
             "# 마고 타종이 구글 로그인으로 저장한 YouTube 로그인 정보입니다. 다른 사람과 공유하지 마세요.", ""]
    n = 0
    for c in cookies:
        dom = str(c.get("domain") or "")
        if not any(dom.endswith(d) for d in KEEP_DOMAINS):
            continue
        exp = c.get("expires")
        exp = int(exp) if isinstance(exp, (int, float)) and exp > 0 else 0
        lines.append("\t".join([dom, "TRUE" if dom.startswith(".") else "FALSE", str(c.get("path") or "/"),
                                "TRUE" if c.get("secure") else "FALSE", str(exp), str(c["name"]), str(c["value"])]))
        n += 1
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    tmp.replace(path)
    return n


def has_login(cookies):
    return any(c.get("name") in LOGIN_COOKIES and str(c.get("domain", "")).endswith("youtube.com") for c in cookies)


def profile_in_use():
    """전용 프로필로 브라우저가 떠 있는지 (프로필 잠금 파일로 확인)."""
    d = profile_dir()
    if _IS_WIN:
        lf = d / "lockfile"
        if not lf.exists():
            return False
        try:
            lf.unlink()          # 브라우저가 쓰는 중이면 지울 수 없다
            return False
        except PermissionError:
            return True
        except OSError:
            return False
    return os.path.islink(d / "SingletonLock") or (d / "SingletonLock").exists()


class LoginSession:
    """전용 프로필로 브라우저를 연다.

    로그인하는 동안에는 브라우저를 평범하게 연다. (개발자 연결을 켜 두면 구글이 '안전하지 않은 브라우저'로
    보고 로그인을 막는다.) 로그인이 끝나 창이 닫히면, 같은 프로필을 화면 없이 잠깐 다시 열어
    로그인 정보만 읽고 바로 닫는다."""

    def __init__(self, exe):
        self.exe = exe
        self.proc = None
        self._id = 0
        self._dev_dir = None

    def _base_args(self):
        return [self.exe, f"--user-data-dir={profile_dir()}", "--no-first-run", "--no-default-browser-check"]

    def open_login(self, url=LOGIN_URL):
        profile_dir().mkdir(parents=True, exist_ok=True)
        args = self._base_args()
        if os.environ.get("MAPL_LOGIN_HEADLESS"):   # 시험용: 화면 없이, 쿠키를 넣을 수 있게
            args += ["--headless=new", "--no-sandbox", "--remote-debugging-port=0"]
        args.append(url)
        self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)

    def running(self):
        if self.proc is not None and self.proc.poll() is None:
            return True
        return profile_in_use()

    def request_close(self, wait=15):
        """창을 정상적으로 닫게 한다 (로그인 정보가 디스크에 저장되도록). 안 닫히면 강제로."""
        if self.proc is not None and self.proc.poll() is None:
            try:
                if _IS_WIN:
                    subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T"], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=0x08000000, timeout=10)
                else:
                    self.proc.terminate()
            except Exception:
                pass
        end = time.monotonic() + wait
        while time.monotonic() < end and self.running():
            time.sleep(0.4)
        if self.running() and self.proc is not None:
            try:
                if _IS_WIN:
                    subprocess.run(["taskkill", "/PID", str(self.proc.pid), "/T", "/F"], stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, creationflags=0x08000000, timeout=10)
                else:
                    self.proc.kill()
            except Exception:
                pass
            time.sleep(1.5)

    # ---- 화면 없이 다시 열어 로그인 정보 읽기 ----
    def _ws_url(self):
        f = profile_dir() / "DevToolsActivePort"
        try:
            port, path = f.read_text(encoding="utf-8").split("\n")[:2]
        except (OSError, ValueError):
            return None
        return f"ws://127.0.0.1:{port.strip()}{path.strip()}"

    def _call(self, method, params=None, timeout=5):
        url = self._ws_url()
        if not url:
            return None
        from websockets.sync.client import connect
        self._id += 1
        with connect(url, open_timeout=timeout, close_timeout=1, max_size=None) as ws:
            ws.send(json.dumps({"id": self._id, "method": method, "params": params or {}}))
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                msg = json.loads(ws.recv(timeout=max(0.1, end - time.monotonic())))
                if msg.get("id") == self._id:
                    if "error" in msg:
                        raise LoginError(str(msg["error"]))
                    return msg.get("result") or {}
        return None

    def read_cookies(self, timeout=30):
        """프로필을 화면 없이 열어 쿠키를 읽고 닫는다."""
        (profile_dir() / "DevToolsActivePort").unlink(missing_ok=True)
        args = self._base_args() + ["--headless=new", "--remote-debugging-port=0", "--disable-gpu",
                                    "--mute-audio", "about:blank"]
        if os.environ.get("MAPL_LOGIN_HEADLESS"):
            args.insert(-1, "--no-sandbox")
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=0x08000000 if _IS_WIN else 0)
        try:
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                try:
                    res = self._call("Storage.getCookies")
                except Exception:
                    res = None
                if res is not None:
                    return res.get("cookies") or []
                if proc.poll() is not None:
                    break
                time.sleep(0.5)
            raise LoginError("로그인 정보를 읽지 못했어요. 브라우저 창을 모두 닫고 다시 해 주세요.")
        finally:
            try:
                self._call("Browser.close", timeout=3)
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                proc.kill()


def run_login(cancel_event=None, status_cb=None, timeout=900, browser=None, done_event=None):
    """로그인 창을 열고, 사용자가 로그인 뒤 창을 닫거나 '마쳤어요'를 누르면 로그인 정보를 읽는다.
    (작업 스레드에서 호출) 성공하면 저장한 쿠키 수, 실패·취소하면 LoginError."""
    found = browser or find_browser()
    if not found:
        raise LoginError("Chrome이나 Edge를 찾지 못했어요. 둘 중 하나를 설치한 뒤 다시 해 주세요.")
    label, exe = found
    s = LoginSession(exe)
    s.open_login()
    if status_cb:
        status_cb(f"{label} 창에서 구글 계정으로 로그인해 주세요")
    start = time.monotonic()
    seen_open = False
    try:
        while True:
            if cancel_event is not None and cancel_event.is_set():
                raise LoginError("로그인을 취소했어요.")
            if time.monotonic() - start > timeout:
                raise LoginError("로그인을 기다리다 시간이 지났어요. 다시 해 주세요.")
            if done_event is not None and done_event.is_set():
                break
            is_open = s.running()
            seen_open = seen_open or is_open
            if not is_open and (seen_open or time.monotonic() - start > 10):
                break                       # 사용자가 창을 닫았다
            time.sleep(0.8)
        if status_cb:
            status_cb("로그인 정보를 확인하고 있어요")
        s.request_close()
        if cancel_event is not None and cancel_event.is_set():
            raise LoginError("로그인을 취소했어요.")
        cookies = s.read_cookies()
        if not has_login(cookies):
            raise LoginError("로그인이 확인되지 않았어요. 브라우저에서 YouTube까지 로그인한 뒤 창을 닫아 주세요.")
        n = _write_cookies(cookies, cookie_file())
        if status_cb:
            status_cb("로그인했어요")
        return n
    except BaseException:
        if cancel_event is not None and cancel_event.is_set():
            s.request_close(wait=5)
        raise
