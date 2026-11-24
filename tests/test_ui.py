import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
from unittest.mock import Mock

from PyQt6.QtCore import QPoint, QRectF, Qt
from PyQt6.QtGui import QFont, QFontMetricsF
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QStackedWidget, QVBoxLayout, QWidget

from app.core import ffmpeg, paths, sound_files
from app.data.db import init_schema
from app.ui.context import AppContext
from app.ui.pages.schedules import SchedulesPage, _SelectionBar
from app.ui.pages.sounds import SoundsPage
from app.ui.select import Select
from app.ui.theme import app_font, build_stylesheet, font, load_fonts, reset_font_cache
from app.ui.widgets import ToastManager
from app.ui.workers import ProgressThread, keep_alive


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

    def _sounds_page(self, rows):
        tmp = Path(tempfile.mkdtemp(prefix="tajong_ui_mp3_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        paths.configure(tmp / "sync", tmp / "local")
        conn = sqlite3.connect(":memory:")
        self.addCleanup(conn.close)
        conn.row_factory = sqlite3.Row
        init_schema(conn, (ROOT / "app/data/schema.sql").read_text(encoding="utf-8"))
        for sid, name, file_name in rows:
            shutil.copy2(ROOT / "app/assets/sounds/bell1.wav", paths.sounds_dir() / file_name)
            conn.execute("INSERT INTO sounds(id, name, file_name) VALUES(?, ?, ?)", (sid, name, file_name))
        conn.commit()
        ctx = AppContext(conn, Mock(is_playing=Mock(return_value=False)),
                         SimpleNamespace(invalidate=Mock(), recompute_next=Mock()))
        toasts = []
        ctx.toast = lambda text, kind="info", *a, **k: toasts.append((text, kind))
        page = SoundsPage(ctx)
        QVBoxLayout(self.host).addWidget(page)
        QTest.qWait(30)
        return tmp, page, toasts

    def test_save_selected_sound_as_mp3(self):
        tmp, page, toasts = self._sounds_page([(1, "1교시 종", "bell1.wav"), (2, "쉬는 시간", "bell2.wav")])
        page.table.select_ids([2])
        QTest.qWait(30)
        self.assertTrue(page.btn_mp3.isEnabled())
        out = tmp / "받은 파일" / "쉬는 시간"           # 확장자를 지워도 .mp3 로 저장
        out.parent.mkdir()
        with mock.patch("app.ui.pages.sounds.QFileDialog.getSaveFileName",
                        return_value=(str(out), "MP3 (*.mp3)")) as dlg:
            QTest.mouseClick(page.btn_mp3, Qt.MouseButton.LeftButton)
        self.assertTrue(dlg.call_args.args[2].endswith("쉬는 시간.mp3"))
        self.assertFalse(page.btn_mp3.isEnabled())
        for _ in range(500):
            if page.btn_mp3.isEnabled():
                break
            QTest.qWait(20)
        self.assertEqual(toasts, [("MP3로 저장했어요", "success")])   # 금방 끝나면 막대 없이 끝났다는 안내만
        self.assertFalse(page.mp3_strip.isVisible())
        saved = out.with_name("쉬는 시간.mp3")
        self.assertEqual(saved.read_bytes()[:3], b"ID3")
        self.assertEqual(sorted(p.name for p in out.parent.iterdir()), ["쉬는 시간.mp3"])
        self.render("sounds-mp3")

    def test_sound_buttons_fit_one_row_in_smallest_window(self):
        _, page, _ = self._sounds_page([(1, "종", "bell1.wav")])
        stack = QStackedWidget(self.host)                 # 메인 창처럼 화면 전환 틀에 넣는다 (쪽의 최소 너비를 무시하고 맞춤)
        stack.setStyleSheet(build_stylesheet(paths.ui_cache_dir()))   # 앱과 같은 스타일 (Button 의 min-width: 0 포함)
        stack.addWidget(page)
        stack.setGeometry(0, 0, 1060 - 220, 700)          # 가장 작은 창(1060)에서 왼쪽 메뉴(220)를 뺀 너비
        stack.show()
        QTest.qWait(50)
        self.assertEqual(page.width(), 840)
        row = [page.btn_yt, page.btn_add, page.btn_play, page.btn_stop, page.btn_editor, page.btn_info,
               page.btn_mp3, page.btn_del]
        tops = {b.mapTo(page, QPoint()).y() for b in row}
        self.assertEqual(len(tops), 1)                    # 모두 한 줄
        lefts = [b.mapTo(page, QPoint()).x() for b in row]
        self.assertEqual(lefts, sorted(lefts))
        self.assertEqual(row.index(page.btn_mp3), row.index(page.btn_info) + 1)
        for a, b in zip(row, row[1:]):
            self.assertLessEqual(a.mapTo(page, QPoint()).x() + a.width(), b.mapTo(page, QPoint()).x())
        self.assertLessEqual(page.btn_del.mapTo(page, QPoint()).x() + page.btn_del.width(), page.width() - 28)
        for b in row:                                     # 글자 양옆 여백은 12px 넘게 남는다
            self.assertGreaterEqual(b.width(), b.sizeHint().width() - 8, b.text())
        self.assertEqual(page.btn_stop.width(), page.btn_stop.sizeHint().width())
        self.render("sounds-row-1060")

    def _long_sound(self, path, seconds=600):
        r = ffmpeg._run(["-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=44100",
                         "-ac", "2", "-c:a", "flac", str(path)], timeout=60, capture_stdout=False)
        self.assertEqual(r.returncode, 0)
        return path

    def _wait_long(self, condition, seconds=8):
        for _ in range(int(seconds * 50)):
            if condition():
                return
            QTest.qWait(20)
        self.assertTrue(condition())

    @unittest.skipUnless(ffmpeg.available(), "ffmpeg 없음")
    def _click_row(self, page, sound_id):
        t = page.table
        t.selectRow(next(r for r in range(t.rowCount()) if t.row_id(r) == sound_id))
        QTest.qWait(30)

    def test_long_mp3_save_shows_progress_and_can_be_cancelled(self):
        tmp, page, toasts = self._sounds_page([(1, "긴 노래", "long.flac"), (2, "종", "bell1.wav")])
        self._long_sound(paths.sounds_dir() / "long.flac")
        self._click_row(page, 1)
        out = tmp / "받은 파일"
        out.mkdir()
        with mock.patch("app.ui.pages.sounds.QFileDialog.getSaveFileName",
                        return_value=(str(out / "긴 노래.mp3"), "MP3 (*.mp3)")):
            QTest.mouseClick(page.btn_mp3, Qt.MouseButton.LeftButton)
        self._wait_long(lambda: page.mp3_strip.isVisible() and page.mp3_bar.value() > 0)
        self.assertRegex(page.mp3_label.text(), r"^‘긴 노래’ MP3로 저장하고 있어요 \d+%$")
        self.assertTrue(page.btn_mp3_cancel.isEnabled())

        # 저장하는 동안: 한 번에 하나만 저장하고, 읽고 있는 그 종소리는 고치거나 지울 수 없다 (듣기·이름은 된다)
        self.assertFalse(page.btn_mp3.isEnabled())
        self.assertFalse(page.btn_del.isEnabled())
        self.assertFalse(page.btn_editor.isEnabled())
        self.assertTrue(page.btn_play.isEnabled())
        self.assertTrue(page.btn_info.isEnabled())
        with mock.patch("app.ui.pages.sounds.confirm") as ask, \
                mock.patch("app.ui.pages.sounds.open_editor_for_sound") as edit, \
                mock.patch("app.ui.pages.sounds.QFileDialog.getSaveFileName") as pick:
            page.on_delete()           # 오른쪽 클릭 메뉴로 불러도 아무 일 없음
            page.on_editor()
            page.on_save_mp3()
        ask.assert_not_called()
        edit.assert_not_called()
        pick.assert_not_called()
        self._click_row(page, 2)       # 다른 종소리는 고치거나 지울 수 있다
        self.assertTrue(page.btn_del.isEnabled())
        self.assertTrue(page.btn_editor.isEnabled())
        self.assertFalse(page.btn_mp3.isEnabled())
        self.render("sounds-mp3-progress")

        QTest.mouseClick(page.btn_mp3_cancel, Qt.MouseButton.LeftButton)
        self.assertEqual(page.mp3_label.text(), "취소하고 있어요")
        self.assertFalse(page.btn_mp3_cancel.isEnabled())
        self._wait_long(lambda: not page.mp3_strip.isVisible())
        self.assertEqual(toasts[-1], ("저장을 취소했어요", "info"))
        self.assertEqual(list(out.iterdir()), [])                 # 반쯤 만든 파일도 지운다
        self.assertTrue(page.btn_mp3.isEnabled())
        self._click_row(page, 1)
        self.assertTrue(page.btn_del.isEnabled())

    @unittest.skipUnless(ffmpeg.available(), "ffmpeg 없음")
    def test_quitting_while_saving_mp3_removes_half_made_file(self):
        tmp = Path(tempfile.mkdtemp(prefix="tajong_ui_quit_"))
        self.addCleanup(shutil.rmtree, tmp, True)
        src = self._long_sound(tmp / "긴 노래.flac")
        out = tmp / "받은 파일"
        out.mkdir()
        th = ProgressThread(sound_files.export_mp3, src, out / "긴 노래.mp3")
        seen = []
        th.progress.connect(seen.append)
        keep_alive(th)
        th.start()
        self._wait_long(lambda: bool(seen))
        QApplication.instance().aboutToQuit.emit()                # 프로그램 끄기
        self.assertTrue(th.isFinished())
        self.assertEqual(list(out.iterdir()), [])

    def test_save_mp3_needs_a_sound(self):
        _, page, _ = self._sounds_page([])
        self.assertFalse(page.btn_mp3.isEnabled())

    def test_save_mp3_cancel(self):
        _, page, toasts = self._sounds_page([(1, "종", "bell1.wav")])
        with mock.patch("app.ui.pages.sounds.QFileDialog.getSaveFileName", return_value=("", "")):
            QTest.mouseClick(page.btn_mp3, Qt.MouseButton.LeftButton)
        self.assertTrue(page.btn_mp3.isEnabled())
        self.assertEqual(toasts, [])


if __name__ == "__main__":
    unittest.main()
