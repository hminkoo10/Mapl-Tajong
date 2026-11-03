import os
import sqlite3
import subprocess
import sys
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from PyQt6.QtCore import QPoint, QRectF, Qt
from PyQt6.QtGui import QFont, QFontMetricsF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QVBoxLayout, QWidget

from app.data.db import init_schema
from app.ui.context import AppContext
from app.ui.pages.schedules import SchedulesPage, _SelectionBar
from app.ui.select import Select
from app.ui.theme import app_font, font, load_fonts, reset_font_cache
from app.ui.widgets import ToastManager


ROOT = Path(__file__).resolve().parents[1]
_app = QApplication.instance() or QApplication([])
load_fonts(ROOT / "app/assets/fonts")
_app.setFont(app_font())
reset_font_cache()


class UiRegressionTests(unittest.TestCase):
    def setUp(self):
        self.host = QWidget()
        self.host.resize(1100, 700)
        self.host.show()
        self.errors = []
        self.old_hook = sys.excepthook
        sys.excepthook = lambda *args: self.errors.append("".join(traceback.format_exception(*args)))

    def tearDown(self):
        self.host.close()
        self.host.deleteLater()
        QTest.qWait(30)
        sys.excepthook = self.old_hook
        self.assertEqual(self.errors, [])

    def render(self, name):
        pixmap = self.host.grab()
        self.assertFalse(pixmap.isNull())
        capture = os.environ.get("TAJONG_UI_CAPTURE_DIR")
        if capture:
            self.assertTrue(pixmap.save(str(Path(capture) / f"{name}.png")))

    def wait_for(self, condition):
        for _ in range(100):
            if condition():
                return
            QTest.qWait(20)
        self.assertTrue(condition())

    def test_select_popup_close_paths_do_not_crash(self):
        result = subprocess.run([sys.executable, "-X", "faulthandler", "-m", "tests.ui_popup_scenario"],
                                cwd=ROOT, env={**os.environ, "QT_QPA_PLATFORM": "offscreen"},
                                capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_old_popup_does_not_clear_new_popup(self):
        combo = Select(self.host)
        combo.addItems(["평일", "주말"])
        combo.showPopup()
        old = combo._popup
        old.hide()
        QTest.qWait(260)
        combo.showPopup()
        current = combo._popup
        self.assertIsNotNone(current)
        combo._popup_closed(old)
        self.assertIs(combo._popup, current)
        combo.hidePopup()
        QTest.qWait(260)

    def test_schedule_enable_disable_toasts_clear_selection_bar(self):
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        init_schema(conn, (ROOT / "app/data/schema.sql").read_text(encoding="utf-8"))
        conn.execute("INSERT INTO sounds(id, name, file_name) VALUES(1, '종', 'bell.wav')")
        conn.execute("""INSERT INTO schedules(id, set_id, name, weekday_mask, time_hhmm, sound_id, enabled)
                        VALUES(1, 1, '1교시', 127, '09:00', 1, 0)""")
        conn.commit()
        ctx = AppContext(conn, None, SimpleNamespace(invalidate=Mock(), recompute_next=Mock()))
        manager = ctx.toasts = ToastManager(self.host)
        page = SchedulesPage(ctx)
        layout = QVBoxLayout(self.host)
        layout.addWidget(page)
        QTest.qWait(30)
        page.table.selectRow(0)
        QTest.qWait(250)
        self.assertTrue(page.selbar.isVisible())
        for button, enabled in ((page.selbar.btn_on, 1), (page.selbar.btn_off, 0)):
            QTest.mouseClick(button, Qt.MouseButton.LeftButton)
            QTest.qWait(300)
            self.assertEqual(conn.execute("SELECT enabled FROM schedules WHERE id=1").fetchone()[0], enabled)
            bar_top = page.selbar.mapTo(self.host, QPoint()).y()
            for toast in manager.toasts:
                self.assertLess(toast.geometry().bottom(), bar_top)
            self.render(f"schedule-{'on' if enabled else 'off'}")

    def test_toasts_clear_bar_during_show_hide_and_resize(self):
        page = QWidget(self.host)
        page.setGeometry(80, 40, 1000, 620)
        page.show()
        bar = _SelectionBar(page)
        bar.label.setText("1개 선택")
        manager = ToastManager(self.host)
        toast = manager.show("일정 1개를 켰어요", "success", 10000)
        QTest.qWait(300)
        normal_bottom = toast.geometry().bottom()
        bar.set_open(True)
        for _ in range(15):
            QTest.qWait(20)
            self.assertLess(toast.geometry().bottom(), bar.mapTo(self.host, QPoint()).y())
        second = manager.show("일정 1개를 껐어요", "success", 10000)
        for _ in range(15):
            QTest.qWait(20)
            self.assertLess(second.geometry().bottom(), bar.mapTo(self.host, QPoint()).y())
        page.resize(980, 570)
        QTest.qWait(30)
        self.assertLess(second.geometry().bottom(), bar.mapTo(self.host, QPoint()).y())
        self.assertLess(toast.geometry().bottom(), second.geometry().top())
        self.render("toast-stacked")
        bar.set_open(False)
        self.wait_for(lambda: not bar.isVisible())
        self.assertEqual(second.geometry().bottom(), normal_bottom)
        bar.set_open(True)
        QTest.qWait(250)
        page.hide()
        QTest.qWait(30)
        self.assertEqual(second.geometry().bottom(), normal_bottom)

    def test_toast_short_text_is_not_clipped(self):
        text = "일정 1개를 켰어요"
        manager = ToastManager(self.host)
        toast = manager.show(text, "success", 10000)
        QTest.qWait(300)
        metrics = QFontMetricsF(font(14, QFont.Weight.Medium))
        # 테두리 4px, 아이콘 쪽 46px, 오른쪽 여백 18px를 빼도 글자가 모두 들어간다
        self.assertGreaterEqual(toast.width() - 68, metrics.horizontalAdvance(text))
        self.render("toast-short")

    def test_toast_timer_stops_when_host_is_deleted(self):
        child = QWidget(self.host)
        child.resize(500, 300)
        child.show()
        manager = ToastManager(child)
        manager.show("일정 1개를 켰어요", "success", 50)
        child.deleteLater()
        QTest.qWait(100)
        self.assertEqual(self.errors, [])

    def test_toast_action_and_timeout_still_dismiss(self):
        manager = ToastManager(self.host)
        action = Mock()
        toast = manager.show("일정 1개를 켰어요", "success", 10000, "되돌리기", action)
        QTest.qWait(300)
        QTest.mouseClick(toast, Qt.MouseButton.LeftButton, pos=toast._action_rect().center().toPoint())
        action.assert_called_once_with()
        self.wait_for(lambda: toast not in manager.toasts)
        timed = manager.show("저장했어요", "success", 40)
        self.wait_for(lambda: timed not in manager.toasts)

    def test_toast_wraps_with_action_and_tracks_host_width(self):
        manager = ToastManager(self.host)
        for i, (text, action) in enumerate((("일정 1개를 켰어요", None),
                                           ("가나다라마바사" * 30, None),
                                           ("클라우드 시간표를 맞췄어요. " * 12, "되돌리기"),
                                           ("첫 줄\n둘째 줄\n셋째 줄", "확인"))):
            with self.subTest(text=text[:20], action=action):
                toast = manager.show(text, "success", 10000, action, lambda: None)
                QTest.qWait(300)
                for width in (1100, 380, 900):
                    self.host.resize(width, 900)
                    QTest.qWait(30)
                    self.assertTrue(self.host.rect().contains(toast.geometry()))
                    rect = toast._text_rect()
                    metrics = QFontMetricsF(font(14, QFont.Weight.Medium))
                    bounds = metrics.boundingRect(QRectF(0, 0, rect.width(), 10000),
                                                  Qt.TextFlag.TextWrapAnywhere, text)
                    self.assertLessEqual(bounds.width(), rect.width())
                    self.assertLessEqual(bounds.height(), rect.height())
                    if action:
                        self.assertLess(rect.right(), toast._action_rect().left())
                        self.assertGreaterEqual(toast._action_rect().width(),
                                                QFontMetricsF(font(14, QFont.Weight.Bold)).horizontalAdvance(action))
                    self.render(f"toast-wrap-{i}-{width}")
                manager._remove(toast)


if __name__ == "__main__":
    unittest.main()
