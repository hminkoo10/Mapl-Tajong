"""Real PC/Android JSON bytes, not a second implementation of either parser.

Regenerate PC snapshots: python -m tests.test_sync_compat --write-pc-fixtures
Android snapshots are generated/checked by SyncCompatibilityTest (see fixtures README).
"""
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from app.core import cloud_sync, data_sign, paths, scheduler
from app.data import repo
from app.data.db import init_schema
from app.ui.context import AppContext
from app.ui.pages import dashboard
from app.ui.pages.dashboard import DashboardPage

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/sync"
KEY = "sync-compat-test-key-한글-only"
TODAY = "2026-11-03"
STAMP = "2026-11-03 01:49:20"
NOW = datetime(2026, 11, 3, 8, 0, 0)
_app = None


def setUpModule():
    global _app
    _app = QApplication.instance() or QApplication([])


def new_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    init_schema(conn, (ROOT / "app/data/schema.sql").read_text(encoding="utf-8"))
    return conn


def body(doc):
    return {k: v for k, v in doc.items() if k not in ("meta", "sig")}


def read_fixture(device, name):
    return json.loads((FIXTURES / device / (name + ".json")).read_bytes())


def pc_documents():
    conn = new_db()
    try:
        conn.execute("DELETE FROM schedule_sets")
        conn.executemany("INSERT INTO sounds(id,name,file_name,volume,created_at) VALUES(?,?,?,?,?)", [
            (5, '시작 "종" 🔔', "bell1.wav", 1.0, STAMP),
            (8, "쉬는 종", "쉬는 종.wav", 0.8, STAMP),
        ])
        conn.executemany("INSERT INTO schedule_sets(id,name,created_at) VALUES(?,?,?)", [
            (3, "평일", STAMP), (6, "주말", STAMP),
        ])
        conn.executemany("""INSERT INTO schedules
            (id,set_id,name,weekday_mask,time_hhmm,sound_id,volume_override,enabled,sort_order,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?)""", [
            (7, 3, "1교시", 127, "09:00", 5, None, 1, 0, STAMP, STAMP),
            (9, 3, "2교시", 31, "10:00", 8, 1.5, 1, 1, STAMP, STAMP),
            (12, 6, "주말", 96, "11:30", 8, 0.0, 0, 2, STAMP, STAMP),
        ])
        repo.set_setting(conn, "active_set_id", "3")
        requests = [
            {"id": "schedule-request", "schedule_id": 7, "sound_id": None,
             "at": "2026-11-03T12:37:54Z", "ring_at": "2026-11-03T12:37:57.257Z",
             "by": "fixture-sender", "by_name": "교무실 폰 🔔"},
            {"id": "sound-request", "schedule_id": None, "sound_id": 8,
             "at": "2026-11-03T12:37:54Z", "ring_at": "2026-11-03T12:37:57.000Z",
             "by": "fixture-sender", "by_name": "교무실 폰 🔔"},
        ]
        docs = {"config": cloud_sync.build_config(conn)}
        repo.add_override(conn, TODAY, 0, "PAUSE_DAY", "admin")
        repo.add_override(conn, TODAY, 7, "SKIP_ONCE", "admin")
        repo.add_override(conn, TODAY, 9, "FIRED_ONCE", "local only")
        for name, paused in (("paused", True), ("day", False)):
            repo.set_setting(conn, "paused", "1" if paused else "0")
            docs[name] = cloud_sync.build_state(conn, requests, today=TODAY)
        conn.execute("DELETE FROM overrides WHERE action IN ('SKIP_ONCE','PAUSE_DAY')")
        docs["resumed"] = cloud_sync.build_state(conn, today=TODAY)
        for doc in docs.values():
            doc["meta"] = {"device_id": "fixture-pc", "device_name": "교무실 PC",
                           "at": "2026-11-03T12:37:54Z"}
        return docs
    finally:
        conn.close()


