"""목록형 표: 둥근 체크, 은은한 행 강조."""
import time

from PyQt6.QtCore import QItemSelectionModel, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import QAbstractItemView, QHeaderView, QStyle, QStyledItemDelegate, QTableWidget, QTableWidgetItem

from app.ui.theme import C, font, qc
from app.ui.widgets import ease_out_cubic

ID_ROLE = Qt.ItemDataRole.UserRole
DATA_ROLE = Qt.ItemDataRole.UserRole + 1


def _draw_check(p, rect, state, pop=1.0):
    """state: 0 없음, 1 일부, 2 전체 — 둥근 체크"""
    s = 20 * (0.88 + 0.12 * pop)
    r = QRectF(rect.center().x() - s / 2, rect.center().y() - s / 2, s, s)
    if state:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(C.accent))
        p.drawEllipse(r)
        p.setPen(QPen(QColor("#FFFFFF"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        if state == 2:
            p.drawPolyline([QPointF(r.left() + s * 0.29, r.top() + s * 0.52), QPointF(r.left() + s * 0.45, r.top() + s * 0.67),
                            QPointF(r.left() + s * 0.72, r.top() + s * 0.36)])
        else:
            p.drawLine(QPointF(r.left() + s * 0.3, r.center().y()), QPointF(r.right() - s * 0.3, r.center().y()))
    else:
        p.setPen(QPen(qc(C.grey300), 1.5))
        p.setBrush(qc("#FFFFFF"))
        p.drawEllipse(r.adjusted(0.75, 0.75, -0.75, -0.75))


class CheckHeader(QHeaderView):
    def __init__(self, table):
        super().__init__(Qt.Orientation.Horizontal, table)
        self.table = table
        self.setSectionsClickable(True)
        self.setHighlightSections(False)

    def paintSection(self, painter, rect, logical):
        super().paintSection(painter, rect, logical)
        if logical == 0 and self.table.check_col:
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            n = len(self.table.selected_rows())
            total = self.table.rowCount()
            _draw_check(painter, QRectF(rect), 0 if n == 0 else (2 if n == total else 1))
            painter.restore()


class _Base(QStyledItemDelegate):
    def _bg(self, p, opt, idx):
        self.initStyleOption(opt, idx)
        text = opt.text
        opt.text = ""
        opt.widget.style().drawControl(QStyle.ControlElement.CE_ItemViewItem, opt, p, opt.widget)
        return text


class CheckDelegate(_Base):
    def __init__(self, table):
        super().__init__(table)
        self.table = table

    def paint(self, p, opt, idx):
        self._bg(p, opt, idx)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        sel = bool(opt.state & QStyle.StateFlag.State_Selected)
        t0 = self.table._pop.get(idx.row())
        pop = ease_out_cubic((time.monotonic() - t0) / 0.2) if t0 else 1.0
        _draw_check(p, QRectF(opt.rect), 2 if sel else 0, pop)
        p.restore()


class PillDelegate(_Base):
    """DATA_ROLE에 (text, fg, bg)"""

    def paint(self, p, opt, idx):
        self._bg(p, opt, idx)
        data = idx.data(DATA_ROLE)
        if not data:
            return
        text, fg, bg = data
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setFont(font(12, QFont.Weight.DemiBold))
        w = p.fontMetrics().horizontalAdvance(text) + 16
        r = QRectF(opt.rect.left() + 10, opt.rect.center().y() - 11, w, 22)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(bg))
        p.drawRoundedRect(r, 6, 6)
        p.setPen(QColor(fg))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, text)
        p.restore()


class TextDelegate(_Base):
    def __init__(self, parent=None, bold=False, px=14, color=None):
        super().__init__(parent)
        self.bold = bold
        self.px = px
        self.color = color

    def paint(self, p, opt, idx):
        text = self._bg(p, opt, idx)
        p.save()
        p.setFont(font(self.px, QFont.Weight.DemiBold if self.bold else QFont.Weight.Normal))
        col = idx.data(Qt.ItemDataRole.ForegroundRole)
        p.setPen(col.color() if col is not None else QColor(self.color or C.grey800))
        r = QRect(opt.rect.left() + 12, opt.rect.top(), opt.rect.width() - 18, opt.rect.height())
        p.drawText(r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   p.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, r.width()))
        p.restore()


