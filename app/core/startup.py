"""예전에 따로 설치해 쓰던 프로그램의 흔적 정리.

컴퓨터를 켜면 자동으로 실행하는 일은 이제 마고에듀 통합 클라우드의 '함께 켜기'가 한다.
"""
from PyQt6.QtCore import QLockFile

from app.core.paths import APP_NAME, legacy_data_dir

try:
    import winreg
except ImportError:  # Windows 이외 환경(개발/테스트)
    winreg = None

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def remove_legacy_autostart():
    """예전 설치 파일이 등록한 자동 실행(HKCU\\...\\Run 의 MaplTajong)을 지운다. 지웠으면 True."""
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
    except OSError:
        return False
    try:
        winreg.DeleteValue(key, APP_NAME)
        return True
    except OSError:
        return False
    finally:
        winreg.CloseKey(key)


def legacy_app_running():
    """예전에 따로 설치한 프로그램이 지금 켜져 있는지 (그 프로그램의 잠금 파일이 잡혀 있음)."""
    p = legacy_data_dir() / f"{APP_NAME}.lock"
    if not p.exists():
        return False
    lock = QLockFile(str(p))
    if lock.tryLock(0):
        lock.unlock()
        return False
    return lock.error() == QLockFile.LockError.LockFailedError
