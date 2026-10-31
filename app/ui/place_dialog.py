"""날씨 지역 고르기: 동네·도시 이름으로 찾거나 자주 쓰는 도시에서 고른다."""
import json

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetricsF, QPainter
from PyQt6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QScrollArea, QVBoxLayout, QWidget

from app.core import weather
from app.ui import icons
from app.ui.dialogs import BaseDialog
from app.ui.theme import C, font, qc
from app.ui.widgets import Button, ChipButton, Spinner
from app.ui.workers import run_async


class _ResultRow(QWidget):
    clicked = pyqtSignal(dict)

    def __init__(self, place, parent=None):
        super().__init__(parent)
        self.place = place
        self.hover = False
        self.setFixedHeight(48)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.place)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = self.rect().adjusted(0, 2, 0, -2)
        if self.hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(C.grey50))
            p.drawRoundedRect(r, 10, 10)
        p.drawPixmap(12, r.center().y() - 8, icons.pixmap("search", C.grey400, 16))
        name = self.place["name"]
        rest = self.place["label"][len(name):].strip(" ()")
        p.setPen(qc(C.grey900))
        p.setFont(font(15, QFont.Weight.DemiBold))
        fm = QFontMetricsF(p.font())
        nw = fm.horizontalAdvance(name)
        p.drawText(r.adjusted(40, 0, 0, 0), Qt.AlignmentFlag.AlignVCenter, name)
        if rest:
            p.setPen(qc(C.grey500))
            p.setFont(font(13))
            p.drawText(r.adjusted(int(48 + nw), 0, -130, 0), Qt.AlignmentFlag.AlignVCenter,
                       QFontMetricsF(p.font()).elidedText(rest, Qt.TextElideMode.ElideRight, r.width() - nw - 190))
        coord = f"{self.place['lat']:.4f}, {self.place['lon']:.4f}"
        p.setFont(font(12, QFont.Weight.Medium) if not self.hover else font(13, QFont.Weight.Bold))
        p.setPen(qc(C.accent_text) if self.hover else qc(C.grey400))
        p.drawText(r.adjusted(0, 0, -14, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight,
                   "고르기" if self.hover else coord)


class PlaceDialog(BaseDialog):
    enter_accepts = False

    def __init__(self, current_name="", parent=None):
        super().__init__("날씨 지역 고르기", "동네·주소로 찾거나, 아래 도시에서 골라 주세요.", None, parent, 560)
        self.result = None
        self._seq = 0

        cur = QLabel(f"지금 지역: {current_name}" if current_name else "")
        cur.setStyleSheet(f"color: {C.grey600}; font-size: 13.5px;")
        self.body.addWidget(cur)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.query = QLineEdit()
        self.query.setPlaceholderText("예) 대치동 · 서울 강남구 테헤란로 152 · 37.50, 127.06")
        self.query.addAction(icons.icon("search", C.grey500, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.query.textChanged.connect(self._filter)
        self.query.returnPressed.connect(self.search)
        self.btn_search = Button("찾기", variant="primary")
        self.btn_search.clicked.connect(self.search)
        row.addWidget(self.query, 1)
        row.addWidget(self.btn_search)
        self.body.addLayout(row)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setMinimumHeight(300)
        holder = QWidget()
        holder.setObjectName("placeHolder")
        self.lay = QVBoxLayout(holder)
        self.lay.setContentsMargins(0, 0, 6, 0)
        self.lay.setSpacing(8)

        self.results_title = QLabel("찾은 곳")
        self.results_title.setStyleSheet(f"color: {C.grey500}; font-size: 13px; font-weight: 600;")
        self.results_title.hide()
        self.lay.addWidget(self.results_title)
        self.results = QVBoxLayout()
        self.results.setSpacing(0)
        self.lay.addLayout(self.results)

        self.cities_title = QLabel("자주 쓰는 도시")
        self.cities_title.setStyleSheet(f"color: {C.grey500}; font-size: 13px; font-weight: 600;")
        self.lay.addWidget(self.cities_title)
        self.grid = QGridLayout()
        self.grid.setHorizontalSpacing(6)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(6, 1)     # 남는 폭은 오른쪽으로 (버튼이 왼쪽부터 붙도록)
        self.lay.addLayout(self.grid)
        self.lay.addStretch(1)
        # 버튼은 처음부터 이 창 안에 만든다 (부모 없이 만들면 잠깐씩 따로 창으로 떴다 사라진다)
        self.chips = []
        for name, lat, lon in weather.CITIES:
            c = ChipButton(name, holder, checkable=False)
            c.clicked.connect(lambda _=False, n=name, a=lat, b=lon: self._choose({"name": n, "lat": a, "lon": b}))
            self.chips.append((name, c))
        self._layout_chips(weather.CITIES)
        self.scroll.setWidget(holder)
        self.body.addWidget(self.scroll, 1)

        st = QHBoxLayout()
        self.spinner = Spinner(18)
        self.spinner.hide()
        st.addWidget(self.spinner)
        self.state = QLabel("")
        self.state.setWordWrap(True)
        self.state.setStyleSheet(f"color: {C.grey600}; font-size: 13px;")
        st.addWidget(self.state, 1)
        self.body.addLayout(st)
        credit = QLabel(weather.GEO_CREDIT)
        credit.setStyleSheet(f"color: {C.grey400}; font-size: 12px;")
        self.body.addWidget(credit)

        self.btn_ok.hide()
        self.btn_cancel.setText("닫기")
        self.resize(600, 600)
        QTimer.singleShot(0, self.query.setFocus)

    def _layout_chips(self, names):
        keep = {n for n, *_ in names} if names and isinstance(names[0], tuple) else set(names)
        for i in reversed(range(self.grid.count())):
            self.grid.takeAt(i)
        k = 0
        for name, chip in self.chips:
            chip.setVisible(name in keep)
            if name in keep:
                self.grid.addWidget(chip, k // 6, k % 6)
                k += 1
        self.cities_title.setVisible(k > 0)

    def _filter(self, text):
        t = text.strip()
        names = [n for n, *_ in weather.CITIES if not t or t in n or n in t]
        self._layout_chips(names)

    def _clear_results(self):
        while self.results.count():
            it = self.results.takeAt(0)
            if it.widget():
                it.widget().hide()
                it.widget().deleteLater()

    def search(self):
        q = self.query.text().strip()
        if not q:
            return
        self._seq += 1
        seq = self._seq
        self.spinner.show()
        self.state.setText("찾고 있어요")
        self.btn_search.setEnabled(False)
        run_async(weather.search_places, q, on_done=lambda r: self._found(seq, r), on_fail=lambda m: self._failed(seq, m))

    def _found(self, seq, places):
        try:
            if seq != self._seq:
                return
            self.spinner.hide()
            self.btn_search.setEnabled(True)
            self._clear_results()
            self.results_title.setVisible(bool(places))
            for pl in places:
                row = _ResultRow(pl)
                row.clicked.connect(self._choose)
                self.results.addWidget(row)
            approx = places and places[0].get("approx")
            if places and places[0].get("exact"):
                self.state.setText("주소를 건물까지 찾았어요. 눌러서 고르세요.")
            elif places:
                self.state.setText((f"건물 번호까지는 못 찾아서 ‘{approx}’ 근처로 찾았어요. " if approx else "")
                                   + f"{len(places)}곳을 찾았어요. 눌러서 고르세요.")
            else:
                self.state.setText("찾는 곳이 없어요. 동네(○○동)나 시·구 이름, 또는 도로명 주소로 찾아 보세요.")
        except RuntimeError:
            pass

    def _failed(self, seq, msg):
        try:
            if seq != self._seq:
                return
            self.spinner.hide()
            self.btn_search.setEnabled(True)
            self.state.setText("지금은 찾을 수 없어요. 인터넷 연결을 확인하거나 아래 도시에서 골라 주세요.")
        except RuntimeError:
            pass

    def _choose(self, place):
        self.result = {"name": place["name"], "lat": round(float(place["lat"]), 4), "lon": round(float(place["lon"]), 4)}
        self.accept()


def pick_place(conn, parent=None):
    """지역을 고르게 하고 저장한다. 고른 이름을 돌려준다 (취소하면 None)."""
    from PyQt6.QtWidgets import QDialog
    from app.data import repo
    name = weather.place_of(weather.setting_value(lambda k, d: repo.get_setting(conn, k, d)))[0]
    dlg = PlaceDialog(name, parent)
    if dlg.exec() != QDialog.DialogCode.Accepted or not dlg.result:
        return None
    repo.set_setting(conn, "weather_place", json.dumps(dlg.result, ensure_ascii=False))
    return dlg.result["name"]
