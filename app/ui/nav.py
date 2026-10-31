"""왼쪽 메뉴."""
from PyQt6.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QFont, QIcon, QPainter, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from app.core.paths import asset_path
from app.core.version import APP_VERSION
from app.ui import icons
from app.ui.theme import C, font, mix, qc
from app.ui.widgets import _anim

ITEM_H = 44


class _NavList(QWidget):
    currentChanged = pyqtSignal(int)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items
        self.index = 0
        self._y = 0.0
        self._hover = -1
        self._hk = {}
        self._ha = {}
        self._a = None
        self.badges = set()
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(len(items) * ITEM_H)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_current(self, i, emit=False):
        if i == self.index:
            return
        self.index = i
        if self._a:
            self._a.stop()
        self._a = _anim(self, self._y, float(i), 260, self._set_y)
        self._a.start()
        if emit:
            self.currentChanged.emit(i)

    def set_badge(self, i, on):
        if on:
            self.badges.add(i)
        else:
            self.badges.discard(i)
        self.update()

    def _set_y(self, v):
        self._y = float(v)
        self.update()

    def _hover_to(self, i, target):
        if i < 0:
            return
        if self._ha.get(i):
            self._ha[i].stop()

        def setv(v, ii=i):
            self._hk[ii] = float(v)
            self.update()
        self._ha[i] = _anim(self, self._hk.get(i, 0.0), target, 140, setv)
        self._ha[i].start()

    def _index_at(self, y):
        i = int(y // ITEM_H)
        return i if 0 <= i < len(self.items) else -1

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().y())
        if i != self._hover:
            self._hover_to(self._hover, 0.0)
            self._hover = i
            self._hover_to(i, 1.0)

    def leaveEvent(self, e):
        self._hover_to(self._hover, 0.0)
        self._hover = -1

    def mousePressEvent(self, e):
        i = self._index_at(e.position().y())
        if i >= 0:
            self.set_current(i, emit=True)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w = self.width()
        p.setPen(Qt.PenStyle.NoPen)
        for i, k in self._hk.items():
            if k > 0.01:
                p.setBrush(qc(C.grey50, k))
                p.drawRoundedRect(QRectF(0, i * ITEM_H + 2, w, ITEM_H - 4), 10, 10)
        p.setBrush(qc(C.grey100))
        p.drawRoundedRect(QRectF(0, self._y * ITEM_H + 2, w, ITEM_H - 4), 10, 10)

        for i, (ic, text) in enumerate(self.items):
            r = QRectF(0, i * ITEM_H, w, ITEM_H)
            k = max(0.0, 1.0 - abs(self._y - i))
            p.drawPixmap(QPointF(14, r.center().y() - 10),
                         icons.pixmap(ic, mix(C.grey500, C.accent, k).name(), 20))
            p.setPen(mix(C.grey600, C.grey900, k))
            p.setFont(font(15, QFont.Weight.DemiBold if k > 0.5 else QFont.Weight.Medium))
            p.drawText(QRectF(46, r.top(), w - 50, r.height()), Qt.AlignmentFlag.AlignVCenter, text)
            if i in self.badges:
                tw = p.fontMetrics().horizontalAdvance(text)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(qc(C.accent))
                p.drawEllipse(QPointF(46 + tw + 8, r.center().y() - 6), 3.5, 3.5)


class _Logo(QWidget):
    """기존 버전의 앱 아이콘(app.ico)을 그대로 사용."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(40, 40)
        p = asset_path("ui", "app.ico")
        self.icon = QIcon(str(p)) if p.exists() else QIcon()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        if self.icon.isNull():
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(C.accent))
            p.drawRoundedRect(r, 10, 10)
            p.drawPixmap(QPointF(10, 10), icons.pixmap("bell", "#FFFFFF", 20))
            return
        dpr = self.devicePixelRatioF()
        pm = self.icon.pixmap(QSize(int(40 * dpr), int(40 * dpr)))
        p.drawPixmap(r, pm, QRectF(pm.rect()))


class NavSidebar(QWidget):
    currentChanged = pyqtSignal(int)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.setFixedWidth(220)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 22, 14, 18)
        lay.setSpacing(0)

        head = QHBoxLayout()
        head.setContentsMargins(6, 0, 0, 0)
        head.setSpacing(10)
        head.addWidget(_Logo())
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        t1 = QLabel("마고 타종")
        t1.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {C.grey900};")
        t2 = QLabel(f"버전 {APP_VERSION}")
        t2.setStyleSheet(f"font-size: 12px; color: {C.grey500};")
        tcol.addWidget(t1)
        tcol.addWidget(t2)
        head.addLayout(tcol)
        head.addStretch(1)
        lay.addLayout(head)
        lay.addSpacing(28)

        self.list = _NavList(items)
        self.list.currentChanged.connect(self.currentChanged)
        lay.addWidget(self.list)
        lay.addStretch(1)

        self.footer = QVBoxLayout()
        self.footer.setSpacing(6)
        lay.addLayout(self.footer)

    def set_current(self, i):
        self.list.set_current(i)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), qc("#FFFFFF"))
        p.setPen(QPen(qc(C.grey100), 1))
        p.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
