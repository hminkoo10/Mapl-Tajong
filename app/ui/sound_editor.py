"""종소리 편집기: 파형을 보면서 구간 자르기, 페이드 인/아웃, 음량, 소리 크기 자동 맞춤."""
import math
import time
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QDialog, QDoubleSpinBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QSizePolicy,
                             QSlider, QStackedLayout, QVBoxLayout, QWidget)

from app.core import ffmpeg, sound_files
from app.core.audio_edit import EditParams, build_filter, compute_peaks, suggest_trim
from app.core.paths import sound_file_path, temp_dir
from app.ui.dialogs import BaseDialog, _row, confirm
from app.ui.theme import C, font, qc
from app.ui.widgets import (Button, SegmentedControl, Spinner, TickingWidget, ToggleSwitch, ease_out_cubic,
                            field_label, muted_label, ticker)
from app.ui.workers import run_async

RATE = 8000


def _fmt(t):
    t = max(0.0, t)
    m, s = divmod(t, 60)
    return f"{int(m)}:{s:05.2f}" if m >= 1 else f"{s:.2f}초"


class WaveformView(TickingWidget):
    selectionChanged = pyqtSignal(float, float)
    seekRequested = pyqtSignal(float)

    HANDLE_PX = 9

    def __init__(self, parent=None):
        super().__init__(parent)
        self.samples = None
        self.duration = 0.0
        self.v0, self.v1 = 0.0, 1.0
        self.sel0, self.sel1 = 0.0, 1.0
        self.fade_in = 0.0
        self.fade_out = 0.0
        self.gain = 1.0
        self.playhead = None
        self._peaks = []
        self._peak_key = None
        self._drag = None
        self._hover = None
        self._intro_t = None
        self.setMouseTracking(True)
        self.setMinimumHeight(210)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self):
        return QSize(640, 230)

    # ---------- 데이터 ----------
    def set_samples(self, samples):
        self.samples = samples
        self.duration = len(samples) / RATE if samples else 0.0
        self.v0, self.v1 = 0.0, max(0.01, self.duration)
        self.sel0, self.sel1 = 0.0, self.duration
        self._peak_key = None
        self._intro_t = ticker().now()
        self.update()

    def set_selection(self, a, b, emit=False):
        a = max(0.0, min(self.duration, a))
        b = max(0.0, min(self.duration, b))
        if b - a < 0.05:
            b = min(self.duration, a + 0.05)
        self.sel0, self.sel1 = a, b
        self.update()
        if emit:
            self.selectionChanged.emit(a, b)

    def zoom(self, factor, center=None):
        if not self.duration:
            return
        c = (self.v0 + self.v1) / 2 if center is None else center
        span = max(0.25, min(self.duration, (self.v1 - self.v0) * factor))
        a = max(0.0, c - span / 2)
        b = a + span
        if b > self.duration:
            b = self.duration
            a = max(0.0, b - span)
        self.v0, self.v1 = a, b
        self._peak_key = None
        self.update()

    def zoom_to_selection(self):
        pad = (self.sel1 - self.sel0) * 0.08
        self.v0 = max(0.0, self.sel0 - pad)
        self.v1 = min(self.duration, self.sel1 + pad)
        self._peak_key = None
        self.update()

    def zoom_all(self):
        self.v0, self.v1 = 0.0, max(0.01, self.duration)
        self._peak_key = None
        self.update()

    # ---------- 좌표 ----------
    def _area(self):
        return QRectF(self.rect()).adjusted(1, 26, -1, -24)

    def x_of(self, t):
        a = self._area()
        return a.left() + (t - self.v0) / max(1e-6, (self.v1 - self.v0)) * a.width()

    def t_of(self, x):
        a = self._area()
        return self.v0 + (x - a.left()) / max(1.0, a.width()) * (self.v1 - self.v0)

    def _ensure_peaks(self, buckets):
        key = (buckets, round(self.v0, 4), round(self.v1, 4))
        if key == self._peak_key or self.samples is None:
            return
        self._peaks = compute_peaks(self.samples, self.v0 * RATE, self.v1 * RATE, buckets)
        self._peak_key = key

    # ---------- 마우스 ----------
    def _hit(self, x):
        if abs(x - self.x_of(self.sel0)) <= self.HANDLE_PX:
            return "start"
        if abs(x - self.x_of(self.sel1)) <= self.HANDLE_PX:
            return "end"
        if self.x_of(self.sel0) < x < self.x_of(self.sel1):
            return "inside"
        return None

    def mousePressEvent(self, e):
        if not self.duration:
            return
        x = e.position().x()
        h = self._hit(x)
        t = self.t_of(x)
        if e.button() == Qt.MouseButton.RightButton:
            self.seekRequested.emit(max(0.0, min(self.duration, t)))
            return
        if h in ("start", "end"):
            self._drag = (h, 0.0)
        elif h == "inside":
            self._drag = ("move", t - self.sel0)
        else:
            self._drag = ("new", t)
            self.set_selection(t, t + 0.05)

    def mouseMoveEvent(self, e):
        x = e.position().x()
        if not self._drag:
            h = self._hit(x)
            if h != self._hover:
                self._hover = h
                self.setCursor(Qt.CursorShape.SizeHorCursor if h in ("start", "end") else
                               Qt.CursorShape.OpenHandCursor if h == "inside" else Qt.CursorShape.IBeamCursor)
                self.update()
            return
        t = max(0.0, min(self.duration, self.t_of(x)))
        kind, ref = self._drag
        if kind == "start":
            self.set_selection(min(t, self.sel1 - 0.05), self.sel1, emit=True)
        elif kind == "end":
            self.set_selection(self.sel0, max(t, self.sel0 + 0.05), emit=True)
        elif kind == "move":
            span = self.sel1 - self.sel0
            a = max(0.0, min(self.duration - span, t - ref))
            self.set_selection(a, a + span, emit=True)
        else:
            self.set_selection(min(ref, t), max(ref, t), emit=True)

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = None
            self.selectionChanged.emit(self.sel0, self.sel1)

    def wheelEvent(self, e):
        if not self.duration:
            return
        dy = e.angleDelta().y()
        if not dy:
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom(0.8 if dy > 0 else 1.25, self.t_of(e.position().x()))
        else:
            span = self.v1 - self.v0
            shift = -span * 0.12 * (1 if dy > 0 else -1)
            a = max(0.0, min(self.duration - span, self.v0 + shift))
            self.v0, self.v1 = a, a + span
            self._peak_key = None
            self.update()

    # ---------- 그리기 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        full = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(C.grey50))
        p.drawRoundedRect(full, 16, 16)
        a = self._area()
        mid = a.center().y()

        if self.samples is None:
            return

        # 선택 영역 배경
        xs0, xs1 = self.x_of(self.sel0), self.x_of(self.sel1)
        sel_rect = QRectF(xs0, a.top(), xs1 - xs0, a.height())
        sg = QLinearGradient(sel_rect.topLeft(), sel_rect.bottomLeft())
        sg.setColorAt(0, qc(C.accent, 0.08))
        sg.setColorAt(1, qc(C.accent, 0.08))
        p.fillRect(sel_rect.intersected(a), sg)

        # 파형
        bar_w, gap = 2.0, 1.0
        buckets = max(10, int(a.width() / (bar_w + gap)))
        self._ensure_peaks(buckets)
        now = ticker().now()
        intro = 1.0
        if self._intro_t is not None:
            intro_el = now - self._intro_t
            if intro_el > 1.2:
                self._intro_t = None
        grad_in = QLinearGradient(QPointF(0, a.top()), QPointF(0, a.bottom()))
        grad_in.setColorAt(0, QColor(C.g0))
        grad_in.setColorAt(0.5, QColor(C.g2))
        grad_in.setColorAt(1, QColor(C.g0))
        out_col = qc(C.grey300)
        p.setPen(Qt.PenStyle.NoPen)
        half = a.height() / 2 - 4
        for i, (mn, mx) in enumerate(self._peaks):
            x = a.left() + i * (bar_w + gap)
            t = self.t_of(x + bar_w / 2)
            if self._intro_t is not None:
                intro = ease_out_cubic((now - self._intro_t - i / max(1, buckets) * 0.5) / 0.6)
                if intro <= 0:
                    continue
            g = self._env(t)
            top = max(-1.0, min(1.0, mx * g)) * half * intro
            bot = max(-1.0, min(1.0, mn * g)) * half * intro
            h = max(1.5, top - bot)
            inside = self.sel0 <= t <= self.sel1
            p.setBrush(grad_in if inside else out_col)
            p.drawRoundedRect(QRectF(x, mid - top, bar_w, h), 1, 1)

        # 중앙선
        p.setPen(QPen(qc(C.grey200), 1))
        p.drawLine(QPointF(a.left(), mid), QPointF(a.right(), mid))

        # 페이드 곡선
        p.setPen(QPen(qc(C.grey700, 0.7), 1.4, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        if self.fade_in > 0:
            path = QPainterPath()
            path.moveTo(xs0, a.bottom())
            path.lineTo(self.x_of(self.sel0 + self.fade_in), a.top() + 4)
            p.drawPath(path)
        if self.fade_out > 0:
            path = QPainterPath()
            path.moveTo(self.x_of(self.sel1 - self.fade_out), a.top() + 4)
            path.lineTo(xs1, a.bottom())
            p.drawPath(path)

        # 선택 바깥 흐리게
        p.fillRect(QRectF(a.left(), a.top(), max(0, xs0 - a.left()), a.height()), qc(C.grey50, 0.5))
        p.fillRect(QRectF(xs1, a.top(), max(0, a.right() - xs1), a.height()), qc(C.grey50, 0.5))

        # 핸들
        for which, x, t in (("start", xs0, self.sel0), ("end", xs1, self.sel1)):
            if x < a.left() - 2 or x > a.right() + 2:
                continue
            hot = self._hover == which or (self._drag and self._drag[0] == which)
            p.setPen(QPen(qc(C.accent), 2.2 if hot else 1.6))
            p.drawLine(QPointF(x, a.top() - 2), QPointF(x, a.bottom() + 2))
            lab = _fmt(t)
            p.setFont(font(11, QFont.Weight.Bold))
            tw = p.fontMetrics().horizontalAdvance(lab) + 14
            bx = x - tw / 2
            bx = max(2, min(self.width() - tw - 2, bx))
            pill = QRectF(bx, 3, tw, 19)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(C.grey900) if hot else qc(C.grey800))
            p.drawRoundedRect(pill, 9.5, 9.5)
            p.setPen(QColor("#FFFFFF"))
            p.drawText(pill, Qt.AlignmentFlag.AlignCenter, lab)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QPointF(x, mid), 6.5 if hot else 5.5, 6.5 if hot else 5.5)
            p.setPen(QPen(qc(C.accent), 2))
            p.drawEllipse(QPointF(x, mid), 6.5 if hot else 5.5, 6.5 if hot else 5.5)

        # 재생 위치
        if self.playhead is not None:
            x = self.x_of(self.playhead)
            if a.left() <= x <= a.right():
                p.setPen(QPen(qc(C.grey900, 0.85), 1.5))
                p.drawLine(QPointF(x, a.top()), QPointF(x, a.bottom()))
                pulse = 0.5 + 0.5 * math.sin(now * 10)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc(C.text, 0.15 + 0.15 * pulse))
                p.drawEllipse(QPointF(x, a.top()), 7, 7)
                p.setBrush(qc(C.text))
                p.drawEllipse(QPointF(x, a.top()), 3.5, 3.5)

        # 눈금
        p.setFont(font(10.5))
        span = self.v1 - self.v0
        step = next((s for s in (0.1, 0.25, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300) if span / s <= 10), 600)
        t = math.ceil(self.v0 / step) * step
        while t <= self.v1 + 1e-6:
            x = self.x_of(t)
            p.setPen(QPen(qc(C.grey300), 1))
            p.drawLine(QPointF(x, a.bottom() + 2), QPointF(x, a.bottom() + 6))
            p.setPen(qc(C.grey400))
            lab = f"{t:.1f}s" if step < 1 else (f"{int(t)}s" if t < 60 else f"{int(t // 60)}:{int(t % 60):02d}")
            p.drawText(QRectF(x - 30, a.bottom() + 6, 60, 16), Qt.AlignmentFlag.AlignCenter, lab)
            t += step

    def _env(self, t):
        """미리보기용 페이드/음량 반영."""
        g = self.gain
        if self.fade_in > 0 and self.sel0 <= t < self.sel0 + self.fade_in:
            g *= (t - self.sel0) / self.fade_in
        if self.fade_out > 0 and self.sel1 - self.fade_out < t <= self.sel1:
            g *= (self.sel1 - t) / self.fade_out
        return g


