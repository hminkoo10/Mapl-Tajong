"""설정 파일 서명(app/core/data_sign.py)과 백업 파일 서명(app/core/backup.py) 시험.

안드로이드 DataSignTest 와 같은 고정 값으로 PC·안드로이드가 같은 서명을 만드는지 본다.

    python -m unittest tests.test_data_sign
"""
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import backup, data_sign, paths  # noqa: E402
from app.data.db import init_schema  # noqa: E402

# 안드로이드 app/src/test/.../DataSignTest.kt 와 같은 값
VECTOR_KEY = "test-key"
VECTOR_DOC = '{"app":"tajong","sig":"' + "0" * 64 + '","v":1}'
VECTOR_SIG = "04ea5198af2926906353ebd72e8967c86760cb18b8bebba19f1f7998ead70484"
KEY = "Zm9vYmFyLWtleS1mb3ItdGVzdHMtb25seS0xMjM0NTY3OA"   # 통합 클라우드가 주는 것과 같은 모양 (base64url)


class SignTests(unittest.TestCase):
    def test_fixed_vector(self):
        signed = data_sign.sign_bytes(VECTOR_DOC.encode("utf-8"), VECTOR_KEY)
        self.assertEqual(signed.decode("utf-8"), VECTOR_DOC.replace("0" * 64, VECTOR_SIG))
        self.assertTrue(data_sign.verify_bytes(signed, VECTOR_KEY))
        self.assertFalse(data_sign.verify_bytes(signed, "other-key"))
        self.assertFalse(data_sign.verify_bytes(VECTOR_DOC.encode("utf-8"), VECTOR_KEY))   # 0 그대로

    def test_signed_json_round_trip(self):
        doc = {"app": "MaplTajong", "kind": "config", "name": '1교시 "종" \\ /', "list": [1, 2.5, None]}
        raw = data_sign.dumps_signed(doc, KEY, ensure_ascii=False, indent=1)
        self.assertTrue(data_sign.verify_bytes(raw, KEY))
        back = json.loads(raw.decode("utf-8"))
        self.assertRegex(back.pop("sig"), r"^[0-9a-f]{64}$")
        self.assertEqual(back, doc)
        self.assertNotIn("sig", doc)                         # 넘긴 dict 는 그대로
        compact = data_sign.dumps_signed(doc, KEY, ensure_ascii=False, separators=(",", ":"))
        self.assertTrue(data_sign.verify_bytes(compact, KEY))

    def test_any_change_breaks_signature(self):
        raw = data_sign.dumps_signed({"app": "MaplTajong", "name": "1교시", "paused": False}, KEY,
                                     ensure_ascii=False, indent=1)
        sig = json.loads(raw)["sig"].encode()
        bad = [
            raw.replace("1교시".encode(), "2교시".encode()),     # 내용
            raw.replace(b"false", b"true"),
            b"\xef\xbb\xbf" + raw,                             # BOM 도 그대로 본다
            raw + b"\n",                                       # 공백도
            raw.replace(sig, b"0" * 64),                       # 서명 자리를 0 으로
            raw.replace(sig, sig[:-1] + (b"0" if sig[-1:] != b"0" else b"1")),
            raw.replace(b'{', b'{\n "sig": "' + sig + b'",', 1),   # 서명이 둘
            raw.replace(b'"sig"', b'"Sig"'),                   # 서명 없음
            raw.replace(sig, sig.upper()),                     # 대문자 16진수는 서명으로 보지 않음
            b"\xff" + raw,                                     # UTF-8 이 아님
        ]
        for b in bad:
            self.assertFalse(data_sign.verify_bytes(b, KEY), b[:80])
        # 키 이름과 값 사이 공백은 어떻게 써도 된다 (쓴 바이트 그대로 서명하므로)
        spaced = data_sign.sign_bytes(VECTOR_DOC.replace('"sig":', '"sig" :\n\t').encode(), VECTOR_KEY)
        self.assertTrue(data_sign.verify_bytes(spaced, VECTOR_KEY))

    def test_sign_needs_one_placeholder(self):
        with self.assertRaises(ValueError):
            data_sign.sign_bytes(b'{"app":"tajong"}', KEY)
        with self.assertRaises(ValueError):
            data_sign.sign_bytes(VECTOR_DOC.replace("0" * 64, VECTOR_SIG).encode(), KEY)

    def test_key_from_environment(self):
        with mock.patch.dict(os.environ, {data_sign.KEY_ENV: KEY}):
            self.assertEqual(data_sign.data_key(), KEY)
        with mock.patch.dict(os.environ, {data_sign.KEY_ENV: ""}):
            self.assertEqual(data_sign.data_key(), "")
        env = {k: v for k, v in os.environ.items() if k != data_sign.KEY_ENV}
        with mock.patch.dict(os.environ, env, clear=True):
            self.assertEqual(data_sign.data_key(), "")


