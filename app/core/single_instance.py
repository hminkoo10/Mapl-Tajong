import hashlib
import os
import sys
from pathlib import Path
from PyQt6.QtCore import QLockFile, QDir

_lock = None

def acquire(app_name, lock_dir):
    global _lock
    p = Path(lock_dir) / f"{app_name}.lock"
    QDir(str(p.parent)).mkpath(".")
    lock = QLockFile(str(p))
    lock.setStaleLockTime(0)

    if not lock.tryLock(0):
        return False

    _lock = lock
    return True


def _server_name(app_name):
    # 계정 폴더를 알기 전에 쓰므로 Windows 사용자 폴더로 구분한다
    home = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return f"{app_name}-{hashlib.sha1(home.encode('utf-8')).hexdigest()[:12]}"


def show_running(app_name):
    """이미 켜진 프로그램이 있으면 창을 열어 달라고 하고 True (두 번째 실행은 조용히 끝냄)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)   # 켜진 쪽이 창을 앞으로 가져올 수 있게
    except Exception:
        pass
    try:
        # 연결 자체가 '창 열기' 요청 (QLocalServer 는 Windows 에서 이름 있는 파이프)
        with open("\\\\.\\pipe\\" + _server_name(app_name), "wb", buffering=0):
            pass
        return True
    except OSError:
        return False


def listen(app_name, on_show):
    """두 번째 실행의 '창 열기' 요청을 받는다. 서버는 프로그램이 끝날 때까지 들고 있어야 함."""
    try:
        from PyQt6.QtNetwork import QLocalServer
    except ImportError:   # 묶음에 QtNetwork 가 없어도 프로그램은 켜져야 한다
        return None
    server = QLocalServer()
    if not server.listen(_server_name(app_name)):
        return None

    def accept():
        while server.hasPendingConnections():
            sock = server.nextPendingConnection()
            sock.disconnected.connect(sock.deleteLater)
            sock.disconnectFromServer()
            on_show()
    server.newConnection.connect(accept)
    return server
