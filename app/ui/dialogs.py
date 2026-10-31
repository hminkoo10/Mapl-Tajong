import math
from pathlib import Path

from PyQt6.QtCore import QPoint, QRectF, Qt, QTime, QTimer, QVariantAnimation
from PyQt6.QtGui import QPainter
from PyQt6.QtWidgets import (QDialog, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMainWindow, QScrollArea, QSlider, QSpinBox, QTimeEdit, QVBoxLayout, QWidget)

from app.core.timeutil import mask_to_days
from app.ui.select import Select
from app.ui.theme import C, paint_soft_shadow, qc
from app.ui.widgets import (Button, DayChips, IconButton, SegmentedControl, SlideBar, ToggleSwitch, _anim, field_label,
                            hline, muted_label)

SHADOW = 22


class _Dim(QWidget):
    """대화상자가 열려 있는 동안 메인 창을 살짝 어둡게."""

    def __init__(self, host):
        super().__init__(host)
        self.k = 0.0
        self.setGeometry(host.rect())
        self.show()
        self.raise_()

    def set_k(self, v):
        self.k = float(v)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), qc("#000000", 0.28 * self.k))


class BaseDialog(QDialog):
    def __init__(self, title, subtitle="", icon_name=None, parent=None, width=480):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setWindowFlags(Qt.WindowType.Dialog | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMinimumWidth(width + SHADOW * 2)
        self._fade = None
        self._dim = None
        self._drag = None

        root = QVBoxLayout(self)
        root.setContentsMargins(SHADOW + 28, SHADOW + 26, SHADOW + 28, SHADOW + 24)
        root.setSpacing(0)

        top = QHBoxLayout()
        top.setSpacing(8)
        tcol = QVBoxLayout()
        tcol.setSpacing(6)
        t = QLabel(title)
        t.setStyleSheet(f"font-size: 20px; font-weight: 700; color: {C.grey900};")
        tcol.addWidget(t)
        if subtitle:
            s = QLabel(subtitle)
            s.setWordWrap(True)
            s.setStyleSheet(f"font-size: 14px; color: {C.grey600};")
            tcol.addWidget(s)
        top.addLayout(tcol, 1)
        close = IconButton("x", "닫기", "subtle", "sm")
        close.clicked.connect(self.reject)
        top.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        root.addLayout(top)
        root.addSpacing(22)

        self.body_widget = QWidget()
        self.body = QVBoxLayout(self.body_widget)
        self.body.setContentsMargins(0, 0, 0, 0)
        self.body.setSpacing(18)
        root.addWidget(self.body_widget, 1)

        self.error = QLabel("")
        self.error.setWordWrap(True)
        self.error.setStyleSheet(f"color: {C.danger}; font-size: 13px; font-weight: 600; padding-top: 12px;")
        self.error.hide()
        root.addWidget(self.error)
        root.addSpacing(24)

        foot = QHBoxLayout()
        foot.setSpacing(8)
        self.footer_left = QHBoxLayout()
        self.footer_left.setSpacing(6)
        foot.addLayout(self.footer_left)
        foot.addStretch(1)
        self.btn_cancel = Button("취소", variant="secondary", size="lg")
        self.btn_ok = Button("확인", variant="primary", size="lg")
        self.btn_cancel.setMinimumWidth(96)
        self.btn_ok.setMinimumWidth(120)
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok.clicked.connect(self._try_accept)
        foot.addWidget(self.btn_cancel)
        foot.addWidget(self.btn_ok)
        root.addLayout(foot)

    # ---------- 그리기 / 이동 ----------
    def panel_rect(self):
        return QRectF(self.rect()).adjusted(SHADOW, SHADOW, -SHADOW, -SHADOW)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.panel_rect()
        paint_soft_shadow(p, r, 24, strength=3, spread=SHADOW - 2, dy=6)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#FFFFFF"))
        p.drawRoundedRect(r, 24, 24)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().y() < SHADOW + 70:
            self._drag = e.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._drag is not None:
            self.move(e.globalPosition().toPoint() - self._drag)
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        self._drag = None
        super().mouseReleaseEvent(e)

    # ---------- 열고 닫기 ----------
    def showEvent(self, e):
        super().showEvent(e)
        pw = self.parentWidget()
        host = pw.window() if pw is not None else None
        if host is not None:
            g = host.frameGeometry()
            self.move(g.center().x() - self.width() // 2, g.center().y() - self.height() // 2)
        if isinstance(host, QMainWindow) and host.centralWidget() is not None and self._dim is None:
            self._dim = _Dim(host.centralWidget())
            _anim(self._dim, 0.0, 1.0, 180, self._dim.set_k).start()
        end = self.pos()
        start = end + QPoint(0, 12)
        self.setWindowOpacity(0.0)

        def step(v):
            k = float(v)
            self.setWindowOpacity(k)
            self.move(start + (end - start) * k)
        self._fade = _anim(self, 0.0, 1.0, 200, step)
        self._fade.start()

    def done(self, r):
        if self._dim is not None:
            dim = self._dim
            self._dim = None
            try:
                _anim(dim, dim.k, 0.0, 150, dim.set_k, on_done=dim.deleteLater).start()
            except RuntimeError:
                pass
        super().done(r)

    def validate(self):
        return None

    def _try_accept(self):
        err = self.validate()
        if err:
            self.show_error(err)
            return
        self.accept()

    def show_error(self, msg):
        self.error.setText(msg)
        self.error.show()
        base = self.pos()
        a = QVariantAnimation(self)
        a.setDuration(360)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(lambda v: self.move(base + QPoint(int(6 * math.sin(float(v) * math.pi * 5) * (1 - float(v))), 0)))
        a.finished.connect(lambda: self.move(base))
        a.start()
        self._shake = a


def _row(label, widget):
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(8)
    lay.addWidget(field_label(label))
    if isinstance(widget, QWidget):
        lay.addWidget(widget)
    else:
        lay.addLayout(widget)
    return w


class VolumeField(QWidget):
    """'기본 음량 사용' 토글 + 0~200% 슬라이더."""

    def __init__(self, allow_default=True, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.use_default = ToggleSwitch("종소리 기본 음량 사용") if allow_default else None
        if self.use_default:
            self.use_default.setChecked(True)
            self.use_default.toggled.connect(self._sync)
            lay.addWidget(self.use_default)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 200)
        self.slider.setSingleStep(5)
        self.slider.setPageStep(10)
        self.slider.setValue(100)
        self.value_label = QLabel("100%")
        self.value_label.setFixedWidth(48)
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.value_label.setStyleSheet(f"font-weight: 700; color: {C.grey900}; font-size: 15px;")
        self.slider.valueChanged.connect(lambda v: self.value_label.setText(f"{v}%"))
        row.addWidget(self.slider, 1)
        row.addWidget(self.value_label)
        lay.addLayout(row)
        self._sync()

    def _sync(self, *_):
        on = not (self.use_default and self.use_default.isChecked())
        self.slider.setEnabled(on)
        self.value_label.setStyleSheet(
            f"font-weight: 700; color: {C.grey900 if on else C.grey400}; font-size: 15px;")

    def set_value(self, v):
        if v is None and self.use_default:
            self.use_default.setChecked(True)
            self.slider.setValue(100)
        else:
            if self.use_default:
                self.use_default.setChecked(False)
            self.slider.setValue(int(round(float(v if v is not None else 1.0) * 100)))
        self._sync()

    def value(self):
        if self.use_default and self.use_default.isChecked():
            return None
        return self.slider.value() / 100.0


def _sound_combo(sounds, current=None):
    cb = Select()
    for s in sounds:
        cb.addItem(str(s["name"]), int(s["id"]))
    if current is not None:
        i = cb.findData(int(current))
        if i >= 0:
            cb.setCurrentIndex(i)
    return cb


# =====================================================================
class ScheduleDialog(BaseDialog):
    def __init__(self, ctx, sounds, data=None, parent=None):
        editing = data is not None
        super().__init__("일정 수정" if editing else "일정 추가", "", None, parent, 500)
        self.ctx = ctx
        self.sounds = sounds
        self.btn_ok.setText("저장")

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("예) 1교시 시작")
        self.body.addWidget(_row("이름", self.name_edit))

        self.days = DayChips()
        self.body.addWidget(_row("요일", self.days))

        trow = QHBoxLayout()
        trow.setSpacing(6)
        self.time_edit = QTimeEdit()
        self.time_edit.setDisplayFormat("HH:mm")
        self.time_edit.setTime(QTime(9, 0))
        self.time_edit.setFixedWidth(120)
        trow.addWidget(self.time_edit)
        for txt, mins in (("-5분", -5), ("+5분", 5), ("+10분", 10)):
            b = Button(txt, variant="secondary", size="sm")
            b.clicked.connect(lambda _=False, m=mins: self.time_edit.setTime(self.time_edit.time().addSecs(m * 60)))
            trow.addWidget(b)
        trow.addStretch(1)
        self.body.addWidget(_row("시간", trow))

        srow = QHBoxLayout()
        srow.setSpacing(6)
        self.sound_combo = _sound_combo(sounds)
        srow.addWidget(self.sound_combo, 1)
        self.btn_preview = IconButton("play", "들어보기", "secondary")
        self.btn_preview.clicked.connect(self._preview)
        srow.addWidget(self.btn_preview)
        self.body.addWidget(_row("종소리", srow))

        self.volume = VolumeField(allow_default=True)
        self.body.addWidget(_row("음량", self.volume))

        self.enabled = ToggleSwitch("이 일정 사용")
        self.enabled.setChecked(True)
        self.body.addWidget(self.enabled)

        if editing:
            self.name_edit.setText(str(data["name"]))
            self.days.set_mask(int(data["weekday_mask"]))
            hh, mm = str(data["time_hhmm"]).split(":")
            self.time_edit.setTime(QTime(int(hh), int(mm)))
            self.enabled.setChecked(int(data["enabled"]) == 1)
            i = self.sound_combo.findData(int(data["sound_id"]))
            if i >= 0:
                self.sound_combo.setCurrentIndex(i)
            self.volume.set_value(data["volume_override"])
        else:
            self.days.set_mask(31)
        QTimer.singleShot(0, self.name_edit.setFocus)

    def _preview(self):
        sid = self.sound_combo.currentData()
        s = next((x for x in self.sounds if int(x["id"]) == int(sid)), None) if sid is not None else None
        if not s or not self.ctx:
            return
        from app.core.paths import sound_file_path
        v = self.volume.value()
        try:
            self.ctx.player.play(str(sound_file_path(str(s["file_name"]))), float(s["volume"]) if v is None else v,
                                 str(s["name"]))
        except Exception as e:
            self.show_error(str(e))

    def validate(self):
        if not self.name_edit.text().strip():
            return "이름을 입력해 주세요."
        if self.days.mask() == 0:
            return "요일을 하나 이상 골라 주세요."
        if self.sound_combo.currentData() is None:
            return "종소리를 골라 주세요."
        return None

    def get_value(self):
        t = self.time_edit.time()
        return (self.name_edit.text().strip(), self.days.mask(), f"{t.hour():02d}:{t.minute():02d}",
                int(self.sound_combo.currentData()), self.volume.value(), 1 if self.enabled.isChecked() else 0)


# =====================================================================
class _Section(QWidget):
    """제목 + 스위치 한 줄. 켜면 아래 내용이 열린다."""

    def __init__(self, title, desc, content, on_change):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 14, 0, 14)
        lay.setSpacing(0)
        head = QHBoxLayout()
        col = QVBoxLayout()
        col.setSpacing(2)
        t = QLabel(title)
        t.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {C.grey900};")
        d = QLabel(desc)
        d.setStyleSheet(f"font-size: 13px; color: {C.grey500};")
        col.addWidget(t)
        col.addWidget(d)
        head.addLayout(col, 1)
        self.toggle = ToggleSwitch("")
        head.addWidget(self.toggle)
        lay.addLayout(head)
        inner = QWidget()
        il = QVBoxLayout(inner)
        il.setContentsMargins(0, 14, 0, 0)
        il.setSpacing(8)
        if isinstance(content, QWidget):
            il.addWidget(content)
        else:
            il.addLayout(content)
        self.slide = SlideBar(inner)
        lay.addWidget(self.slide)
        self.toggle.toggled.connect(self.slide.set_open)
        self.toggle.toggled.connect(lambda *_: on_change())

    def active(self):
        return self.toggle.isChecked()


class BatchEditDialog(BaseDialog):
    def __init__(self, ctx, rows, sounds, sets, current_set_id, parent=None):
        n = len(rows)
        super().__init__(f"일정 {n}개 한 번에 바꾸기", "바꿀 항목만 켜 주세요. 나머지는 그대로 둬요.", None, parent, 540)
        self.rows = rows
        self.btn_ok.setText("바꾸기")

        names = ", ".join(f"{r['time_hhmm']} {r['name']}" for r in rows[:4]) + (f" 외 {n - 4}개" if n > 4 else "")
        preview = QLabel(names)
        preview.setWordWrap(True)
        preview.setStyleSheet(f"color: {C.grey700}; font-size: 13px; background: {C.grey50};"
                              f" border-radius: 10px; padding: 10px 12px;")
        self.body.addWidget(preview)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        holder = QWidget()
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 10, 0)
        hl.setSpacing(0)
        scroll.setWidget(holder)
        scroll.setMinimumHeight(380)
        self.body.addWidget(scroll, 1)

        self.seg_enabled = SegmentedControl(["켜기", "끄기"], compact=True)
        self.seg_enabled.changed.connect(self._update_summary)
        self.sec_enabled = _Section("사용 여부", "일정을 켜거나 꺼요", self.seg_enabled, self._update_summary)

        dl = QVBoxLayout()
        dl.setSpacing(10)
        self.seg_days = SegmentedControl(["이 요일로", "요일 추가", "요일 빼기"], compact=True)
        self.seg_days.changed.connect(self._update_summary)
        self.days = DayChips()
        self.days.maskChanged.connect(self._update_summary)
        dl.addWidget(self.seg_days)
        dl.addWidget(self.days)
        self.sec_days = _Section("요일", "요일을 바꾸거나 더하고 빼요", dl, self._update_summary)

        tw = QWidget()
        twl = QVBoxLayout(tw)
        twl.setContentsMargins(0, 0, 0, 0)
        twl.setSpacing(8)
        tl = QHBoxLayout()
        tl.setSpacing(6)
        self.shift = QSpinBox()
        self.shift.setRange(-720, 720)
        self.shift.setSuffix("분")
        self.shift.setFixedWidth(110)
        self.shift.valueChanged.connect(self._update_summary)
        tl.addWidget(self.shift)
        for txt, m in (("-10", -10), ("-5", -5), ("+5", 5), ("+10", 10)):
            b = Button(txt, variant="secondary", size="sm")
            b.clicked.connect(lambda _=False, mm=m: self.shift.setValue(self.shift.value() + mm))
            tl.addWidget(b)
        tl.addStretch(1)
        twl.addLayout(tl)
        twl.addWidget(muted_label("자정을 넘기면 요일도 같이 바뀌어요.", wrap=True))
        self.sec_shift = _Section("시간 옮기기", "전부 같은 만큼 당기거나 미뤄요", tw, self._update_summary)

        self.sound_combo = _sound_combo(sounds)
        self.sound_combo.currentIndexChanged.connect(self._update_summary)
        self.sec_sound = _Section("종소리", "모두 같은 종소리로 바꿔요", self.sound_combo, self._update_summary)

        self.volume = VolumeField(allow_default=True)
        self.volume.slider.valueChanged.connect(self._update_summary)
        self.volume.use_default.toggled.connect(self._update_summary)
        self.sec_volume = _Section("음량", "일정마다 쓰는 음량이에요", self.volume, self._update_summary)

        nl = QGridLayout()
        nl.setHorizontalSpacing(8)
        self.find_edit = QLineEdit()
        self.find_edit.setPlaceholderText("찾을 글자")
        self.repl_edit = QLineEdit()
        self.repl_edit.setPlaceholderText("바꿀 글자 (비우면 지워요)")
        self.find_edit.textChanged.connect(self._update_summary)
        self.repl_edit.textChanged.connect(self._update_summary)
        nl.addWidget(self.find_edit, 0, 0)
        arrow = QLabel("→")
        arrow.setStyleSheet(f"color: {C.grey400};")
        nl.addWidget(arrow, 0, 1)
        nl.addWidget(self.repl_edit, 0, 2)
        self.sec_name = _Section("이름", "이름 일부를 찾아 바꿔요", nl, self._update_summary)

        self.set_combo = Select()
        for s in sets:
            self.set_combo.addItem(str(s["name"]), int(s["id"]))
        i = self.set_combo.findData(int(current_set_id))
        if i >= 0:
            self.set_combo.setCurrentIndex(i)
        self.set_combo.currentIndexChanged.connect(self._update_summary)
        self.sec_set = _Section("세트 옮기기", "다른 세트로 옮겨요", self.set_combo, self._update_summary)
        self.current_set_id = int(current_set_id)

        self.sections = [self.sec_enabled, self.sec_days, self.sec_shift, self.sec_sound, self.sec_volume,
                         self.sec_name, self.sec_set]
        for i, s in enumerate(self.sections):
            if i:
                hl.addWidget(hline())
            hl.addWidget(s)
        hl.addStretch(1)

        self.summary = QLabel("")
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet(f"color: {C.grey700}; font-size: 13px;")
        self.body.addWidget(self.summary)
        self._update_summary()
        self.resize(640, 760)

    def _update_summary(self, *_):
        parts = []
        if self.sec_enabled.active():
            parts.append("켜기" if self.seg_enabled.current() == 0 else "끄기")
        if self.sec_days.active():
            mode = ["→", "+", "−"][self.seg_days.current()]
            parts.append(f"요일 {mode} {mask_to_days(self.days.mask()) if self.days.mask() else '(없음)'}")
        if self.sec_shift.active() and self.shift.value():
            parts.append(f"{self.shift.value():+d}분")
        if self.sec_sound.active():
            parts.append(f"종소리 {self.sound_combo.currentText()}")
        if self.sec_volume.active():
            v = self.volume.value()
            parts.append("기본 음량" if v is None else f"음량 {int(round(v * 100))}%")
        if self.sec_name.active() and self.find_edit.text():
            parts.append(f"'{self.find_edit.text()}' → '{self.repl_edit.text()}'")
        if self.sec_set.active() and self.set_combo.currentData() != self.current_set_id:
            parts.append(f"{self.set_combo.currentText()} 세트로")
        self.summary.setText(" · ".join(parts) if parts else "")
        self.summary.setVisible(bool(parts))
        self.btn_ok.setEnabled(bool(parts))

    def validate(self):
        if self.sec_days.active() and self.days.mask() == 0:
            return "요일을 하나 이상 골라 주세요."
        return None

    def get_changes(self):
        ch = {}
        if self.sec_enabled.active():
            ch["enabled"] = 1 if self.seg_enabled.current() == 0 else 0
        if self.sec_days.active():
            ch["days_mode"] = ["set", "add", "remove"][self.seg_days.current()]
            ch["days_mask"] = self.days.mask()
        if self.sec_shift.active() and self.shift.value():
            ch["shift_minutes"] = self.shift.value()
        if self.sec_sound.active() and self.sound_combo.currentData() is not None:
            ch["sound_id"] = int(self.sound_combo.currentData())
        if self.sec_volume.active():
            ch["volume"] = self.volume.value()
        if self.sec_name.active() and self.find_edit.text():
            ch["name_find"] = self.find_edit.text()
            ch["name_replace"] = self.repl_edit.text()
        if self.sec_set.active() and self.set_combo.currentData() != self.current_set_id:
            ch["set_id"] = int(self.set_combo.currentData())
        return ch


