from datetime import datetime

from PyQt6.QtCore import QDateTime, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PyQt6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from app.core.paths import sound_file_path
from app.core.timeutil import ampm, ampm_parts, format_remaining
from app.core.version import DEVELOPER
from app.data import repo
from app.ui.select import Select
from app.ui.theme import C, font, qc
from app.ui.widgets import (ActionTile, Button, Card, CountdownRing, CountUpLabel, EqualizerBars, RollingClock,
                            StatusDot, TickingWidget, ToggleSwitch, ease_out_cubic, ticker)

WEEK_KO = ["월", "화", "수", "목", "금", "토", "일"]

# 상태: (글자, 글자색)
STATUS = {
    "played": ("울림", C.success),
    "skipped": ("건너뜀", C.warning),
    "will_skip": ("건너뛸 예정", C.warning),
    "rang_early": ("미리 울림", C.success),
    "failed": ("실패", C.danger),
    "missed": ("놓침", C.danger),
    "passed": ("지남", C.grey400),
    "next": ("다음", C.accent),
    "upcoming": ("예정", C.grey500),
    "paused": ("쉼", C.grey400),
}


def when_text(dt, now=None):
    now = now or datetime.now()
    hm = ampm(dt)
    d = (dt.date() - now.date()).days
    if d == 0:
        return f"오늘 {hm}"
    if d == 1:
        return f"내일 {hm}"
    return f"{dt.month}월 {dt.day}일 ({WEEK_KO[dt.weekday()]}) {hm}"


def remain_words(sec):
    sec = max(0, int(sec))
    if sec < 60:
        return f"{sec}초 후"
    m = sec // 60
    if m < 60:
        return f"{m}분 후"
    h, m = divmod(m, 60)
    return f"{h}시간 {m}분 후" if m else f"{h}시간 후"


UNDOABLE = {"will_skip": "SKIP_ONCE", "rang_early": "FIRED_ONCE"}
UNDO_LABEL = {"will_skip": "울리기", "rang_early": "제때 울리기"}


