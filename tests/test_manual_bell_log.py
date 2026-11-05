"""직접 울린 종은 기록하고, 들어보기는 기록하지 않는지 시험."""
from datetime import datetime
from types import SimpleNamespace
from unittest import mock

from PyQt6.QtCore import QTimer

from tests import test_cloud_sync as fixtures
from app.core import cloud_sync
from app.core.scheduler import NextEvent
from app.data import repo
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.logs import detail_text
from app.ui.pages.sounds import SoundsPage
from app.ui.sound_editor import SoundEditorDialog

setUpModule = fixtures.setUpModule


class ManualBellLogTests(fixtures.Base):
    def setUp(self):
        super().setUp()
        self.device = fixtures.Device(self.data, "devA", "원장님 PC")
        self.devices = [self.device]
        fixtures.fill_sample(self.device.conn)
        self.sound = repo.get_sound(self.device.conn, 8)
        ctx = SimpleNamespace(player=self.device.player, sync=None, toast=mock.Mock())
        self.page = SimpleNamespace(conn=self.device.conn, ctx=ctx, sch=self.device.sch,
                                    sound_combo=mock.Mock(), eq=mock.Mock())
        self.page.sound_combo.currentData.return_value = 8
        self.page._play = lambda s: DashboardPage._play(self.page, s)

    def tearDown(self):
        for device in self.devices:
            for timer in device.sync.findChildren(QTimer):
                timer.stop()
            device.conn.close()
        super().tearDown()

    def rows(self, device=None):
        return [dict(r) for r in (device or self.device).conn.execute("SELECT * FROM logs ORDER BY id")]

    def test_dashboard_manual_sound_records_and_notifies(self):
        self.device.sch.on_ring = mock.Mock()
        DashboardPage.on_play_selected(self.page)
        self.assertEqual(self.device.player.played, [("rest.wav", 0.8, "쉬는 종")])
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["schedule_id"])
        self.assertEqual(rows[0]["schedule_name"], "")
        self.assertEqual(rows[0]["sound_name"], "쉬는 종")
        self.assertEqual(rows[0]["result"], "PLAYED")
        self.assertEqual(rows[0]["detail"], "forced")
        self.assertEqual(rows[0]["occurred_at"][:10], fixtures.today())
        self.assertTrue(self.device.sync._logs_timer.isActive())
        self.device.sch.on_ring.assert_called_once()
        event, forced = self.device.sch.on_ring.call_args.args
        self.assertIsNone(event.schedule_id)
        self.assertTrue(forced)
        self.assertEqual(fixtures.overrides(self.device.conn), [])

    def test_dashboard_cloud_sound_records_only_when_played(self):
        self.device.start()
        self.page.ctx.sync = self.device.sync
        with mock.patch.object(cloud_sync, "RING_DELAY_SEC", 30):
            DashboardPage.on_play_selected(self.page)
        self.assertEqual(self.rows(), [])
        self.device.sync._ring_due(self.device.sync._requests[-1]["id"])
        self.assertEqual([(r["result"], r["detail"]) for r in self.rows()], [("PLAYED", "forced")])
        self.device.sync.handle_requests()
        self.assertEqual(len(self.rows()), 1)

    def test_cancelled_or_disabled_pending_sound_is_not_recorded(self):
        self.device.start()
        self.page.ctx.sync = self.device.sync
        for cancel in (True, False):
            with self.subTest(cancel=cancel):
                with mock.patch.object(cloud_sync, "RING_DELAY_SEC", 30):
                    DashboardPage.on_play_selected(self.page)
                req = self.device.sync._requests[-1]["id"]
                if cancel:
                    self.device.sync.cancel_ring(req)
                else:
                    self.device.sch.set_ring_enabled(False)
                self.device.sync._ring_due(req)
                self.assertEqual(self.rows(), [])
                self.assertEqual(self.device.player.played, [])

    def test_remote_sound_records_once_and_syncs(self):
        self.device.start()
        other = fixtures.Device(self.data, "devB", "강의실 PC").start()
        self.devices.append(other)
        with mock.patch.object(cloud_sync, "RING_DELAY_SEC", 0):
            self.device.sync.request_ring(sound_id=8)
        other.sync.check_files()
        other.sync.handle_requests()
        rows = self.rows(other)
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["schedule_id"])
        self.assertEqual((rows[0]["sound_name"], rows[0]["result"], rows[0]["detail"]),
                         ("쉬는 종", "PLAYED", "forced · 원장님 PC"))
        self.assertEqual(fixtures.overrides(other.conn), [])
        other.sync.export_logs()
        self.device.sync.check_files()
        merged = cloud_sync.list_logs(self.device.conn, self.device.sync.remote_rows(),
                                      fixtures.today(), fixtures.today(), "ALL", "", 100)
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["detail"], "forced · 원장님 PC")

    def test_failed_manual_sound_records_error_and_source(self):
        self.device.sch.on_event = mock.Mock()
        with mock.patch.object(self.device.player, "play", side_effect=RuntimeError("파일 없음")):
            DashboardPage.on_play_selected(self.page)
        self.assertEqual([(r["result"], r["detail"]) for r in self.rows()], [("FAILED", "forced · 파일 없음")])
        self.page.ctx.toast.assert_called_once_with(
            "스피커 연결과 종소리 파일을 확인하세요.\n\n자세한 내용: 파일 없음",
            "error", 6000)
        self.page.eq.set_active.assert_not_called()
        self.device.sch.on_event.assert_called_once()
        self.assertEqual(self.device.sch.on_event.call_args.args[0], "failed")

    def test_failed_remote_sound_records_error_and_requester(self):
        notices = []
        self.device.sync.notice.connect(lambda text, kind: notices.append(kind))
        with mock.patch.object(self.device.player, "play", side_effect=RuntimeError("파일 없음")):
            self.device.sync._ring_sound(8, "교무실 폰")
        self.assertEqual([(r["result"], r["detail"]) for r in self.rows()],
                         [("FAILED", "forced · 교무실 폰 · 파일 없음")])
        self.assertEqual(notices, ["error"])

    def test_failed_manual_schedule_keeps_source(self):
        ev = NextEvent(7, "1교시", datetime.now(), "bell1", "bell1.wav", 1.0)
        with mock.patch.object(self.device.player, "play", side_effect=RuntimeError("파일 없음")):
            self.device.sch.ring_event(ev, "forced · 교무실 폰")
        self.assertEqual([(r["schedule_id"], r["result"], r["detail"]) for r in self.rows()],
                         [(7, "FAILED", "forced · 교무실 폰 · 파일 없음")])

    def test_automatic_schedule_has_no_manual_marker(self):
        ev = NextEvent(7, "1교시", datetime.now(), "bell1", "bell1.wav", 1.0)
        self.device.sch._ring(ev, forced=False)
        with mock.patch.object(self.device.player, "play", side_effect=RuntimeError("파일 없음")):
            self.device.sch._ring(ev, forced=False)
        self.assertEqual([(r["result"], r["detail"]) for r in self.rows()],
                         [("PLAYED", ""), ("FAILED", "파일 없음")])

    def test_disabled_device_does_not_record_cloud_sound(self):
        self.device.start()
        self.page.ctx.sync = self.device.sync
        self.device.sch.set_ring_enabled(False)
        with mock.patch.object(cloud_sync, "RING_DELAY_SEC", 0):
            DashboardPage.on_play_selected(self.page)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.device.player.played, [])

    def test_sound_list_preview_is_not_recorded(self):
        self.page._selected = lambda: self.sound
        SoundsPage.on_play(self.page)
        self.assertEqual(len(self.device.player.played), 1)
        self.assertEqual(self.rows(), [])

    def test_editor_preview_is_not_recorded(self):
        editor = SimpleNamespace(_loading=False, btn_play=mock.Mock(), wave=SimpleNamespace(duration=10),
                                 ctx=self.page.ctx, _ph=mock.Mock(), show_error=mock.Mock())
        with mock.patch("app.ui.sound_editor.run_async") as run:
            SoundEditorDialog._render_and_play(editor, mock.Mock(), 0)
            run.call_args.kwargs["on_done"](str(self.tmp / "preview.wav"))
        self.assertEqual(len(self.device.player.played), 1)
        self.assertEqual(self.rows(), [])

    def test_old_and_manual_details_still_display(self):
        for detail, label in [(None, ""), ("", ""), ("late=121s", "late=121s"),
                              ("forced", "수동 타종"), ("forced · 폰", "수동 타종 · 폰"),
                              ("forced · 폰 · 파일 없음", "수동 타종 · 폰 · 파일 없음")]:
            with self.subTest(detail=detail):
                self.assertEqual(detail_text(detail), label)
