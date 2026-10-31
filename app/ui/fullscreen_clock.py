"""교실 모니터·TV용 전체화면 시계."""
import math
import time
from datetime import datetime

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QRadialGradient
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.core.timeutil import format_remaining
from app.ui.pages.dashboard import STATUS, WEEK_KO, when_text
from app.ui.theme import font, qc
from app.ui.widgets import CountdownRing, Button, RollingClock, TickingWidget, ease_out_cubic, ticker


class _UpcomingStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.setMinimumHeight(110)

    def set_items(self, items):
        self.items = items[:5]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.items:
            p.setPen(qc("#FFFFFF", 0.55))
            p.setFont(font(max(14, self.height() * 0.2), QFont.Weight.DemiBold))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "오늘 남은 종이 없어요")
            return
        n = len(self.items)
        gap = 16
        w = min(300.0, (self.width() - gap * (n - 1)) / n)
        total = w * n + gap * (n - 1)
        x = (self.width() - total) / 2
        h = self.height() - 8
        for i, ev in enumerate(self.items):
            r = QRectF(x, 4, w, h)
            nxt = ev["status"] == "next"
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc("#FFFFFF", 0.10 if nxt else 0.05))
            p.drawRoundedRect(r, 20, 20)
            p.setPen(qc("#FFFFFF"))
            p.setFont(font(h * 0.28, QFont.Weight.Bold))
            p.drawText(QRectF(r.left() + 18, r.top() + 8, r.width() - 36, h * 0.42), Qt.AlignmentFlag.AlignVCenter,
                       ev["time"])
            p.setFont(font(h * 0.16, QFont.Weight.DemiBold))
            p.setPen(qc("#FFFFFF", 0.85))
            fm = QFontMetricsF(p.font())
            p.drawText(QRectF(r.left() + 18, r.top() + h * 0.50, r.width() - 36, h * 0.24), Qt.AlignmentFlag.AlignVCenter,
                       fm.elidedText(ev["name"], Qt.TextElideMode.ElideRight, r.width() - 36))
            label = STATUS.get(ev["status"], STATUS["upcoming"])[0]
            p.setFont(font(h * 0.13, QFont.Weight.Medium))
            p.setPen(qc("#FFB27A" if nxt else "#FFFFFF", 0.95 if nxt else 0.5))
            p.drawText(QRectF(r.left() + 18, r.top() + h * 0.74, r.width() - 36, h * 0.2), Qt.AlignmentFlag.AlignVCenter,
                       f"{label}  ·  {ev['sound']}")
            x += w + gap


