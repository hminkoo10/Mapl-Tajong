"""새 버전으로 다시 켜기.

새 버전은 마고에듀 통합 클라우드가 옆 폴더에 받아 둔다. 타종은 알맞은 때 종료 코드 75 로 끝나기만 하면 되고,
그러면 통합 클라우드가 새 버전으로 바로 다시 켠다.
알맞은 때: 소리가 나지 않고, 전체화면 시계를 띄워 두지 않았고, 임시 작업창이 없고, 다음 종까지 10분 넘게 남았고,
타종 창을 보고 쓰는 중이 아닐 때.
"""
import sys
from datetime import datetime

from PyQt6.QtCore import QFileSystemWatcher, QObject, QTimer
from PyQt6.QtWidgets import QApplication, QDialog

from app.core import magoedu_cloud as cloud
from app.core.version import APP_VERSION

CHECK_EVERY_MS = 60 * 1000
SAFE_GAP_MIN = 10  # 다음 종까지 이 시간보다 많이 남았을 때만 다시 켠다
ACTIVE_IDLE_MIN = 2  # 타종 창이 앞에 있으면 이 시간 동안 손대지 않았을 때만 다시 켠다


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


def is_safe_to_restart(now, next_event, ringing=False, modal_open=False):
    """종이 울리지 않고, 임시 작업창이 없으면 다시 켜도 된다."""
    if ringing or modal_open:
        return False
    if next_event is None:
        return True
    return (next_event.run_at - now).total_seconds() > SAFE_GAP_MIN * 60


class RestartWatch(QObject):
    def __init__(self, ctx, restart, app_id="tajong"):
        super().__init__()
        self.ctx = ctx
        self.restart = restart
        self.app_id = app_id
        self.version = None
        self._restarting = False
        self._installed_dir = cloud.installed_version_file(app_id).parent
        self._watcher = QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self.check)
        self._watch_installed_dir()
        self._restart_timer = QTimer(self)
        self._restart_timer.setSingleShot(True)
        self._restart_timer.timeout.connect(self._do_restart)
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_EVERY_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()
        QTimer.singleShot(0, self.check)

    def _watch_installed_dir(self):
        # installed.json 은 이름 바꾸기로 교체되므로 파일 대신 부모 폴더를 지켜본다.
        path = str(self._installed_dir)
        if self._installed_dir.is_dir() and path not in self._watcher.directories():
            self._watcher.addPath(path)

    def is_safe_now(self, now=None):
        """종을 울리지 않고, 임시 작업창이 없으며, 다음 종까지 충분한지."""
        now = now or datetime.now()
        win = getattr(self.ctx, "window", None)
        if win is not None and getattr(win, "_fullscreen", None) is not None:
            try:
                if win._fullscreen.isVisible():
                    return False     # 교실 화면에 시계를 띄워 둔 동안은 미룬다
            except RuntimeError:
                pass
        app = QApplication.instance()
        modal_open = isinstance(app, QApplication) and (
            app.activeModalWidget() is not None
            or any(w.isVisible() and (isinstance(w, QDialog) or w.isWindowModified())
                   for w in app.topLevelWidgets()))
        if isinstance(app, QApplication) and app.activeWindow() is not None:
            idle = idle_seconds()
            if idle is not None and idle < ACTIVE_IDLE_MIN * 60:
                return False     # 타종 창을 쓰는 중에는 갑자기 꺼지지 않게 미룬다
        sync = getattr(self.ctx, "sync", None)
        ringing = self.ctx.player.is_playing() or bool(sync is not None and sync._pending)
        return is_safe_to_restart(now, self.ctx.scheduler.next_event,
                                  ringing=ringing, modal_open=modal_open)

    def check(self):
        self._watch_installed_dir()
        if self._restarting:
            return
        v = cloud.newer_version_installed(self.app_id, APP_VERSION)
        if not v:
            return
        self.version = v
        if not self.is_safe_now():
            return
        self._restarting = True
        self.ctx.toast(f"{v} 버전으로 다시 켤게요. 잠깐 꺼졌다 켜져요.", "info", 5000,
                       "지금 다시 켜기", self.restart_now)
        self._restart_timer.start(5000)

    def restart_now(self):
        """알림의 '지금 다시 켜기'."""
        self._restart_timer.stop()
        self._do_restart()

    def _do_restart(self):
        if not cloud.newer_version_installed(self.app_id, APP_VERSION) or not self.is_safe_now():
            self._restarting = False
            return
        self._restarting = True
        if self.restart() is False:
            self._restarting = False
