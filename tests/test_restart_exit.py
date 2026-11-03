import os
import sqlite3
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from app.core import magoedu_cloud as cloud


with mock.patch.dict(sys.modules, {"pygame": mock.Mock()}):
    from app.ui.main_window import MainWindow

ROOT = Path(__file__).resolve().parents[1]


class RestartExitTests(unittest.TestCase):
    def make_window(self):
        return SimpleNamespace(
            scheduler=mock.Mock(), player=mock.Mock(), conn=mock.Mock(), sync=mock.Mock(),
            tray=mock.Mock(), _fullscreen=None, _really_quit=False, app=mock.Mock(),
            restart_watch=SimpleNamespace(is_safe_now=lambda: True),
        )

    def test_restart_for_update_preserves_shutdown_result_and_code(self):
        window = SimpleNamespace(_shutdown=mock.Mock(return_value=False))
        self.assertFalse(MainWindow.restart_for_update(window))
        window._shutdown.assert_called_once_with(cloud.RESTART_EXIT_CODE)

    def test_shutdown_saves_state_before_stopping_and_exiting(self):
        window = self.make_window()
        order = mock.Mock()
        for name in ("conn", "sync", "scheduler", "player", "tray", "app"):
            order.attach_mock(getattr(window, name), name)
        self.assertTrue(MainWindow._shutdown(window, cloud.RESTART_EXIT_CODE))
        self.assertEqual(order.mock_calls, [
            mock.call.conn.commit(), mock.call.sync.flush(), mock.call.scheduler.stop(),
            mock.call.player.stop(), mock.call.tray.hide(), mock.call.app.exit(75),
        ])
        self.assertTrue(window._really_quit)

    def test_uncommitted_state_is_persisted_before_exit(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            db = Path(tmp) / "state.db"
            conn = sqlite3.connect(db)
            self.addCleanup(conn.close)
            conn.execute("CREATE TABLE settings (value TEXT)")
            conn.execute("INSERT INTO settings VALUES ('saved')")
            window = self.make_window()
            window.conn = conn

            def check_saved(code):
                other = sqlite3.connect(db)
                try:
                    self.assertEqual(other.execute("SELECT value FROM settings").fetchone(), ("saved",))
                    self.assertEqual(code, 75)
                finally:
                    other.close()

            window.app.exit.side_effect = check_saved
            MainWindow._shutdown(window, 75)
            window.app.exit.assert_called_once_with(75)
            conn.close()

    def test_save_failure_does_not_stop_bells_or_exit(self):
        for component, method in [("conn", "commit"), ("sync", "flush")]:
            with self.subTest(component=component):
                window = self.make_window()
                getattr(getattr(window, component), method).side_effect = OSError("cannot save")
                self.assertFalse(MainWindow._shutdown(window, 75))
                window.scheduler.stop.assert_not_called()
                window.player.stop.assert_not_called()
                window.app.exit.assert_not_called()
                self.assertFalse(window._really_quit)

    def test_schedule_changed_during_flush_defers_exit(self):
        window = self.make_window()
        window.sync.flush.side_effect = lambda: setattr(window.restart_watch, "is_safe_now", lambda: False)
        self.assertFalse(MainWindow._shutdown(window, 75))
        window.scheduler.stop.assert_not_called()
        window.app.exit.assert_not_called()

    def test_unsaved_sync_files_defer_exit(self):
        window = self.make_window()
        window.sync.flush.return_value = False
        self.assertFalse(MainWindow._shutdown(window, 75))
        window.scheduler.stop.assert_not_called()
        window.app.exit.assert_not_called()

    def test_normal_exit_still_uses_zero(self):
        window = self.make_window()
        MainWindow._shutdown(window)
        window.app.exit.assert_called_once_with(0)

    def test_window_close_hides_to_tray_unless_really_quitting(self):
        window = self.make_window()
        window.hide = mock.Mock()
        event = mock.Mock()
        MainWindow.closeEvent(window, event)
        window.hide.assert_called_once_with()
        event.ignore.assert_called_once_with()
        window.app.exit.assert_not_called()
        window._really_quit = True
        MainWindow.closeEvent(window, event)
        event.accept.assert_called_once_with()


class QtRestartTests(unittest.TestCase):
    def run_script(self, source):
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONDONTWRITEBYTECODE="1")
        return subprocess.run([sys.executable, "-B", "-c", textwrap.dedent(source)],
                              cwd=ROOT, env=env, capture_output=True, text=True, timeout=20)

    def test_real_modal_and_unsaved_editor_block_countdown_and_manual_restart(self):
        result = self.run_script('''
            from pathlib import Path
            from types import SimpleNamespace
            from unittest import mock
            from PyQt6.QtCore import QTimer
            from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QWidget
            from app.ui.cloud_update import RestartWatch, cloud

            app = QApplication([])
            app.setQuitOnLastWindowClosed(False)
            restart = mock.Mock()
            ctx = SimpleNamespace(player=SimpleNamespace(is_playing=lambda: False),
                                  scheduler=SimpleNamespace(next_event=None), window=None, sync=None, toast=mock.Mock())
            with mock.patch.object(cloud, "installed_version_file", return_value=Path.cwd() / "absent" / "installed.json"), \
                 mock.patch.object(cloud, "newer_version_installed", return_value="999.0.0"), \
                 mock.patch.object(QTimer, "singleShot"):
                watch = RestartWatch(ctx, restart)
                watch.check()
                dialog = QDialog()
                editor = QLineEdit(dialog)
                editor.setText("unsaved")
                dialog.setModal(True)
                dialog.show()
                assert app.activeModalWidget() is dialog
                watch._restart_timer.stop()
                watch._restart_timer.timeout.emit()
                watch.restart_now()
                restart.assert_not_called()
                dialog.close()
                dialog.setModal(False)
                dialog.show()
                assert not watch.is_safe_now()
                dialog.close()
                window = QWidget()
                window.setWindowModified(True)
                window.show()
                assert not watch.is_safe_now()
                window.close()
                watch.check()
                watch._restart_timer.stop()
                watch._restart_timer.timeout.emit()
                restart.assert_called_once_with()
                watch._timer.stop()
        ''')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_real_qt_and_main_propagate_restart_code_even_from_tray(self):
        for hidden in (False, True):
            with self.subTest(hidden=hidden):
                result = self.run_script('''
                    import sys
                    from pathlib import Path
                    from types import SimpleNamespace
                    from unittest import mock
                    from PyQt6.QtCore import QTimer
                    from PyQt6.QtWidgets import QApplication, QMainWindow

                    with mock.patch.dict(sys.modules, {"pygame": mock.Mock()}):
                        from app import main as entry
                    MainWindow = entry.MainWindow

                    class Window(QMainWindow):
                        closeEvent = MainWindow.closeEvent
                        _shutdown = MainWindow._shutdown
                        restart_for_update = MainWindow.restart_for_update

                        def __init__(self, conn, app, session, prefer_local):
                            super().__init__()
                            self.conn, self.app = conn, app
                            self.scheduler, self.player, self.sync, self.tray = (mock.Mock() for _ in range(4))
                            self._fullscreen = None
                            self.restart_watch = None
                            self._really_quit = False
                            QTimer.singleShot(0, self.finish)

                        def finish(self):
                            if HIDDEN:
                                self.close()
                                assert self.isHidden() and not self._really_quit
                            self.restart_for_update()

                    session = SimpleNamespace(dev=True, data_dir=Path.cwd(), local_dir=Path.cwd())
                    with mock.patch.multiple(entry, MainWindow=Window, _set_app_id=mock.Mock(),
                                             _install_excepthook=mock.Mock(), enable_crash_log=mock.Mock(),
                                             acquire=mock.Mock(return_value=True), load_fonts=mock.Mock(),
                                             reset_font_cache=mock.Mock(), build_stylesheet=mock.Mock(return_value=""),
                                             legacy_app_running=mock.Mock(return_value=False), HangWatch=mock.Mock(),
                                             app_data_dir=mock.Mock(return_value=Path.cwd()),
                                             ui_cache_dir=mock.Mock(return_value=Path.cwd())), \
                         mock.patch.object(entry.cloud, "check", return_value=session), \
                         mock.patch.object(entry.paths, "configure"), \
                         mock.patch.object(entry.cloud_sync, "open_database", return_value=(mock.Mock(), False)):
                        entry.main()
                '''.replace("HIDDEN", repr(hidden)))
                self.assertEqual(result.returncode, 75, result.stdout + result.stderr)
