"""부드럽게 열리는 드롭다운과 메뉴.

Select 는 QComboBox 를 그대로 상속해서 addItem/currentData/currentIndexChanged 등은 같고,
보이는 모양과 펼쳐지는 목록만 직접 그린다.
"""
import time

from PyQt6.QtCore import QEasingCurve, QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QFontMetricsF, QGuiApplication, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QComboBox, QMenu, QWidget

from app.ui import icons
from app.ui.theme import C, font, mix, paint_soft_shadow, qc
from app.ui.widgets import _anim

ROW_H = 40
MAX_ROWS = 8
PAD = 6
SHADOW = 14


class _SelectPopup(QWidget):
    def __init__(self, combo):
        super().__init__(None, Qt.WindowType.Popup | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
        self.combo = combo
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.items = [combo.itemText(i) for i in range(combo.count())]
        self.current = combo.currentIndex()
        self.hover = self.current if self.current >= 0 else 0
        self._hy = float(self.hover)
        self._ha = None
        self.k = 0.0
        self.offset = 0
        self.above = False
        self._closing = False
        self.rows = min(MAX_ROWS, max(1, len(self.items)))

        fm = QFontMetricsF(font(14, QFont.Weight.DemiBold))
        text_w = max((fm.horizontalAdvance(t) for t in self.items), default=80)
        w = max(combo.width(), int(text_w) + 70)
        h = self.rows * ROW_H + PAD * 2
        self.resize(w + SHADOW * 2, h + SHADOW * 2)

        if self.current >= self.rows:
            self.offset = min(len(self.items) - self.rows, self.current - self.rows // 2)

        g = combo.mapToGlobal(QPoint(0, combo.height()))
        x, y = g.x() - SHADOW, g.y() + 6 - SHADOW
        scr = (combo.screen() or QGuiApplication.primaryScreen()).availableGeometry()
        if y + self.height() > scr.bottom():
            self.above = True
            y = combo.mapToGlobal(QPoint(0, 0)).y() - 6 - self.height() + SHADOW
        x = max(scr.left(), min(x, scr.right() - self.width()))
        self.move(x, y)

        self._open = _anim(self, 0.0, 1.0, 180, self._set_k)

    def _set_k(self, v):
        self.k = float(v)
        self.update()

    def popup(self):
        self.show()
        self.setFocus()
        self._open.start()

    def close_animated(self):
        if self._closing:
            return
        self._closing = True
        # 애니메이션 끝 콜백 안에서 팝업을 바로 닫으면 Qt가 충돌하므로 한 박자 뒤에 닫는다
        a = _anim(self, self.k, 0.0, 110, self._set_k, QEasingCurve.Type.InCubic,
                  on_done=lambda: QTimer.singleShot(0, self.close))
        a.start()
        self._close_anim = a

    # ---------- 좌표 ----------
    def _list_rect(self):
        return QRectF(SHADOW, SHADOW, self.width() - SHADOW * 2, self.height() - SHADOW * 2)

    def _row_at(self, pos):
        r = self._list_rect()
        if not r.contains(pos):
            return -1
        i = int((pos.y() - r.top() - PAD) // ROW_H) + self.offset
        return i if 0 <= i < len(self.items) else -1

    def _move_hover(self, i, animate=True):
        i = max(0, min(len(self.items) - 1, i))
        self.hover = i
        if i < self.offset:
            self.offset = i
        elif i >= self.offset + self.rows:
            self.offset = i - self.rows + 1
        if self._ha:
            self._ha.stop()
        if animate:
            self._ha = _anim(self, self._hy, float(i), 140, self._set_hy)
            self._ha.start()
        else:
            self._hy = float(i)
        self.update()

    def _set_hy(self, v):
        self._hy = float(v)
        self.update()

    # ---------- 입력 ----------
    def mouseMoveEvent(self, e):
        i = self._row_at(e.position())
        if i >= 0 and i != self.hover:
            self._move_hover(i)

    def mouseReleaseEvent(self, e):
        i = self._row_at(e.position())
        if i >= 0:
            self._choose(i)

    def wheelEvent(self, e):
        if len(self.items) <= self.rows:
            return
        step = -1 if e.angleDelta().y() > 0 else 1
        self.offset = max(0, min(len(self.items) - self.rows, self.offset + step))
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key.Key_Down, Qt.Key.Key_Tab):
            self._move_hover(self.hover + 1)
        elif k in (Qt.Key.Key_Up, Qt.Key.Key_Backtab):
            self._move_hover(self.hover - 1)
        elif k == Qt.Key.Key_PageDown:
            self._move_hover(self.hover + self.rows)
        elif k == Qt.Key.Key_PageUp:
            self._move_hover(self.hover - self.rows)
        elif k == Qt.Key.Key_Home:
            self._move_hover(0)
        elif k == Qt.Key.Key_End:
            self._move_hover(len(self.items) - 1)
        elif k in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self._choose(self.hover)
        elif k == Qt.Key.Key_Escape:
            self.close_animated()
        else:
            super().keyPressEvent(e)

    def _choose(self, i):
        combo = self.combo
        changed = i != combo.currentIndex()
        combo.setCurrentIndex(i)
        combo.activated.emit(i)
        combo.textActivated.emit(combo.itemText(i))
        if changed:
            self.current = i
        self.close_animated()

    def hideEvent(self, e):
        super().hideEvent(e)
        try:
            self.combo._popup_closed()
        except RuntimeError:
            pass

    # ---------- 그리기 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        k = self.k
        ek = 1 - (1 - k) ** 3
        p.setOpacity(min(1.0, k * 1.3))
        dy = (1 - ek) * (6 if self.above else -6)
        p.translate(0, dy)
        r = self._list_rect()
        paint_soft_shadow(p, r, 14, strength=4, spread=SHADOW - 2, dy=4)
        p.setPen(QPen(qc(C.grey200), 1))
        p.setBrush(qc("#FFFFFF"))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 14, 14)

        clip = QPainterPath()
        clip.addRoundedRect(r, 14, 14)
        p.setClipPath(clip)
        p.setPen(Qt.PenStyle.NoPen)
        hy = r.top() + PAD + (self._hy - self.offset) * ROW_H
        p.setBrush(qc(C.grey100))
        p.drawRoundedRect(QRectF(r.left() + PAD, hy, r.width() - PAD * 2, ROW_H), 9, 9)

        for row in range(self.rows):
            i = row + self.offset
            if i >= len(self.items):
                break
            rr = QRectF(r.left() + PAD, r.top() + PAD + row * ROW_H, r.width() - PAD * 2, ROW_H)
            sel = i == self.current
            p.setFont(font(14, QFont.Weight.DemiBold if sel else QFont.Weight.Normal))
            p.setPen(qc(C.accent_text if sel else C.grey800))
            tw = rr.width() - 46
            p.drawText(rr.adjusted(12, 0, -34, 0), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetricsF(p.font()).elidedText(self.items[i], Qt.TextElideMode.ElideRight, tw))
            if sel:
                p.drawPixmap(QPointF(rr.right() - 28, rr.center().y() - 8), icons.pixmap("check", C.accent, 16))

        if len(self.items) > self.rows:
            total = len(self.items)
            bar_h = max(24.0, (r.height() - 12) * self.rows / total)
            y = r.top() + 6 + (r.height() - 12 - bar_h) * self.offset / max(1, total - self.rows)
            p.setBrush(qc(C.grey300))
            p.drawRoundedRect(QRectF(r.right() - 6, y, 3, bar_h), 1.5, 1.5)


class Select(QComboBox):
    """토스 느낌의 드롭다운. QComboBox 와 같은 방식으로 쓰면 된다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._popup = None
        self._closed_at = 0.0
        self._open_k = 0.0
        self._hover = 0.0
        self._oa = None
        self._ha = None
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    # ---------- 크기 ----------
    def sizeHint(self):
        fm = QFontMetricsF(font(14))
        tw = max((fm.horizontalAdvance(self.itemText(i)) for i in range(self.count())), default=60)
        return QSize(int(min(360, tw + 56)), 40)

    def minimumSizeHint(self):
        return QSize(90, 40)

    # ---------- 펼치기 ----------
    def showPopup(self):
        if self.count() == 0 or not self.isEnabled():
            return
        if self._popup is not None or time.monotonic() - self._closed_at < 0.25:
            return
        self._popup = _SelectPopup(self)
        self._animate_open(1.0)
        self._popup.popup()

    def hidePopup(self):
        if self._popup is not None:
            try:
                self._popup.close_animated()
            except RuntimeError:
                self._popup = None
        super().hidePopup()

    def _popup_closed(self):
        self._popup = None
        self._closed_at = time.monotonic()
        self._animate_open(0.0)

    def _animate_open(self, target):
        if self._oa:
            self._oa.stop()
        self._oa = _anim(self, self._open_k, target, 200, self._set_open)
        self._oa.start()

    def _set_open(self, v):
        self._open_k = float(v)
        self.update()

    def _set_h(self, v):
        self._hover = float(v)
        self.update()

    def enterEvent(self, e):
        super().enterEvent(e)
        self._ha = _anim(self, self._hover, 1.0, 120, self._set_h)
        self._ha.start()

    def leaveEvent(self, e):
        super().leaveEvent(e)
        self._ha = _anim(self, self._hover, 0.0, 160, self._set_h)
        self._ha.start()

    def wheelEvent(self, e):
        # 화면을 스크롤하다가 값이 바뀌는 실수를 막는다
        e.ignore()

    # ---------- 그리기 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        on_page = bool(self.property("page"))
        base = "#FFFFFF" if on_page else C.grey100
        hov = C.grey50 if on_page else "#EBEEF1"
        active = self.hasFocus() or self._open_k > 0.01
        bg = mix(base, hov, self._hover)
        if active:
            bg = mix(bg, "#FFFFFF", max(self._open_k, 1.0 if self.hasFocus() else 0.0))
        p.setBrush(bg)
        border = qc(C.accent) if active else (qc(C.grey200, self._hover) if on_page else QColor(0, 0, 0, 0))
        p.setPen(QPen(border, 1) if border.alpha() else Qt.PenStyle.NoPen)
        p.drawRoundedRect(r, 10, 10)

        enabled = self.isEnabled()
        p.setPen(qc(C.grey900 if enabled else C.grey400))
        p.setFont(font(14))
        tr = r.adjusted(12, 0, -34, 0)
        p.drawText(tr, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   QFontMetricsF(p.font()).elidedText(self.currentText(), Qt.TextElideMode.ElideRight, tr.width()))

        cx, cy = r.right() - 18, r.center().y()
        p.save()
        p.translate(cx, cy)
        p.rotate(180 * self._open_k)
        p.setPen(QPen(qc(C.grey600 if enabled else C.grey300), 1.7, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPolyline([QPointF(-4.5, -2), QPointF(0, 2.5), QPointF(4.5, -2)])
        p.restore()


class Menu(QMenu):
    """둥근 모서리로 살짝 내려오며 나타나는 메뉴."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._a = None

    def showEvent(self, e):
        super().showEvent(e)
        end = self.pos()
        start = end + QPoint(0, -6)
        self.setWindowOpacity(0.0)

        def step(v):
            k = float(v)
            self.setWindowOpacity(k)
            self.move(start + (end - start) * k)
        self._a = _anim(self, 0.0, 1.0, 150, step)
        self._a.start()
