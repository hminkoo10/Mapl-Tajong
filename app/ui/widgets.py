"""공용 위젯.

움직임 원칙: 짧고(150~300ms) 작게(10px 이하) 움직인다. 눌렀을 때 살짝 작아지고, 값이 바뀌면 숫자가 굴러간다.
"""
import math
import time

from PyQt6.QtCore import (QEasingCurve, QEvent, QObject, QPoint, QPointF, QRectF, QSize, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import QColor, QConicalGradient, QFont, QFontMetricsF, QPainter, QPen, QPixmap, QRegion
from PyQt6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStackedWidget,
                             QVBoxLayout, QWidget)

from app.ui import icons
from app.ui.theme import C, font, mix, paint_app_background, qc


def ease_out_cubic(t):
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_out_back(t, s=1.2):
    t = max(0.0, min(1.0, t)) - 1
    return t * t * ((s + 1) * t + s) + 1


def ease_in_out(t):
    t = max(0.0, min(1.0, t))
    return 0.5 - 0.5 * math.cos(math.pi * t)


# =====================================================================
# 공용 프레임 틱 (보이는 위젯만 구독 → 트레이로 숨기면 멈춤)
# =====================================================================
class FrameTicker(QObject):
    _inst = None

    @classmethod
    def instance(cls):
        if cls._inst is None:
            cls._inst = FrameTicker()
        return cls._inst

    def __init__(self):
        super().__init__()
        self._t0 = time.monotonic()
        self._subs = []
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)  # Windows 기본(Coarse)은 15.6ms 단위라 프레임이 들쭉날쭉
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)

    def now(self):
        return time.monotonic() - self._t0

    def subscribe(self, w):
        if w not in self._subs:
            self._subs.append(w)
        try:
            if not self._timer.isActive():
                self._timer.start()
        except RuntimeError:
            pass

    def unsubscribe(self, w):
        if w in self._subs:
            self._subs.remove(w)
        if not self._subs:
            try:
                self._timer.stop()
            except RuntimeError:
                pass

    def _tick(self):
        t = self.now()
        for w in list(self._subs):
            try:
                if w.window().isMinimized():
                    continue
                w.on_frame(t)
            except RuntimeError:
                self.unsubscribe(w)


def ticker():
    return FrameTicker.instance()


class TickingWidget(QWidget):
    always_tick = True

    def showEvent(self, e):
        super().showEvent(e)
        if self.always_tick:
            ticker().subscribe(self)

    def hideEvent(self, e):
        super().hideEvent(e)
        ticker().unsubscribe(self)

    def start_ticking(self):
        if self.isVisible():
            ticker().subscribe(self)

    def stop_ticking(self):
        ticker().unsubscribe(self)

    def on_frame(self, t):
        self.update()


def _anim(parent, start, end, ms, on_value, curve=QEasingCurve.Type.OutCubic, on_done=None):
    a = QVariantAnimation(parent)
    a.setStartValue(float(start))
    a.setEndValue(float(end))
    a.setDuration(int(ms))
    a.setEasingCurve(curve)
    a.valueChanged.connect(on_value)
    if on_done:
        a.finished.connect(on_done)
    return a


class _PressMixin:
    """hover/press 진행값을 부드럽게 바꿔 주는 공통 동작."""

    def _init_press(self):
        self._hover = 0.0
        self._press = 0.0
        self._ha = None
        self._pa = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)

    def _set_h(self, v):
        self._hover = float(v)
        self.update()

    def _set_p(self, v):
        self._press = float(v)
        self.update()

    def _hover_to(self, target, ms=120):
        if self._ha:
            self._ha.stop()
        self._ha = _anim(self, self._hover, target, ms, self._set_h)
        self._ha.start()

    def _press_to(self, target, ms):
        if self._pa:
            self._pa.stop()
        self._pa = _anim(self, self._press, target, ms, self._set_p)
        self._pa.start()

    def enterEvent(self, e):
        super().enterEvent(e)
        if self.isEnabled():
            self._hover_to(1.0)

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._hover_to(0.0, 180)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.isEnabled():
            self._press_to(1.0, 80)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._press_to(0.0, 220)
        super().mouseReleaseEvent(e)


# =====================================================================
# 카드
# =====================================================================
class Card(QWidget):
    """흰 바탕, 둥근 모서리, 테두리·그림자 없음."""

    def __init__(self, parent=None, padding=20, radius=20, tint=None):
        super().__init__(parent)
        self.radius = radius
        self.tint = tint
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(padding, padding, padding, padding)
        self.body.setSpacing(12)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(self.tint or C.surface))
        p.drawRoundedRect(QRectF(self.rect()), self.radius, self.radius)