class FixtureTests(unittest.TestCase):
    def test_pc_snapshots_are_actual_builder_and_signer_output(self):
        for name, doc in pc_documents().items():
            with self.subTest(name=name):
                raw = data_sign.dumps_signed(doc, KEY, ensure_ascii=False, indent=1)
                self.assertEqual((FIXTURES / "pc" / (name + ".json")).read_bytes(), raw)

    def test_android_config_and_all_state_transitions_apply_unchanged(self):
        conn = new_db()
        self.addCleanup(conn.close)
        config = read_fixture("android", "config")
        cloud_sync.apply_config(conn, config)
        self.assertEqual(body(config), cloud_sync.build_config(conn))
        repo.add_override(conn, TODAY, 9, "FIRED_ONCE", "local only")
        for name in ("paused", "day", "resumed", "paused"):
            with self.subTest(name=name):
                doc = read_fixture("android", name)
                paused, requests = cloud_sync.apply_state(conn, doc, today=TODAY)
                self.assertIs(paused, doc["paused"])
                self.assertEqual(body(doc), cloud_sync.build_state(conn, requests, today=TODAY))
                self.assertTrue(repo.has_override(conn, TODAY, 9, "FIRED_ONCE"))

    def test_phone_227_real_files_apply_unchanged(self):
        # Original signatures retained. Unknown account key: payload compatibility only.
        conn = new_db()
        self.addCleanup(conn.close)
        config, state = (read_fixture("phone-2.2.7", n) for n in ("config", "state"))
        cloud_sync.apply_config(conn, config)
        paused, requests = cloud_sync.apply_state(conn, state, today=TODAY)
        self.assertEqual(body(config), cloud_sync.build_config(conn))
        self.assertTrue(paused)
        self.assertEqual(body(state), cloud_sync.build_state(conn, requests, today=TODAY))
        self.assertEqual("2026-11-03T12:37:57.257Z", requests[0]["ring_at"])

    def test_android_signatures_verify_without_reserializing(self):
        for name in ("config", "paused", "day", "resumed"):
            with self.subTest(name=name):
                raw = (FIXTURES / "android" / (name + ".json")).read_bytes()
                self.assertTrue(data_sign.verify_bytes(raw, KEY))
                self.assertFalse(data_sign.verify_bytes(raw, "wrong-key"))
                self.assertFalse(data_sign.verify_bytes(raw + b"\n", KEY))

    def test_old_request_without_ring_at_keeps_fallback(self):
        conn = new_db()
        self.addCleanup(conn.close)
        cloud_sync.apply_config(conn, read_fixture("android", "config"))
        doc = body(read_fixture("android", "paused"))
        for request in doc["ring_requests"]:
            del request["ring_at"]
        _, requests = cloud_sync.apply_state(conn, doc, today=TODAY)
        self.assertEqual(doc, cloud_sync.build_state(conn, requests, today=TODAY))
        self.assertEqual(cloud_sync.parse_utc(requests[0]["at"]), cloud_sync._ring_time(requests[0]))


class TriggerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tajong_compat_")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = mock.patch.object(cloud_sync, "app_data_dir", return_value=self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = new_db()
        self.addCleanup(self.conn.close)
        for patcher in (
            mock.patch.dict(os.environ, {data_sign.KEY_ENV: KEY}),
            mock.patch.object(cloud_sync, "_today", return_value=TODAY),
            mock.patch.object(cloud_sync, "utc_now", return_value=NOW.replace(tzinfo=timezone.utc)),
            mock.patch.object(paths, "_sync_dir", self.root),
            mock.patch.object(paths, "_local_dir", self.root),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        for module in (scheduler, dashboard):
            patcher = mock.patch.object(module, "datetime", wraps=datetime)
            patcher.start().now.return_value = NOW
            self.addCleanup(patcher.stop)
        self.player = mock.Mock()
        self.player.is_playing.return_value = False
        self.sch = scheduler.Scheduler(self.conn, self.player)
        self.ctx = AppContext(self.conn, self.player, self.sch)
        self.sync = cloud_sync.CloudSync(self.conn, self.root, "fixture-receiver", "PC", self.sch)
        self.ctx.sync = self.sync
        self.sync.remote_applied.connect(self.ctx.remote_changed)
        self.events = []
        self.ctx.data_changed.connect(self.events.append)
        self.addCleanup(self.stop_sync)

    def stop_sync(self):
        for timer in self.sync.findChildren(QTimer):
            timer.stop()
        if self.sync.watcher is not None:
            self.sync.watcher.blockSignals(True)
        self.sync.deleteLater()
        QApplication.processEvents()

    def replace(self, name, raw):
        tmp = self.root / (name + ".incoming")
        tmp.write_bytes(raw)
        os.replace(tmp, self.root / name)

    def wait_for(self, condition):
        for _ in range(200):
            if condition():
                return
            QTest.qWait(10)
        self.assertTrue(condition(), "file watcher did not apply the remote file")

    def seed_files(self):
        for path, fixture in (("config.json", "config"), ("state.json", "resumed")):
            self.replace(path, (FIXTURES / "android" / (fixture + ".json")).read_bytes())

    def test_real_watcher_updates_scheduler_and_home_without_echo(self):
        self.seed_files()
        self.sch.start()
        self.sync.start(watch=True)
        self.sync._poll.stop()  # Prove QFileSystemWatcher, not the 30-second fallback.
        page = DashboardPage(self.ctx)
        self.addCleanup(page.deleteLater)
        self.addCleanup(page.close)
        page.show()
        self.events.clear()
        for name in ("paused", "day", "resumed"):
            with self.subTest(name=name):
                raw = (FIXTURES / "android" / (name + ".json")).read_bytes()
                self.replace("state.json", raw)
                self.wait_for(lambda: "state" in self.events)
                self.events.clear()
                expected = read_fixture("android", name)
                self.assertEqual(expected["paused"], self.sch.paused)
                self.assertEqual("다시 시작하기" if expected["paused"] else "잠시 멈추기", page.t_pause.title)
                self.assertEqual(name != "resumed", self.sch.is_paused_today(TODAY))
                self.assertEqual(name != "resumed", page.pause_today.isChecked())
                self.assertEqual("오늘은 쉬는 날" if name != "resumed" else "자동 타종 중", page.state_label.text())
                self.assertFalse(self.sync._export_timer.isActive())
                self.sync.export_now()
                self.assertEqual(raw, (self.root / "state.json").read_bytes())
                self.assertIn(str(self.root / "state.json"), self.sync.watcher.files())

    def test_signed_android_requests_reach_player_at_milliseconds_only_once(self):
        self.seed_files()
        self.sch.start()
        self.sync.start(watch=False)
        raw = (FIXTURES / "android/paused.json").read_bytes()
        self.replace("state.json", raw)
        with mock.patch.object(cloud_sync, "utc_now", return_value=datetime(2026, 11, 3, 12, 37, 57, tzinfo=timezone.utc)):
            self.sync.check_files()
            self.assertTrue(self.sch.paused)  # Manual requests still ring while automatic bells are paused.
            self.assertEqual(1, self.player.play.call_count)  # .000Z request is due now.
            self.assertIn("schedule-request", self.sync._pending)
            self.assertEqual(257, self.sync._pending["schedule-request"][0].interval())
            self.assertTrue(repo.has_override(self.conn, "2026-11-04", 7, "FIRED_ONCE"))
            self.wait_for(lambda: self.player.play.call_count == 2)
            self.sync.check_files()
            self.assertEqual(0, self.sync.handle_requests())
            self.assertEqual(2, self.player.play.call_count)
            self.assertEqual(["쉬는 종.wav", "bell1.wav"], [Path(c.args[0]).name for c in self.player.play.call_args_list])

    def test_remote_pause_day_recomputes_next_bell_like_android(self):
        self.seed_files()
        self.sch.start()
        self.sync.start(watch=False)
        self.assertEqual(TODAY, self.sch.next_event.run_at.strftime("%Y-%m-%d"))
        self.sync._apply("state", read_fixture("android", "day"))
        self.assertEqual("2026-11-04", self.sch.next_event.run_at.strftime("%Y-%m-%d"))
        self.sync._apply("state", read_fixture("android", "resumed"))
        self.assertEqual(TODAY, self.sch.next_event.run_at.strftime("%Y-%m-%d"))

    def test_remote_ring_marks_next_unblocked_occurrence_like_android(self):
        cloud_sync.apply_config(self.conn, read_fixture("android", "config"))
        for day, sid, action in (("2026-11-03", 0, "PAUSE_DAY"),
                                 ("2026-11-04", 7, "SKIP_ONCE"),
                                 ("2026-11-05", 7, "FIRED_ONCE")):
            repo.add_override(self.conn, day, sid, action, "admin")
        event = self.sch.mark_schedule_fired(7)
        self.assertEqual("2026-11-06", event.run_at.strftime("%Y-%m-%d"))
        self.assertTrue(repo.has_override(self.conn, "2026-11-06", 7, "FIRED_ONCE"))
        for day in range(7, 11):
            repo.add_override(self.conn, f"2026-11-{day:02d}", 0, "PAUSE_DAY", "admin")
        before = self.conn.execute("SELECT COUNT(*) FROM overrides").fetchone()[0]
        self.assertIsNotNone(self.sch.mark_schedule_fired(7))  # Manual sound still plays; no automatic occurrence to mark.
        self.assertEqual(before, self.conn.execute("SELECT COUNT(*) FROM overrides").fetchone()[0])

    def test_unsigned_android_files_accepted_only_before_first_signature(self):
        for path, name in (("config.json", "config"), ("state.json", "paused")):
            doc = read_fixture("android", name)
            doc.pop("sig")
            self.replace(path, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        self.sync.start(watch=False)
        self.assertTrue(self.sch.paused)
        for kind in ("config", "state"):
            self.assertEqual("1", repo.get_setting(self.conn, "data_signed_" + kind))
            self.assertTrue(data_sign.verify_bytes((self.root / (kind + ".json")).read_bytes(), KEY))
        resumed = body(read_fixture("android", "resumed"))
        self.replace("state.json", json.dumps(resumed).encode("utf-8"))
        self.sync.check_files()
        self.assertTrue(self.sch.paused)  # Second unsigned file was not applied.
        self.assertTrue(data_sign.verify_bytes((self.root / "state.json").read_bytes(), KEY))


if __name__ == "__main__":
    if sys.argv[1:] == ["--write-pc-fixtures"]:
        dest = FIXTURES / "pc"
        dest.mkdir(parents=True, exist_ok=True)
        for name, doc in pc_documents().items():
            (dest / (name + ".json")).write_bytes(data_sign.dumps_signed(doc, KEY, ensure_ascii=False, indent=1))
    else:
        unittest.main()
