"""교실 모니터·TV용 전체화면 시계 (다크/라이트, 날씨 예보)."""
import time
from datetime import datetime

from PyQt6.QtCore import QDateTime, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPixmap, QRadialGradient
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.core import weather
from app.core.timeutil import ampm, ampm_parts, format_remaining
from app.data import repo
from app.ui.pages.dashboard import STATUS, WEEK_KO, when_text
from app.ui.theme import C, font, paint_soft_shadow, qc
from app.ui.weather_icons import paint_weather
from app.ui.widgets import Button, CountdownRing, RollingClock, TickingWidget, ease_out_cubic, ticker
from app.ui.workers import run_async

THEMES = {
    "dark": {
        "dark": True, "bg": "#121316", "fg": "#FFFFFF", "sub": ("#FFFFFF", 0.6), "dim": ("#FFFFFF", 0.42),
        "card": ("#FFFFFF", 0.05), "card_next": ("#FFFFFF", 0.10), "glow": 0.30, "accent": "#FFB27A",
        "button": "hero",
    },
    "light": {
        "dark": False, "bg": "#F4F5F7", "fg": C.grey900, "sub": (C.grey600, 1.0), "dim": (C.grey500, 1.0),
        "card": ("#FFFFFF", 1.0), "card_next": ("#FFFFFF", 1.0), "glow": 0.16, "accent": C.accent_text,
        "button": "white",
    },
}


def _rgba(spec):
    c = QColor(spec[0])
    return f"rgba({c.red()},{c.green()},{c.blue()},{spec[1]:.2f})"


def _temp(v):
    return "-" if v is None else f"{round(v):d}°"


def _card(p, r, th, nxt=False, radius=20):
    if th["dark"]:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(*(th["card_next"] if nxt else th["card"])))
        p.drawRoundedRect(r, radius, radius)
    else:
        paint_soft_shadow(p, r, radius, strength=1.4, spread=10, dy=3)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#FFFFFF"))
        p.drawRoundedRect(r, radius, radius)
        if nxt:
            p.setBrush(qc(C.accent, 0.07))
            p.drawRoundedRect(r, radius, radius)


class _UpcomingStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items = []
        self.th = THEMES["dark"]
        self.setMinimumHeight(110)

    def set_items(self, items):
        self.items = items[:5]
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th = self.th
        if not self.items:
            p.setPen(qc(*th["dim"]))
            p.setFont(font(max(14, self.height() * 0.2), QFont.Weight.DemiBold))
            p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, "오늘 남은 종이 없어요")
            return
        n = len(self.items)
        gap = 16
        w = min(300.0, (self.width() - 24 - gap * (n - 1)) / n)
        total = w * n + gap * (n - 1)
        x = (self.width() - total) / 2
        h = self.height() - 16
        for ev in self.items:
            r = QRectF(x, 6, w, h)
            nxt = ev["status"] == "next"
            _card(p, r, th, nxt)
            part, hm = ampm_parts(ev["time"])
            p.setPen(qc(th["fg"]))
            p.setFont(font(h * 0.28, QFont.Weight.Bold))
            fm = QFontMetricsF(p.font())
            p.drawText(QRectF(r.left() + 18, r.top() + 8, r.width() - 36, h * 0.42), Qt.AlignmentFlag.AlignVCenter, hm)
            p.setFont(font(h * 0.14, QFont.Weight.DemiBold))
            p.setPen(qc(*th["sub"]))
            p.drawText(QRectF(r.left() + 22 + fm.horizontalAdvance(hm), r.top() + 8, 120, h * 0.42),
                       Qt.AlignmentFlag.AlignVCenter, part)
            p.setFont(font(h * 0.16, QFont.Weight.DemiBold))
            p.setPen(qc(th["fg"], 0.88))
            fm2 = QFontMetricsF(p.font())
            p.drawText(QRectF(r.left() + 18, r.top() + h * 0.50, r.width() - 36, h * 0.24), Qt.AlignmentFlag.AlignVCenter,
                       fm2.elidedText(ev["name"], Qt.TextElideMode.ElideRight, r.width() - 36))
            label = STATUS.get(ev["status"], STATUS["upcoming"])[0]
            p.setFont(font(h * 0.13, QFont.Weight.Medium))
            p.setPen(qc(th["accent"]) if nxt else qc(*th["dim"]))
            fm3 = QFontMetricsF(p.font())
            p.drawText(QRectF(r.left() + 18, r.top() + h * 0.74, r.width() - 36, h * 0.2), Qt.AlignmentFlag.AlignVCenter,
                       fm3.elidedText(f"{label}  ·  {ev['sound']}", Qt.TextElideMode.ElideRight, r.width() - 36))
            x += w + gap