class TodayList(TickingWidget):
    """오늘 일정 목록. '건너뛸 예정'·'미리 울림' 줄은 눌러서 되돌릴 수 있다."""
    ROW_H = 56
    always_tick = False
    undoRequested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.events = []
        self._t_set = None
        self._hover = -1
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(200)

    def set_events(self, events):
        self.events = events
        self.setFixedHeight(max(1, len(events)) * self.ROW_H if events else 200)
        self.update()

    def replay(self):
        self._t_set = ticker().now()
        self.start_ticking()

    def next_row_y(self):
        for i, e in enumerate(self.events):
            if e["status"] == "next":
                return i * self.ROW_H
        return None

    def on_frame(self, t):
        if self._t_set is None or t - self._t_set > 0.03 * len(self.events) + 0.4:
            self._t_set = None
            self.stop_ticking()
        self.update()

    def _row_at(self, y):
        i = int(y // self.ROW_H)
        return i if 0 <= i < len(self.events) else -1

    def _button_rect(self, i, label=None):
        ev = self.events[i]
        label = label or UNDO_LABEL.get(ev["status"], "")
        fm = QFontMetricsF(font(13, QFont.Weight.Bold))
        w = fm.horizontalAdvance(label) + 26
        top = i * self.ROW_H
        return QRectF(self.width() - w - 10, top + (self.ROW_H - 32) / 2, w, 32)

    def mouseMoveEvent(self, e):
        i = self._row_at(e.position().y())
        undoable = i >= 0 and self.events[i]["status"] in UNDOABLE
        on_btn = undoable and self._button_rect(i).contains(e.position())
        self.setCursor(Qt.CursorShape.PointingHandCursor if undoable else Qt.CursorShape.ArrowCursor)
        if i != self._hover or on_btn != getattr(self, "_on_btn", False):
            self._hover = i
            self._on_btn = on_btn
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        i = self._row_at(e.position().y())
        if i >= 0 and self.events[i]["status"] in UNDOABLE:
            self.undoRequested.emit(self.events[i])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = ticker().now()
        if not self.events:
            p.setPen(qc(C.grey500))
            p.setFont(font(14))
            p.drawText(QRectF(self.rect()).adjusted(0, -10, 0, -10), Qt.AlignmentFlag.AlignCenter,
                       "오늘은 울릴 종이 없어요")
            return
        now = datetime.now()
        for i, ev in enumerate(self.events):
            k = 1.0
            if self._t_set is not None:
                k = ease_out_cubic((t - self._t_set - i * 0.03) / 0.3)
                if k <= 0:
                    continue
            p.save()
            p.setOpacity(min(1.0, k))
            p.translate(0, 8 * (1 - k))
            self._row(p, ev, i * self.ROW_H, now, hovered=(i == self._hover))
            p.restore()

    def _row(self, p, ev, top, now, hovered=False):
        w = self.width()
        st = ev["status"]
        nxt = st == "next"
        past = st in ("played", "skipped", "failed", "missed", "passed")
        undoable = st in UNDOABLE
        r = QRectF(0, top + 2, w, self.ROW_H - 4)
        if nxt or (undoable and hovered):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(C.accent_softer if nxt else C.grey50))
            p.drawRoundedRect(r, 12, 12)

        # 시각: 작은 '오전/오후' + 굵은 '2:40'
        part, hm = ampm_parts(ev["time"])
        p.setPen(qc(C.grey400 if past else (C.accent if nxt else C.grey500)))
        p.setFont(font(11.5, QFont.Weight.DemiBold))
        p.drawText(QRectF(14, r.top() + 7, 60, 18), Qt.AlignmentFlag.AlignVCenter, part)
        p.setPen(qc(C.grey400 if past else (C.accent if nxt else C.grey900)))
        p.setFont(font(15, QFont.Weight.DemiBold))
        p.drawText(QRectF(14, r.top() + 24, 60, 22), Qt.AlignmentFlag.AlignVCenter, hm)

        tx = 78
        label, col = STATUS.get(st, STATUS["upcoming"])
        if nxt:
            label = remain_words((ev["run_at"] - now).total_seconds())
        if undoable:
            # 꺼 둔 종: 오른쪽에 늘 보이는 '울리기' 버튼, 상태는 아래 줄에
            btn = self._button_rect(int(top // self.ROW_H))
            on_btn = hovered and getattr(self, "_on_btn", False)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(C.accent if on_btn else C.accent_soft))
            p.drawRoundedRect(btn, 10, 10)
            p.setPen(qc("#FFFFFF" if on_btn else C.accent_text))
            p.setFont(font(13, QFont.Weight.Bold))
            p.drawText(btn, Qt.AlignmentFlag.AlignCenter, UNDO_LABEL[st])
            tw = btn.left() - tx - 10
            p.setPen(qc(C.grey400))
            p.setFont(font(15, QFont.Weight.Medium))
            p.drawText(QRectF(tx, r.top() + 7, tw, 22), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetricsF(p.font()).elidedText(ev["name"], Qt.TextElideMode.ElideRight, tw))
            p.setFont(font(12.5, QFont.Weight.DemiBold))
            p.setPen(QColor(col))
            fm = QFontMetricsF(p.font())
            lw = fm.horizontalAdvance(label)
            p.drawText(QRectF(tx, r.top() + 28, lw + 2, 18), Qt.AlignmentFlag.AlignVCenter, label)
            p.setPen(qc(C.grey400))
            p.setFont(font(12.5))
            p.drawText(QRectF(tx + lw + 6, r.top() + 28, max(0, tw - lw - 6), 18), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetricsF(p.font()).elidedText(f"· {ev['sound']}", Qt.TextElideMode.ElideRight,
                                                          max(0, tw - lw - 6)))
            return

        p.setFont(font(13, QFont.Weight.DemiBold))
        lw = QFontMetricsF(p.font()).horizontalAdvance(label)
        tw = w - tx - lw - 30
        p.setPen(qc(C.grey400 if past else C.grey900))
        p.setFont(font(15, QFont.Weight.Medium))
        p.drawText(QRectF(tx, r.top() + 7, tw, 22), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(ev["name"], Qt.TextElideMode.ElideRight, tw))
        p.setPen(qc(C.grey400 if past else C.grey500))
        p.setFont(font(12.5))
        p.drawText(QRectF(tx, r.top() + 28, tw, 18), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetricsF(p.font()).elidedText(ev["sound"], Qt.TextElideMode.ElideRight, tw))
        p.setPen(QColor(col))
        p.setFont(font(13, QFont.Weight.DemiBold))
        p.drawText(QRectF(w - lw - 16, r.top(), lw + 2, r.height()), Qt.AlignmentFlag.AlignVCenter, label)


class DashboardPage(QWidget):
    openFullscreen = pyqtSignal()

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.conn = ctx.conn
        self.sch = ctx.scheduler
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(16)

        # ---------------- 머리: 날짜 + 큰 시계 + 상태 ----------------
        head = QHBoxLayout()
        head.setContentsMargins(4, 0, 4, 0)
        hl = QVBoxLayout()
        hl.setSpacing(0)
        self.date_label = QLabel("")
        self.date_label.setStyleSheet(f"color: {C.grey600}; font-size: 15px; font-weight: 600;")
        hl.addWidget(self.date_label)
        self.clock = RollingClock(46, C.grey900, QFont.Weight.Bold)
        hl.addWidget(self.clock)
        head.addLayout(hl)
        head.addStretch(1)
        st = QHBoxLayout()
        st.setSpacing(6)
        self.dot = StatusDot(C.success)
        st.addWidget(self.dot)
        self.state_label = QLabel("")
        self.state_label.setStyleSheet(f"color: {C.grey700}; font-size: 14px; font-weight: 600;")
        st.addWidget(self.state_label)
        head.addLayout(st)
        root.addLayout(head)

        cols = QHBoxLayout()
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)

        # ---------------- 다음 종 카드 ----------------
        self.next_card = Card(padding=24)
        nl = QHBoxLayout()
        nl.setSpacing(20)
        info = QVBoxLayout()
        info.setSpacing(6)
        cap = QLabel("다음 종")
        cap.setStyleSheet(f"color: {C.grey600}; font-size: 14px; font-weight: 600;")
        info.addWidget(cap)
        self.next_name = QLabel("-")
        self.next_name.setStyleSheet(f"color: {C.grey900}; font-size: 26px; font-weight: 700;")
        self.next_name.setMinimumWidth(10)
        self.next_name.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        info.addWidget(self.next_name)
        self.next_when = QLabel("")
        self.next_when.setStyleSheet(f"color: {C.grey600}; font-size: 15px;")
        info.addWidget(self.next_when)
        info.addStretch(1)
        self.set_label = QLabel("")
        self.set_label.setStyleSheet(f"color: {C.grey500}; font-size: 13px;")
        info.addWidget(self.set_label)
        nl.addLayout(info, 1)
        self.ring = CountdownRing(size=150, thickness=10)
        nl.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignVCenter)
        self.next_card.body.addLayout(nl)
        left.addWidget(self.next_card)

        # ---------------- 빠른 동작 ----------------
        grid = QGridLayout()
        grid.setSpacing(12)
        self.t_ring = ActionTile("ring", "다음 종 지금 울리기", "기다리지 않고 바로 울려요")
        self.t_skip = ActionTile("skip", "다음 종 건너뛰기", "이번 한 번만 울리지 않아요")
        self.t_pause = ActionTile("pause", "잠시 멈추기", "자동 타종을 멈춰요")
        self.t_full = ActionTile("fullscreen", "전체화면 시계", "교실 화면에 크게 띄워요")
        grid.addWidget(self.t_ring, 0, 0)
        grid.addWidget(self.t_skip, 0, 1)
        grid.addWidget(self.t_pause, 1, 0)
        grid.addWidget(self.t_full, 1, 1)
        left.addLayout(grid)

        # ---------------- 바로 울리기 ----------------
        self.manual = Card(padding=20)
        mh = QHBoxLayout()
        ml = QLabel("종소리 바로 울리기")
        ml.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {C.grey900};")
        mh.addWidget(ml)
        mh.addStretch(1)
        self.eq = EqualizerBars()
        mh.addWidget(self.eq)
        self.manual.body.addLayout(mh)
        mb = QHBoxLayout()
        mb.setSpacing(8)
        self.sound_combo = Select()
        mb.addWidget(self.sound_combo, 1)
        self.btn_play = Button("울리기", variant="primary")
        self.btn_stop = Button("정지", variant="secondary")
        mb.addWidget(self.btn_play)
        mb.addWidget(self.btn_stop)
        self.manual.body.addLayout(mb)
        left.addWidget(self.manual)
        left.addStretch(1)
        credit = QLabel(f"{DEVELOPER} 개발")
        credit.setStyleSheet(f"color: {C.grey400}; font-size: 12px; padding-left: 4px;")
        left.addWidget(credit, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom)
        cols.addLayout(left, 3)

        # ---------------- 오늘 ----------------
        self.today = Card(padding=20)
        self.today.body.setSpacing(14)
        tt = QLabel("오늘")
        tt.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {C.grey900};")
        self.today.body.addWidget(tt)
        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.stat_played = self._stat(stats, "울린 종", "번")
        self.stat_left = self._stat(stats, "남은 종", "번")
        self.today.body.addLayout(stats)
        self.timeline = TodayList()
        self.tl_scroll = QScrollArea()
        self.tl_scroll.setWidgetResizable(True)
        self.tl_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.tl_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tl_scroll.setWidget(self.timeline)
        self.today.body.addWidget(self.tl_scroll, 1)
        line = QWidget()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background: {C.grey100};")
        self.today.body.addWidget(line)
        self.pause_today = ToggleSwitch("오늘 하루 자동 타종 끄기", text_left=True)
        self.pause_today.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.today.body.addWidget(self.pause_today)
        self.today.setMinimumWidth(300)
        cols.addWidget(self.today, 2)
        root.addLayout(cols, 1)

        # ---------------- 연결 ----------------
        self.t_ring.clicked.connect(self.on_ring_next)
        self.t_skip.clicked.connect(self.on_skip_next)
        self.t_pause.clicked.connect(self.on_toggle_pause)
        self.t_full.clicked.connect(self.openFullscreen.emit)
        self.btn_play.clicked.connect(self.on_play_selected)
        self.btn_stop.clicked.connect(self.on_stop)
        self.pause_today.toggled.connect(self.on_pause_today)
        ctx.data_changed.connect(self._on_data_changed)
        ctx.rang.connect(self._on_rang)
        ctx.scheduler_event.connect(lambda kind, ev: self.refresh_timeline())

        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._on_second)
        self._tl_timer = QTimer(self)
        self._tl_timer.setInterval(15000)
        self._tl_timer.timeout.connect(self.refresh_timeline)
        self._last_next_id = None
        self._set_name = repo.active_set_name(self.conn)
        self.timeline.undoRequested.connect(self.on_undo)

        self.refresh_sounds()
        self.refresh_timeline(animate=True)
        self.tick()

    def _stat(self, lay, label, suffix):
        box = QFrame()
        box.setObjectName("Stat")
        box.setStyleSheet(f"QFrame#Stat {{ background: {C.grey50}; border-radius: 12px; }}")
        v = QVBoxLayout(box)
        v.setContentsMargins(14, 10, 14, 10)
        v.setSpacing(2)
        cap = QLabel(label)
        cap.setStyleSheet(f"color: {C.grey600}; font-size: 13px; background: transparent;")
        num = CountUpLabel(0, suffix)
        num.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {C.grey900}; background: transparent;")
        v.addWidget(cap)
        v.addWidget(num)
        lay.addWidget(box, 1)
        return num

    # ---------------- 갱신 ----------------
    def _schedule_next_second(self):
        # 다음 초가 바뀌는 순간에 맞춰 깨어나서 1초에 한 번만 갱신
        ms = 1000 - QDateTime.currentDateTime().time().msec() + 5
        self._timer.start(ms)

    def _on_second(self):
        self.tick()
        self.timeline.update()
        self._schedule_next_second()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh_timeline()
        self.tick()
        self._schedule_next_second()
        self._tl_timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._timer.stop()
        self._tl_timer.stop()

    def on_enter(self):
        self.refresh_timeline(animate=True)
        self.ring.intro()

    def _on_data_changed(self, what):
        if what in ("all", "sounds"):
            self.refresh_sounds()
        self.refresh_timeline()
        self.tick()

    def refresh_sounds(self):
        cur = self.sound_combo.currentData()
        self.sound_combo.blockSignals(True)
        self.sound_combo.clear()
        pick = 0
        for i, s in enumerate(repo.list_sounds(self.conn)):
            self.sound_combo.addItem(str(s["name"]), int(s["id"]))
            if cur is not None and int(s["id"]) == cur:
                pick = i
            elif cur is None and str(s["name"]).lower().startswith("bell"):
                pick = i
        if self.sound_combo.count():
            self.sound_combo.setCurrentIndex(pick)
        self.sound_combo.blockSignals(False)

    def refresh_timeline(self, animate=False):
        events = self.sch.today_events()
        self.timeline.set_events(events)
        if animate:
            self.timeline.replay()
        today = datetime.now().strftime("%Y-%m-%d")
        self.stat_played.set_value(repo.count_played_on(self.conn, today))
        self.stat_left.set_value(sum(1 for e in events if e["status"] in ("next", "upcoming")))
        self.pause_today.blockSignals(True)
        self.pause_today.setChecked(self.sch.is_paused_today(today))
        self.pause_today.blockSignals(False)
        self._set_name = repo.active_set_name(self.conn)
        self.set_label.setText(f"{self._set_name} 세트")
        nid = next((e["id"] for e in events if e["status"] == "next"), None)
        if nid != self._last_next_id:
            self._last_next_id = nid
            y = self.timeline.next_row_y()
            if y is not None:
                QTimer.singleShot(50, lambda: self.tl_scroll.ensureVisible(0, int(y) + 28, 0, 120))

    def tick(self):
        if not self.isVisible():
            return
        now = datetime.now()
        self.clock.setText(now.strftime("%H:%M:%S"))
        self.date_label.setText(f"{now.month}월 {now.day}일 {WEEK_KO[now.weekday()]}요일")
        paused_day = self.sch.is_paused_today()
        ev = self.sch.next_event

        if ev:
            remain = (ev.run_at - now).total_seconds()
            prev = now.replace(hour=0, minute=0, second=0, microsecond=0)
            for e in self.timeline.events:
                if prev < e["run_at"] <= now:
                    prev = e["run_at"]
            total = max(1.0, (ev.run_at - prev).total_seconds())
            urgent = 0 <= remain <= 60
            self.ring.set_state(1 - max(0.0, remain) / total, format_remaining(remain, short=True), "남음", urgent)
            self.next_name.setText(QFontMetricsF(self.next_name.font()).elidedText(
                ev.name, Qt.TextElideMode.ElideRight, max(120, self.next_name.width())))
            self.next_when.setText(f"{when_text(ev.run_at, now)}  ·  {ev.sound_name}")
        else:
            self.ring.set_state(0, "--:--", "")
            self.next_name.setText("예정된 종이 없어요")
            self.next_when.setText("시간표에서 일정을 추가해 보세요")

        if paused_day:
            self.state_label.setText("오늘은 쉬는 날")
            self.dot.set_color(C.grey400, pulse=False)
        elif self.sch.paused:
            self.state_label.setText("잠시 멈춤")
            self.dot.set_color(C.warning, pulse=False)
        elif ev:
            self.state_label.setText("자동 타종 중")
            self.dot.set_color(C.success, pulse=True)
        else:
            self.state_label.setText("대기 중")
            self.dot.set_color(C.grey400, pulse=False)

        if self.sch.paused:
            self.t_pause.set_content("play", "다시 시작하기", "멈춘 자동 타종을 이어가요")
        else:
            self.t_pause.set_content("pause", "잠시 멈추기", "자동 타종을 멈춰요")
        self.t_ring.setEnabled(ev is not None)
        self.t_skip.setEnabled(ev is not None)
        self.eq.set_active(self.ctx.player.is_playing())

    # ---------------- 동작 ----------------
    def _on_rang(self, ev, forced):
        self.ring.burst()
        self.refresh_timeline()
        if not forced:
            self.ctx.toast(f"{ev.name} 종을 울렸어요", "bell", 3000)

    def on_ring_next(self):
        ev = self.sch.ring_next_now()
        self.ctx.changed("schedules")
        if ev is None:
            self.ctx.toast("울릴 종이 없어요", "warning")
            return
        date = ev.run_at.strftime("%Y-%m-%d")
        self.ctx.toast(f"{ev.name} 종을 미리 울렸어요", "bell", 6000, "되돌리기",
                       lambda: self._undo(ev.schedule_id, date, "FIRED_ONCE"))

    def on_skip_next(self):
        ev = self.sch.skip_next_once()
        self.ctx.changed("schedules")
        if ev:
            date = ev.run_at.strftime("%Y-%m-%d")
            self.ctx.toast(f"{ampm(ev.run_at)} {ev.name} 종은 이번에 건너뛸게요", "info", 6000, "되돌리기",
                           lambda: self._undo(ev.schedule_id, date, "SKIP_ONCE"))

    def on_undo(self, item):
        """오늘 목록에서 '건너뛸 예정' / '미리 울림' 줄을 눌렀을 때."""
        self._undo(item["id"], item["date"], UNDOABLE[item["status"]])

    def _undo(self, schedule_id, date, action):
        if action == "FIRED_ONCE":
            self.ctx.player.stop()
        ok = self.sch.undo(schedule_id, date, action)
        self.ctx.changed("schedules")
        if ok:
            self.ctx.toast("건너뛰기를 취소했어요. 정해진 시간에 울려요" if action == "SKIP_ONCE"
                           else "되돌렸어요. 정해진 시간에 다시 울려요", "success")

    def on_toggle_pause(self):
        if self.sch.paused:
            self.sch.resume()
            self.sch.recompute_next()
            self.ctx.toast("자동 타종을 다시 시작했어요", "success")
        else:
            self.sch.pause()
            self.ctx.toast("자동 타종을 멈췄어요", "warning")
        self.tick()

    def on_pause_today(self, on):
        repo.set_pause_today(self.conn, datetime.now().strftime("%Y-%m-%d"), on)
        self.ctx.changed("schedules")
        self.ctx.toast("오늘은 종을 울리지 않을게요" if on else "오늘 자동 타종을 다시 켰어요", "info" if on else "success")

    def on_play_selected(self):
        sid = self.sound_combo.currentData()
        if sid is None:
            return
        s = repo.get_sound(self.conn, sid)
        if not s:
            return
        try:
            self.ctx.player.play(str(sound_file_path(str(s["file_name"]))), float(s["volume"]), str(s["name"]))
            self.eq.set_active(True)
        except Exception as e:
            self.ctx.toast(str(e), "error")

    def on_stop(self):
        self.ctx.player.stop()
        self.eq.set_active(False)
