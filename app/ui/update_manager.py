"""업데이트 흐름 관리: 주기적 확인 → 받기 → 아무도 쓰지 않고 종도 멀었을 때 설치."""
import sys
import threading
import time
from datetime import datetime

from PyQt6.QtCore import QObject, QThread, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices

from app.core import updater
from app.core.version import APP_VERSION
from app.data import repo
from app.ui.workers import keep_alive, run_async

CHECK_EVERY_MS = 6 * 60 * 60 * 1000
FIRST_CHECK_MS = 60 * 1000
SAFE_GAP_MIN = 10  # 다음 종까지 이 시간 이상 남았을 때만 자동 설치
IDLE_MIN = 5       # 컴퓨터를 이 시간 이상 아무도 만지지 않았을 때만 자동 설치


def idle_seconds():
    """키보드·마우스를 마지막으로 쓴 뒤 지난 시간(초). 알 수 없으면 None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(lii)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            return None
        now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
        return ((now - lii.dwTime) & 0xFFFFFFFF) / 1000.0
    except Exception:
        return None


class _DownloadThread(QThread):
    progress = pyqtSignal(float)
    done = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, info):
        super().__init__()
        self.info = info
        self.cancel_event = threading.Event()

    def run(self):
        try:
            p = updater.download(self.info, lambda f: self.progress.emit(float(f)), self.cancel_event)
            self.done.emit(str(p))
        except Exception as e:
            self.failed.emit(str(e))


class UpdateManager(QObject):
    """state: idle | checking | latest | available | downloading | ready | installing | error"""
    changed = pyqtSignal()

    def __init__(self, ctx, quit_for_update):
        super().__init__()
        self.ctx = ctx
        self.conn = ctx.conn
        self.quit_for_update = quit_for_update
        self.state = "idle"
        self.info = None
        self.path = None
        self.progress = 0.0
        self.message = ""
        self.last_check = None
        self._manual = False
        self._install_after = False
        self._dl = None
        self._installing = False
        self._nagged = False
        self._last_touch = time.monotonic()
        self.installed = updater.is_installed()

        self._check_timer = QTimer(self)
        self._check_timer.timeout.connect(lambda: self.check(manual=False))
        QTimer.singleShot(FIRST_CHECK_MS, lambda: (self.check(manual=False), self._check_timer.start(CHECK_EVERY_MS)))

        self._safe_timer = QTimer(self)
        self._safe_timer.setInterval(30 * 1000)
        self._safe_timer.timeout.connect(self._try_auto_install)

    # ---------- 설정 ----------
    @property
    def auto(self):
        return repo.get_setting(self.conn, "update_auto", "1") == "1"

    def set_auto(self, on):
        repo.set_setting(self.conn, "update_auto", "1" if on else "0")
        if on and self.state == "available" and self.installed:
            self.download()
        elif on and self.state == "ready":
            self._safe_timer.start()
        elif not on:
            self._safe_timer.stop()
        self.changed.emit()

    def has_update(self):
        return self.state in ("available", "downloading", "ready", "installing")

    def _set(self, state, message=""):
        self.state = state
        self.message = message
        self.changed.emit()

    # ---------- 확인 ----------
    def check(self, manual=True):
        if self.state in ("checking", "downloading", "installing"):
            return
        self._manual = manual
        self._set("checking")
        run_async(updater.check, on_done=self._checked, on_fail=self._check_failed)

    def _check_failed(self, msg):
        self.last_check = datetime.now()
        if self.info is not None:
            self._set("available")
            return
        self._set("error" if self._manual else "idle", msg)
        if self._manual:
            self.ctx.toast(msg, "warning")

    def _checked(self, info):
        self.last_check = datetime.now()
        if info is None:
            self.info = None
            self._set("latest")
            if self._manual:
                self.ctx.toast("최신 버전을 쓰고 있어요", "success")
            return
        self.info = info
        self._set("available")
        seen = repo.get_setting(self.conn, "update_notified", "")
        if seen != info.version or self._manual:
            repo.set_setting(self.conn, "update_notified", info.version)
            if not (self.auto and self.installed):
                self.ctx.toast(f"새 버전 {info.version}이 나왔어요. 설정에서 업데이트할 수 있어요.", "info", 4000)
        if self.auto and self.installed:
            self.download()

    # ---------- 받기 ----------
    def download(self):
        if self.info is None or self._dl is not None:
            return
        self.progress = 0.0
        self._set("downloading")
        th = _DownloadThread(self.info)
        th.progress.connect(self._on_progress)
        th.done.connect(self._downloaded)
        th.failed.connect(self._download_failed)
        th.finished.connect(lambda: setattr(self, "_dl", None))
        self._dl = keep_alive(th)
        th.start()

    def _on_progress(self, f):
        self.progress = f
        self.changed.emit()

    def _download_failed(self, msg):
        self._install_after = False
        self._set("available", msg)
        if self._manual:
            self.ctx.toast(msg, "warning")

    def _downloaded(self, path):
        self.path = path
        updater.cleanup(keep=path)
        self._set("ready")
        if self._install_after:
            self._install_after = False
            self.install_now()
        elif self.auto:
            self._safe_timer.start()
            self._try_auto_install()

    # ---------- 설치 ----------
    def touch(self):
        """프로그램 화면을 쓰는 중임을 알린다 (Windows가 아닐 때의 유휴 판단용)."""
        self._last_touch = time.monotonic()

    def user_away(self):
        """아무도 컴퓨터를 쓰고 있지 않은지. 쓰는 중에 갑자기 꺼지지 않도록."""
        idle = idle_seconds()
        if idle is None:
            idle = time.monotonic() - self._last_touch
        return idle >= IDLE_MIN * 60

    def is_safe_now(self):
        """종을 울리는 중이 아니고, 다음 종까지 충분히 남았는지."""
        if self.ctx.player.is_playing():
            return False
        win = getattr(self.ctx, "window", None)
        if win is not None and getattr(win, "_fullscreen", None) is not None:
            try:
                if win._fullscreen.isVisible():
                    return False     # 교실 화면에 시계를 띄워 둔 동안은 미룬다
            except RuntimeError:
                pass
        ev = self.ctx.scheduler.next_event
        if ev is None:
            return True
        return (ev.run_at - datetime.now()).total_seconds() >= SAFE_GAP_MIN * 60

    def _try_auto_install(self):
        if self.state != "ready" or not self.auto or self._installing:
            return
        if not self.is_safe_now():
            return
        if not self.user_away():
            if not self._nagged:
                self._nagged = True
                self.ctx.toast(f"새 버전 {self.info.version}이 준비됐어요. 컴퓨터를 쓰지 않을 때 설치할게요.", "info",
                               8000, "지금 설치", self.install_now)
            return
        self._safe_timer.stop()
        self.ctx.toast(f"{self.info.version} 버전으로 업데이트할게요. 잠깐 꺼졌다 다시 켜져요.", "info", 5000)
        self._installing = True
        QTimer.singleShot(5000, self._do_install)

    def install_now(self):
        """설정 화면의 '업데이트' 버튼."""
        if not self.installed:
            self.open_page()
            return
        if self.state == "available":
            self._install_after = True
            self._manual = True
            self.download()
            return
        if self.state == "ready":
            self._installing = True
            self._do_install(visible=True)

    def _do_install(self, visible=False):
        if not self.path or self.info is None:
            self._installing = False
            return
        repo.set_setting(self.conn, "update_pending_version", self.info.version)
        repo.set_setting(self.conn, "update_pending_notes", self.info.notes[:4000])
        try:
            updater.launch_installer(self.path, visible=visible)
        except Exception as e:
            self._installing = False
            self._set("ready", str(e))
            self.ctx.toast(f"설치를 시작하지 못했어요: {e}", "error")
            return
        self._set("installing")
        QTimer.singleShot(300, self.quit_for_update)

    def open_page(self):
        url = self.info.page_url if self.info else updater.RELEASES_PAGE
        QDesktopServices.openUrl(QUrl(url))

    # ---------- 업데이트 직후 ----------
    def take_whats_new(self):
        """방금 업데이트됐다면 (버전, 노트)를 돌려주고 기록을 지운다."""
        pending = repo.get_setting(self.conn, "update_pending_version", "")
        if not pending:
            return None
        notes = repo.get_setting(self.conn, "update_pending_notes", "")
        repo.set_setting(self.conn, "update_pending_version", "")
        repo.set_setting(self.conn, "update_pending_notes", "")
        if updater.parse_version(pending) == updater.parse_version(APP_VERSION):
            return pending, notes
        return None

    def status_text(self):
        s = self.state
        if not self.installed and s in ("available", "downloading", "ready"):
            return f"새 버전 {self.info.version}이 나왔어요. 설치 파일을 받아 설치해 주세요."
        if s == "checking":
            return "확인하고 있어요"
        if s == "available":
            return self.message or f"새 버전 {self.info.version}이 나왔어요"
        if s == "downloading":
            return f"{self.info.version} 받는 중 {int(self.progress * 100)}%"
        if s == "ready":
            if self.message:
                return self.message
            if self.auto:
                return f"{self.info.version} 설치 준비 완료 · 다음 종까지 {SAFE_GAP_MIN}분 넘게 남으면 설치해요"
            return f"{self.info.version} 설치 준비 완료"
        if s == "installing":
            return "설치를 시작했어요"
        if s == "latest":
            t = self.last_check.strftime("%H:%M") if self.last_check else ""
            return f"최신 버전이에요 · {t}에 확인"
        if s == "error":
            return self.message
        return "아직 확인하지 않았어요"