# =====================================================================
# 버튼
# =====================================================================
_BTN = {
    #             기본            hover            pressed          글자
    "primary": (C.accent, C.accent_hover, C.accent_pressed, "#FFFFFF"),
    "secondary": (C.grey100, C.grey200, "#DDE1E5", C.grey700),
    "white": ("#FFFFFF", C.grey50, C.grey100, C.grey700),
    "soft": (C.accent_softer, C.accent_soft, "#FFDDC4", C.accent_text),
    "subtle": ("#00FFFFFF", C.grey100, C.grey200, C.grey600),
    "danger": (C.danger_soft, "#FFE1E3", "#FFD3D6", C.danger),
    "danger_solid": (C.danger, "#E63A48", "#D9303E", "#FFFFFF"),
    "hero": ("#1FFFFFFF", "#2EFFFFFF", "#3DFFFFFF", "#FFFFFF"),
}


class Button(_PressMixin, QPushButton):
    def __init__(self, text="", icon_name=None, variant="secondary", size="md", parent=None):
        super().__init__(text, parent)
        self.variant = variant
        self.size_kind = size
        self.icon_name = icon_name
        self._init_press()
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def set_icon_name(self, name):
        self.icon_name = name
        self.updateGeometry()
        self.update()

    def set_variant(self, v):
        self.variant = v
        self.update()

    def _metrics(self):
        # 높이, 좌우 여백, 글자 크기, 아이콘 크기, 모서리
        return {"sm": (32, 12, 13, 15, 8), "md": (40, 16, 14, 17, 10), "lg": (48, 20, 15, 18, 12)}[self.size_kind]

    def sizeHint(self):
        h, pad, fpx, isz, _ = self._metrics()
        if not self.text():
            return QSize(h, h)
        fm = QFontMetricsF(font(fpx, QFont.Weight.DemiBold))
        w = pad * 2 + fm.horizontalAdvance(self.text())
        if self.icon_name:
            w += isz + 6
        return QSize(int(math.ceil(w)), h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        h, pad, fpx, isz, rad = self._metrics()
        bg, hov, prs, fg = _BTN.get(self.variant, _BTN["secondary"])
        r = QRectF(self.rect())
        sc = 1.0 - 0.03 * self._press
        p.translate(r.center())
        p.scale(sc, sc)
        p.translate(-r.center())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(mix(bg, hov, self._hover), prs, self._press))
        p.drawRoundedRect(r, rad, rad)

        f = font(fpx, QFont.Weight.DemiBold)
        tw = QFontMetricsF(f).horizontalAdvance(self.text()) if self.text() else 0
        total = tw + (isz if self.icon_name else 0) + (6 if self.icon_name and self.text() else 0)
        x = r.center().x() - total / 2
        if self.icon_name:
            p.drawPixmap(QPointF(x, r.center().y() - isz / 2), icons.pixmap(self.icon_name, QColor(fg).name(), isz))
            x += isz + 6
        if self.text():
            p.setFont(f)
            p.setPen(QColor(fg))
            p.drawText(QRectF(x, r.top(), tw + 2, r.height()), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                       self.text())


class IconButton(Button):
    def __init__(self, icon_name, tooltip="", variant="subtle", size="md", parent=None):
        super().__init__("", icon_name, variant, size, parent)
        self.setToolTip(tooltip)


class ActionTile(_PressMixin, QAbstractButton):
    """대시보드 빠른 동작: 아이콘 + 제목 + 설명."""

    def __init__(self, icon_name, title, caption="", parent=None):
        super().__init__(parent)
        self.icon_name = icon_name
        self.title = title
        self.caption = caption
        self._init_press()
        self.setMinimumHeight(72)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_content(self, icon_name=None, title=None, caption=None):
        if icon_name is not None:
            self.icon_name = icon_name
        if title is not None:
            self.title = title
        if caption is not None:
            self.caption = caption
        self.update()

    def sizeHint(self):
        return QSize(220, 72)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        r = QRectF(self.rect())
        sc = 1.0 - 0.025 * self._press
        p.translate(r.center())
        p.scale(sc, sc)
        p.translate(-r.center())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(C.surface, C.grey50, self._hover))
        p.drawRoundedRect(r, 18, 18)

        bs = 40
        badge = QRectF(r.left() + 16, r.center().y() - bs / 2, bs, bs)
        p.setBrush(mix(C.accent_softer, C.accent_soft, self._hover))
        p.drawEllipse(badge)
        p.drawPixmap(QPointF(badge.center().x() - 10, badge.center().y() - 10), icons.pixmap(self.icon_name, C.accent, 20))

        tx = badge.right() + 14
        tw = r.right() - tx - 12
        p.setPen(qc(C.grey900))
        p.setFont(font(15, QFont.Weight.DemiBold))
        title = QFontMetricsF(p.font()).elidedText(self.title, Qt.TextElideMode.ElideRight, tw)
        if self.caption:
            p.drawText(QRectF(tx, r.center().y() - 20, tw, 21), Qt.AlignmentFlag.AlignVCenter, title)
            p.setPen(qc(C.grey500))
            p.setFont(font(12.5))
            p.drawText(QRectF(tx, r.center().y() + 1, tw, 19), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetricsF(p.font()).elidedText(self.caption, Qt.TextElideMode.ElideRight, tw))
        else:
            p.drawText(QRectF(tx, r.top(), tw, r.height()), Qt.AlignmentFlag.AlignVCenter, title)


