"""종소리 파일을 동기화 폴더에 원자적으로 쓰는지 (<이름>.tmp 에 다 쓴 뒤 이름 바꾸기) 시험.

    python -m unittest tests.test_sound_files
"""
import shutil
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core import ffmpeg, paths, sound_files  # noqa: E402

BELL = ROOT / "app" / "assets" / "sounds" / "bell1.wav"


class AtomicWriteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tajong_snd_"))
        paths.configure(self.tmp / "sync", self.tmp / "local")
        self.sounds = paths.sounds_dir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def leftovers(self):
        return sorted(p.name for p in self.sounds.iterdir() if p.name.endswith(".tmp"))

    def test_write_goes_through_tmp_in_same_folder(self):
        dst = self.sounds / "a.wav"
        seen = []

        def produce(tmp):
            seen.append(Path(tmp))
            self.assertFalse(dst.exists())          # 다 쓰기 전에는 최종 이름이 없다
            Path(tmp).write_bytes(b"done")
        self.assertEqual(sound_files.write_atomic(dst, produce), dst)
        self.assertEqual(seen, [self.sounds / "a.wav.tmp"])
        self.assertEqual(dst.read_bytes(), b"done")
        self.assertEqual(self.leftovers(), [])

    def test_failure_keeps_old_file_and_removes_tmp(self):
        dst = self.sounds / "a.wav"
        dst.write_bytes(b"old")

        def produce(tmp):
            Path(tmp).write_bytes(b"half")
            raise RuntimeError("변환 실패")
        with self.assertRaises(RuntimeError):
            sound_files.write_atomic(dst, produce)
        self.assertEqual(dst.read_bytes(), b"old")
        self.assertEqual(self.leftovers(), [])

    def test_copy_atomic_replaces_existing(self):
        dst = self.sounds / "bell1.wav"
        dst.write_bytes(b"old")
        sound_files.copy_atomic(BELL, dst)
        self.assertEqual(dst.read_bytes(), BELL.read_bytes())
        self.assertEqual(self.leftovers(), [])

    def test_import_playable_file(self):
        dst = sound_files.import_file(BELL)
        self.assertEqual(dst, self.sounds / "bell1.wav")
        self.assertEqual(dst.read_bytes(), BELL.read_bytes())
        self.assertEqual(sound_files.import_file(BELL).name, "bell1_2.wav")
        self.assertEqual(self.leftovers(), [])

    @unittest.skipUnless(ffmpeg.available(), "ffmpeg 없음")
    def test_ffmpeg_render_to_tmp_path_is_wav(self):
        out = self.tmp / "x.wav.tmp"
        ffmpeg.render(BELL, out)
        with wave.open(str(out), "rb") as w:
            self.assertGreater(w.getnframes(), 0)

    @unittest.skipUnless(ffmpeg.available(), "ffmpeg 없음")
    def test_import_with_conversion(self):
        src = self.tmp / "종소리.flac"             # 바로 재생할 수 없는 확장자 → wav 로 변환
        shutil.copy2(BELL, src)
        dst = sound_files.import_file(src)
        self.assertEqual(dst, self.sounds / "종소리.wav")
        with wave.open(str(dst), "rb") as w:
            self.assertEqual(w.getsampwidth(), 2)
        self.assertEqual(self.leftovers(), [])

    def test_leftover_tmp_removed(self):
        (self.sounds / "keep.wav").write_bytes(b"x")
        (self.sounds / "crash.wav.tmp").write_bytes(b"half")
        self.assertEqual(sound_files.remove_leftover_tmp(self.sounds), 1)
        self.assertEqual(sorted(p.name for p in self.sounds.iterdir()), ["keep.wav"])


if __name__ == "__main__":
    unittest.main()