class SoundEditorDialog(BaseDialog):
    """mode='new': 새 종소리로 등록 (YouTube/파일), mode='existing': 기존 종소리 편집"""

    def __init__(self, ctx, src_path, name="", mode="new", sound_row=None, parent=None):
        super().__init__("종소리 다듬기", "필요한 부분만 남기고, 시작과 끝을 부드럽게 만들어요.", None, parent, 820)
        self.ctx = ctx
        self.src = Path(src_path)
        self.mode = mode
        self.sound_row = sound_row
        self.result_id = None
        self._preview_path = None
        self._play_t0 = None
        self._play_offset = 0.0
        self._play_len = 0.0
        self._loading = True

        # 이름 / 저장 방식
        top = QHBoxLayout()
        top.setSpacing(12)
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("종소리 이름")
        top.addWidget(_row("이름", self.name_edit), 1)
        if mode == "existing":
            self.save_mode = SegmentedControl(["새로 저장", "원래 파일에 덮어쓰기"], compact=True)
            wrap = QVBoxLayout()
            wrap.setSpacing(6)
            wrap.addWidget(field_label("저장"))
            wrap.addWidget(self.save_mode)
            top.addLayout(wrap)
        else:
            self.save_mode = None
        self.body.addLayout(top)

        # 파형 + 로딩
        self.wave_holder = QWidget()
        stack = QStackedLayout(self.wave_holder)
        self.wave = WaveformView()
        loading = QWidget()
        ll = QVBoxLayout(loading)
        ll.addStretch(1)
        sp_row = QHBoxLayout()
        sp_row.addStretch(1)
        sp_row.addWidget(Spinner(34))
        sp_row.addStretch(1)
        ll.addLayout(sp_row)
        self.loading_label = QLabel("파형을 불러오는 중…")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet(f"color: {C.grey500};")
        ll.addWidget(self.loading_label)
        ll.addStretch(1)
        stack.addWidget(loading)
        stack.addWidget(self.wave)
        self._stack = stack
        self.wave_holder.setMinimumHeight(230)
        self.body.addWidget(self.wave_holder, 1)
        self.notice = QLabel("")
        self.notice.setWordWrap(True)
        self.notice.setStyleSheet(f"color: {C.grey700}; background: {C.grey50}; border-radius: 10px;"
                                  f" padding: 8px 12px; font-weight: 600;")
        self.notice.hide()
        self.body.addWidget(self.notice)

        zr = QHBoxLayout()
        zr.setSpacing(6)
        hint = muted_label("끌어서 구간을 고르고, 양 끝을 잡아 조절해요. 오른쪽 클릭하면 그 자리부터 들려줘요.")
        hint.setStyleSheet(f"color: {C.grey400}; font-size: 12.5px;")
        zr.addWidget(hint)
        zr.addStretch(1)
        for txt, fn in (("확대", lambda: self.wave.zoom(0.6)), ("축소", lambda: self.wave.zoom(1.6)),
                        ("고른 부분만", self.wave.zoom_to_selection), ("전체", self.wave.zoom_all)):
            b = Button(txt, variant="subtle", size="sm")
            b.clicked.connect(fn)
            zr.addWidget(b)
        self.body.addLayout(zr)

        # 조절 영역
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(8)

        def dspin(maxv=9999.0, step=0.05, suffix=" 초"):
            s = QDoubleSpinBox()
            s.setDecimals(2)
            s.setRange(0.0, maxv)
            s.setSingleStep(step)
            s.setSuffix(suffix)
            s.setKeyboardTracking(False)
            return s

        self.start_spin = dspin()
        self.end_spin = dspin()
        self.len_label = QLabel("-")
        self.len_label.setStyleSheet(f"font-weight: 700; color: {C.grey900}; font-size: 16px;")
        self.fade_in = dspin(30, 0.1)
        self.fade_out = dspin(30, 0.1)
        self.gain = QSlider(Qt.Orientation.Horizontal)
        self.gain.setRange(-120, 120)
        self.gain.setValue(0)
        self.gain_label = QLabel("0.0 dB")
        self.gain_label.setFixedWidth(64)
        self.gain_label.setStyleSheet(f"font-weight: 600; color: {C.grey800};")
        self.normalize = ToggleSwitch("크기 자동 맞춤")
        self.normalize.setToolTip("다른 종소리와 비슷한 크기가 되도록 음량을 자동으로 맞춥니다.")

        grid.addWidget(field_label("시작"), 0, 0)
        grid.addWidget(field_label("끝"), 0, 1)
        grid.addWidget(field_label("남길 길이"), 0, 2)
        grid.addWidget(field_label("페이드 인"), 0, 3)
        grid.addWidget(field_label("페이드 아웃"), 0, 4)
        grid.addWidget(self.start_spin, 1, 0)
        grid.addWidget(self.end_spin, 1, 1)
        grid.addWidget(self.len_label, 1, 2)
        grid.addWidget(self.fade_in, 1, 3)
        grid.addWidget(self.fade_out, 1, 4)

        gr = QHBoxLayout()
        gr.setSpacing(10)
        gr.addWidget(field_label("음량 조절"))
        gr.addWidget(self.gain, 1)
        gr.addWidget(self.gain_label)
        gr.addSpacing(10)
        gr.addWidget(self.normalize)
        gr.addSpacing(10)
        self.btn_autotrim = Button("앞뒤 조용한 부분 자르기", variant="secondary", size="sm")
        gr.addWidget(self.btn_autotrim)
        self.btn_reset = Button("처음으로", variant="subtle", size="sm")
        gr.addWidget(self.btn_reset)

        self.body.addLayout(grid)
        self.body.addLayout(gr)

        # 미리듣기 (footer 왼쪽)
        self.btn_play = Button("들어보기", icon_name="play", variant="secondary", size="lg")
        self.btn_stop = Button("", icon_name="stop", variant="secondary", size="lg")
        self.footer_left.addWidget(self.btn_play)
        self.footer_left.addWidget(self.btn_stop)
        if mode == "existing" and sound_files.original_backup(int(sound_row["id"])):
            self.btn_restore = Button("원본으로 되돌리기", variant="subtle", size="lg")
            self.btn_restore.clicked.connect(self._restore)
            self.footer_left.addWidget(self.btn_restore)
        self.btn_ok.setText("저장")
        self.btn_ok.setEnabled(False)

        # 연결
        self.wave.selectionChanged.connect(self._from_wave)
        self.wave.seekRequested.connect(self._play_from)
        self.start_spin.valueChanged.connect(self._from_spins)
        self.end_spin.valueChanged.connect(self._from_spins)
        self.fade_in.valueChanged.connect(self._sync_env)
        self.fade_out.valueChanged.connect(self._sync_env)
        self.gain.valueChanged.connect(self._sync_env)
        self.btn_autotrim.clicked.connect(self._auto_trim)
        self.btn_reset.clicked.connect(self._reset)
        self.btn_play.clicked.connect(self._preview)
        self.btn_stop.clicked.connect(self._stop)

        self._ph = ticker()
        self.resize(900, 640)

        if not ffmpeg.available():
            self.loading_label.setText("ffmpeg를 찾을 수 없어 편집할 수 없습니다.")
        else:
            run_async(ffmpeg.decode_mono, str(self.src), RATE, on_done=self._loaded, on_fail=self._load_failed)

    # ---------- 로딩 ----------
    def _loaded(self, samples):
        try:
            self.wave.set_samples(samples)
        except RuntimeError:
            return
        self._loading = False
        self._stack.setCurrentIndex(1)
        d = self.wave.duration
        for s in (self.start_spin, self.end_spin):
            s.setMaximum(d)
        self.start_spin.blockSignals(True)
        self.end_spin.blockSignals(True)
        self.start_spin.setValue(0.0)
        self.end_spin.setValue(d)
        self.start_spin.blockSignals(False)
        self.end_spin.blockSignals(False)
        self._update_len()
        self.btn_ok.setEnabled(True)
        if d > 30 and self.mode == "new":
            # 긴 음원(YouTube 등)은 앞쪽 소리 나는 부분 10초를 먼저 제안
            a, _ = suggest_trim(samples[: int(RATE * min(d, 120))], RATE)
            self.wave.set_selection(a, min(d, a + 10.0), emit=True)
            self.fade_out.setValue(1.0)
            self.notice.setText("긴 음원이라 소리가 시작되는 앞부분 10초를 먼저 골라 두었어요. 핸들을 끌어 바꿀 수 있어요.")
            self.notice.show()

    def _load_failed(self, msg):
        self.loading_label.setText("음원을 불러오지 못했습니다.\n" + msg[-200:])

    # ---------- 동기화 ----------
    def _from_wave(self, a, b):
        for s, v in ((self.start_spin, a), (self.end_spin, b)):
            s.blockSignals(True)
            s.setValue(v)
            s.blockSignals(False)
        self._update_len()

    def _from_spins(self, *_):
        a, b = self.start_spin.value(), self.end_spin.value()
        if b <= a:
            b = min(self.wave.duration, a + 0.05)
        self.wave.set_selection(a, b)
        self._update_len()

    def _update_len(self):
        self.len_label.setText(_fmt(self.wave.sel1 - self.wave.sel0))
        self._sync_env()

    def _sync_env(self, *_):
        db = self.gain.value() / 10.0
        self.gain_label.setText(f"{db:+.1f} dB")
        self.wave.gain = 10 ** (db / 20)
        self.wave.fade_in = self.fade_in.value()
        self.wave.fade_out = self.fade_out.value()
        self.wave.update()

    def _auto_trim(self):
        if self.wave.samples is None:
            return
        a, b = suggest_trim(self.wave.samples, RATE)
        self.wave.set_selection(a, b, emit=True)
        self.notice.setText(f"앞뒤 조용한 부분을 잘라 {_fmt(b - a)}만 남겼어요.")
        self.notice.show()

    def _reset(self):
        self.wave.set_selection(0, self.wave.duration, emit=True)
        self.fade_in.setValue(0)
        self.fade_out.setValue(0)
        self.gain.setValue(0)
        self.normalize.setChecked(False)
        self.wave.zoom_all()

    def params(self):
        return EditParams(start=self.wave.sel0, end=self.wave.sel1, fade_in=self.fade_in.value(),
                          fade_out=self.fade_out.value(), gain_db=self.gain.value() / 10.0,
                          normalize=self.normalize.isChecked())

    # ---------- 미리듣기 ----------
    def _preview(self):
        self._render_and_play(self.params(), self.wave.sel0)

    def _play_from(self, t):
        p = self.params()
        p.start = t
        if p.end <= t:
            p.end = self.wave.duration
        p.fade_in = 0
        self._render_and_play(p, t)

    def _render_and_play(self, params, offset):
        if self._loading:
            return
        self.btn_play.setEnabled(False)
        out = temp_dir() / f"preview_{int(time.time() * 1000)}.wav"
        dur = self.wave.duration

        def work():
            ffmpeg.render(self.src, out, build_filter(params, dur))
            return str(out)

        def done(path):
            try:
                self.btn_play.setEnabled(True)
                self.ctx.player.play(path, 1.0, "미리듣기")
                self._preview_path = path
                self._play_t0 = time.monotonic()
                self._play_offset = offset
                self._play_len = params.length(dur)
                self._ph.subscribe(self)
            except Exception as e:
                self.show_error(str(e))

        def fail(msg):
            try:
                self.btn_play.setEnabled(True)
                self.show_error("미리듣기를 만들지 못했어요: " + msg[-160:])
            except RuntimeError:
                pass

        run_async(work, on_done=done, on_fail=fail)

    def on_frame(self, t):
        if self._play_t0 is None:
            self._ph.unsubscribe(self)
            return
        el = time.monotonic() - self._play_t0
        if el > self._play_len + 0.2 or not self.ctx.player.is_playing():
            self._play_t0 = None
            self.wave.playhead = None
        else:
            self.wave.playhead = self._play_offset + el
        self.wave.update()

    def _stop(self):
        self.ctx.player.stop()
        self._play_t0 = None
        self.wave.playhead = None
        self.wave.update()

    # ---------- 저장 ----------
    def validate(self):
        if self._loading:
            return "아직 음원을 불러오는 중이에요."
        if not self.name_edit.text().strip():
            return "이름을 입력해 주세요."
        if self.wave.sel1 - self.wave.sel0 < 0.1:
            return "구간이 너무 짧아요."
        return None

    def _try_accept(self):
        err = self.validate()
        if err:
            self.show_error(err)
            return
        self._stop()
        name = self.name_edit.text().strip()
        params = self.params()
        dur = self.wave.duration
        overwrite = self.save_mode is not None and self.save_mode.current() == 1
        if overwrite and not confirm(self, "원래 파일에 덮어쓸까요?", "원본은 따로 보관해 두니까 나중에 되돌릴 수 있어요.",
                                     "덮어쓰기", danger=False):
            return
        self.btn_ok.setEnabled(False)
        self.btn_ok.setText("저장 중…")
        self.btn_cancel.setEnabled(False)
        self._saving = True
        row = self.sound_row
        src = self.src

        # 소리 만들기는 오래 걸릴 수 있어 작업 스레드에서, 파일 교체와 기록은 화면 스레드에서 한다
        def work():
            if overwrite:
                return sound_files.render_edit_temp(row, params, dur)
            return sound_files.render_edit_new(src, params, dur, name)

        def done(path):
            try:
                from app.data import repo
                if overwrite:
                    sound_files.commit_overwrite(self.ctx.conn, self.ctx.player, row, path)
                    repo.update_sound(self.ctx.conn, int(row["id"]), name, float(row["volume"]))
                    self.result_id = int(row["id"])
                else:
                    vol = float(row["volume"]) if row is not None else 1.0
                    self.result_id = repo.insert_sound(self.ctx.conn, name, Path(path).name, vol)
            except RuntimeError:
                return
            except Exception as e:
                fail(str(e))
                return
            self._saving = False
            self.accept()

        def fail(msg):
            try:
                self._saving = False
                self.btn_ok.setEnabled(True)
                self.btn_ok.setText("저장")
                self.btn_cancel.setEnabled(True)
                self.show_error("저장하지 못했어요: " + str(msg)[-200:])
            except RuntimeError:
                pass

        run_async(work, on_done=done, on_fail=fail)

    def _restore(self):
        if not confirm(self, "원본으로 되돌릴까요?", "처음 넣었던 소리로 돌아가요.", "되돌리기", danger=False):
            return
        self._stop()
        sound_files.restore_original(self.ctx.conn, self.ctx.player, self.sound_row)
        self.result_id = int(self.sound_row["id"])
        self.ctx.toast("원본으로 되돌렸어요", "success")
        self.accept()

    def reject(self):
        if getattr(self, "_saving", False):
            return
        super().reject()

    def done(self, r):
        self._stop()
        self._ph.unsubscribe(self)
        super().done(r)


def open_editor_for_sound(ctx, sound_row, parent):
    path = sound_file_path(str(sound_row["file_name"]))
    if not path.exists():
        from app.ui.dialogs import notify
        notify(parent, "파일 없음", "종소리 파일을 찾을 수 없어요.", "warning")
        return None
    dlg = SoundEditorDialog(ctx, path, str(sound_row["name"]), "existing", sound_row, parent)
    if dlg.exec() == QDialog.DialogCode.Accepted:
        return dlg.result_id
    return None
