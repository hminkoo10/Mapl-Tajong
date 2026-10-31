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


class LoginSession:
    """전용 프로필로 브라우저를 열고, 로그인될 때까지 지켜본다."""

    def __init__(self, exe, extra_args=None):
        self.exe = exe
        self.extra_args = list(extra_args or [])
        self.proc = None
        self._id = 0
        self._reused = False

    def start(self, url=LOGIN_URL):
        d = profile_dir()
        d.mkdir(parents=True, exist_ok=True)
        # 지난번 로그인 창이 아직 열려 있으면 그 창에 새 탭으로 연다
        try:
            if self._call("Browser.getVersion", timeout=2) is not None:
                self._call("Target.createTarget", {"url": url}, timeout=3)
                self._reused = True
                return
        except Exception:
            pass
        (d / "DevToolsActivePort").unlink(missing_ok=True)
        args = [self.exe, f"--user-data-dir={d}", "--remote-debugging-port=0", "--no-first-run",
                "--no-default-browser-check", "--disable-sync", "--new-window", *self.extra_args, url]
        if os.environ.get("MAPL_LOGIN_HEADLESS"):   # 시험용
            args[1:1] = ["--headless=new", "--no-sandbox"]
        self.proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL)

    def alive(self):
        if self.proc is not None and self.proc.poll() is None:
            return True
        try:
            return self._call("Browser.getVersion", timeout=2) is not None
        except Exception:
            return False

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

    def cookies(self):
        """브라우저가 아직 준비되지 않았으면 None."""
        res = self._call("Storage.getCookies")
        return None if res is None else (res.get("cookies") or [])

    def close(self):
        try:
            self._call("Browser.close", timeout=3)
        except Exception:
            pass
        if self.proc is not None:
            try:
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.terminate()
                except Exception:
                    pass


def run_login(cancel_event=None, status_cb=None, timeout=900, browser=None):
    """로그인 창을 열고 끝날 때까지 기다린다 (작업 스레드에서 호출).
    성공하면 저장한 쿠키 수, 사용자가 창을 닫거나 취소하면 LoginError."""
    found = browser or find_browser()
    if not found:
        raise LoginError("Chrome이나 Edge를 찾지 못했어요. 둘 중 하나를 설치한 뒤 다시 해 주세요.")
    label, exe = found
    s = LoginSession(exe)
    s.start()
    if status_cb:
        status_cb(f"{label} 창에서 구글 계정으로 로그인해 주세요")
    start = time.monotonic()
    end = start + timeout
    seen_devtools = False
    try:
        while time.monotonic() < end:
            if cancel_event is not None and cancel_event.is_set():
                raise LoginError("로그인을 취소했어요.")
            try:
                cookies = s.cookies()
                seen_devtools = seen_devtools or cookies is not None
            except Exception:
                cookies = None
            if cookies and has_login(cookies):
                n = _write_cookies(cookies, cookie_file())
                if status_cb:
                    status_cb("로그인했어요")
                return n
            if not s.alive() and (seen_devtools or time.monotonic() > start + 10):
                raise LoginError("로그인 창이 닫혔어요. 다시 해 주세요.")
            time.sleep(1.2)
        raise LoginError("로그인을 기다리다 시간이 지났어요. 다시 해 주세요.")
    finally:
        s.close()
