"""통합 클라우드 동기화(app/core/cloud_sync.py) 시험.

두 기기(A, B)가 같은 동기화 폴더를 쓰는 것처럼 꾸며서 (통합 클라우드가 파일을 옮겨 준 셈)
내보내기 → 적용이 docs/cloud-sync.md 대로 되는지 본다.

    python -m unittest tests.test_cloud_sync
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QCoreApplication  # noqa: E402

from app.core import cloud_sync, paths  # noqa: E402
from app.core.scheduler import NextEvent, Scheduler  # noqa: E402
from app.data import repo  # noqa: E402
from app.data.db import init_schema  # noqa: E402

SCHEMA = (ROOT / "app" / "data" / "schema.sql").read_text(encoding="utf-8")
_app = None


def setUpModule():
    global _app
    _app = QCoreApplication.instance() or QCoreApplication([])


class FakePlayer:
    def __init__(self):
        self.played = []

    def play(self, path, volume, name=""):
        self.played.append((Path(path).name, volume, name))

    def is_playing(self):
        return False

    def stop(self):
        pass


def new_db(path=":memory:"):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    init_schema(conn, SCHEMA)
    return conn


def fill_sample(conn):
    """ID 가 1부터가 아닌 시간표 (ID 가 그대로 가는지 보려고)."""
    conn.execute("INSERT INTO sounds(id, name, file_name, volume) VALUES(5, 'bell1', 'bell1.wav', 1.0)")
    conn.execute("INSERT INTO sounds(id, name, file_name, volume) VALUES(8, '쉬는 종', 'rest.wav', 0.8)")
    conn.execute("INSERT INTO schedule_sets(id, name) VALUES(3, '평일')")
    conn.execute("""INSERT INTO schedules(id, set_id, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled)
                    VALUES(7, 3, '1교시', 127, '23:58', 5, NULL, 1)""")
    conn.execute("""INSERT INTO schedules(id, set_id, name, weekday_mask, time_hhmm, sound_id, volume_override, enabled)
                    VALUES(9, 3, '2교시', 127, '23:59', 8, 1.5, 1)""")
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('active_set_id', '3')")
    conn.commit()


def today():
    return datetime.now().strftime("%Y-%m-%d")


def overrides(conn):
    return sorted((r[0], int(r[1]), r[2]) for r in
                  conn.execute("SELECT date_yyyymmdd, schedule_id, action FROM overrides").fetchall())


class Device:
    def __init__(self, data_dir, dev_id, name, conn=None):
        self.conn = conn or new_db()
        self.player = FakePlayer()
        self.sch = Scheduler(self.conn, self.player)
        self.sch.start()
        self.sync = cloud_sync.CloudSync(self.conn, data_dir, dev_id, name, self.sch)
        self.sch.on_log = self.sync.log_added
        self.sch.remote_logs = self.sync.remote_logs_on
        self.applied = []
        self.sync.remote_applied.connect(self.applied.append)

    def start(self, prefer_local=False):
        self.sync.start(prefer_local, watch=False)
        return self


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tajong_sync_"))
        self.data = self.tmp / "sync"
        self.local = self.tmp / "local"
        self.data.mkdir()
        self.local.mkdir()
        paths.configure(self.data, self.local)
        self._appdata = os.environ.get("APPDATA")
        os.environ["APPDATA"] = str(self.tmp / "appdata")   # 예전 데이터 위치도 시험 폴더로

    def tearDown(self):
        if self._appdata is None:
            os.environ.pop("APPDATA", None)
        else:
            os.environ["APPDATA"] = self._appdata
        shutil.rmtree(self.tmp, ignore_errors=True)

    def read(self, name):
        return json.loads((self.data / name).read_text(encoding="utf-8"))

    def write(self, name, doc):
        cloud_sync.write_json_atomic(self.data / name, doc)


class ConfigTests(Base):
    def test_export_then_apply_keeps_ids(self):
        a = Device(self.data, "devA", "교무실 PC")
        fill_sample(a.conn)
        a.start()
        doc = self.read("config.json")
        self.assertEqual(doc["kind"], "config")
        self.assertEqual(doc["meta"]["device_id"], "devA")
        self.assertEqual([s["id"] for s in doc["sounds"]], [5, 8])
        self.assertEqual([s["id"] for s in doc["schedules"]], [7, 9])
        self.assertFalse(list(self.data.glob("*.tmp")))

        b = Device(self.data, "devB", "강의실 PC").start()
        self.assertIn("all", b.applied)
        self.assertEqual(cloud_sync.content_key(cloud_sync.build_config(b.conn)),
                         cloud_sync.content_key(cloud_sync.build_config(a.conn)))
        self.assertEqual(repo.active_set_id(b.conn), 3)
        self.assertEqual([int(r["id"]) for r in repo.list_schedules(b.conn, 3)], [7, 9])

    def test_apply_keeps_overrides_of_unchanged_schedules(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        b = Device(self.data, "devB", "B").start()
        d = today()
        for sid in (7, 9):
            repo.add_override(b.conn, d, sid, "FIRED_ONCE", "auto")
        repo.add_override(b.conn, d, 9, "SKIP_ONCE", "admin")

        # A 에서 2교시 시각을 바꾸고 이름만 1교시를 바꿈 → 2교시 표시만 지워져야 한다
        repo.update_schedule(a.conn, 9, "2교시", 127, "23:57", 8, 1.5, 1)
        repo.update_schedule(a.conn, 7, "첫 시간", 127, "23:58", 5, None, 1)
        a.sync.export_now()
        b.sync.check_files()
        self.assertEqual(overrides(b.conn), [(d, 7, "FIRED_ONCE")])
        self.assertEqual(repo.get_schedules(b.conn, [7])[0]["name"], "첫 시간")

        # 일정을 지우면 그 일정 표시도 지운다
        repo.delete_schedule(a.conn, 7)
        a.sync.export_now()
        b.sync.check_files()
        self.assertEqual(overrides(b.conn), [])
        self.assertEqual([int(r["id"]) for r in repo.list_schedules(b.conn, 3)], [9])

    def test_no_reexport_after_applying_remote(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        b = Device(self.data, "devB", "B").start()
        before = (self.data / "config.json").stat().st_mtime_ns
        # 받은 것을 적용한 뒤에는 B 가 다시 쓰지 않는다
        b.sync.local_changed()
        self.assertFalse(b.sync._export("config"))
        b.sync.export_now()
        self.assertEqual(self.read("config.json")["meta"]["device_id"], "devA")
        self.assertEqual((self.data / "config.json").stat().st_mtime_ns, before)
        # 값 표기가 조금 달라도(정수 1 ↔ 1.0, true) 적용한 뒤 다시 쓰지 않는다
        doc = self.read("config.json")
        doc["sounds"][0]["volume"] = 1
        doc["schedules"][0]["enabled"] = True
        doc["meta"] = {"device_id": "phone", "device_name": "폰", "at": "2026-11-01T00:00:00Z"}
        self.write("config.json", doc)
        b.sync.check_files()
        self.assertFalse(b.sync._export("config"))
        self.assertEqual(self.read("config.json")["meta"]["device_id"], "phone")
        # 이 기기에서 바꾸면 그때는 쓴다
        repo.update_sound(b.conn, 5, "bell 하나", 1.0)
        self.assertTrue(b.sync._export("config"))
        self.assertEqual(self.read("config.json")["meta"]["device_id"], "devB")

    def test_pending_remote_change_wins_over_local_edit(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        b = Device(self.data, "devB", "B").start()
        notices = []
        b.sync.notice.connect(lambda t, k: notices.append(t))
        repo.update_sound(a.conn, 5, "A가 바꿈", 1.0)
        a.sync.export_now()                       # 파일은 왔지만 B 는 아직 못 읽음
        repo.update_sound(b.conn, 8, "B가 바꿈", 1.0)
        b.sync.export_now()                       # 쓰기 전에 받은 것을 먼저 적용
        self.assertEqual(repo.get_sound(b.conn, 5)["name"], "A가 바꿈")
        self.assertEqual(self.read("config.json")["meta"]["device_id"], "devA")
        self.assertTrue(notices)

    def test_start_removes_leftover_tmp(self):
        (self.data / "sounds").mkdir()
        (self.data / "sounds" / "new.wav.tmp").write_bytes(b"half")
        (self.data / "config.json.tmp").write_text("{", encoding="utf-8")
        (self.data / "sounds" / "bell1.wav").write_bytes(b"x")
        Device(self.data, "devA", "A").start()
        self.assertEqual(sorted(p.name for p in (self.data / "sounds").iterdir()), ["bell1.wav"])
        self.assertFalse((self.data / "config.json.tmp").exists())
        self.assertTrue((self.data / "config.json").exists())

    def test_partial_or_invalid_file_is_tolerated(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        good = (self.data / "config.json").read_text(encoding="utf-8")
        b = Device(self.data, "devB", "B").start()
        (self.data / "config.json").write_text(good[: len(good) // 2], encoding="utf-8")
        b.sync.check_files()                      # 반쯤 쓴 파일: 적용하지 않고 조금 뒤 다시
        self.assertTrue(b.sync._check_timer.isActive())
        self.assertEqual(len(repo.list_schedules(b.conn, 3)), 2)
        doc = json.loads(good)
        doc["schedules"] = doc["schedules"][:1]
        doc["schedules"][0]["sound_id"] = 999     # 없는 종소리 → 통째로 적용하지 않음
        self.write("config.json", doc)
        b.sync.check_files()
        self.assertEqual(len(repo.list_schedules(b.conn, 3)), 2)
        doc["schedules"][0]["sound_id"] = 5
        self.write("config.json", doc)
        b.sync.check_files()
        self.assertEqual([int(r["id"]) for r in repo.list_schedules(b.conn, 3)], [7])


class StateTests(Base):
    def test_state_export_apply_pause_skip(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        b = Device(self.data, "devB", "B").start()
        d = today()
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        a.sch.recompute_next()
        ev = a.sch.skip_next_once()
        self.assertIsNotNone(ev)
        repo.set_pause_today(a.conn, tomorrow, True)
        repo.add_override(a.conn, yesterday, 7, "SKIP_ONCE", "admin")   # 지난 날짜는 넣지 않음
        repo.add_override(a.conn, d, 9, "FIRED_ONCE", "auto")           # 기기마다 따로
        a.sch.pause()
        a.sync.export_now()

        st = self.read("state.json")
        self.assertTrue(st["paused"])
        self.assertEqual(sorted((o["date"], o["schedule_id"], o["action"]) for o in st["overrides"]),
                         sorted([(ev.run_at.strftime("%Y-%m-%d"), ev.schedule_id, "SKIP_ONCE"),
                                 (tomorrow, 0, "PAUSE_DAY")]))

        b.sync.check_files()
        self.assertTrue(b.sch.paused)
        self.assertEqual(repo.get_setting(b.conn, "paused"), "1")
        self.assertTrue(repo.has_skip_once(b.conn, ev.run_at.strftime("%Y-%m-%d"), ev.schedule_id))
        self.assertTrue(repo.is_pause_today(b.conn, tomorrow))
        self.assertNotIn((d, 9, "FIRED_ONCE"), overrides(b.conn))
        self.assertFalse(b.sync._export("state"))   # 적용한 것을 다시 쓰지 않음

        # B 에서 다시 시작·건너뛰기 취소 → A 도 맞춰짐 (멈춤은 켤 때도 그대로)
        b.sch.resume()
        b.sch.undo(ev.schedule_id, ev.run_at.strftime("%Y-%m-%d"), "SKIP_ONCE")
        b.sync.export_now()
        a.sync.check_files()
        self.assertFalse(a.sch.paused)
        self.assertFalse(repo.has_skip_once(a.conn, ev.run_at.strftime("%Y-%m-%d"), ev.schedule_id))
        self.assertTrue(repo.is_pause_today(a.conn, tomorrow))
        again = Scheduler(a.conn, FakePlayer())
        again.start()
        self.assertFalse(again.paused)
        a.sch.pause()
        again.start()
        self.assertTrue(again.paused)


class RingTests(Base):
    def _due_event(self, sch, sid=7):
        r = repo.get_schedules(sch.conn, [sid])[0]
        return NextEvent(sid, str(r["name"]), datetime.now() - timedelta(seconds=1), str(r["sound_name"]),
                         str(r["sound_file_name"]), 1.0)

    def test_ring_gate_off_and_on(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        a.sch.set_ring_enabled(False)
        ev = self._due_event(a.sch)
        a.sch.next_event = ev
        a.sch._last_second = None
        a.sch.tick()
        self.assertEqual(a.player.played, [])
        self.assertEqual(a.conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0], 0)
        self.assertIsNot(a.sch.next_event, ev)
        self.assertEqual(repo.get_setting(a.conn, "ring_device"), "0")

        a.sch.set_ring_enabled(True)
        a.sch.next_event = self._due_event(a.sch)
        a.sch._last_second = None
        a.sch.tick()
        self.assertEqual([p[0] for p in a.player.played], ["bell1.wav"])
        rows = a.conn.execute("SELECT result FROM logs").fetchall()
        self.assertEqual([r[0] for r in rows], ["PLAYED"])
        self.assertTrue(a.sync._logs_timer.isActive())   # 기록은 몇 초 모아서 내보낸다

    def test_ring_next_now_when_off_only_marks(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        a.sch.set_ring_enabled(False)
        a.sch.recompute_next()
        ev = a.sch.ring_next_now()
        self.assertIsNotNone(ev)
        self.assertEqual(a.player.played, [])
        self.assertTrue(repo.has_override(a.conn, ev.run_at.strftime("%Y-%m-%d"), ev.schedule_id, "FIRED_ONCE"))

    def test_ring_request_handled_once_and_expired_ignored(self):
        a = Device(self.data, "devA", "원장님 PC")
        fill_sample(a.conn)
        a.start()
        a.sch.set_ring_enabled(False)
        b = Device(self.data, "devB", "강의실 PC").start()
        self.assertTrue(b.sch.ring_enabled)

        req = a.sync.request_ring(schedule_id=9)
        a.sync.export_now()
        self.assertEqual([r["id"] for r in self.read("state.json")["ring_requests"]], [req["id"]])
        self.assertEqual(a.player.played, [])

        b.sync.check_files()
        self.assertEqual([p[0] for p in b.player.played], ["rest.wav"])
        log = b.conn.execute("SELECT schedule_id, result, detail FROM logs").fetchall()
        self.assertEqual([tuple(r) for r in log], [(9, "PLAYED", "forced · 원장님 PC")])
        self.assertTrue(b.conn.execute(
            "SELECT 1 FROM overrides WHERE schedule_id=9 AND action='FIRED_ONCE' AND note='forced'").fetchone())

        # 같은 요청은 다시 울리지 않는다 (다시 적용해도, 다시 켜도)
        b.sync.handle_requests()
        b.sync._seen.pop("state")
        b.sync.check_files()
        b.sync._sig.clear()
        b.sync.check_files()
        b2 = Device(self.data, "devB", "강의실 PC", conn=b.conn).start()
        self.assertEqual(len(b.player.played), 1)
        self.assertEqual(b2.player.played, [])

        # 소리 요청, 오래된 요청, 앞으로 너무 먼 요청, 내가 낸 요청
        now = datetime.now(timezone.utc)
        st = self.read("state.json")
        st["ring_requests"] = [
            {"id": "old", "schedule_id": 7, "sound_id": None, "at": cloud_sync.utc_iso(now - timedelta(minutes=5)),
             "by": "devA", "by_name": "원장님 PC"},
            {"id": "future", "schedule_id": 7, "sound_id": None,
             "at": cloud_sync.utc_iso(now + timedelta(minutes=3)), "by": "devA", "by_name": "원장님 PC"},
            {"id": "mine", "schedule_id": 7, "sound_id": None, "at": cloud_sync.utc_iso(now),
             "by": "devB", "by_name": "강의실 PC"},
            {"id": "snd", "schedule_id": None, "sound_id": 5, "at": cloud_sync.utc_iso(now - timedelta(seconds=30)),
             "by": "phone", "by_name": "원장님 폰"},
        ]
        self.write("state.json", st)
        b2.sync.check_files()
        self.assertEqual([p[0] for p in b2.player.played], ["bell1.wav"])

        # 종을 울리지 않는 기기는 요청을 처리하지 않는다
        c = Device(self.data, "devC", "C")
        c.conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('ring_device', '0')")
        c.sch.start()
        c.start()
        self.assertEqual(c.player.played, [])

    def test_unsent_request_survives_remote_state(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        a.sch.set_ring_enabled(False)
        b = Device(self.data, "devB", "B").start()
        b.sch.recompute_next()
        b.sch.skip_next_once()
        b.sync.export_now()                     # 그 사이 B 가 state.json 을 바꿈
        req = a.sync.request_ring(sound_id=5)   # A 는 아직 보내지 않은 요청이 있음
        a.sync.check_files()
        a.sync.export_now()
        ids = [r["id"] for r in self.read("state.json")["ring_requests"]]
        self.assertEqual(ids, [req["id"]])
        self.assertTrue(self.read("state.json")["overrides"])   # B 의 건너뛰기도 그대로

    def test_old_requests_pruned_when_writing(self):
        a = Device(self.data, "devA", "A")
        fill_sample(a.conn)
        a.start()
        old = cloud_sync.utc_iso(datetime.now(timezone.utc) - timedelta(minutes=11))
        a.sync._requests = [{"id": "x", "schedule_id": 7, "sound_id": None, "at": old, "by": "p", "by_name": "p"}]
        a.sch.pause()
        a.sync.export_now()
        self.assertEqual(self.read("state.json")["ring_requests"], [])


class LogTests(Base):
    def test_logs_export_and_merge(self):
        a = Device(self.data, "devA", "교무실 PC")
        fill_sample(a.conn)
        a.start()
        b = Device(self.data, "devB", "강의실 PC").start()
        d = today()
        repo.insert_log(a.conn, f"{d} 00:00:10", 7, "1교시", "bell1", "PLAYED", "")
        repo.insert_log(a.conn, f"{d} 00:00:30", 9, "2교시", "쉬는 종", "FAILED", "no file")
        repo.insert_log(b.conn, f"{d} 00:00:20", 9, "2교시", "쉬는 종", "PLAYED", "")
        repo.insert_log(a.conn, "2000-01-01 09:00:00", 7, "1교시", "bell1", "PLAYED", "")  # 60일 지난 것
        self.assertTrue(a.sync.export_logs())
        self.assertFalse(a.sync.export_logs())     # 바뀐 것이 없으면 다시 쓰지 않음
        doc = self.read("logs/devA.json")
        self.assertEqual(doc["device_name"], "교무실 PC")
        self.assertEqual([r["occurred_at"][-8:] for r in doc["logs"]], ["00:00:10", "00:00:30"])

        b.sync.check_files()
        self.assertIn("logs", b.applied)
        rows = cloud_sync.list_logs(b.conn, b.sync.remote_rows(), d, d, "ALL", "", 100)
        self.assertEqual([(r["occurred_at"][-8:], r["device_name"]) for r in rows],
                         [("00:00:30", "교무실 PC"), ("00:00:20", None), ("00:00:10", "교무실 PC")])
        only_failed = cloud_sync.list_logs(b.conn, b.sync.remote_rows(), d, d, "FAILED", "", 100)
        self.assertEqual(len(only_failed), 1)
        self.assertEqual(len(cloud_sync.list_logs(b.conn, b.sync.remote_rows(), "", "", "ALL", "1교시", 100)), 1)

        # 오늘 결과: 이 기기 기록이 있으면 그것, 없으면 다른 기기 기록 (기기 이름과 함께)
        res = b.sch.today_results(d)
        self.assertEqual(res[7], ("PLAYED", "교무실 PC"))
        self.assertEqual(res[9], ("PLAYED", None))
        self.assertEqual(b.sch.played_count(d), 2)

        # 내 기록 파일은 다른 기기 기록으로 읽지 않는다
        self.assertTrue(all(r["device_id"] == "devA" for r in b.sync.remote_rows()))


class FirstConnectionTests(Base):
    def _legacy(self, with_schedule=True):
        legacy = Path(os.environ["APPDATA"]) / "MaplTajong"
        (legacy / "sounds").mkdir(parents=True)
        conn = new_db(legacy / "tajong.db")
        if with_schedule:
            fill_sample(conn)
            repo.insert_log(conn, "2026-10-01 09:00:00", 7, "1교시", "bell1", "PLAYED", "")
        conn.close()
        (legacy / "sounds" / "bell1.wav").write_bytes(b"legacy-bell")
        (legacy / "sounds" / "rest.wav").write_bytes(b"legacy-rest")
        return legacy

    def test_no_cloud_starts_from_legacy(self):
        self._legacy()
        conn, prefer_local = cloud_sync.open_database(SCHEMA, ask_choice=lambda: self.fail("묻지 않아야 함"))
        self.assertFalse(prefer_local)
        self.assertEqual([int(r["id"]) for r in repo.list_schedules(conn, 3)], [7, 9])
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0], 1)
        self.assertEqual((self.data / "sounds" / "rest.wav").read_bytes(), b"legacy-rest")
        Device(self.data, "devA", "A", conn=conn).start()
        self.assertEqual([s["id"] for s in self.read("config.json")["schedules"]], [7, 9])
        conn.close()

    def test_no_cloud_no_legacy_seeds_defaults(self):
        conn, _ = cloud_sync.open_database(SCHEMA)
        self.assertGreater(conn.execute("SELECT COUNT(*) FROM sounds").fetchone()[0], 0)
        self.assertTrue((self.data / "sounds" / "bell1.wav").exists())
        conn.close()

    def _cloud_config(self):
        other = new_db()
        other.execute("INSERT INTO sounds(id, name, file_name, volume) VALUES(1, 'bell2', 'bell2.wav', 1.0)")
        other.execute("""INSERT INTO schedules(id, set_id, name, weekday_mask, time_hhmm, sound_id, enabled)
                         VALUES(1, 1, '클라우드 종', 31, '08:00', 1, 1)""")
        other.commit()
        doc = cloud_sync.build_config(other)
        doc["meta"] = {"device_id": "phone", "device_name": "폰", "at": cloud_sync.utc_iso()}
        self.write("config.json", doc)

    def test_both_differ_use_cloud_keeps_backup(self):
        self._legacy()
        self._cloud_config()
        asked = []
        conn, prefer_local = cloud_sync.open_database(SCHEMA, ask_choice=lambda: asked.append(1) or "cloud")
        self.assertEqual(asked, [1])
        self.assertFalse(prefer_local)
        zips = list((self.local / "backups").glob("*.zip"))
        self.assertEqual(len(zips), 1)
        with zipfile.ZipFile(zips[0]) as z:
            self.assertIn("sounds/rest.wav", z.namelist())
            self.assertEqual(len(json.loads(z.read("data.json"))["schedules"]), 2)
        self.assertFalse((self.data / "sounds" / "rest.wav").exists())   # 예전 종소리는 올리지 않음
        Device(self.data, "devA", "A", conn=conn).start()
        self.assertEqual([r["name"] for r in conn.execute("SELECT name FROM schedules")], ["클라우드 종"])
        self.assertEqual(self.read("config.json")["meta"]["device_id"], "phone")
        self.assertEqual(conn.execute("SELECT COUNT(*) FROM logs").fetchone()[0], 1)   # 기록은 그대로
        conn.close()

    def test_both_differ_use_local(self):
        self._legacy()
        self._cloud_config()
        conn, prefer_local = cloud_sync.open_database(SCHEMA, ask_choice=lambda: "local")
        self.assertTrue(prefer_local)
        Device(self.data, "devA", "A", conn=conn).start(prefer_local)
        doc = self.read("config.json")
        self.assertEqual(doc["meta"]["device_id"], "devA")
        self.assertEqual([s["id"] for s in doc["schedules"]], [7, 9])
        self.assertEqual((self.data / "sounds" / "rest.wav").read_bytes(), b"legacy-rest")
        conn.close()

    def test_default_legacy_does_not_ask(self):
        legacy = self._legacy(with_schedule=False)
        c = new_db(legacy / "tajong.db")
        c.execute("INSERT INTO sounds(name, file_name, volume) VALUES('bell1', 'bell1.wav', 1.0)")
        c.commit()
        c.close()
        self._cloud_config()
        conn, prefer_local = cloud_sync.open_database(SCHEMA, ask_choice=lambda: self.fail("묻지 않아야 함"))
        self.assertFalse(prefer_local)
        conn.close()

    def test_second_start_is_not_first_connection(self):
        conn, _ = cloud_sync.open_database(SCHEMA)
        conn.close()
        self._legacy()
        self._cloud_config()
        conn, prefer_local = cloud_sync.open_database(SCHEMA, ask_choice=lambda: self.fail("묻지 않아야 함"))
        self.assertFalse(prefer_local)
        conn.close()


if __name__ == "__main__":
    unittest.main()
