from PyQt6.QtCore import QObject, pyqtSignal


class AppContext(QObject):
    """페이지들이 공유하는 상태와 신호."""
    data_changed = pyqtSignal(str)        # 'sounds' | 'schedules' | 'sets' | 'logs' | 'all'
    rang = pyqtSignal(object, bool)       # (NextEvent, forced)
    scheduler_event = pyqtSignal(str, object)

    def __init__(self, conn, player, scheduler, window=None):
        super().__init__()
        self.conn = conn
        self.player = player
        self.scheduler = scheduler
        self.window = window
        self.toasts = None
        self.updates = None
        scheduler.on_ring = lambda ev, forced: self.rang.emit(ev, forced)
        scheduler.on_event = lambda kind, ev: self.scheduler_event.emit(kind, ev)

    def toast(self, text, kind="info", ms=2600, action_text=None, on_action=None):
        if self.toasts:
            self.toasts.show(text, kind, ms, action_text, on_action)

    def changed(self, what="all"):
        self.scheduler.invalidate()
        self.scheduler.recompute_next()
        self.data_changed.emit(what)
