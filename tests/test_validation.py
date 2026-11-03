import json
import tempfile
import zipfile
import sqlite3
import sys
import unittest
from types import SimpleNamespace
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import backup, cloud_sync, paths, sound_files
from app.data.db import init_schema


SCHEMA = (ROOT / "app" / "data" / "schema.sql").read_text(encoding="utf-8")


class ValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.old_paths = paths._sync_dir, paths._local_dir
        paths.configure(Path(self.tmp.name) / "sync", Path(self.tmp.name) / "local")
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        init_schema(self.conn, SCHEMA)
        self.conn.execute("INSERT INTO sounds(id, name, file_name, volume) VALUES(5, 'bell', 'bell.wav', 1.0)")
        self.conn.execute("INSERT INTO schedule_sets(id, name) VALUES(3, '평일')")
        self.conn.execute("INSERT INTO schedules(id, set_id, name, weekday_mask, time_hhmm, sound_id, enabled) "
                          "VALUES(7, 3, '1교시', 127, '09:00', 5, 1)")
        self.conn.commit()

    def tearDown(self):
        self.conn.close()
        paths._sync_dir, paths._local_dir = self.old_paths
        self.tmp.cleanup()

    def test_config_drops_bad_rows_and_repairs_bad_values(self):
        doc = cloud_sync.build_config(self.conn)
        doc["sounds"].append({"id": 6, "name": "evil", "file_name": "../outside.wav", "volume": 1})
        doc["sounds"][0]["volume"] = float("nan")
        doc["schedules"].append({"id": 8, "set_id": 3, "name": "bad", "weekday_mask": 127,
                                  "time_hhmm": "25:99", "sound_id": 5})
        cloud_sync.apply_config(self.conn, doc)
        sound = self.conn.execute("SELECT file_name, volume FROM sounds WHERE id=5").fetchone()
        self.assertEqual((sound[0], sound[1]), ("bell.wav", 1.0))
        self.assertEqual([r[0] for r in self.conn.execute("SELECT id FROM schedules")], [7])

    def test_config_without_table_is_rejected_not_emptied(self):
        doc = cloud_sync.build_config(self.conn)
        doc["schedules"] = None
        with self.assertRaises(ValueError):
            cloud_sync.apply_config(self.conn, doc)
        self.assertEqual([r[0] for r in self.conn.execute("SELECT id FROM schedules")], [7])

    def test_old_backup_rows_without_set_id_are_kept(self):
        raw = {"sounds": [{"id": 5, "name": "bell", "file_name": "bell.wav"}], "schedule_sets": [],
               "schedules": [{"id": 9, "name": "1교시", "weekday_mask": 31, "time_hhmm": "09:00", "sound_id": 5}]}
        rows = backup.sanitize_tables(raw)["schedules"]
        self.assertEqual([(r["id"], r["set_id"]) for r in rows], [(9, None)])

    def test_state_drops_garbage_without_rejecting_valid_item(self):
        today = datetime.now().strftime("%Y-%m-%d")
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        doc = {"app": "MaplTajong", "kind": "state", "format": 1, "paused": "yes",
               "overrides": [{"date": tomorrow, "schedule_id": 7, "action": "SKIP_ONCE", "note": "ok"},
                              {"date": tomorrow, "schedule_id": -1, "action": "SKIP_ONCE"},
                              {"date": "not-a-date", "schedule_id": 7, "action": "SKIP_ONCE"}],
               "ring_requests": [{"id": "ok", "schedule_id": 7, "at": "2026-11-03T00:00:00Z"},
                                  {"id": "bad", "sound_id": "NaN", "at": "not-time"}]}
        paused, requests = cloud_sync.apply_state(self.conn, doc, today)
        self.assertFalse(paused)
        self.assertEqual(requests, [{"id": "ok", "schedule_id": 7, "sound_id": None,
                                     "at": "2026-11-03T00:00:00Z", "by": "", "by_name": ""}])
        self.assertEqual([(r[0], r[1], r[2]) for r in self.conn.execute(
            "SELECT date_yyyymmdd, schedule_id, action FROM overrides")], [(tomorrow, 7, "SKIP_ONCE")])

    def test_backup_tables_never_accept_path_or_wrong_shape(self):
        raw = {"sounds": [{"id": 1, "name": "ok", "file_name": "sounds/ok.wav", "volume": 1},
                           {"id": 2, "name": "bad", "file_name": "C:\\outside.wav", "volume": 1}],
               "schedule_sets": {}, "schedules": [], "settings": []}
        clean = backup.sanitize_tables(raw)
        self.assertEqual([r["file_name"] for r in clean["sounds"]], ["ok.wav"])
        self.assertEqual(clean["schedule_sets"], [])
        self.assertEqual(clean["settings"], {})

    def test_config_boundaries_and_shared_sound_files_survive(self):
        doc = cloud_sync.build_config(self.conn)
        doc["sounds"] += [dict(doc["sounds"][0], id=6, volume=0)]
        doc["schedules"][0].update(time_hhmm="00:00", volume_override=2, enabled=0)
        doc["schedules"] += [dict(doc["schedules"][0], id=8, time_hhmm="23:59", weekday_mask=1)]
        cloud_sync.apply_config(self.conn, doc)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM sounds").fetchone()[0], 2)
        self.assertEqual([tuple(r) for r in self.conn.execute("SELECT time_hhmm, enabled, volume_override FROM schedules ORDER BY id")],
                         [("00:00", 0, 2), ("23:59", 0, 2)])

    def test_invalid_paths_are_dropped_not_rebased(self):
        for name in ("../bell.wav", "..\\bell.wav", "/tmp/a.wav", "C:/a.wav", "C:a.wav", "\\\\server\\a.wav",
                     "a.wav:stream", "sounds/../a.wav", "a.wav ", "a.", "NUL.wav", "COM1.wav", "CONIN$", "a\x00.wav", "x" * 201,
                     "한" * 100 + ".wav", "\ud800.wav"):
            with self.subTest(name=name):
                doc = cloud_sync.build_config(self.conn)
                doc["sounds"].insert(0, dict(doc["sounds"][0], id=6, file_name=name))
                with self.assertLogs("tajong.validation", level="WARNING"):
                    cloud_sync.apply_config(self.conn, doc)
                self.assertEqual([r[0] for r in self.conn.execute("SELECT id FROM sounds")], [5])

    def test_bad_ids_and_shapes_do_not_discard_good_rows(self):
        for value in (True, False, 0, -1, 1.5, float("inf"), float("nan"), 2 ** 63, "9" * 5000, "6", [], {}):
            with self.subTest(value=type(value).__name__):
                doc = cloud_sync.build_config(self.conn)
                doc["sounds"][:0] = [None, [], 1, dict(doc["sounds"][0], id=value)]
                cloud_sync.apply_config(self.conn, doc)
                self.assertEqual([r[0] for r in self.conn.execute("SELECT id FROM schedules")], [7])

    def test_huge_json_integer_does_not_hide_valid_items(self):
        doc = cloud_sync.build_config(self.conn)
        doc["sounds"].insert(0, dict(doc["sounds"][0], id="HUGE"))
        text = json.dumps(doc).replace('"HUGE"', "9" * 5000)
        target = Path(self.tmp.name) / "config.json"
        target.write_text(text, encoding="utf-8")
        cloud_sync.apply_config(self.conn, cloud_sync.read_json(target))
        self.assertEqual([r[0] for r in self.conn.execute("SELECT id FROM sounds")], [5])
        target = Path(self.tmp.name) / "backup.zip"
        with zipfile.ZipFile(target, "w") as z:
            z.writestr("manifest.json", json.dumps({"app": "MaplTajong", "format": 1}))
            z.writestr("data.json", text)
        self.assertEqual(backup.import_backup(self.conn, target)["sounds"], 1)

    def test_bad_optional_fields_and_unknown_columns_do_not_abort_sql(self):
        doc = cloud_sync.build_config(self.conn)
        doc["sounds"][0].update(volume=float("inf"), updated_at="2026-11-03", created_at={}, extra=[])
        doc["schedules"][0].update(volume_override=-1, sort_order=10 ** 100, enabled={}, updated_at="x")
        cloud_sync.apply_config(self.conn, doc)
        self.assertEqual(tuple(self.conn.execute("SELECT volume_override, sort_order, enabled FROM schedules").fetchone()),
                         (None, 0, 1))
        self.assertEqual(self.conn.execute("SELECT volume FROM sounds").fetchone()[0], 1)
        doc["sounds"][0]["volume"] = "2"
        doc["schedules"][0].update(volume_override="2", enabled="0")
        cloud_sync.apply_config(self.conn, doc)
        self.assertEqual(self.conn.execute("SELECT volume FROM sounds").fetchone()[0], 1)
        self.assertEqual(tuple(self.conn.execute("SELECT volume_override, enabled FROM schedules").fetchone()), (None, 1))

    def test_duplicates_and_bad_required_fields(self):
        doc = cloud_sync.build_config(self.conn)
        doc["sounds"].insert(0, dict(doc["sounds"][0], name=[]))
        doc["sounds"].append(dict(doc["sounds"][-1]))
        doc["schedule_sets"].append({"id": 4, "name": "평일"})
        for i, changes in enumerate((dict(time_hhmm="24:00"), dict(time_hhmm="9:00"), dict(weekday_mask=128),
                                     dict(weekday_mask=-1), dict(name="x" * 201), dict(name="x\x00"), dict(name="\ud800"),
                                     dict(set_id=999), dict(sound_id=999))):
            doc["schedules"].append(dict(doc["schedules"][0], id=20+i, **changes))
        cloud_sync.apply_config(self.conn, doc)
        self.assertEqual([r[0] for r in self.conn.execute("SELECT id FROM schedules")], [7])

    def test_table_shapes_and_limits(self):
        for bad in (None, {}, "x", 1):
            doc = {"sounds": bad, "schedule_sets": [], "schedules": [], "settings": bad}
            self.assertEqual(backup.sanitize_tables(doc)["sounds"], [])
        for table, limit in backup.MAX_ROWS.items():
            doc = cloud_sync.build_config(self.conn)
            row = doc[table][-1]
            doc[table] = [dict(row, id=i+1, name=f"row{i}") for i in range(limit+1)]
            self.assertEqual(len(backup.sanitize_tables(doc)[table]), limit)

    def test_headers_reject_wrong_shape_and_version_without_changing_db(self):
        good = cloud_sync.build_config(self.conn)
        for bad in (None, [], {}, "x"):
            with self.assertRaises(ValueError):
                cloud_sync.apply_config(self.conn, bad)
        for fmt in (True, 0, -1, 1.5, float("inf"), {}, "9" * 5000, "1", 2):
            with self.assertRaises(ValueError):
                cloud_sync.apply_config(self.conn, dict(good, format=fmt))
        self.assertEqual(cloud_sync.build_config(self.conn), good)

    def test_state_dates_ids_duplicates_and_logging(self):
        valid = {"date": "2026-11-04", "schedule_id": 7, "action": "SKIP_ONCE"}
        request = {"id": "ok", "schedule_id": 7, "at": "2026-11-03T00:00:00Z"}
        doc = {"app": "MaplTajong", "kind": "state", "format": 1, "paused": "yes",
               "overrides": [valid, valid, None] + [dict(valid, **v) for v in
                   ({"date": "2026-02-30"}, {"date": "2026-11-4"}, {"schedule_id": 0}, {"action": "BAD"}, {"schedule_id": 999})],
               "ring_requests": [request, request, [], dict(request, id="bad", sound_id={}),
                                 dict(request, id="date", at="2026-11-03"), dict(request, id="missing", schedule_id=999)]}
        with self.assertLogs("tajong.validation", level="WARNING"):
            paused, requests = cloud_sync.apply_state(self.conn, doc, "2026-11-03")
        self.assertIn("state", (paths.app_data_dir() / "validation.log").read_text(encoding="utf-8"))
        self.assertFalse(paused)
        self.assertEqual([r["id"] for r in requests], ["ok"])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM overrides").fetchone()[0], 1)

    def test_state_shapes_and_limits(self):
        doc = {"app": "MaplTajong", "kind": "state", "format": 1, "overrides": {}, "ring_requests": "x"}
        self.assertEqual(cloud_sync._validated_state(doc, "2026-11-03"), (False, [], []))
        doc["overrides"] = [{"date": "2026-11-04", "schedule_id": i+1, "action": "SKIP_ONCE"} for i in range(501)]
        doc["ring_requests"] = [{"id": str(i), "sound_id": 5, "at": "2026-11-03T00:00:00Z"} for i in range(2001)]
        _, overrides, requests = cloud_sync._validated_state(doc, "2026-11-03")
        self.assertEqual((len(overrides), len(requests)), (500, 2000))

    def test_backup_import_uses_same_validation_before_extracting(self):
        doc = cloud_sync.build_config(self.conn)
        doc["sounds"] += [{"id": 6, "name": "evil", "file_name": "../outside.wav"}]
        doc["schedules"] += [dict(doc["schedules"][0], id=8, time_hhmm="24:00")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = paths._sync_dir, paths._local_dir
            paths.configure(root / "sync", root / "local")
            try:
                target = root / "backup.zip"
                with zipfile.ZipFile(target, "w") as z:
                    z.writestr("manifest.json", json.dumps({"app": "MaplTajong", "format": 1}))
                    z.writestr("data.json", json.dumps(doc))
                    z.writestr("sounds/bell.wav", b"bell")
                    z.writestr("sounds/../outside.wav", b"bad")
                counts = backup.import_backup(self.conn, target)
                self.assertEqual(counts["schedules"], 1)
                self.assertEqual((root / "sync/sounds/bell.wav").read_bytes(), b"bell")
                self.assertFalse((root / "sync/outside.wav").exists())
            finally:
                paths._sync_dir, paths._local_dir = old

    def test_manifest_bad_counts_and_version(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "backup.zip"
            for value in (True, -1, float("inf"), {}, 2):
                with zipfile.ZipFile(target, "w") as z:
                    z.writestr("manifest.json", json.dumps({"app": "MaplTajong", "format": value}))
                with self.assertRaises(backup.BackupError):
                    backup.read_manifest(target)
            with zipfile.ZipFile(target, "w") as z:
                z.writestr("manifest.json", json.dumps({"app": "MaplTajong", "format": 1, "counts": {"sounds": -1}, "app_version": []}))
            manifest = backup.read_manifest(target)
            self.assertEqual(manifest["counts"], {"sounds": 0, "schedule_sets": 0, "schedules": 0})
            self.assertEqual(manifest["app_version"], "")

    def test_backup_wrong_root_does_not_replace_existing_data(self):
        good = cloud_sync.build_config(self.conn)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "backup.zip"
            for data in ([], None, "text"):
                with zipfile.ZipFile(target, "w") as z:
                    z.writestr("manifest.json", json.dumps({"app": "MaplTajong", "format": 1}))
                    z.writestr("data.json", json.dumps(data))
                with self.assertRaises(backup.BackupError):
                    backup.import_backup(self.conn, target)
                self.assertEqual(cloud_sync.build_config(self.conn), good)

    def test_duration_cache_validates_each_item_and_caps_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            old = paths._sync_dir, paths._local_dir, sound_files._dur_loaded, sound_files._dur_cache
            paths.configure(root / "sync", root / "local")
            try:
                good = str(paths.sounds_dir() / "bell.wav")
                for bad in (float("nan"), float("inf"), -1, [], {}, "10", True):
                    sound_files._dur_loaded = False
                    sound_files._dur_cache = {}
                    data = {"broken": 1, f"{good}|1|1": bad, f"{root / 'outside.wav'}|1|1": 1, f"{good}|2|2": 1.5}
                    sound_files._dur_file().write_text(json.dumps(data), encoding="utf-8")
                    with self.assertLogs("tajong.validation", level="WARNING"):
                        sound_files._load_durations()
                    self.assertEqual(sound_files._dur_cache, {(good, 2, 2): 1.5})
                for data in ([], {f"{good}|{i}|1": 1 for i in range(501)}):
                    sound_files._dur_loaded = False
                    sound_files._dur_cache = {}
                    sound_files._dur_file().write_text(json.dumps(data), encoding="utf-8")
                    sound_files._load_durations()
                    self.assertLessEqual(len(sound_files._dur_cache), 500)
            finally:
                paths._sync_dir, paths._local_dir, sound_files._dur_loaded, sound_files._dur_cache = old

    def test_handled_requests_are_bounded_and_typed(self):
        for data in ([], {"ok": "2026-11-03T00:00:00Z", "bad": [], "huge": "x" * 5000, "x" * 129: "2026-11-03T00:00:00Z"},
                     {str(i): "2026-11-03T00:00:00Z" for i in range(2001)}):
            self.conn.execute("INSERT OR REPLACE INTO settings(key,value) VALUES('ring_handled',?)", (json.dumps(data),))
            with self.assertLogs("tajong.validation", level="WARNING"):
                clean = cloud_sync.CloudSync._load_handled(SimpleNamespace(conn=self.conn))
            self.assertLessEqual(len(clean), 2000)
            self.assertNotIn("bad", clean)
            if isinstance(data, dict) and "ok" in data:
                self.assertEqual(clean, {"ok": "2026-11-03T00:00:00Z"})


if __name__ == "__main__":
    unittest.main()