# =====================================================================
# 토글 / 칩 / 세그먼트
# =====================================================================
class ToggleSwitch(QAbstractButton):
    def __init__(self, text="", parent=None, on_dark=False, text_left=False):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self.on_dark = on_dark
        self.text_left = text_left
        self._pos = 0.0
        self._anim = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggled.connect(self._on_toggled)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

    def _on_toggled(self, on):
        if self._anim:
            self._anim.stop()
        self._anim = _anim(self, self._pos, 1.0 if on else 0.0, 200, self._set_pos)
        self._anim.start()

    def _set_pos(self, v):
        self._pos = float(v)
        self.update()

    def sizeHint(self):
        fm = QFontMetricsF(font(14))
        w = 44 + (12 + fm.horizontalAdvance(self.text()) if self.text() else 0)
        return QSize(int(w) + 2, 28)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        if not (self._anim and self._anim.state() == QVariantAnimation.State.Running):
            self._pos = 1.0 if self.isChecked() else 0.0
        pos = self._pos
        tx0 = (self.width() - 44) if (self.text_left and self.text()) else 0
        track = QRectF(tx0 + 1, (self.height() - 26) / 2, 42, 26)
        off = qc("#FFFFFF", 0.25) if self.on_dark else qc(C.grey200)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(off, C.accent, pos))
        p.drawRoundedRect(track, 13, 13)
        knob = QRectF(track.left() + 3 + pos * 16, track.top() + 3, 20, 20)
        p.setBrush(qc("#000000", 0.08))
        p.drawEllipse(knob.adjusted(0, 1, 0, 1))
        p.setBrush(qc("#FFFFFF"))
        p.drawEllipse(knob)
        if self.text():
            p.setPen(qc("#FFFFFF") if self.on_dark else qc(C.grey800))
            p.setFont(font(14))
            if self.text_left:
                p.drawText(QRectF(0, 0, track.left() - 10, self.height()), Qt.AlignmentFlag.AlignVCenter, self.text())
            else:
                p.drawText(QRectF(track.right() + 10, 0, self.width() - track.right() - 10, self.height()),
                           Qt.AlignmentFlag.AlignVCenter, self.text())


class ChipButton(_PressMixin, QAbstractButton):
    def __init__(self, text, parent=None, checkable=True, round_=False):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(checkable)
        self.round_ = round_
        self._on = 0.0
        self._a = None
        self._init_press()
        self.toggled.connect(self._on_toggle)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _on_toggle(self, on):
        if self._a:
            self._a.stop()
        self._a = _anim(self, self._on, 1.0 if on else 0.0, 160, self._set_on)
        self._a.start()

    def _set_on(self, v):
        self._on = float(v)
        self.update()

    def sizeHint(self):
        if self.round_:
            return QSize(38, 38)
        fm = QFontMetricsF(font(13.5, QFont.Weight.Medium))
        return QSize(int(fm.horizontalAdvance(self.text()) + 28), 34)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)
        if not (self._a and self._a.state() == QVariantAnimation.State.Running):
            self._on = 1.0 if self.isChecked() else 0.0
        on = self._on
        r = QRectF(self.rect())
        sc = 1.0 - 0.05 * self._press
        p.translate(r.center())
        p.scale(sc, sc)
        p.translate(-r.center())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(mix(mix(C.grey100, C.grey200, self._hover), C.accent, on))
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setFont(font(13.5, QFont.Weight.DemiBold if on > 0.5 else QFont.Weight.Medium))
        p.setPen(mix(C.grey700, "#FFFFFF", on))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text())


class DayChips(QWidget):
    maskChanged = pyqtSignal(int)

    def __init__(self, parent=None, presets=True):
        super().__init__(parent)
        from app.core.timeutil import WEEKDAYS
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.chips = []
        for label, bit in WEEKDAYS:
            c = ChipButton(label, round_=True)
            c.toggled.connect(self._changed)
            self.chips.append((c, bit))
            lay.addWidget(c)
        if presets:
            lay.addSpacing(8)
            for text, mask in (("평일", 31), ("주말", 96), ("매일", 127)):
                b = Button(text, variant="subtle", size="sm")
                b.clicked.connect(lambda _=False, m=mask: self.set_mask(m, emit=True))
                lay.addWidget(b)
        lay.addStretch(1)
        self._block = False

    def _changed(self, *_):
        if not self._block:
            self.maskChanged.emit(self.mask())

    def mask(self):
        m = 0
        for c, bit in self.chips:
            if c.isChecked():
                m |= bit
        return m

    def set_mask(self, mask, emit=False):
        self._block = True
        for c, bit in self.chips:
            c.setChecked(bool(int(mask) & bit))
        self._block = False
        if emit:
            self.maskChanged.emit(self.mask())