# =====================================================================
class DuplicateDialog(BaseDialog):
    def __init__(self, count, sets, current_set_id, parent=None):
        super().__init__(f"일정 {count}개 복제", "", None, parent, 440)
        self.btn_ok.setText("복제")
        self.set_combo = Select()
        for s in sets:
            self.set_combo.addItem(str(s["name"]), int(s["id"]))
        i = self.set_combo.findData(int(current_set_id))
        if i >= 0:
            self.set_combo.setCurrentIndex(i)
        self.body.addWidget(_row("어느 세트에 만들까요?", self.set_combo))

        row = QHBoxLayout()
        row.setSpacing(6)
        self.shift = QSpinBox()
        self.shift.setRange(-720, 720)
        self.shift.setSuffix("분")
        self.shift.setFixedWidth(110)
        row.addWidget(self.shift)
        for txt, m in (("+5", 5), ("+10", 10), ("+30", 30)):
            b = Button(txt, variant="secondary", size="sm")
            b.clicked.connect(lambda _=False, mm=m: self.shift.setValue(self.shift.value() + mm))
            row.addWidget(b)
        row.addStretch(1)
        self.body.addWidget(_row("시간 옮기기", row))

        self.suffix = QLineEdit()
        self.suffix.setPlaceholderText("예) (보충)")
        self.body.addWidget(_row("이름 뒤에 붙일 글자", self.suffix))

    def get_value(self):
        suf = self.suffix.text()
        if suf and not suf.startswith(" "):
            suf = " " + suf
        return int(self.set_combo.currentData()), int(self.shift.value()), suf