class SmartTable(QTableWidget):
    selectionCountChanged = pyqtSignal(int)

    def __init__(self, headers, check_col=False, parent=None):
        super().__init__(parent)
        self.check_col = check_col
        self._flash = {}
        self._pop = {}
        self._prev_sel = set()
        self._hover_row = -1
        self.setColumnCount(len(headers))
        if check_col:
            self.setHorizontalHeader(CheckHeader(self))
        self.setHorizontalHeaderLabels(headers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection
                              if check_col else QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(52)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.horizontalHeader().setMinimumSectionSize(40)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setItemDelegate(TextDelegate(self))
        if check_col:
            self.setItemDelegateForColumn(0, CheckDelegate(self))
            self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            self.setColumnWidth(0, 52)
            self.horizontalHeader().sectionClicked.connect(self._header_clicked)
        self.itemSelectionChanged.connect(self._sel_changed)
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._anim_tick)

    def _header_clicked(self, col):
        if col != 0:
            return
        if len(self.selected_rows()) == self.rowCount():
            self.clearSelection()
        else:
            self.selectAll()

    def mousePressEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        if self.check_col and idx.isValid() and idx.column() == 0 and e.button() == Qt.MouseButton.LeftButton:
            sm = self.selectionModel()
            sm.select(idx, QItemSelectionModel.SelectionFlag.Toggle | QItemSelectionModel.SelectionFlag.Rows)
            sm.setCurrentIndex(idx, QItemSelectionModel.SelectionFlag.NoUpdate)
            return
        if not idx.isValid():
            self.clearSelection()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        idx = self.indexAt(e.position().toPoint())
        if self.check_col and idx.isValid() and idx.column() == 0:
            return
        super().mouseDoubleClickEvent(e)

    def _sel_changed(self):
        rows = set(self.selected_rows())
        now = time.monotonic()
        for r in rows ^ self._prev_sel:
            self._pop[r] = now
        self._prev_sel = rows
        if self._pop:
            self._timer.start()
        self.horizontalHeader().viewport().update()
        self.selectionCountChanged.emit(len(rows))

    def selected_rows(self):
        sm = self.selectionModel()
        return [] if sm is None else sorted({i.row() for i in sm.selectedRows()})

    def row_id(self, row):
        it = self.item(row, 0)
        return None if it is None else it.data(ID_ROLE)

    def selected_ids(self):
        return [self.row_id(r) for r in self.selected_rows() if self.row_id(r) is not None]

    def select_ids(self, ids):
        ids = set(ids)
        self.blockSignals(True)
        self.clearSelection()
        sm = self.selectionModel()
        for r in range(self.rowCount()):
            if self.row_id(r) in ids:
                sm.select(self.model().index(r, 0),
                          QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        self.blockSignals(False)
        self._prev_sel = set(self.selected_rows())
        self.selectionCountChanged.emit(len(self._prev_sel))
        self.horizontalHeader().viewport().update()

    def set_cell(self, row, col, text, data=None, fg=None, align=None, tooltip=None):
        it = QTableWidgetItem(str(text))
        if data is not None:
            it.setData(DATA_ROLE, data)
        if fg:
            it.setForeground(QColor(fg))
        if align is not None:
            it.setTextAlignment(align)
        if tooltip:
            it.setToolTip(tooltip)
        self.setItem(row, col, it)
        return it

    def set_row_id(self, row, rid):
        it = self.item(row, 0)
        if it is None:
            it = QTableWidgetItem("")
            self.setItem(row, 0, it)
        it.setData(ID_ROLE, rid)

    def flash_ids(self, ids):
        now = time.monotonic()
        for i in ids:
            self._flash[i] = now
        if self._flash:
            self._timer.start()

    def _anim_tick(self):
        now = time.monotonic()
        self._flash = {k: v for k, v in self._flash.items() if now - v < 1.2}
        self._pop = {k: v for k, v in self._pop.items() if now - v < 0.22}
        if not self._flash and not self._pop:
            self._timer.stop()
        self.viewport().update()

    def mouseMoveEvent(self, e):
        r = self.rowAt(int(e.position().y()))
        if r != self._hover_row:
            self._hover_row = r
            self.viewport().update()
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._hover_row = -1
        self.viewport().update()
        super().leaveEvent(e)

    def paintEvent(self, e):
        if self._hover_row >= 0 and self._hover_row not in self.selected_rows():
            p = QPainter(self.viewport())
            y = self.rowViewportPosition(self._hover_row)
            p.fillRect(QRectF(0, y, self.viewport().width(), self.rowHeight(self._hover_row)), qc(C.grey50))
            p.end()
        super().paintEvent(e)
        if not self._flash:
            return
        p = QPainter(self.viewport())
        now = time.monotonic()
        w = self.viewport().width()
        for r in range(self.rowCount()):
            rid = self.row_id(r)
            if rid in self._flash:
                k = (now - self._flash[rid]) / 1.2
                p.fillRect(QRectF(0, self.rowViewportPosition(r), w, self.rowHeight(r)),
                           qc(C.accent, 0.16 * (1 - ease_out_cubic(k))))
