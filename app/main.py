import sys
from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QFont

from app.data.db import connect, init_schema
from app.core.bootstrap import seed_if_empty
from app.core.paths import resource_path, app_data_dir, APP_NAME
from app.core.single_instance import acquire
from app.ui.main_window import MainWindow

def read_schema():
    p = resource_path("app", "data", "schema.sql")
    return p.read_text(encoding="utf-8")

def main():
    app = QApplication(sys.argv)

    ok = acquire(APP_NAME, app_data_dir())
    if not ok:
        QMessageBox.information(None, "알림", "이미 프로그램이 실행 중입니다.")
        return

    font = QFont("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)

    conn = connect()
    init_schema(conn, read_schema())
    seed_if_empty(conn)

    win = MainWindow(conn, app)
    win.resize(1100, 650)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
