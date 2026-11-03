import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QCoreApplication, QEventLoop, QThread, QTimer

from app.core import single_instance


@unittest.skipUnless(sys.platform == "win32", "Windows 이름 있는 파이프")
class SecondLaunchTests(unittest.TestCase):
    def setUp(self):
        self.app = QCoreApplication.instance() or QCoreApplication([])
        self.name = "MaplTajongTest-" + uuid.uuid4().hex

    def test_second_launch_asks_running_one_to_show(self):
        shown = []
        server = single_instance.listen(self.name, lambda: shown.append(1))
        self.assertIsNotNone(server)
        try:
            self.assertTrue(single_instance.show_running(self.name))
            loop = QEventLoop()
            QTimer.singleShot(500, loop.quit)
            loop.exec()
            self.assertEqual(shown, [1])
        finally:
            server.close()

    def test_nothing_running(self):
        self.assertFalse(single_instance.show_running(self.name + "-none"))

    def test_quit_pipe_is_separate_and_runs_callback_on_gui_thread(self):
        shown = []
        stopped = []
        server = single_instance.listen(self.name, lambda: shown.append(1))
        quit_server = single_instance.listen_quit(self.name, lambda: stopped.append(QThread.currentThread()))
        self.assertIsNotNone(quit_server)
        try:
            self.assertTrue(single_instance.show_running(self.name))
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
            self.assertEqual(shown, [1])
            self.assertEqual(stopped, [])
            self.assertTrue(single_instance.request_quit(self.name))
            QTimer.singleShot(100, loop.quit)
            loop.exec()
            self.assertEqual(shown, [1])
            self.assertEqual(stopped, [self.app.thread()])
        finally:
            server.close()
            quit_server.close()

    def test_quit_with_nothing_running(self):
        self.assertFalse(single_instance.request_quit(self.name + "-none"))


class QuitArgumentTests(unittest.TestCase):
    def test_quit_entry_point_exits_zero_before_importing_gui_or_cloud(self):
        source = '''
            import runpy
            import sys
            from unittest import mock
            from app.core import single_instance

            sys.modules['PyQt6.QtWidgets'] = None
            sys.modules['app.core.cloud_sync'] = None
            sys.argv = ['Mataf.exe', '--quit']
            with mock.patch.object(single_instance, 'request_quit', return_value=False) as request, \\
                 mock.patch.object(single_instance, 'acquire') as acquire:
                try:
                    runpy.run_module('app.main', run_name='__main__')
                except SystemExit as result:
                    assert result.code == 0
                else:
                    raise AssertionError('종료하지 않음')
                request.assert_called_once()
                acquire.assert_not_called()
        '''
        result = subprocess.run([sys.executable, '-c', textwrap.dedent(source)],
                                cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '')

    def test_quit_returns_without_cloud_lock_or_window_even_if_nothing_running(self):
        with mock.patch.dict(sys.modules, {"pygame": mock.Mock()}):
            from app import main as entry
        for connected in (False, True):
            with self.subTest(connected=connected), \
                 mock.patch.object(sys, "argv", ["Mataf.exe", "--quit"]), \
                 mock.patch.object(entry, "request_quit", return_value=connected) as request, \
                 mock.patch.multiple(entry, QApplication=mock.DEFAULT, acquire=mock.DEFAULT,
                                     show_running=mock.DEFAULT, MainWindow=mock.DEFAULT,
                                     app_data_dir=mock.DEFAULT) as unused, \
                 mock.patch.object(entry.cloud, "check") as check:
                self.assertIsNone(entry.main())
                request.assert_called_once_with(entry.APP_NAME)
                check.assert_not_called()
                for fn in unused.values():
                    fn.assert_not_called()

    @unittest.skipUnless(sys.platform == "win32", "Windows 이름 있는 파이프")
    def test_main_quit_request_commits_and_flushes_before_exit(self):
        with mock.patch.dict(sys.modules, {"pygame": mock.Mock()}):
            from app import main as entry
        qt = QCoreApplication.instance() or QCoreApplication([])
        order = []
        app = mock.Mock()
        app.exit.side_effect = lambda code: order.append(('exit', code))
        win = mock.Mock(_fullscreen=None)
        win.conn.commit.side_effect = lambda: order.append('commit')
        win.sync.flush.side_effect = lambda: order.append('flush')
        win.app = app
        # MainWindow 생성만 바꾸고, 종료 처리는 실제 메서드를 실행한다.
        shutdown = entry.MainWindow._shutdown
        win._shutdown.side_effect = lambda code: shutdown(win, code)

        def event_loop():
            self.assertTrue(single_instance.request_quit(entry.APP_NAME))
            loop = QEventLoop()
            QTimer.singleShot(100, loop.quit)
            loop.exec()
            return 0

        app.exec.side_effect = event_loop
        with tempfile.TemporaryDirectory() as root, \
             mock.patch.dict(os.environ, {'LOCALAPPDATA': root}), \
             mock.patch.object(sys, 'argv', ['Mataf.exe']), \
             mock.patch.multiple(entry, QApplication=mock.Mock(return_value=app), MainWindow=mock.Mock(return_value=win),
                                 QGuiApplication=mock.Mock(), QIcon=mock.Mock(), app_font=mock.Mock(),
                                 acquire=mock.Mock(return_value=True), _set_app_id=mock.Mock(), _install_excepthook=mock.Mock(),
                                 enable_crash_log=mock.Mock(), load_fonts=mock.Mock(), reset_font_cache=mock.Mock(),
                                 build_stylesheet=mock.Mock(return_value=''), legacy_app_running=mock.Mock(return_value=False),
                                 HangWatch=mock.Mock(), app_data_dir=mock.Mock(return_value=Path(root)),
                                 ui_cache_dir=mock.Mock(return_value=Path(root))), \
             mock.patch.object(entry.cloud, 'check', return_value=SimpleNamespace(dev=True, data_dir=root, local_dir=root)), \
             mock.patch.object(entry.paths, 'configure'), \
             mock.patch.object(entry.cloud_sync, 'open_database', return_value=(mock.Mock(), False)):
            with self.assertRaises(SystemExit) as result:
                entry.main()
            self.assertEqual(result.exception.code, 0)
        self.assertEqual(order, ['commit', 'flush', ('exit', 0)])


if __name__ == "__main__":
    unittest.main()


class BuildKeepsNetworkTests(unittest.TestCase):
    def test_build_does_not_prune_qt_network(self):
        from tools import build
        self.assertFalse([p for p in build.PRUNE if "Network" in p])