class FullscreenClock(TickingWidget):
    def __init__(self, ctx, screen=None):
        super().__init__(None)
        self.ctx = ctx
        self.setWindowTitle("전체화면 시계")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self._flash = None
        self._ui_k = 0.0
        self._last_move = time.monotonic()
        self._last_paint = 0
        self._opening = time.monotonic()
        if screen is not None:
            self.setScreen(screen)
            self.setGeometry(screen.geometry())

        root = QVBoxLayout(self)
        root.setContentsMargins(60, 36, 60, 40)
        root.setSpacing(0)

        top = QHBoxLayout()
        self.date_label = QLabel("")
        top.addWidget(self.date_label)
        top.addStretch(1)
        self.btn_close = Button("닫기", variant="hero")
        self.btn_close.clicked.connect(self.close)
        top.addWidget(self.btn_close)
        root.addLayout(top)
        root.addStretch(1)

        mid = QHBoxLayout()
        mid.setSpacing(60)
        lc = QVBoxLayout()
        lc.setSpacing(6)
        self.clock = RollingClock(160, "#FFFFFF", QFont.Weight.Bold)
        lc.addWidget(self.clock)
        self.state = QLabel("")
        lc.addWidget(self.state)
        mid.addStretch(1)
        mid.addLayout(lc)
        self.ring = CountdownRing(size=320, thickness=18, on_dark=True)
        rc = QVBoxLayout()
        rc.setSpacing(8)
        rc.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignHCenter)
        self.next_name = QLabel("")
        self.next_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rc.addWidget(self.next_name)
        self.next_when = QLabel("")
        self.next_when.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rc.addWidget(self.next_when)
        mid.addLayout(rc)
        mid.addStretch(1)
        root.addLayout(mid)
        root.addStretch(1)

        self.strip = _UpcomingStrip()
        root.addWidget(self.strip)

        self._timer = QTimer(self)
        self._timer.setInterval(200)
        self._timer.timeout.connect(self.refresh)
        self._timer.start()
        self._ev_timer = QTimer(self)
        self._ev_timer.setInterval(3000)
        self._ev_timer.timeout.connect(self._refresh_events)
        self._ev_timer.start()
        ctx.rang.connect(self._on_rang)
        self._events = []
        self._apply_sizes()
        self._refresh_events()
        self.refresh()

    # ---------- 크기 ----------
    def _apply_sizes(self):
        h = max(600, self.height() or 900)
        w = max(800, self.width() or 1400)
        portrait = h > w
        self.clock.set_px(int(min(h * 0.20, w * (0.13 if not portrait else 0.18))))
        self.ring.set_size(int(min(h * 0.36, w * 0.28)))
        self.ring.thickness = max(10, int(h * 0.013))
        self.date_label.setStyleSheet(f"color: rgba(255,255,255,0.6); font-size: {int(h * 0.026)}px; font-weight: 600;")
        self.state.setStyleSheet(f"color: rgba(255,255,255,0.5); font-size: {int(h * 0.022)}px;")
        self.next_name.setStyleSheet(f"color: #FFFFFF; font-size: {int(h * 0.034)}px; font-weight: 700;")
        self.next_when.setStyleSheet(f"color: rgba(255,255,255,0.6); font-size: {int(h * 0.022)}px;")
        self.strip.setFixedHeight(int(h * 0.16))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_sizes()

    # ---------- 데이터 ----------
    def _refresh_events(self):
        try:
            evs = self.ctx.scheduler.today_events()
        except Exception:
            evs = []
        self._events = evs
        self.strip.set_items([e for e in evs if e["status"] in ("next", "upcoming", "will_skip", "paused")])

    def refresh(self):
        now = datetime.now()
        self.clock.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(f"{now.year}년 {now.month}월 {now.day}일 {WEEK_KO[now.weekday()]}요일")
        sch = self.ctx.scheduler
        ev = sch.next_event
        if ev:
            remain = (ev.run_at - now).total_seconds()
            prev = now.replace(hour=0, minute=0, second=0, microsecond=0)
            for e in self._events:
                if prev < e["run_at"] <= now:
                    prev = e["run_at"]
            total = max(1.0, (ev.run_at - prev).total_seconds())
            urgent = 0 <= remain <= 60
            self.ring.set_state(1 - max(0.0, remain) / total, format_remaining(remain, short=True), "남음", urgent)
            self.next_name.setText(ev.name)
            self.next_when.setText(f"{when_text(ev.run_at, now)}  ·  {ev.sound_name}")
        else:
            self.ring.set_state(0, "--:--", "")
            self.next_name.setText("예정된 종이 없어요")
            self.next_when.setText("")
        if sch.paused:
            self.state.setText("잠시 멈춤")
        else:
            from app.data import repo
            self.state.setText("오늘은 쉬는 날" if repo.is_pause_today(self.ctx.conn, now.strftime("%Y-%m-%d"))
                               else "")
        idle = time.monotonic() - self._last_move
        self.btn_close.setVisible(idle < 3.0)
        self.setCursor(Qt.CursorShape.BlankCursor if idle > 3.0 else Qt.CursorShape.ArrowCursor)

    def _on_rang(self, ev, forced):
        try:
            self.ring.burst()
            self._flash = ticker().now()
            self._refresh_events()
        except RuntimeError:
            pass

    # ---------- 입력 ----------
    def mouseMoveEvent(self, e):
        self._last_move = time.monotonic()
        super().mouseMoveEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.close()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        try:
            self.ctx.rang.disconnect(self._on_rang)
        except (TypeError, RuntimeError):
            pass
        self._timer.stop()
        self._ev_timer.stop()
        super().closeEvent(e)

    # ---------- 그리기 ----------
    def on_frame(self, t):
        if t - self._last_paint >= 1 / 30:
            self._last_paint = t
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        t = ticker().now()
        p.fillRect(r, QColor("#121316"))
        # 아래쪽에서 은은하게 번지는 주황빛 (아주 천천히 숨쉬듯)
        breathe = 0.9 + 0.1 * math.sin(t * 0.4)
        rg = QRadialGradient(QPointF(r.center().x(), r.bottom() + r.height() * 0.25), r.width() * 0.75 * breathe)
        rg.setColorAt(0.0, qc("#F76B15", 0.30))
        rg.setColorAt(0.5, qc("#F76B15", 0.10))
        rg.setColorAt(1.0, qc("#F76B15", 0.0))
        p.fillRect(r, rg)
        op = ease_out_cubic((time.monotonic() - self._opening) / 0.5)
        if op < 1:
            p.fillRect(r, qc("#000000", 1 - op))
        if self._flash is not None:
            k = (t - self._flash) / 1.4
            if k >= 1:
                self._flash = None
            else:
                p.fillRect(r, qc("#F76B15", 0.18 * (1 - ease_out_cubic(k))))
