"""새 버전으로 다시 켜기.

새 버전은 마고에듀 통합 클라우드가 옆 폴더에 받아 둔다. 타종은 알맞은 때 종료 코드 75 로 끝나기만 하면 되고,
그러면 통합 클라우드가 새 버전으로 바로 다시 켠다.
알맞은 때: 소리가 나지 않고, 전체화면 시계를 띄워 두지 않았고, 다음 종까지 10분 넘게 남았고,
컴퓨터를 5분 넘게 아무도 쓰지 않음.
"""
import sys
import time
from datetime import datetime

from PyQt6.QtCore import QObject, QTimer

from app.core import magoedu_cloud as cloud
from app.core.version import APP_VERSION

CHECK_EVERY_MS = 60 * 1000
SAFE_GAP_MIN = 10  # 다음 종까지 이 시간 이상 남았을 때만 다시 켠다
IDLE_MIN = 5       # 컴퓨터를 이 시간 이상 아무도 만지지 않았을 때만 다시 켠다


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


class RestartWatch(QObject):
    def __init__(self, ctx, restart, app_id="tajong"):
        super().__init__()
        self.ctx = ctx
        self.restart = restart
        self.app_id = app_id
        self.version = None
        self._nagged = False
        self._restarting = False
        self._started = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(CHECK_EVERY_MS)
        self._timer.timeout.connect(self.check)
        self._timer.start()

    def user_away(self):
        """아무도 컴퓨터를 쓰고 있지 않은지. 쓰는 중에 갑자기 꺼지지 않도록."""
        idle = idle_seconds()
        if idle is None:
            idle = time.monotonic() - self._started
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

    def check(self):
        if self._restarting:
            return
        v = cloud.newer_version_installed(self.app_id, APP_VERSION)
        if not v:
            return
        self.version = v
        if not self.is_safe_now():
            return
        if not self.user_away():
            if not self._nagged:
                self._nagged = True
                self.ctx.toast(f"새 버전 {v}을 받아 두었어요. 컴퓨터를 쓰지 않을 때 다시 켤게요.", "info",
                               8000, "지금 다시 켜기", self.restart_now)
            return
        self._restarting = True
        self.ctx.toast(f"{v} 버전으로 다시 켤게요. 잠깐 꺼졌다 켜져요.", "info", 5000)
        QTimer.singleShot(5000, self._do_restart)

    def restart_now(self):
        """알림의 '지금 다시 켜기'."""
        self._restarting = True
        self.restart()

    def _do_restart(self):
        if not self.is_safe_now():
            self._restarting = False
            return
        self.restart()