# =====================================================================
class SoundInfoDialog(BaseDialog):
    """파일에서 종소리 추가 / 이름·음량 수정"""

    def __init__(self, ctx, name="", volume=1.0, pick_file=False, parent=None):
        super().__init__("종소리 추가" if pick_file else "이름과 음량",
                         "wav, mp3, ogg 같은 음원 파일을 넣을 수 있어요." if pick_file else "", None, parent, 460)
        self.ctx = ctx
        self.selected_path = None
        self.pick_file = pick_file
        self.btn_ok.setText("추가" if pick_file else "저장")
        if pick_file:
            row = QHBoxLayout()
            row.setSpacing(6)
            self.path_edit = QLineEdit()
            self.path_edit.setReadOnly(True)
            self.path_edit.setPlaceholderText("파일을 골라 주세요")
            b = Button("찾아보기", variant="secondary")
            b.clicked.connect(self._pick)
            row.addWidget(self.path_edit, 1)
            row.addWidget(b)
            self.body.addWidget(_row("파일", row))
        self.name_edit = QLineEdit(name)
        self.name_edit.setPlaceholderText("예) 수업 시작종")
        self.body.addWidget(_row("이름", self.name_edit))
        self.volume = VolumeField(allow_default=False)
        self.volume.set_value(volume)
        self.body.addWidget(_row("기본 음량", self.volume))

    def _pick(self):
        path, _ = QFileDialog.getOpenFileName(self, "종소리 파일 선택", "",
                                              "오디오 파일 (*.wav *.mp3 *.ogg *.flac *.m4a *.aac *.wma *.opus);;모든 파일 (*)")
        if path:
            self.selected_path = path
            self.path_edit.setText(Path(path).name)
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(path).stem)

    def validate(self):
        if self.pick_file and not self.selected_path:
            return "파일을 골라 주세요."
        if not self.pick_file and not self.name_edit.text().strip():
            return "이름을 입력해 주세요."
        return None

    def get_value(self):
        return self.name_edit.text().strip(), self.selected_path, self.volume.value()


