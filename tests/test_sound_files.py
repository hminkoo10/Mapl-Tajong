"""종소리 파일을 동기화 폴더에 원자적으로 쓰는지 (<이름>.tmp 에 다 쓴 뒤 이름 바꾸기) 시험.

    python -m unittest tests.test_sound_files
"""
import math
import re
import shutil
import struct
import sys
import tempfile
import threading
import unittest
import wave
from pathlib import Path
from unittest import mock

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


def _probe(path):
    """ffmpeg 가 읽은 (코덱, 샘플레이트, 길이초)"""
    r = ffmpeg._run(["-i", str(path)], timeout=20, capture_stdout=False)
    text = (r.stderr or b"").decode("utf-8", "replace")
    m = re.search(r"Audio:\s*(\w+).*?(\d+) Hz", text)
    return (m.group(1), int(m.group(2))) if m else (None, None), ffmpeg.probe_duration(path)


def _sine_wav(path, rate, seconds, channels=1):
    n = int(rate * seconds)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        frame = lambda i: struct.pack("<h", int(12000 * math.sin(2 * math.pi * 440 * i / rate))) * channels
        w.writeframes(b"".join(frame(i) for i in range(n)))


def _long_flac(path, seconds):
    """긴 종소리 (사인파 FLAC 은 작아서 빨리 만든다)"""
    r = ffmpeg._run(["-y", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}:sample_rate=44100", "-ac", "2",
                     "-c:a", "flac", str(path)], timeout=60, capture_stdout=False)
    assert r.returncode == 0, ffmpeg._tail(r.stderr)
    return path


