import json
import os
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QCoreApplication, QTimer

from app.core import magoedu_cloud as cloud
from app.ui.cloud_update import CHECK_EVERY_MS, RestartWatch, is_safe_to_restart


_app = None
ROOT = Path(__file__).resolve().parents[1]


def setUpModule():
    global _app
    _app = QCoreApplication.instance() or QCoreApplication([])


class RestartDecisionTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 3, 10, 0)

    def test_no_bell_is_safe(self):
        self.assertTrue(is_safe_to_restart(self.now, None))

    def test_next_bell_must_be_more_than_ten_minutes_away(self):
        for seconds, safe in [(-1, False), (0, False), (599, False), (600, False), (601, True), (86400, True)]:
            with self.subTest(seconds=seconds):
                event = SimpleNamespace(run_at=self.now + timedelta(seconds=seconds))
                self.assertEqual(is_safe_to_restart(self.now, event), safe)

    def test_ringing_or_modal_editor_is_not_safe_even_without_bells(self):
        self.assertFalse(is_safe_to_restart(self.now, None, ringing=True))
        self.assertFalse(is_safe_to_restart(self.now, None, modal_open=True))


class RestartWatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.tmp.cleanup)
        self.installed = Path(self.tmp.name) / "installed.json"
        patch = mock.patch.object(cloud, "installed_version_file", return_value=self.installed)
        patch.start()
        self.addCleanup(patch.stop)
        self.now = datetime(2026, 11, 3, 10, 0)
        patch = mock.patch("app.ui.cloud_update.datetime")
        self.clock = patch.start()
        self.clock.now.return_value = self.now
        self.addCleanup(patch.stop)
        patch = mock.patch.object(QTimer, "singleShot")
        self.single_shot = patch.start()
        self.addCleanup(patch.stop)
        self.restart = mock.Mock()
        self.ctx = SimpleNamespace(
            player=SimpleNamespace(is_playing=lambda: False),
            scheduler=SimpleNamespace(next_event=None),
            window=None, sync=None, toast=mock.Mock(),
        )
        self.watch = RestartWatch(self.ctx, self.restart)
        self.addCleanup(self.stop_watch)

    def stop_watch(self):
        self.watch._timer.stop()
        self.watch._restart_timer.stop()
        dirs = self.watch._watcher.directories()
        if dirs:
            self.watch._watcher.removePaths(dirs)

    def install(self, version="999.0.0"):
        tmp = self.installed.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": version}), encoding="utf-8")
        tmp.replace(self.installed)

    def finish_countdown(self):
        self.watch._restart_timer.stop()
        self.watch._restart_timer.timeout.emit()

    def test_checks_immediately_and_periodically_without_idle_requirement(self):
        self.assertTrue(self.watch._timer.isActive())
        self.assertEqual(self.watch._timer.interval(), CHECK_EVERY_MS)
        self.single_shot.assert_called_once_with(0, self.watch.check)
        self.install()
        self.watch._timer.timeout.emit()
        self.assertTrue(self.watch._restart_timer.isActive())
        self.assertEqual(self.watch._restart_timer.interval(), 5000)
        self.finish_countdown()
        self.restart.assert_called_once_with()

    def test_no_newer_version_never_restarts(self):
        for content in [None, "{", "{\"version\": \"0.0.0\"}"]:
            with self.subTest(content=content):
                if content is not None:
                    self.installed.write_text(content, encoding="utf-8")
                self.watch.check()
                self.watch.restart_now()
                self.assertFalse(self.watch._restart_timer.isActive())
                self.restart.assert_not_called()

    def test_waits_until_next_bell_is_far_enough(self):
        self.install()
        self.ctx.scheduler.next_event = SimpleNamespace(run_at=self.now + timedelta(minutes=5))
        self.watch.check()
        self.assertFalse(self.watch._restart_timer.isActive())
        self.ctx.scheduler.next_event = SimpleNamespace(run_at=self.now + timedelta(hours=1))
        self.watch._timer.timeout.emit()
        self.finish_countdown()
        self.restart.assert_called_once_with()

    def test_countdown_rechecks_safety_and_retries(self):
        self.install()
        self.watch.check()
        self.ctx.player.is_playing = lambda: True
        self.finish_countdown()
        self.restart.assert_not_called()
        self.assertFalse(self.watch._restarting)
        self.ctx.player.is_playing = lambda: False
        self.watch.check()
        self.finish_countdown()
        self.restart.assert_called_once_with()

    def test_countdown_crossing_ten_minute_boundary_defers(self):
        self.install()
        self.ctx.scheduler.next_event = SimpleNamespace(run_at=self.now + timedelta(seconds=601))
        self.watch.check()
        self.clock.now.return_value = self.now + timedelta(seconds=5)
        self.finish_countdown()
        self.restart.assert_not_called()
        self.assertFalse(self.watch._restarting)

    def test_pending_synchronized_bell_defers_restart(self):
        self.ctx.sync = SimpleNamespace(_pending={"ring": object()})
        self.assertFalse(self.watch.is_safe_now(self.now))
        self.ctx.sync._pending.clear()
        self.assertTrue(self.watch.is_safe_now(self.now))

    def test_fullscreen_clock_keeps_existing_safety_guard(self):
        self.ctx.window = SimpleNamespace(_fullscreen=SimpleNamespace(isVisible=lambda: True))
        self.assertFalse(self.watch.is_safe_now(self.now))

    def test_changed_installation_cancels_countdown(self):
        self.install()
        self.watch.check()
        self.install("0.0.0")
        self.finish_countdown()
        self.restart.assert_not_called()
        self.assertFalse(self.watch._restarting)

    def test_manual_button_cancels_timer_and_restarts(self):
        self.install()
        self.watch.check()
        toast = self.ctx.toast.call_args.args
        self.assertEqual(toast[3], "지금 다시 켜기")
        toast[4]()
        self.assertFalse(self.watch._restart_timer.isActive())
        self.watch.check()
        self.restart.assert_called_once_with()

    def test_manual_button_cannot_interrupt_bell(self):
        self.install()
        self.watch.check()
        self.ctx.player.is_playing = lambda: True
        self.watch.restart_now()
        self.restart.assert_not_called()
        self.assertFalse(self.watch._restart_timer.isActive())
        self.assertFalse(self.watch._restarting)

    def test_duplicate_checks_only_schedule_once(self):
        self.install()
        self.watch.check()
        self.watch.check()
        self.ctx.toast.assert_called_once()
        self.finish_countdown()
        self.watch.check()
        self.restart.assert_called_once_with()

    def test_failed_save_allows_periodic_retry(self):
        self.install()
        self.restart.return_value = False
        self.watch.check()
        self.finish_countdown()
        self.assertFalse(self.watch._restarting)
        self.restart.return_value = True
        self.watch.check()
        self.finish_countdown()
        self.assertEqual(self.restart.call_count, 2)

    def test_atomic_install_replacement_detected_without_polling(self):
        self.watch._timer.stop()
        self.install("0.0.0")
        QCoreApplication.processEvents()
        self.assertFalse(self.watch._restarting)
        self.install()
        deadline = time.monotonic() + 2
        while not self.watch._restarting and time.monotonic() < deadline:
            QCoreApplication.processEvents()
            time.sleep(0.01)
        self.assertTrue(self.watch._restarting)
        self.assertTrue(self.watch._restart_timer.isActive())
        self.restart.assert_not_called()

    def test_periodic_check_restores_missing_directory_watch(self):
        self.watch._watcher.removePaths(self.watch._watcher.directories())
        self.watch._installed_dir = Path(self.tmp.name) / "later"
        self.watch.check()
        self.assertEqual(self.watch._watcher.directories(), [])
        self.watch._installed_dir.mkdir()
        self.watch.check()
        self.assertIn(str(self.watch._installed_dir), self.watch._watcher.directories())


class InstalledVersionTests(unittest.TestCase):
    def test_windows_installation_path_uses_launcher_root(self):
        with mock.patch.object(cloud.sys, "platform", "win32"), \
             mock.patch.dict(os.environ, {"LOCALAPPDATA": str(ROOT / "test-local")}):
            self.assertEqual(cloud.installed_version_file("tajong"),
                             ROOT / "test-local" / "MagoEduCloud" / "apps" / "tajong" / "installed.json")

    def test_non_windows_installation_path_uses_trust_root(self):
        with mock.patch.object(cloud.sys, "platform", "linux"), \
             mock.patch.object(cloud, "default_trust_file", return_value=ROOT / "trust.json"):
            self.assertEqual(cloud.installed_version_file("tajong"),
                             ROOT / "local" / "apps" / "tajong" / "installed.json")
