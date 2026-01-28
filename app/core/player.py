from pathlib import Path
import pygame

class SoundPlayer:
    def __init__(self):
        pygame.mixer.init()
        self._loaded = None

    def play(self, path, volume):
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(str(p))
        pygame.mixer.music.load(str(p))
        pygame.mixer.music.set_volume(max(0.0, min(1.0, float(volume))))
        pygame.mixer.music.play()

    def stop(self):
        try:
            pygame.mixer.music.stop()
        except:
            pass
