import sys

try:
    import winreg
except ImportError:  # Windows 이외 환경(개발/테스트)
    winreg = None

APP_NAME = "MaplTajong"
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def is_supported():
    return winreg is not None


def is_startup_enabled():
    if winreg is None:
        return False
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, APP_NAME)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False


def enable_startup():
    if winreg is None:
        return
    exe_path = sys.executable
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, f'"{exe_path}"')
    winreg.CloseKey(key)


def disable_startup():
    if winreg is None:
        return
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE)
        winreg.DeleteValue(key, APP_NAME)
        winreg.CloseKey(key)
    except FileNotFoundError:
        pass


def sync_startup_path():
    """설치 위치가 바뀌었으면(예: 예전 exe → 설치 버전) 자동 실행 경로를 지금 실행 파일로 맞춘다."""
    if winreg is None or not getattr(sys, "frozen", False):
        return
    want = f'"{sys.executable}"'
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE)
    except OSError:
        return
    try:
        cur, _ = winreg.QueryValueEx(key, APP_NAME)
        if str(cur).strip().strip('"').lower() != sys.executable.lower():
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, want)
    except FileNotFoundError:
        pass
    finally:
        winreg.CloseKey(key)
