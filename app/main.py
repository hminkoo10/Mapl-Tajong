import os
import sys

# 종료 요청 실행은 화면·재생 모듈도 불러오지 않는다 (창·잠금·허가증 없이 바로 전달).
if __name__ == "__main__" and "--quit" in sys.argv:
    from app.core.paths import APP_NAME
    from app.core.single_instance import request_quit
    request_quit(APP_NAME)
    sys.exit(0)

os.environ.setdefault("SDL_NO_SIGNAL_HANDLERS", "1")  # pygame(SDL)이 종료 신호를 가로채지 않도록

# windowed(.exe)로 실행하면 stdout/stderr가 없어 라이브러리 출력에서 오류가 날 수 있다.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from PyQt6.QtCore import Qt, QTimer, QUrl
from PyQt6.QtGui import QDesktopServices, QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.core import cloud_sync
from app.core import magoedu_cloud as cloud
from app.core import paths
from app.core.paths import APP_NAME, app_data_dir, asset_path, resource_path, ui_cache_dir
from app.core.single_instance import acquire, listen, listen_quit, request_quit, show_running
from app.core.startup import legacy_app_running, remove_legacy_autostart
from app.core.watchdog import HangWatch, enable_crash_log
from app.ui.main_window import MainWindow
from app.ui.theme import app_font, build_stylesheet, load_fonts, reset_font_cache

APP_ID = "tajong"


def read_schema():
    p = resource_path("app", "data", "schema.sql")
    return p.read_text(encoding="utf-8")


def _install_excepthook():
    """버튼 하나에서 오류가 나도 프로그램 전체가 꺼지지 않도록 기록만 남기고 계속 실행한다."""
    import traceback
    from datetime import datetime

    def hook(exc_type, exc, tb):
        try:
            with open(app_data_dir() / "error.log", "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n")
                f.write("".join(traceback.format_exception(exc_type, exc, tb)))
        except Exception:
            pass

    sys.excepthook = hook


def _set_app_id():
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Mapl.Tajong.2")
        except Exception:
            pass


def _cloud_installed():
    """통합 클라우드가 설치되어 있는지 (magoedu:// 주소를 열 수 있음)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magoedu"))
        return True
    except OSError:
        return False


def _without_cloud():
    """통합 클라우드에서 켜지 않았을 때. 통합 클라우드가 있으면 조용히 넘겨서 켜 달라고 하고 끝낸다."""
    launched = bool(os.environ.get("MAGOEDU_TICKET"))  # 통합 클라우드가 켰는데 확인이 안 됨 → 다시 넘기지 않음
    if not launched and _cloud_installed() and cloud.open_cloud(APP_ID):
        return
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    if launched:
        text = cloud.REASON
    else:
        text = ("통합 클라우드에 로그인한 뒤 ‘마고 타종’을 열어요.")
    box = QMessageBox(QMessageBox.Icon.Information, "마고에듀 통합 클라우드", text)
    get = box.addButton("통합 클라우드 받기", QMessageBox.ButtonRole.AcceptRole)
    box.addButton("닫기", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    if box.clickedButton() is get:
        QDesktopServices.openUrl(QUrl(cloud.DEFAULT_SERVER))


def _ask_first_sync():
    from app.ui.dialogs import choose_first_sync
    return choose_first_sync()


def main():
    if "--quit" in sys.argv:   # 허가증·잠금·창 없이 요청만 전달. 켜진 게 없어도 조용히 끝낸다
        request_quit(APP_NAME)
        return
    if show_running(APP_NAME):   # 이미 켜져 있으면 그 창을 열고 끝 (허가증을 다시 확인하지 않음)
        return
    session = cloud.check(APP_ID)
    if session is None:
        _without_cloud()
        return
    paths.configure(session.data_dir, session.local_dir)

    _set_app_id()
    _install_excepthook()
    enable_crash_log(app_data_dir())
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    ok = acquire(APP_NAME, app_data_dir())
    if not ok:
        QMessageBox.information(None, "알림", "작업 표시줄 오른쪽의 마고 타종 아이콘을 눌러요.")
        return

    load_fonts(asset_path("fonts"))
    app.setFont(app_font())
    reset_font_cache()
    ico = asset_path("ui", "app.ico")
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    app.setStyleSheet(build_stylesheet(ui_cache_dir()))

    if not session.dev:
        # 예전에 따로 설치한 프로그램의 자동 실행은 지운다 (이제 통합 클라우드의 '함께 켜기')
        try:
            remove_legacy_autostart()
        except Exception:
            pass
    if legacy_app_running():
        from app.ui.dialogs import notify
        notify(None, "예전 마고 타종이 켜져 있어요",
               "예전 마고 타종을 종료해요. 두 프로그램이 켜져 있으면 종이 두 번 울려요.")

    conn, prefer_local = cloud_sync.open_database(read_schema(), ask_choice=_ask_first_sync)

    win = MainWindow(conn, app, session, prefer_local)
    win.resize(1240, 800)
    win.show()
    server = listen(APP_NAME, lambda: win._tray_show())  # noqa: F841 (끝날 때까지 들고 있음)
    quit_server = listen_quit(APP_NAME, lambda: win._shutdown(0))  # noqa: F841 (저장·flush 후 정상 종료)

    watch = HangWatch(app_data_dir())
    beat = QTimer()
    beat.setInterval(1000)
    beat.timeout.connect(watch.pulse)
    beat.start()
    watch.start()
    code = app.exec()
    watch.stop()
    sys.exit(code)


if __name__ == "__main__":
    main()