class TextInputDialog(BaseDialog):
    def __init__(self, title, label, text="", parent=None, ok_text="확인"):
        super().__init__(title, "", None, parent, 400)
        self.btn_ok.setText(ok_text)
        self.edit = QLineEdit(text)
        self.edit.selectAll()
        self.edit.returnPressed.connect(self._try_accept)
        self.body.addWidget(_row(label, self.edit))
        QTimer.singleShot(0, self.edit.setFocus)

    def validate(self):
        return None if self.edit.text().strip() else "내용을 입력해 주세요."

    def value(self):
        return self.edit.text().strip()


def ask_text(parent, title, label, text="", icon_name=None, ok_text="확인"):
    d = TextInputDialog(title, label, text, parent, ok_text)
    if d.exec() == QDialog.DialogCode.Accepted:
        return d.value()
    return None


class ConfirmDialog(BaseDialog):
    def __init__(self, title, text, ok_text="확인", danger=True, icon_name=None, parent=None):
        super().__init__(title, "", None, parent, 400)
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        lbl.setStyleSheet(f"font-size: 15px; color: {C.grey700};")
        self.body.addWidget(lbl)
        self.btn_ok.setText(ok_text)
        if danger:
            self.btn_ok.set_variant("danger_solid")


def confirm(parent, title, text, ok_text="확인", danger=True, icon_name=None):
    return ConfirmDialog(title, text, ok_text, danger, icon_name, parent).exec() == QDialog.DialogCode.Accepted


def notify(parent, title, text, icon_name=None):
    d = ConfirmDialog(title, text, "확인", False, icon_name, parent)
    d.btn_cancel.hide()
    d.exec()