class _WeatherNow(QWidget):
    """오른쪽 위: 지금 날씨와 오늘 최고/최저. 누르면 지역을 바꾼다."""
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.failed = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip("눌러서 날씨 지역 바꾸기")
        self.th = THEMES["dark"]
        self.px = 40

    def set_data(self, data):
        self.data = data
        self.updateGeometry()
        self.update()

    def set_px(self, px):
        self.px = px
        h = int(px * 1.9)
        self.setFixedHeight(h)
        self.setMinimumWidth(int(px * 10))
        self.updateGeometry()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def paintEvent(self, e):
        d = self.data
        if not d:
            if self.failed:
                p = QPainter(self)
                p.setPen(qc(*self.th["dim"]))
                p.setFont(font(self.px * 0.5, QFont.Weight.Medium))
                p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                           "날씨를 불러오지 못했어요 · 눌러서 지역 확인")
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th = self.th
        now = d["now"]
        h = self.height()
        icon = h * 0.92
        temp = _temp(now["temp"])
        p.setFont(font(self.px * 1.15, QFont.Weight.Bold))
        tw = QFontMetricsF(p.font()).horizontalAdvance(temp)
        detail_font = font(self.px * 0.6, QFont.Weight.DemiBold)
        sub_font = font(self.px * 0.5, QFont.Weight.Medium)
        line1 = f"{d.get('city', '')} · {now['text']}"
        t = d.get("today") or {}
        line2 = f"최고 {_temp(t.get('max'))}  최저 {_temp(t.get('min'))}"
        dw = max(QFontMetricsF(detail_font).horizontalAdvance(line1), QFontMetricsF(sub_font).horizontalAdvance(line2))
        total = icon + 10 + tw + 18 + dw
        x = self.width() - total
        paint_weather(p, QRectF(x, (h - icon) / 2, icon, icon), now["kind"], now["night"], th["dark"])
        x += icon + 10
        p.setPen(qc(th["fg"]))
        p.setFont(font(self.px * 1.15, QFont.Weight.Bold))
        p.drawText(QRectF(x, 0, tw + 4, h), Qt.AlignmentFlag.AlignVCenter, temp)
        x += tw + 18
        p.setFont(detail_font)
        p.setPen(qc(th["fg"], 0.9))
        p.drawText(QRectF(x, 0, dw + 4, h * 0.5), Qt.AlignmentFlag.AlignBottom, line1)
        p.setFont(sub_font)
        p.setPen(qc(*th["sub"]))
        p.drawText(QRectF(x, h * 0.54, dw + 4, h * 0.46), Qt.AlignmentFlag.AlignTop, line2)


class _HourlyStrip(QWidget):
    """시계 아래: 앞으로 몇 시간의 날씨."""

    SLOTS = 6

    def __init__(self, parent=None):
        super().__init__(parent)
        self.data = None
        self.th = THEMES["dark"]

    def set_data(self, data):
        self.data = data
        self.setVisible(bool(data and data.get("hours")))
        self.update()

    def paintEvent(self, e):
        d = self.data
        if not d or not d.get("hours"):
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th = self.th
        r = QRectF(self.rect()).adjusted(4, 4, -4, -8)
        _card(p, r, th, radius=22)
        hours = d["hours"]
        step = 2 if len(hours) >= self.SLOTS * 2 else 1
        picks = hours[::step][: self.SLOTS]
        n = len(picks)
        cw = r.width() / max(1, n)
        h = r.height()
        for i, it in enumerate(picks):
            cx = r.left() + cw * i
            t = datetime.strptime(it["time"], "%Y-%m-%dT%H:%M")
            part = "오전" if t.hour < 12 else "오후"
            label = f"{part} {t.hour % 12 or 12}시"
            p.setPen(qc(*th["sub"]))
            p.setFont(font(h * 0.14, QFont.Weight.DemiBold))
            p.drawText(QRectF(cx, r.top() + h * 0.08, cw, h * 0.22), Qt.AlignmentFlag.AlignCenter, label)
            isz = h * 0.40
            paint_weather(p, QRectF(cx + (cw - isz) / 2, r.top() + h * 0.29, isz, isz), it["kind"], it["night"],
                          th["dark"])
            p.setPen(qc(th["fg"]))
            p.setFont(font(h * 0.17, QFont.Weight.Bold))
            p.drawText(QRectF(cx, r.top() + h * 0.68, cw, h * 0.26), Qt.AlignmentFlag.AlignCenter, _temp(it["temp"]))


