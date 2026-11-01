from PyQt6.QtCore import QObject, pyqtSignal


class AppContext(QObject):
    """페이지들이 공유하는 상태와 신호."""
    data_changed = pyqtSignal(str)        # 'sounds' | 'schedules' | 'sets' | 'state' | 'logs' | 'all'
    rang = pyqtSignal(object, bool)       # (NextEvent, forced)
    scheduler_event = pyqtSignal(str, object)

    def __init__(self, conn, player, scheduler, window=None):
        super().__init__()
        self.conn = conn
        self.player = player
        self.scheduler = scheduler
        self.window = window
        self.toasts = None
        self.sync = None                  # CloudSync (통합 클라우드 동기화)
        scheduler.on_ring = lambda ev, forced: self.rang.emit(ev, forced)
        scheduler.on_event = lambda kind, ev: self.scheduler_event.emit(kind, ev)

    def toast(self, text, kind="info", ms=2600, action_text=None, on_action=None):
        if self.toasts:
            self.toasts.show(text, kind, ms, action_text, on_action)

    def changed(self, what="all"):
        """이 기기에서 데이터를 바꾼 뒤: 화면을 맞추고 함께 쓰는 데이터를 내보낸다."""
        self.scheduler.invalidate()
        self.scheduler.recompute_next()
        self.data_changed.emit(what)
        if self.sync is not None:
            self.sync.local_changed(what)

    def remote_changed(self, what="all"):
        """다른 기기에서 바뀐 것을 적용한 뒤: 화면만 맞춘다 (다시 내보내지 않음)."""
        self.scheduler.invalidate()
        self.scheduler.recompute_next()
        self.data_changed.emit(what)
