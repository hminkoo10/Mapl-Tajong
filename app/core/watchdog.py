"""멈춤·충돌 기록.

- 프로그램이 갑자기 꺼지면(파이썬 밖의 충돌) crash.log 에 그 순간의 호출 위치를 남긴다.
- 화면이 8초 넘게 응답하지 않으면 hang.log 에 무엇을 하느라 멈췄는지 남긴다.
문제가 다시 생겼을 때 이 파일들로 원인을 바로 찾을 수 있다.
"""
import faulthandler
import threading
import time
from datetime import datetime

_crash_file = None


def enable_crash_log(log_dir):
    global _crash_file
    try:
        _crash_file = open(log_dir / "crash.log", "a", encoding="utf-8")
        _crash_file.write(f"\n=== 시작 {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
        _crash_file.flush()
        faulthandler.enable(file=_crash_file, all_threads=True)
    except Exception:
        _crash_file = None


class HangWatch:
    def __init__(self, log_dir, threshold=8.0):
        self.path = log_dir / "hang.log"
        self.threshold = threshold
        self._beat = time.monotonic()
        self._reported = False
        self._stop = threading.Event()
        self._thread = None

    def pulse(self):
        """화면 스레드에서 주기적으로 호출."""
        self._beat = time.monotonic()

    def start(self):
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="hangwatch", daemon=True)
            self._thread.start()

    def stop(self):
        self._stop.set()

    def _loop(self):
        last = time.monotonic()
        while not self._stop.wait(2.0):
            now = time.monotonic()
            if now - last > 6.0:
                # 컴퓨터가 절전에서 깨어난 경우: 멈춘 것이 아니다
                self._beat = now
            last = now
            stalled = now - self._beat
            if stalled < self.threshold:
                self._reported = False
                continue
            if self._reported:
                continue
            self._reported = True
            self._write(stalled)

    def _write(self, stalled):
        try:
            if self.path.exists() and self.path.stat().st_size > 512 * 1024:
                self.path.write_text("", encoding="utf-8")
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} 화면이 {stalled:.0f}초째 응답 없음 ===\n")
                f.flush()
                faulthandler.dump_traceback(file=f, all_threads=True)
        except Exception:
            pass
