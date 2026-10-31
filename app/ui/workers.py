"""백그라운드 작업 스레드 (UI가 멈추지 않도록)."""
import threading
import urllib.request

from PyQt6.QtCore import QThread, pyqtSignal

_live = set()


def keep_alive(th):
    """실행 중인 QThread가 GC되어 크래시 나는 것을 막는다."""
    _live.add(th)
    th.finished.connect(lambda: _live.discard(th))
    return th


class FuncThread(QThread):
    done = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self.fn = fn
        self.args = args
        self.kwargs = kwargs

    def run(self):
        try:
            self.done.emit(self.fn(*self.args, **self.kwargs))
        except Exception as e:
            self.failed.emit(str(e) or e.__class__.__name__)


def run_async(fn, *args, on_done=None, on_fail=None, **kwargs):
    th = FuncThread(fn, *args, **kwargs)
    if on_done:
        th.done.connect(on_done)
    if on_fail:
        th.failed.connect(on_fail)
    keep_alive(th)
    th.start()
    return th


class DownloadThread(QThread):
    progress = pyqtSignal(float, str)
    done = pyqtSignal(str, str)   # path, title
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(self, url, out_dir, browser=None):
        super().__init__()
        self.url = url
        self.out_dir = out_dir
        self.browser = browser
        self.cancel_event = threading.Event()

    def cancel(self):
        self.cancel_event.set()

    def run(self):
        from app.core import youtube
        try:
            path, title = youtube.download_audio(self.url, self.out_dir,
                                                 lambda f, s: self.progress.emit(float(f), s), self.cancel_event,
                                                 self.browser)
            self.done.emit(str(path), str(title))
        except youtube.Cancelled:
            self.cancelled.emit()
        except Exception as e:
            self.failed.emit(str(e))


class ThumbThread(QThread):
    loaded = pyqtSignal(int, bytes)

    def __init__(self, items):
        super().__init__()
        self.items = list(items)  # [(index, url)]
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        for i, url in self.items:
            if self._stop:
                return
            if not url:
                continue
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=6) as r:
                    data = r.read(400_000)
                if not self._stop:
                    self.loaded.emit(i, data)
            except Exception:
                pass