@unittest.skipUnless(ffmpeg.available(), "ffmpeg 없음")
class Mp3ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="tajong_mp3_"))
        paths.configure(self.tmp / "sync", self.tmp / "local")
        self.out_dir = self.tmp / "내 문서"          # 한글·빈칸이 있는 폴더에도 저장
        self.out_dir.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def leftovers(self):
        return sorted(p.name for p in self.out_dir.iterdir() if p.name.endswith(".tmp"))

    def test_wav_becomes_playable_mp3_of_same_length(self):
        dst = self.out_dir / "1교시 종.mp3"
        self.assertEqual(sound_files.export_mp3(BELL, dst), dst)
        (codec, rate), dur = _probe(dst)
        self.assertEqual(codec, "mp3")
        self.assertEqual(rate, 44100)
        with wave.open(str(BELL), "rb") as w:
            wav_dur = w.getnframes() / w.getframerate()
        self.assertAlmostEqual(dur, wav_dur, delta=0.1)
        self.assertEqual(self.leftovers(), [])

    def test_high_sample_rate_wav_is_converted(self):
        src = self.tmp / "hi.wav"                  # MP3 가 받지 않는 96kHz 도 저장된다
        _sine_wav(src, 96000, 1.5)
        dst = sound_files.export_mp3(src, self.out_dir / "hi.mp3")
        (codec, rate), dur = _probe(dst)
        self.assertEqual(codec, "mp3")
        self.assertLessEqual(rate, 48000)
        self.assertAlmostEqual(dur, 1.5, delta=0.1)

    def test_mp3_is_copied_without_converting_again(self):
        src = paths.sounds_dir() / "already.mp3"
        ffmpeg.encode_mp3(BELL, src)
        dst = sound_files.export_mp3(src, self.out_dir / "copy.mp3")
        self.assertEqual(dst.read_bytes(), src.read_bytes())

    def test_overwrites_existing_file(self):
        dst = self.out_dir / "old.mp3"
        dst.write_bytes(b"old")
        sound_files.export_mp3(BELL, dst)
        self.assertEqual(_probe(dst)[0][0], "mp3")
        self.assertEqual(self.leftovers(), [])

    def test_failure_keeps_existing_file_and_removes_tmp(self):
        bad = self.tmp / "broken.wav"
        bad.write_bytes(b"not a sound")
        dst = self.out_dir / "keep.mp3"
        dst.write_bytes(b"old")
        with self.assertRaises(ffmpeg.FfmpegError):
            sound_files.export_mp3(bad, dst)
        self.assertEqual(dst.read_bytes(), b"old")
        self.assertEqual(self.leftovers(), [])

    def test_missing_sound_file(self):
        with self.assertRaises(FileNotFoundError):
            sound_files.export_mp3(self.tmp / "없음.wav", self.out_dir / "x.mp3")
        self.assertEqual(list(self.out_dir.iterdir()), [])

    def test_reports_progress_until_done(self):
        src = _long_flac(self.tmp / "긴 종.flac", 180)
        seen = []
        dst = sound_files.export_mp3(src, self.out_dir / "긴 종.mp3", on_progress=seen.append)
        self.assertEqual(seen[-1], 1.0)
        self.assertEqual(seen, sorted(seen))                      # 뒤로 가지 않는다
        self.assertTrue(all(0.0 <= f <= 1.0 for f in seen))
        self.assertTrue(any(0.0 < f < 1.0 for f in seen), seen)   # 중간 진행도 알린다
        self.assertAlmostEqual(_probe(dst)[1], 180, delta=0.2)

    def test_cancel_midway_removes_half_made_file_and_keeps_old_one(self):
        src = _long_flac(self.tmp / "긴 종.flac", 180)
        dst = self.out_dir / "keep.mp3"
        dst.write_bytes(b"old")
        cancel = threading.Event()
        seen = []

        def progress(f):
            seen.append(f)
            if f < 1.0:
                cancel.set()
        with self.assertRaises(ffmpeg.Cancelled):
            sound_files.export_mp3(src, dst, on_progress=progress, cancel=cancel)
        self.assertTrue(seen and seen[-1] < 1.0)
        self.assertEqual(dst.read_bytes(), b"old")
        self.assertEqual(self.leftovers(), [])

    def test_cancel_before_start(self):
        cancel = threading.Event()
        cancel.set()
        for src in (BELL, paths.sounds_dir() / "already.mp3"):
            if src.suffix == ".mp3":
                shutil.copy2(BELL, src)
            with self.assertRaises(ffmpeg.Cancelled):
                sound_files.export_mp3(src, self.out_dir / "x.mp3", cancel=cancel)
        self.assertEqual(list(self.out_dir.iterdir()), [])

    @unittest.skipUnless(sys.platform == "win32", "Windows 우선순위")
    def test_runs_below_bell_priority(self):
        with mock.patch.object(ffmpeg.subprocess, "Popen", wraps=ffmpeg.subprocess.Popen) as popen:
            sound_files.export_mp3(BELL, self.out_dir / "1.mp3")
        flags = popen.call_args.kwargs["creationflags"]
        self.assertTrue(flags & 0x00004000)                       # BELOW_NORMAL_PRIORITY_CLASS: 종소리가 먼저


class DurationFormatTests(unittest.TestCase):
    def test_sound_list_shows_hours_from_one_hour(self):
        f = sound_files.format_duration
        self.assertEqual(f(None), "-")
        self.assertEqual(f(5.5), "5.5초")
        self.assertEqual(f(75.2), "1:15")
        self.assertEqual(f(59 * 60 + 59.4), "59:59")       # 1시간 아래는 예전 그대로
        self.assertEqual(f(3600), "1:00:00")
        self.assertEqual(f(75 * 60 + 3), "1:15:03")        # 예전에는 75:03
        self.assertEqual(f(10 * 3600 + 5), "10:00:05")

    def test_editor_time_shows_hours_from_one_hour(self):
        from app.ui.sound_editor import _fmt   # PyQt6 가 있어야 불러올 수 있다
        self.assertEqual(_fmt(5.5), "5.50초")
        self.assertEqual(_fmt(75.2), "1:15.20")
        self.assertEqual(_fmt(59 * 60 + 59.4), "59:59.40")
        self.assertEqual(_fmt(3600), "1:00:00.00")
        self.assertEqual(_fmt(75 * 60 + 3.25), "1:15:03.25")


if __name__ == "__main__":
    unittest.main()