class SegmentedControl(QWidget):
    """회색 트랙 위에서 흰 선택 표시가 미끄러진다."""
    changed = pyqtSignal(int)

    def __init__(self, options, parent=None, compact=False, on_page=False):
        super().__init__(parent)
        self.on_page = on_page
        self.options = list(options)
        self.index = 0
        self.compact = compact
        self._x = 0.0
        self._hover = -1
        self._a = None
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def _font(self, bold=False):
        return font(13 if self.compact else 14, QFont.Weight.DemiBold if bold else QFont.Weight.Medium)

    def _seg_w(self):
        fm = QFontMetricsF(self._font(True))
        return max(fm.horizontalAdvance(o) for o in self.options) + (22 if self.compact else 30)

    def sizeHint(self):
        return QSize(int(self._seg_w() * len(self.options) + 8), 36 if self.compact else 40)

    def current(self):
        return self.index

    def set_current(self, i, animate=True, emit=False):
        i = max(0, min(len(self.options) - 1, int(i)))
        if i == self.index and not emit:
            return
        self.index = i
        if animate and self.isVisible():
            if self._a:
                self._a.stop()
            self._a = _anim(self, self._x, float(i), 240, self._set_x)
            self._a.start()
        else:
            self._x = float(i)
            self.update()
        if emit:
            self.changed.emit(i)

    def _set_x(self, v):
        self._x = float(v)
        self.update()

    def _idx(self, x):
        i = int((x - 4) // self._seg_w())
        return i if 0 <= i < len(self.options) else -1

    def mouseMoveEvent(self, e):
        i = self._idx(e.position().x())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        i = self._idx(e.position().x())
        if i >= 0 and i != self.index:
            self.set_current(i, emit=True)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.5)
        r = QRectF(self.rect())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#FFFFFF" if self.on_page else C.grey100))
        p.drawRoundedRect(r, 10, 10)
        sw = self._seg_w()
        pill = QRectF(4 + self._x * sw, 4, sw, r.height() - 8)
        if not self.on_page:
            p.setBrush(qc("#000000", 0.05))
            p.drawRoundedRect(pill.adjusted(0, 1, 0, 1.5), 7, 7)
        p.setBrush(qc(C.grey100 if self.on_page else "#FFFFFF"))
        p.drawRoundedRect(pill, 7, 7)
        for i, o in enumerate(self.options):
            seg = QRectF(4 + i * sw, 4, sw, r.height() - 8)
            k = max(0.0, 1.0 - abs(self._x - i))
            p.setFont(self._font(k > 0.5))
            p.setPen(mix(C.grey800 if i == self._hover else C.grey500, C.grey900, k))
            p.drawText(seg, Qt.AlignmentFlag.AlignCenter, o)


# =====================================================================
# 숫자 / 링
# =====================================================================
class RollingClock(QWidget):
    """숫자가 바뀌면 아래에서 위로 굴러 올라온다."""

    def __init__(self, px=64, color=C.grey900, weight=QFont.Weight.Bold, align="left", parent=None):
        super().__init__(parent)
        self.px = px
        self.color = QColor(color)
        self.weight = weight
        self.align = align
        self._text = ""
        self._old = ""
        self._starts = {}
        self._dur = 0.36
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._tick)
        self.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)

    def set_px(self, px):
        if px != self.px:
            self.px = px
            self.updateGeometry()
            self.update()

    def set_color(self, c):
        self.color = QColor(c)
        self.update()

    def _font(self):
        return font(self.px, self.weight)

    def _cells(self, text):
        fm = QFontMetricsF(self._font())
        dw = max(fm.horizontalAdvance(d) for d in "0123456789")
        return [dw if ch.isdigit() else fm.horizontalAdvance(ch) for ch in text]

    def sizeHint(self):
        fm = QFontMetricsF(self._font())
        return QSize(int(sum(self._cells(self._text or "00:00:00")) + 4), int(fm.height()))

    def text(self):
        return self._text

    def setText(self, s):
        if s == self._text:
            return
        old = self._text
        now = time.monotonic()
        if old and len(old) == len(s):
            for i, (a, b) in enumerate(zip(old, s)):
                if a != b:
                    self._starts[i] = now
            self._old = old
        else:
            self._starts.clear()
            self._old = s
            self.updateGeometry()
        self._text = s
        if self._starts and not self._timer.isActive():
            self._timer.start()
        self.update()

    def _tick(self):
        now = time.monotonic()
        self._starts = {i: t for i, t in self._starts.items() if now - t < self._dur}
        if not self._starts:
            self._timer.stop()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(self._font())
        cells = self._cells(self._text)
        total = sum(cells)
        x = {"center": (self.width() - total) / 2, "right": self.width() - total}.get(self.align, 0.0)
        h = self.height()
        p.setClipRect(self.rect())
        now = time.monotonic()
        travel = h * 0.42
        for i, ch in enumerate(self._text):
            cell = QRectF(x, 0, cells[i], h)
            if i in self._starts:
                k = ease_out_cubic((now - self._starts[i]) / self._dur)
                old_ch = self._old[i] if i < len(self._old) else ""
                c = QColor(self.color)
                c.setAlphaF(self.color.alphaF() * (1 - k))
                p.setPen(c)
                p.drawText(cell.translated(0, -k * travel), Qt.AlignmentFlag.AlignCenter, old_ch)
                c = QColor(self.color)
                c.setAlphaF(self.color.alphaF() * k)
                p.setPen(c)
                p.drawText(cell.translated(0, (1 - k) * travel), Qt.AlignmentFlag.AlignCenter, ch)
            else:
                p.setPen(self.color)
                p.drawText(cell, Qt.AlignmentFlag.AlignCenter, ch)
            x += cells[i]


