"""Qt 팝업의 네이티브 충돌은 별도 프로세스에서 확인한다."""
import ctypes
import gc
import sqlite3
import sys
import traceback
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6 import sip
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QSignalSpy, QTest
from PyQt6.QtWidgets import QApplication

from app.data.db import init_schema
from app.ui.context import AppContext
from app.ui.pages.schedules import SchedulesPage


def run():
    if sys.platform == "win32":
        ctypes.windll.kernel32.SetErrorMode(0x0001 | 0x0002)
    app = QApplication.instance() or QApplication([])
    errors = []

    def exception_hook(*args):
        errors.append("".join(traceback.format_exception(*args)))
    sys.excepthook = exception_hook

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn, (Path(__file__).resolve().parents[1] / "app/data/schema.sql").read_text(encoding="utf-8"))
    conn.execute("INSERT INTO schedule_sets(name) VALUES('주말')")
    conn.commit()
    scheduler = SimpleNamespace(invalidate=Mock(), recompute_next=Mock())
    ctx = AppContext(conn, None, scheduler)
    page = SchedulesPage(ctx)
    page.resize(1000, 700)
    page.show()
    QTest.qWait(30)
    combo = page.set_combo
    changes = QSignalSpy(combo.currentIndexChanged)
    closed = QSignalSpy(app.lastWindowClosed)

    for mode in ("outside", "escape", "same", "other", "hide") * 2:
        QTest.qWait(260)
        combo.showPopup()
        QTest.qWait(200)
        assert combo._popup is not None, mode
        before = len(changes)
        index = combo.currentIndex()
        # 팝업 참조를 따로 보관하면 원본의 조기 삭제 충돌이 가려진다
        if mode == "outside":
            QTest.mouseClick(page.windowHandle(), Qt.MouseButton.LeftButton, pos=QPoint(10, 650))
        elif mode == "escape":
            QTest.keyClick(combo._popup, Qt.Key.Key_Escape)
        elif mode == "same":
            QTest.keyClick(combo._popup, Qt.Key.Key_Return)
        elif mode == "other":
            QTest.keyClick(combo._popup, Qt.Key.Key_Down if index == 0 else Qt.Key.Key_Up)
            QTest.keyClick(combo._popup, Qt.Key.Key_Return)
        else:
            combo.hidePopup()
        QTest.qWait(240)
        gc.collect()
        assert combo._popup is None, mode
        assert combo.currentIndex() == (1 - index if mode == "other" else index), mode
        assert len(changes) == before + (mode == "other"), mode
        assert not closed, "팝업만 닫아도 앱 종료 신호가 발생함"
        assert not errors, errors

    combo.setCurrentIndex(-1)
    combo.showPopup()
    QTest.qWait(30)
    QTest.keyClick(combo._popup, Qt.Key.Key_Escape)
    QTest.qWait(260)
    assert combo.currentIndex() == -1
    combo.showPopup()
    popup = combo._popup
    page.deleteLater()
    QTest.qWait(30)
    assert sip.isdeleted(popup)
    assert not errors, errors
    conn.close()


if __name__ == "__main__":
    run()
