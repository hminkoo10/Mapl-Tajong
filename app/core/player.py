import hashlib
import threading
import time
from pathlib import Path

import pygame

from app.core import ffmpeg
from app.core.paths import amp_cache_dir

AMP_CACHE_LIMIT = 400 * 1024 * 1024   # 키운 소리 보관 용량
LONG_SOUND_SEC = 300                   # 이보다 길면 wav 대신 ogg로 (용량 절약)


class SoundPlayer:
    def __init__(self):
        self._cache = {}
        self._ok = False
        self.current_path = None
        self.current_name = ""
        self.started_at = 0.0
        self._last_active = time.monotonic()
        self._amp_lock = threading.Lock()
        self._amp_busy = set()
        self._amp_queue = []
        self._amp_thread = None

    def _init_mixer(self):
        if self._ok:
            return True
        try:
            # 버퍼를 넉넉히 두면 소리 장치가 CPU를 덜 깨운다 (종소리는 지연에 민감하지 않다)
            pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            self._ok = True
            self._last_active = time.monotonic()
        except Exception:
            try:
                pygame.mixer.init()
                self._ok = True
            except Exception:
                self._ok = False
        return self._ok

    IDLE_RELEASE_SEC = 180
    PREWARM_SEC = 20

    def idle_tick(self, next_bell_in=None):
        """1초마다 호출. 오래 안 쓰면 소리 장치를 놓아 CPU를 아끼고, 다음 종이 가까우면 미리 켠다."""
        soon = next_bell_in is not None and next_bell_in <= self.PREWARM_SEC
        if soon:
            self._init_mixer()
            self._last_active = time.monotonic()
            return
        if not self._ok:
            return
        if self.is_playing():
            return
        if time.monotonic() - self._last_active >= self.IDLE_RELEASE_SEC:
            self.stop()
            try:
                pygame.mixer.quit()
            except Exception:
                pass
            self._ok = False

    # ---- 증폭(100% 초과 음량) ----
    # 키운 소리 파일은 시간이 걸릴 수 있어 항상 뒤에서 만든다. 화면이 멈추지 않도록 재생은 기다리지 않는다.
    def _amp_key(self, path, gain):
        p = Path(path)
        try:
            st = p.stat()
            stamp = f"{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            stamp = "0"
        return hashlib.sha1(f"{p}|{stamp}|{gain:.3f}".encode("utf-8")).hexdigest()

    def _amp_target(self, src, gain, key):
        stem = f"{src.stem[:40]}_x{int(round(gain * 100))}_{key[:10]}"
        d = amp_cache_dir()
        for ext in (".wav", ".ogg"):
            c = d / (stem + ext)
            if c.exists() and c.stat().st_size > 0:
                return c, True
        return d / stem, False

    def cached_amp(self, src_path, gain):
        src = Path(src_path)
        gain = min(2.0, float(gain))
        key = self._amp_key(src, gain)
        hit = self._cache.get(key)
        if hit and Path(hit).exists():
            return hit
        target, exists = self._amp_target(src, gain, key)
        if exists:
            self._cache[key] = str(target)
            return str(target)
        return None

    def prepare(self, src_path, gain):
        """증폭 파일을 만든다 (오래 걸릴 수 있으니 작업 스레드에서 호출)."""
        if gain is None or float(gain) <= 1.0 or not ffmpeg.available():
            return None
        src = Path(src_path)
        if not src.exists():
            return None
        gain = min(2.0, float(gain))
        hit = self.cached_amp(src, gain)
        if hit:
            return hit
        key = self._amp_key(src, gain)
        target, _ = self._amp_target(src, gain, key)
        dur = ffmpeg.probe_duration(src) or 0
        long = dur > LONG_SOUND_SEC
        dst = target.with_suffix(".ogg" if long else ".wav")
        tmp = dst.with_name(dst.stem + ".part" + dst.suffix)
        try:
            if long:
                r = ffmpeg._run(["-y", "-i", str(src), "-vn", "-af", f"volume={gain:.3f}", "-ar", "44100", "-ac", "2",
                                 "-c:a", "libvorbis", "-q:a", "6", str(tmp)], timeout=900, capture_stdout=False)
                if r.returncode != 0:
                    raise ffmpeg.FfmpegError(ffmpeg._tail(r.stderr))
            else:
                ffmpeg.render(src, tmp, f"volume={gain:.3f}")
            tmp.replace(dst)
        except Exception:
            tmp.unlink(missing_ok=True)
            return None
        self._cache[key] = str(dst)
        self._prune_amp_cache()
        return str(dst)

    def prepare_async(self, src_path, gain):
        if gain is None or float(gain) <= 1.0:
            return
        item = (str(src_path), min(2.0, float(gain)))
        if self.cached_amp(*item) or not Path(item[0]).exists():
            return
        with self._amp_lock:
            if item in self._amp_busy:
                return
            self._amp_busy.add(item)
            self._amp_queue.append(item)
            if self._amp_thread is None or not self._amp_thread.is_alive():
                self._amp_thread = threading.Thread(target=self._amp_worker, name="amp", daemon=True)
                self._amp_thread.start()

    def _amp_worker(self):
        while True:
            with self._amp_lock:
                if not self._amp_queue:
                    self._amp_thread = None
                    return
                item = self._amp_queue.pop(0)
            try:
                self.prepare(*item)
            except Exception:
                pass
            finally:
                with self._amp_lock:
                    self._amp_busy.discard(item)

    def _prune_amp_cache(self):
        try:
            files = sorted((f for f in amp_cache_dir().iterdir() if f.is_file()), key=lambda f: f.stat().st_mtime,
                           reverse=True)
        except OSError:
            return
        total = 0
        for f in files:
            try:
                total += f.stat().st_size
                if total > AMP_CACHE_LIMIT or ".part" in f.name:
                    f.unlink()
            except OSError:
                pass

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
            mixer_vol = 1.0
            amp = self.cached_amp(str(p), vol)
            if amp:
                src = amp
            else:
                # 아직 준비가 안 됐으면 우선 100%로 울리고, 다음부터 키운 소리를 쓴다
                self.prepare_async(str(p), vol)

        pygame.mixer.music.load(src)
        pygame.mixer.music.set_volume(mixer_vol)
        pygame.mixer.music.play()
        self._last_active = time.monotonic()
        self.current_path = str(p)
        self.current_name = name or p.stem
        self.started_at = time.monotonic()

    def is_playing(self):
        if not self._ok:
            return False
        try:
            busy = bool(pygame.mixer.music.get_busy())
        except Exception:
            return False
        if busy:
            self._last_active = time.monotonic()
        return busy

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
        stem = Path(str(path)).stem[:40] + "_x"
        for k, v in list(self._cache.items()):
            if Path(v).stem.startswith(stem):
                try:
                    Path(v).unlink()
                except OSError:
                    pass
                self._cache.pop(k, None)
