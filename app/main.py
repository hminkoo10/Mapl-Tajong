import sys
from pathlib import Path
from PyQt6.QtWidgets import QApplication

from app.data.db import connect, init_schema
from app.core.bootstrap import seed_if_empty
from app.core.paths import resource_path
from app.ui.main_window import MainWindow
from PyQt6.QtGui import QFont

def read_schema():
    p = resource_path("app", "data", "schema.sql")
    return p.read_text(encoding="utf-8")

def main():
    conn = connect()
    init_schema(conn, read_schema())
    seed_if_empty(conn)

    app = QApplication(sys.argv)
    font = QFont("Segoe UI")
    font.setPointSize(10)
    app.setFont(font)
    win = MainWindow(conn, app)
    win.resize(1100, 650)
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