SCHEMA = (ROOT / "app" / "data" / "schema.sql").read_text(encoding="utf-8")


def sample_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    init_schema(conn, SCHEMA)
    conn.execute("INSERT INTO sounds(id, name, file_name, volume) VALUES(5, 'bell1', 'bell1.wav', 1.0)")
    conn.execute("INSERT INTO schedule_sets(id, name) VALUES(3, '평일')")
    conn.execute("""INSERT INTO schedules(id, set_id, name, weekday_mask, time_hhmm, sound_id, enabled)
                    VALUES(7, 3, '1교시', 127, '09:00', 5, 1)""")
    conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('active_set_id', '3')")
    conn.commit()
    return conn


def names(conn):
    return [r[0] for r in conn.execute("SELECT name FROM schedules ORDER BY id")]


class BackupSignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tajong_sign_"))
        paths.configure(self.tmp / "sync", self.tmp / "local")
        (paths.sounds_dir() / "bell1.wav").write_bytes(b"bell")
        self.conn = sample_db()

    def tearDown(self):
        self.conn.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def export(self, key):
        dst = self.tmp / f"backup_{len(list(self.tmp.glob('*.zip')))}.zip"
        with mock.patch.dict(os.environ, {data_sign.KEY_ENV: key}):
            backup.export_backup(self.conn, dst)
        return dst

    def rewrite_data(self, src, fn):
        """zip 안의 data.json 을 손으로 고친 것처럼 바꾼다."""
        dst = src.with_name("edited_" + src.name)
        with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w") as zout:
            for item in zin.infolist():
                data = zin.read(item.filename)
                zout.writestr(item, fn(data) if item.filename == "data.json" else data)
        return dst

    def restore(self, src, key):
        with mock.patch.dict(os.environ, {data_sign.KEY_ENV: key}):
            backup.read_manifest(src)
            return backup.import_backup(self.conn, src)

    def test_signed_backup_restores(self):
        src = self.export(KEY)
        with zipfile.ZipFile(src) as z:
            raw = z.read("data.json")
        self.assertTrue(data_sign.verify_bytes(raw, KEY))
        self.conn.execute("UPDATE schedules SET name='바뀜'")
        self.conn.commit()
        self.assertEqual(self.restore(src, KEY)["schedules"], 1)
        self.assertEqual(names(self.conn), ["1교시"])

    def test_edited_or_unsigned_backup_refused(self):
        signed = self.export(KEY)
        edited = self.rewrite_data(signed, lambda b: b.replace("1교시".encode(), "가짜 교시".encode()))
        unsigned = self.export("")                         # 서명하기 전 버전이 만든 백업
        stripped = self.rewrite_data(signed, lambda b: json.dumps(
            {k: v for k, v in json.loads(b).items() if k != "sig"}, ensure_ascii=False).encode())
        other_key = self.export("another-key")
        self.conn.execute("UPDATE schedules SET name='지금'")
        self.conn.commit()
        for src in (edited, unsigned, stripped, other_key):
            with mock.patch.dict(os.environ, {data_sign.KEY_ENV: KEY}):
                with self.assertRaises(backup.BackupError) as e:
                    backup.read_manifest(src)
                self.assertEqual(str(e.exception), backup.TAMPERED_MSG)
                with self.assertRaises(backup.BackupError):
                    backup.import_backup(self.conn, src)
        self.assertEqual(names(self.conn), ["지금"])        # 아무것도 바꾸지 않음

    def test_signing_off_is_old_behaviour(self):
        signed = self.export(KEY)
        unsigned = self.export("")
        with zipfile.ZipFile(unsigned) as z:
            self.assertNotIn("sig", json.loads(z.read("data.json")))
        edited = self.rewrite_data(unsigned, lambda b: b.replace("1교시".encode(), "고친 교시".encode()))
        self.restore(edited, "")
        self.assertEqual(names(self.conn), ["고친 교시"])
        # 서명한 백업도 서명을 쓰지 않는 쪽(예전 버전과 같음)에서 그대로 불러온다 (sig 는 무시)
        self.restore(signed, "")
        self.assertEqual(names(self.conn), ["1교시"])


if __name__ == "__main__":
    unittest.main()