class _Crossfade(QWidget):
    """테마를 바꿀 때 이전 화면을 덮었다가 서서히 걷어 낸다."""

    def __init__(self, parent, pixmap: QPixmap):
        super().__init__(parent)
        self.pm = pixmap
        self.k = 0.0
        self.t0 = time.monotonic()
        self.setGeometry(parent.rect())
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)
        self._timer.start()
        self.show()
        self.raise_()

    def _step(self):
        self.k = (time.monotonic() - self.t0) / 0.38
        if self.k >= 1:
            self._timer.stop()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setOpacity(1 - ease_out_cubic(self.k))
        p.drawPixmap(0, 0, self.pm)


class FullscreenClock(TickingWidget):
    def __init__(self, ctx, screen=None):
        super().__init__(None)
        self.ctx = ctx
        self.setWindowTitle("전체화면 시계")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self._flash = None
        self._last_move = time.monotonic()
        self._last_paint = 0
        self._opening = time.monotonic()
        self._theme = "light" if repo.get_setting(ctx.conn, "fs_theme", "dark") == "light" else "dark"
        self._weather_on = repo.get_setting(ctx.conn, "weather_on", "1") != "0"
        self._weather = None
        self._wx_seq = 0
        if screen is not None:
            self.setScreen(screen)
            self.setGeometry(screen.geometry())

        root = QVBoxLayout(self)
        root.setContentsMargins(60, 36, 60, 28)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(10)
        self.date_label = QLabel("")
        top.addWidget(self.date_label, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addStretch(1)
        self.wx_now = _WeatherNow()
        self.wx_now.clicked.connect(self._pick_place)
        top.addWidget(self.wx_now, 0, Qt.AlignmentFlag.AlignVCenter)
        top.addSpacing(8)
        self.btn_theme = Button("", icon_name="sun")
        self.btn_theme.setToolTip("밝은 화면 / 어두운 화면 (T)")
        self.btn_theme.clicked.connect(self.toggle_theme)
        top.addWidget(self.btn_theme, 0, Qt.AlignmentFlag.AlignVCenter)
        self.btn_close = Button("닫기")
        self.btn_close.clicked.connect(self.close)
        top.addWidget(self.btn_close, 0, Qt.AlignmentFlag.AlignVCenter)
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
        lc.addSpacing(18)
        self.hourly = _HourlyStrip()
        self.hourly.hide()
        lc.addWidget(self.hourly)
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
        self.credit = QLabel(weather.CREDIT)
        self.credit.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.credit.setVisible(self._weather_on)
        root.addWidget(self.credit)

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_second)
        self._timer.start(0)
        self._ev_timer = QTimer(self)
        self._ev_timer.setInterval(3000)
        self._ev_timer.timeout.connect(self._refresh_events)
        self._ev_timer.start()
        self._wx_timer = QTimer(self)
        self._wx_timer.setInterval(10 * 60 * 1000)
        self._wx_timer.timeout.connect(self._load_weather)
        if self._weather_on:
            self._wx_timer.start()
        ctx.rang.connect(self._on_rang)
        self._events = []
        self._apply_theme()
        self._refresh_events()
        self.refresh()
        self._load_weather()

    # ---------- 테마 ----------
    @property
    def th(self):
        return THEMES[self._theme]

    def toggle_theme(self):
        try:
            snap = self.grab()
        except Exception:
            snap = None
        self._theme = "light" if self._theme == "dark" else "dark"
        repo.set_setting(self.ctx.conn, "fs_theme", self._theme)
        self._apply_theme()
        if snap is not None and not snap.isNull():
            _Crossfade(self, snap)

    def _apply_theme(self):
        th = self.th
        self.clock.set_color(th["fg"])
        self.ring.on_dark = th["dark"]
        self.ring.track_color = None if th["dark"] else C.grey200
        self.ring.update()
        for w in (self.strip, self.wx_now, self.hourly):
            w.th = th
            w.update()
        for b in (self.btn_theme, self.btn_close):
            b.set_variant(th["button"])
        self.btn_theme.set_icon_name("sun" if th["dark"] else "moon")
        self.btn_theme.setText("밝게" if th["dark"] else "어둡게")
        self.btn_theme.updateGeometry()
        self._apply_sizes()
        self.update()

    # ---------- 크기 ----------
    def _apply_sizes(self):
        th = self.th
        h = max(600, self.height() or 900)
        w = max(800, self.width() or 1400)
        portrait = h > w
        self.clock.set_px(int(min(h * 0.20, w * (0.13 if not portrait else 0.18))))
        self.ring.set_size(int(min(h * 0.36, w * 0.28)))
        self.ring.thickness = max(10, int(h * 0.013))
        fg, sub, dim = th["fg"], _rgba(th["sub"]), _rgba(th["dim"])
        self.date_label.setStyleSheet(f"color: {sub}; font-size: {int(h * 0.026)}px; font-weight: 600;")
        self.state.setStyleSheet(f"color: {dim}; font-size: {int(h * 0.022)}px;")
        self.next_name.setStyleSheet(f"color: {fg}; font-size: {int(h * 0.034)}px; font-weight: 700;")
        self.next_when.setStyleSheet(f"color: {sub}; font-size: {int(h * 0.022)}px;")
        self.credit.setStyleSheet(f"color: {dim}; font-size: {max(11, int(h * 0.011))}px;")
        self.strip.setFixedHeight(int(h * 0.16))
        self.wx_now.set_px(max(20, int(h * 0.03)))
        self.hourly.setFixedHeight(int(h * 0.15))
        self.hourly.setMinimumWidth(int(min(w * 0.42, h * 0.75)))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._apply_sizes()

    # ---------- 날씨 ----------
    def _load_weather(self):
        if not self._weather_on:
            self.wx_now.set_data(None)
            self.hourly.set_data(None)
            return
        city = weather.setting_value(lambda k, d: repo.get_setting(self.ctx.conn, k, d))
        self._wx_seq += 1
        seq = self._wx_seq
        run_async(weather.get, city, on_done=lambda d: self._weather_ready(seq, d),
                  on_fail=lambda m: self._weather_ready(seq, None))

    def _pick_place(self):
        from app.ui.place_dialog import pick_place
        if pick_place(self.ctx.conn, self):
            self._load_weather()

    def _weather_ready(self, seq, data):
        try:
            if seq != self._wx_seq:
                return
            self._weather = data
            self.wx_now.failed = data is None
            self.wx_now.set_data(data)
            self.hourly.set_data(data)
            self.credit.setVisible(bool(data))
        except RuntimeError:
            pass

    # ---------- 데이터 ----------
    def _refresh_events(self):
        try:
            evs = self.ctx.scheduler.today_events()
        except Exception:
            evs = []
        self._events = evs
        self.strip.set_items([e for e in evs if e["status"] in ("next", "upcoming", "will_skip", "paused")])

    def _on_second(self):
        self.refresh()
        self._timer.start(1000 - QDateTime.currentDateTime().time().msec() + 5)

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
            self.state.setText("오늘은 쉬는 날" if repo.is_pause_today(self.ctx.conn, now.strftime("%Y-%m-%d"))
                               else "")
        idle = time.monotonic() - self._last_move
        show = idle < 3.0
        self.btn_close.setVisible(show)
        self.btn_theme.setVisible(show)
        self.setCursor(Qt.CursorShape.BlankCursor if idle > 3.0 else Qt.CursorShape.ArrowCursor)

    def _on_rang(self, ev, forced):
        try:
            self.ring.burst()
            self._flash = ticker().now()
            self.start_ticking()
            self._refresh_events()
        except RuntimeError:
            pass

    # ---------- 입력 ----------
    def mouseMoveEvent(self, e):
        self._last_move = time.monotonic()
        if not self.btn_close.isVisible():
            self.btn_close.show()
            self.btn_theme.show()
        super().mouseMoveEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.close()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_F11):
            self.close()
            return
        if e.key() == Qt.Key.Key_T:
            self.toggle_theme()
            return
        super().keyPressEvent(e)

    def closeEvent(self, e):
        try:
            self.ctx.rang.disconnect(self._on_rang)
        except (TypeError, RuntimeError):
            pass
        self._timer.stop()
        self._ev_timer.stop()
        self._wx_timer.stop()
        self._wx_seq += 1
        super().closeEvent(e)

    # ---------- 그리기 ----------
    def on_frame(self, t):
        # 열릴 때의 페이드와 종이 울릴 때의 반짝임 동안만 다시 그린다
        busy = time.monotonic() - self._opening < 0.6 or self._flash is not None
        if not busy:
            self.stop_ticking()
            return
        if t - self._last_paint >= 1 / 60:
            self._last_paint = t
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        th = self.th
        r = QRectF(self.rect())
        t = ticker().now()
        p.fillRect(r, QColor(th["bg"]))
        # 아래쪽에서 은은하게 번지는 주황빛
        rg = QRadialGradient(QPointF(r.center().x(), r.bottom() + r.height() * 0.25), r.width() * 0.75)
        rg.setColorAt(0.0, qc("#F76B15", th["glow"]))
        rg.setColorAt(0.5, qc("#F76B15", th["glow"] / 3))
        rg.setColorAt(1.0, qc("#F76B15", 0.0))
        p.fillRect(r, rg)
        op = ease_out_cubic((time.monotonic() - self._opening) / 0.5)
        if op < 1:
            p.fillRect(r, qc("#000000" if th["dark"] else "#FFFFFF", 1 - op))
        if self._flash is not None:
            k = (t - self._flash) / 1.4
            if k >= 1:
                self._flash = None
            else:
                p.fillRect(r, qc("#F76B15", 0.18 * (1 - ease_out_cubic(k))))
