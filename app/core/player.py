import hashlib
import time
import wave
from pathlib import Path

import pygame

from app.core import ffmpeg
from app.core.paths import amp_cache_dir

try:  # Python 3.13부터 audioop가 제거됨
    import audioop
except ImportError:
    audioop = None


class SoundPlayer:
    def __init__(self):
        self._cache = {}
        self._ok = False
        self.current_path = None
        self.current_name = ""
        self.started_at = 0.0
        self._init_mixer()

    def _init_mixer(self):
        if self._ok:
            return True
        try:
            pygame.mixer.init()
            self._ok = True
        except Exception:
            self._ok = False
        return self._ok

    # ---- 증폭(100% 초과 음량) ----
    def _amp_key(self, path, gain):
        p = Path(path)
        try:
            st = p.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            stamp = "0"
        return hashlib.sha1(f"{p}|{stamp}|{gain:.3f}".encode("utf-8")).hexdigest()

    def _amplified(self, src_path, gain):
        src = Path(src_path)
        gain = min(2.0, float(gain))
        key = self._amp_key(src, gain)
        cached = self._cache.get(key)
        if cached and Path(cached).exists():
            return cached

        dst = amp_cache_dir() / f"{src.stem}_x{int(gain * 100)}_{key[:10]}.wav"
        if dst.exists():
            self._cache[key] = str(dst)
            return str(dst)

        done = False
        if src.suffix.lower() == ".wav" and audioop is not None:
            try:
                with wave.open(str(src), "rb") as wf:
                    params = wf.getparams()
                    frames = wf.readframes(wf.getnframes())
                boosted = audioop.mul(frames, params.sampwidth, gain)
                with wave.open(str(dst), "wb") as out:
                    out.setnchannels(params.nchannels)
                    out.setsampwidth(params.sampwidth)
                    out.setframerate(params.framerate)
                    out.writeframes(boosted)
                done = True
            except Exception:
                done = False
        if not done and ffmpeg.available():
            try:
                ffmpeg.amplify(src, dst, gain)
                done = True
            except Exception:
                done = False
        if not done:
            return None
        self._cache[key] = str(dst)
        return str(dst)

    # ---- 재생 ----
    def play(self, path, volume, name=""):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        if not self._init_mixer():
            raise RuntimeError("오디오 장치를 초기화할 수 없습니다. 스피커 연결을 확인해 주세요.")

        vol = 1.0 if volume is None else max(0.0, min(2.0, float(volume)))
        src, mixer_vol = str(p), vol
        if vol > 1.0:
            amp = self._amplified(str(p), vol)
            if amp:
                src, mixer_vol = amp, 1.0
            else:
                mixer_vol = 1.0

        pygame.mixer.music.load(src)
        pygame.mixer.music.set_volume(mixer_vol)
        pygame.mixer.music.play()
        self.current_path = str(p)
        self.current_name = name or p.stem
        self.started_at = time.monotonic()

    def is_playing(self):
        if not self._ok:
            return False
        try:
            return bool(pygame.mixer.music.get_busy())
        except Exception:
            return False

    def elapsed(self):
        return time.monotonic() - self.started_at if self.is_playing() else 0.0

    def stop(self):
        if not self._ok:
            return
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        try:
            pygame.mixer.music.unload()
        except Exception:
            pass
        self.current_path = None
        self.current_name = ""

    def release(self, path=None):
        """파일을 덮어쓰거나 지우기 전에 호출 (Windows 파일 잠금 해제)."""
        self.stop()
        if path is None:
            return
        key_path = str(Path(path))
        for k, v in list(self._cache.items()):
            if Path(v).stem.startswith(Path(key_path).stem + "_x"):
                try:
                    Path(v).unlink()
                except OSError:
                    pass
                self._cache.pop(k, None)
