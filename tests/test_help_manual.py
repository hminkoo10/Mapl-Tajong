import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon

from app.core import magoedu_cloud as cloud, paths, youtube
from app.data.db import init_schema
from app.ui.main_window import MainWindow
from app.ui.messages import error_message
from app.ui.pages.settings import SettingsPage
from app.ui.widgets import Button
from app.ui.youtube_dialog import YoutubeDialog


ROOT = Path(__file__).resolve().parents[1]
_app = QApplication.instance() or QApplication([])


class HelpUrlTests(unittest.TestCase):
    def test_uses_cloud_server_and_removes_trailing_slashes(self):
        for server, base in [
            ("https://school.example", "https://school.example"),
            ("https://school.example///", "https://school.example"),
            (" http://localhost:8080/cloud/ ", "http://localhost:8080/cloud"),
            ("http://[::1]:8080/", "http://[::1]:8080"),
        ]:
            with self.subTest(server=server):
                self.assertEqual(cloud.help_url(SimpleNamespace(server=server)), base + "/help/tajong.html")

    def test_missing_session_uses_default_server(self):
        self.assertEqual(cloud.help_url(None), cloud.DEFAULT_SERVER + "/help/tajong.html")

    def test_invalid_servers_use_default_server(self):
        for server in [
            "", "   ", None, 123, "school.example", "//school.example", "https://",
            "https:///path", "file:///C:/help", "javascript:alert(1)", "ftp://school.example",
            "https://school.example:bad", "https://school.example:99999", "http://localhost:0",
            "https://[broken", "https://bad host", "https://bad\nhost", "https://bad\\host",
            "https://user:password@school.example", "https://school.example/?q=1",
            "https://school.example/#help", "https://school.example/?", "https://school.example/#",
            "https://%invalid",
        ]:
            with self.subTest(server=server):
                self.assertEqual(cloud.help_url(SimpleNamespace(server=server)),
                                 cloud.DEFAULT_SERVER + "/help/tajong.html")


class HelpButtonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT / "tests")
        self.addCleanup(self.tmp.cleanup)
        patch = mock.patch.multiple(paths, _sync_dir=Path(self.tmp.name) / "sync",
                                    _local_dir=Path(self.tmp.name) / "local")
        patch.start()
        self.addCleanup(patch.stop)
        self.conn = sqlite3.connect(":memory:")
        self.addCleanup(self.conn.close)
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn, (ROOT / "app/data/schema.sql").read_text(encoding="utf-8"))
        with mock.patch.object(QSystemTrayIcon, "show"):
            self.window = MainWindow(self.conn, _app)
        self.addCleanup(self.close_window)

    def close_window(self):
        self.window.timer.stop()
        self.window.scheduler.stop()
        self.window._really_quit = True
        self.window.close()
        self.window.deleteLater()

    def test_both_help_buttons_open_the_current_session_manual(self):
        footer = {b.text(): b for b in self.window.nav.findChildren(Button)}
        settings = next(p for p in self.window.pages if isinstance(p, SettingsPage))
        for server, expected in [("https://school.example/", "https://school.example/help/tajong.html"),
                                 ("file:///help", cloud.DEFAULT_SERVER + "/help/tajong.html")]:
            self.window.ctx.session = SimpleNamespace(server=server)
            for button in (footer["도움말"], settings.btn_help):
                with self.subTest(server=server, button=button.text()), \
                     mock.patch.object(QDesktopServices, "openUrl", return_value=True) as open_url:
                    button.click()
                    open_url.assert_called_once_with(QUrl(expected))

    def test_settings_manual_still_opens_when_login_server_is_malformed(self):
        self.window.ctx.session = SimpleNamespace(server="https://[broken", user={"username": "teacher"})
        settings = SettingsPage(self.window.ctx)
        self.addCleanup(settings.deleteLater)
        with mock.patch.object(QDesktopServices, "openUrl", return_value=True) as open_url:
            settings.btn_help.click()
        open_url.assert_called_once_with(QUrl(cloud.DEFAULT_SERVER + "/help/tajong.html"))


class ErrorMessageTests(unittest.TestCase):
    def test_action_comes_before_short_single_line_details(self):
        summary = "종소리를 저장하지 못했어요. 파일을 닫고 다시 해 주세요."
        result = error_message(summary, RuntimeError("trace\n" * 80 + "Permission denied"))
        self.assertTrue(result.startswith(summary + "\n\n자세한 내용: "))
        detail = result.split("자세한 내용: ", 1)[1]
        self.assertLessEqual(len(detail), 150)
        self.assertNotIn("\n", detail)
        self.assertTrue(detail.endswith("Permission denied"))

    def test_empty_details_do_not_add_an_empty_section(self):
        self.assertEqual(error_message("다시 해 주세요.", " \n "), "다시 해 주세요.")

    def test_youtube_login_retry_uses_original_error_before_shortening(self):
        dialog = SimpleNamespace(btn_login=mock.Mock(), state_label=mock.Mock(), spinner=mock.Mock())
        retry = mock.Mock()
        with mock.patch("app.ui.youtube_dialog.google_login.is_logged_in", return_value=False):
            YoutubeDialog._set_state(dialog, youtube.BLOCKED_MSG + "x" * 300, error=True,
                                     retry=retry, error_summary="종소리를 받지 못했어요. 로그인 후 다시 받아 주세요.")
        self.assertIs(dialog._retry, retry)
        dialog.btn_login.setVisible.assert_called_once_with(True)
        self.assertIn("자세한 내용: ", dialog.state_label.setText.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
