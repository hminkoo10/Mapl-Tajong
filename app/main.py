import os
import sys

os.environ.setdefault("SDL_NO_SIGNAL_HANDLERS", "1")  # pygame(SDL)이 종료 신호를 가로채지 않도록

# windowed(.exe)로 실행하면 stdout/stderr가 없어 라이브러리 출력에서 오류가 날 수 있다.
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from app.core.bootstrap import seed_if_empty
from app.core.paths import APP_NAME, app_data_dir, asset_path, resource_path, ui_cache_dir
from app.core.single_instance import acquire
from app.core.startup import sync_startup_path
from app.core.watchdog import HangWatch, enable_crash_log
from app.data.db import connect, init_schema
from app.ui.main_window import MainWindow
from app.ui.theme import app_font, build_stylesheet, load_fonts


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


def main():
    _set_app_id()
    _install_excepthook()
    enable_crash_log(app_data_dir())
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)

    ok = acquire(APP_NAME, app_data_dir())
    if not ok:
        QMessageBox.information(None, "알림", "이미 프로그램이 실행 중입니다.\n작업 표시줄 오른쪽 트레이 아이콘을 확인해 주세요.")
        return

    load_fonts(asset_path("fonts"))
    app.setFont(app_font())
    ico = asset_path("ui", "app.ico")
    if ico.exists():
        app.setWindowIcon(QIcon(str(ico)))
    app.setStyleSheet(build_stylesheet(ui_cache_dir()))

    try:
        sync_startup_path()
    except Exception:
        pass

    conn = connect()
    init_schema(conn, read_schema())
    seed_if_empty(conn)

    win = MainWindow(conn, app)
    win.resize(1240, 800)
    win.show()

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
