from pathlib import Path
import hashlib
import wave
import audioop
import pygame
from app.core.paths import amp_cache_dir

class SoundPlayer:
    def __init__(self):
        pygame.mixer.init()
        self._cache = {}

    def _amp_key(self, path, gain):
        s = f"{path}|{gain:.3f}".encode("utf-8")
        return hashlib.sha1(s).hexdigest()

    def _amplify_wav(self, src_path, gain):
        src = Path(src_path)
        if src.suffix.lower() != ".wav":
            return str(src)

        if gain <= 1.0:
            return str(src)

        if gain > 2.0:
            gain = 2.0

        key = self._amp_key(str(src), gain)
        cached = self._cache.get(key)
        if cached and Path(cached).exists():
            return cached

        dst = amp_cache_dir() / f"{src.stem}_x{int(gain*100)}_{key[:8]}.wav"
        if dst.exists():
            self._cache[key] = str(dst)
            return str(dst)

        with wave.open(str(src), "rb") as wf:
            nch = wf.getnchannels()
            sw = wf.getsampwidth()
            fr = wf.getframerate()
            nframes = wf.getnframes()
            frames = wf.readframes(nframes)

        boosted = audioop.mul(frames, sw, float(gain))

        with wave.open(str(dst), "wb") as out:
            out.setnchannels(nch)
            out.setsampwidth(sw)
            out.setframerate(fr)
            out.writeframes(boosted)

        self._cache[key] = str(dst)
        return str(dst)

    def play(self, path, volume):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))

        vol = float(volume) if volume is not None else 1.0
        if vol < 0.0:
            vol = 0.0
        if vol > 2.0:
            vol = 2.0

        src = str(p)
        if vol > 1.0:
            src = self._amplify_wav(str(p), vol)
            pygame.mixer.music.load(src)
            pygame.mixer.music.set_volume(1.0)
            pygame.mixer.music.play()
            return

        pygame.mixer.music.load(src)
        pygame.mixer.music.set_volume(vol)
        pygame.mixer.music.play()

    def stop(self):
        try:
            pygame.mixer.music.stop()
        except:
            pass
        try:
            pygame.mixer.music.unload()
        except:
            pass