class CountdownRing(TickingWidget):
    """다음 종까지의 진행을 보여주는 얇은 링. 값이 바뀔 때만 부드럽게 움직인다."""
    always_tick = False

    def __init__(self, parent=None, size=160, thickness=10, on_dark=False):
        super().__init__(parent)
        self.progress = 0.0
        self._shown = 0.0
        self._tween = None
        self.center_text = "--:--"
        self.sub_text = "남음"
        self.urgent = False
        self.thickness = thickness
        self.on_dark = on_dark
        self._bursts = []
        self._size = size
        self.setMinimumSize(size, size)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def sizeHint(self):
        return QSize(self._size, self._size)

    def set_size(self, s):
        if s != self._size:
            self._size = s
            self.setMinimumSize(s, s)
            self.updateGeometry()

    def _set_shown(self, v):
        self._shown = float(v)
        self.update()

    def set_state(self, progress, center, sub=None, urgent=False):
        progress = max(0.0, min(1.0, float(progress)))
        changed = (center != self.center_text or sub not in (None, self.sub_text) or urgent != self.urgent)
        self.center_text = center
        if sub is not None:
            self.sub_text = sub
        self.urgent = urgent
        if abs(progress - self.progress) > 0.0005:
            self.progress = progress
            jump = abs(progress - self._shown) > 0.02
            if self._tween:
                self._tween.stop()
            if jump and self.isVisible():
                self._tween = _anim(self, self._shown, progress, 700, self._set_shown)
                self._tween.start()
            else:
                self._shown = progress
                changed = True
        if changed:
            self.update()

    def burst(self):
        self._bursts.append(ticker().now())
        self.start_ticking()

    def intro(self):
        self._shown = 0.0
        target = self.progress
        self.progress = -1.0
        self.set_state(target, self.center_text, self.sub_text, self.urgent)

    def on_frame(self, t):
        self._bursts = [b for b in self._bursts if t - b < 1.2]
        if not self._bursts:
            self.stop_ticking()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = ticker().now()
        side = min(self.width(), self.height())
        th = self.thickness
        margin = th / 2 + 10
        rect = QRectF((self.width() - side) / 2 + margin, (self.height() - side) / 2 + margin,
                      side - margin * 2, side - margin * 2)
        center = rect.center()

        for b in self._bursts:
            k = (t - b) / 1.2
            rr = rect.width() / 2 + (side / 2 - rect.width() / 2 - 1) * ease_out_cubic(k)
            p.setPen(QPen(qc(C.accent, 0.5 * (1 - k)), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(center, rr, rr)

        track = qc("#FFFFFF", 0.12) if self.on_dark else qc(C.grey100)
        p.setPen(QPen(track, th, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        prog = max(0.0, min(1.0, self._shown))
        if prog > 0.003:
            cg = QConicalGradient(center, 90)
            cg.setColorAt(0.0, QColor(C.g2))
            cg.setColorAt(1.0, QColor(C.g0))
            p.setPen(QPen(cg, th, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawArc(rect, 90 * 16, int(-prog * 360 * 16))

        txt = QColor("#FFFFFF") if self.on_dark else QColor(C.grey900)
        if self.urgent:
            txt = QColor("#FFB27A") if self.on_dark else QColor(C.accent)
        sub = qc("#FFFFFF", 0.6) if self.on_dark else qc(C.grey500)
        inner = rect.adjusted(th, th, -th, -th)
        big = max(16, int(inner.height() * (0.25 if len(self.center_text) <= 5 else 0.19)))
        p.setPen(txt)
        p.setFont(font(big, QFont.Weight.Bold))
        p.drawText(QRectF(inner.left(), center.y() - big * 0.82, inner.width(), big * 1.3),
                   Qt.AlignmentFlag.AlignCenter, self.center_text)
        sp = max(11, int(big * 0.4))
        p.setPen(sub)
        p.setFont(font(sp, QFont.Weight.Medium))
        p.drawText(QRectF(inner.left(), center.y() + big * 0.52, inner.width(), sp * 1.6),
                   Qt.AlignmentFlag.AlignCenter, self.sub_text)


class EqualizerBars(TickingWidget):
    always_tick = False

    def __init__(self, parent=None, color=None, bars=4):
        super().__init__(parent)
        self.active = False
        self.color = QColor(color or C.accent)
        self.bars = bars
        self._level = 0.0
        self._last = 0.0
        self.setFixedSize(22, 16)

    def set_active(self, on):
        on = bool(on)
        if on != self.active:
            self.active = on
            self.start_ticking()

    def showEvent(self, e):
        super().showEvent(e)
        if self.active or self._level > 0.01:
            self.start_ticking()

    def on_frame(self, t):
        if t - self._last < 1 / 30:
            return
        self._last = t
        target = 1.0 if self.active else 0.0
        self._level += (target - self._level) * 0.25
        if not self.active and self._level < 0.02:
            self._level = 0.0
            self.stop_ticking()
        self.update()

    def paintEvent(self, e):
        if self._level < 0.03:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(min(1.0, self._level * 1.4))
        t = ticker().now()
        bw = 3
        gap = (self.width() - self.bars * bw) / (self.bars - 1)
        for i in range(self.bars):
            wob = 0.5 + 0.5 * math.sin(t * (6 + i * 1.5) + i * 1.3)
            h = 3 + (self.height() - 3) * (0.2 + 0.8 * wob) * self._level
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(self.color)
            p.drawRoundedRect(QRectF(i * (bw + gap), self.height() - h, bw, h), 1.5, 1.5)


class CountUpLabel(QLabel):
    def __init__(self, value=0, suffix="", parent=None):
        super().__init__(parent)
        self._value = 0.0
        self.suffix = suffix
        self._a = None
        self.set_value(value, animate=False)

    def set_value(self, v, animate=True):
        v = float(v)
        if self._a:
            self._a.stop()
        if not animate or abs(v - self._value) < 0.5:
            self._value = v
            self.setText(f"{int(round(v))}{self.suffix}")
            return
        self._a = _anim(self, self._value, v, 600, self._set)
        self._a.start()

    def _set(self, v):
        self._value = float(v)
        self.setText(f"{int(round(self._value))}{self.suffix}")


class StatusDot(QWidget):
    """상태 점 (계속 깜빡이지 않음 — 조용하고 CPU도 안 씀)."""

    def __init__(self, color=C.success, parent=None):
        super().__init__(parent)
        self.color = QColor(color)
        self.setFixedSize(14, 14)

    def set_color(self, c, pulse=False):
        c = QColor(c)
        if c != self.color:
            self.color = c
            self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        p.setPen(Qt.PenStyle.NoPen)
        halo = QColor(self.color)
        halo.setAlphaF(0.18)
        p.setBrush(halo)
        p.drawEllipse(c, 6, 6)
        p.setBrush(self.color)
        p.drawEllipse(c, 3.5, 3.5)


class Spinner(TickingWidget):
    def __init__(self, size=24, color=None, parent=None):
        super().__init__(parent)
        self.color = QColor(color or C.accent)
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = ticker().now()
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setPen(QPen(qc(C.grey200), 3))
        p.drawEllipse(r)
        p.setPen(QPen(self.color, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.drawArc(r, int((-t * 360) % 360 * 16), 100 * 16)


# =====================================================================
# 페이지 전환: 이전 화면은 빠르게 사라지고, 새 화면 블록이 차례로 살짝 올라온다
# =====================================================================
def collect_layout_widgets(layout, out=None):
    out = [] if out is None else out
    if layout is None:
        return out
    for i in range(layout.count()):
        it = layout.itemAt(i)
        w = it.widget()
        if w is not None:
            if w.isVisible() and w.width() > 0 and w.height() > 0:
                out.append(w)
        elif it.layout() is not None:
            collect_layout_widgets(it.layout(), out)
    return out


def render_widget(w):
    dpr = w.devicePixelRatioF()
    pm = QPixmap(max(1, int(w.width() * dpr)), max(1, int(w.height() * dpr)))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    w.render(pm, QPoint(0, 0), QRegion(), QWidget.RenderFlag.DrawChildren)
    return pm


class _RevealOverlay(TickingWidget):
    always_tick = False
    DUR = 0.3
    DIST = 8

    def __init__(self, stack, old_pix):
        super().__init__(stack)
        self.stack = stack
        self.old_pix = old_pix
        self.pieces = []
        self.t0 = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setGeometry(stack.rect())
        self.raise_()
        self.show()

    def begin(self, page):
        targets = page.reveal_targets() if hasattr(page, "reveal_targets") else []
        if not targets:
            targets = collect_layout_widgets(page.layout()) or [page]
        try:
            full = render_widget(page)
            dpr = full.devicePixelRatio()
            origin = page.mapTo(self.stack, QPoint(0, 0))
        except Exception:
            full = None
        step = min(0.03, 0.15 / max(1, len(targets)))
        for i, w in enumerate(targets):
            try:
                pos = w.mapTo(page, QPoint(0, 0))
                if full is not None:
                    piece = full.copy(int(pos.x() * dpr), int(pos.y() * dpr), int(w.width() * dpr), int(w.height() * dpr))
                    piece.setDevicePixelRatio(dpr)
                else:
                    piece = render_widget(w)
                self.pieces.append((piece, QPoint(pos.x() + origin.x(), pos.y() + origin.y()), 0.02 + i * step))
            except Exception:
                pass
        self.t0 = time.monotonic()
        self.start_ticking()

    def on_frame(self, t):
        if self.t0 is None:
            return
        el = time.monotonic() - self.t0
        last = max([d for _, _, d in self.pieces] or [0]) + self.DUR
        if el > last:
            self.stop_ticking()
            self.hide()
            self.deleteLater()
            return
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        paint_app_background(p, QRectF(self.rect()))
        el = 0.0 if self.t0 is None else time.monotonic() - self.t0
        if self.old_pix is not None:
            k = min(1.0, el / 0.1)
            if k < 1.0:
                p.setOpacity(1 - k)
                p.drawPixmap(QPoint(0, 0), self.old_pix)
        for pm, pos, delay in self.pieces:
            k = (el - delay) / self.DUR
            if k <= 0:
                continue
            p.setOpacity(min(1.0, k * 1.6))
            # 정수 좌표로 그려야 확대·보간 없이 빠르다
            p.drawPixmap(QPoint(pos.x(), pos.y() + round(self.DIST * (1 - ease_out_cubic(k)))), pm)


class AnimatedStack(QStackedWidget):
    def paintEvent(self, e):
        p = QPainter(self)
        paint_app_background(p, QRectF(self.rect()))

    def switch_to(self, index, animate=True):
        if index == self.currentIndex() and animate:
            return
        old = self.currentWidget()
        old_pix = render_widget(old) if (old is not None and animate and self.isVisible()) else None
        self.setCurrentIndex(index)
        page = self.currentWidget()
        if hasattr(page, "on_enter"):
            page.on_enter()
        if animate and self.isVisible():
            self.reveal(old_pix)

    def reveal(self, old_pix=None):
        ov = _RevealOverlay(self, old_pix)
        page = self.currentWidget()
        QTimer.singleShot(0, lambda: ov.begin(page) if page is not None else None)


# =====================================================================
# 토스트
# =====================================================================
class _Toast(QWidget):
    def __init__(self, host, text, kind, action_text=None, on_action=None):
        super().__init__(host)
        self.text = text
        self.kind = kind
        self.action_text = action_text
        self.on_action = on_action
        self.k = 0.0
        self.out = False
        self._hover = False
        if not action_text:
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        else:
            self.setMouseTracking(True)
        f = font(14, QFont.Weight.Medium)
        fm = QFontMetricsF(f)
        lines = text.split("\n")
        w = max(fm.horizontalAdvance(l) for l in lines) + 66
        if action_text:
            w += QFontMetricsF(font(14, QFont.Weight.Bold)).horizontalAdvance(action_text) + 34
        h = max(48, int(fm.height() * len(lines) + 26))
        self.resize(int(min(w, 620)), h)

    def _action_rect(self):
        if not self.action_text:
            return QRectF()
        aw = QFontMetricsF(font(14, QFont.Weight.Bold)).horizontalAdvance(self.action_text) + 24
        return QRectF(self.width() - aw - 8, 8, aw, self.height() - 16)

    def mouseMoveEvent(self, e):
        hov = self._action_rect().contains(e.position())
        if hov != self._hover:
            self._hover = hov
            self.setCursor(Qt.CursorShape.PointingHandCursor if hov else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if self.on_action and self._action_rect().contains(e.position()) and not self.out:
            cb, self.on_action = self.on_action, None
            cb()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setOpacity(max(0.0, min(1.0, self.k)))
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(C.grey800, 0.96))
        p.drawRoundedRect(r, 14, 14)
        col, ic = {
            "success": ("#4CD3A0", "check"), "error": ("#FF7A85", "x"), "warning": ("#FFC25C", "warning"),
            "bell": ("#FFA352", "bell"),
        }.get(self.kind, ("#C9D0D8", "info"))
        p.drawPixmap(QPointF(r.left() + 18, r.center().y() - 9), icons.pixmap(ic, col, 18))
        right = 18
        if self.action_text:
            ar = self._action_rect()
            right = self.width() - ar.left() + 6
            if self._hover:
                p.setBrush(qc("#FFFFFF", 0.10))
                p.drawRoundedRect(ar, 8, 8)
            p.setPen(QColor("#FFA352"))
            p.setFont(font(14, QFont.Weight.Bold))
            p.drawText(ar, Qt.AlignmentFlag.AlignCenter, self.action_text)
        p.setPen(QColor("#FFFFFF"))
        p.setFont(font(14, QFont.Weight.Medium))
        p.drawText(r.adjusted(46, 0, -right, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, self.text)


class ToastManager(QObject):
    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.toasts = []
        host.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.host and ev.type() == QEvent.Type.Resize:
            self._layout()
        return False

    def show(self, text, kind="info", ms=2400, action_text=None, on_action=None):
        """action_text/on_action 을 주면 '되돌리기' 같은 버튼이 붙는다."""
        t = None

        def act():
            on_action()
            self._dismiss(t)
        t = _Toast(self.host, text, kind, action_text, act if on_action else None)
        t.show()
        t.raise_()
        self.toasts.append(t)
        if len(self.toasts) > 3:
            self._dismiss(self.toasts[0])
        _anim(t, 0.0, 1.0, 260, lambda v, tt=t: self._set_k(tt, v)).start()
        QTimer.singleShot(ms if not action_text else max(ms, 6000), lambda tt=t: self._dismiss(tt))
        self._layout()
        return t

    def _set_k(self, t, v):
        try:
            t.k = float(v)
            self._layout()
            t.update()
        except RuntimeError:
            pass

    def _dismiss(self, t):
        if t is None or t not in self.toasts or t.out:
            return
        t.out = True
        _anim(t, t.k, 0.0, 200, lambda v, tt=t: self._set_k(tt, v), QEasingCurve.Type.InCubic,
              on_done=lambda tt=t: self._remove(tt)).start()

    def _remove(self, t):
        if t in self.toasts:
            self.toasts.remove(t)
        try:
            t.deleteLater()
        except RuntimeError:
            pass
        self._layout()

    def _layout(self):
        y = self.host.height() - 28
        for t in reversed(self.toasts):
            try:
                k = ease_out_cubic(t.k)
                x = (self.host.width() - t.width()) // 2
                t.move(x, int(y - t.height() + (1 - k) * 16))
                y -= int((t.height() + 8) * max(0.0, min(1.0, t.k)))
            except RuntimeError:
                pass


# =====================================================================
# 기타
# =====================================================================
class PageHeader(QWidget):
    def __init__(self, title, subtitle="", parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 0, 0, 0)
        lay.setSpacing(12)
        col = QVBoxLayout()
        col.setSpacing(4)
        self.title = QLabel(title)
        self.title.setProperty("role", "title")
        col.addWidget(self.title)
        if subtitle:
            self.subtitle = QLabel(subtitle)
            self.subtitle.setProperty("role", "subtitle")
            self.subtitle.setWordWrap(True)
            col.addWidget(self.subtitle)
        lay.addLayout(col, 1)
        self.right = QHBoxLayout()
        self.right.setSpacing(8)
        lay.addLayout(self.right)


class SlideBar(QWidget):
    """높이가 부드럽게 열리고 닫히는 영역."""

    def __init__(self, content, parent=None):
        super().__init__(parent)
        self.content = content
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(content)
        self._open = False
        self._a = None
        self.setMaximumHeight(0)

    def set_open(self, on):
        if on == self._open:
            return
        self._open = on
        target = self.content.sizeHint().height() if on else 0
        if self._a:
            self._a.stop()
        self._a = _anim(self, self.maximumHeight(), target, 220, lambda v: self.setMaximumHeight(int(v)))
        self._a.start()


def section_label(text):
    l = QLabel(text)
    l.setProperty("role", "section")
    return l


def field_label(text):
    l = QLabel(text)
    l.setProperty("role", "field")
    return l


def muted_label(text, wrap=False):
    l = QLabel(text)
    l.setProperty("role", "muted")
    l.setWordWrap(wrap)
    return l


class Pill(QLabel):
    """작은 상태 배지."""

    def __init__(self, text="", fg=C.accent_text, bg=C.accent_softer, parent=None):
        super().__init__(text, parent)
        self.set_colors(fg, bg)

    def set_colors(self, fg, bg):
        self.setStyleSheet(
            f"QLabel {{ color: {QColor(fg).name()}; background: {QColor(bg).name(QColor.NameFormat.HexArgb)};"
            f" border-radius: 6px; padding: 3px 8px; font-size: 12px; font-weight: 600; }}"
        )


def page_field(w):
    """회색 페이지 배경 위에 놓이는 입력칸은 흰색으로."""
    w.setProperty("page", True)
    return w


def hline():
    w = QWidget()
    w.setFixedHeight(1)
    w.setStyleSheet(f"background: {C.grey100};")
    return w
