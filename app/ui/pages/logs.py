from PyQt6.QtCore import QDate
from PyQt6.QtWidgets import QComboBox, QDateEdit, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QSpinBox, QVBoxLayout, QWidget

from app.core.backup import RESULT_LABELS, export_logs_csv
from app.data import repo
from app.ui import icons
from app.ui.dialogs import notify
from app.ui.tables import PillDelegate, SmartTable
from app.ui.theme import C
from app.ui.widgets import Button, IconButton, PageHeader, SegmentedControl, SlideBar, page_field

RESULT_STYLE = {
    "PLAYED": (C.success, C.success_soft),
    "SKIPPED": (C.warning, C.warning_soft),
    "FAILED": (C.danger, C.danger_soft),
    "MISSED": (C.danger, C.danger_soft),
}
RESULT_TEXT = RESULT_LABELS
RANGES = ["오늘", "7일", "30일", "전체", "직접"]


class LogsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.conn = ctx.conn
        self._rows = []
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 20)
        root.setSpacing(16)

        header = PageHeader("기록", "종이 언제 울렸는지, 건너뛰었는지 볼 수 있어요.")
        self.limit = page_field(QSpinBox())
        self.limit.setRange(50, 5000)
        self.limit.setSingleStep(50)
        self.limit.setValue(500)
        self.limit.setPrefix("최대 ")
        self.limit.setSuffix("건")
        header.right.addWidget(self.limit)
        self.btn_csv = Button("엑셀로 내보내기", variant="white")
        header.right.addWidget(self.btn_csv)
        root.addWidget(header)

        bl = QHBoxLayout()
        bl.setSpacing(8)
        self.range = SegmentedControl(RANGES, compact=True, on_page=True)
        self.range.set_current(1, animate=False)
        bl.addWidget(self.range)
        self.d_from = page_field(QDateEdit())
        self.d_to = page_field(QDateEdit())
        for d in (self.d_from, self.d_to):
            d.setCalendarPopup(True)
            d.setDisplayFormat("yyyy-MM-dd")
            d.setFixedWidth(132)
        self.d_from.setDate(QDate.currentDate().addDays(-6))
        self.d_to.setDate(QDate.currentDate())
        dw = QWidget()
        dl = QHBoxLayout(dw)
        dl.setContentsMargins(4, 8, 4, 0)
        dl.setSpacing(8)
        dl.addWidget(QLabel("기간"))
        dl.addWidget(self.d_from)
        dl.addWidget(QLabel("~"))
        dl.addWidget(self.d_to)
        dl.addStretch(1)
        self.dates_bar = SlideBar(dw)
        self.result = page_field(QComboBox())
        self.result.addItem("모든 결과", "ALL")
        for k, v in RESULT_TEXT.items():
            self.result.addItem(v, k)
        bl.addWidget(self.result)
        self.keyword = page_field(QLineEdit())
        self.keyword.setPlaceholderText("이름이나 종소리로 찾기")
        self.keyword.setClearButtonEnabled(True)
        self.keyword.addAction(icons.icon("search", C.grey500, 16), QLineEdit.ActionPosition.LeadingPosition)
        bl.addWidget(self.keyword, 1)
        self.btn_refresh = IconButton("refresh", "새로고침", "white")
        bl.addWidget(self.btn_refresh)
        bwrap = QVBoxLayout()
        bwrap.setSpacing(0)
        bwrap.addLayout(bl)
        bwrap.addWidget(self.dates_bar)
        root.addLayout(bwrap)

        self.table = SmartTable(["", "시간", "결과", "이벤트", "종소리", "상세"])
        self.table.setColumnHidden(0, True)
        self.table.setItemDelegateForColumn(2, PillDelegate(self.table))
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 170)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 90)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setDefaultSectionSize(48)
        root.addWidget(self.table, 1)
        self.footer = QLabel("")
        self.footer.setStyleSheet(f"color: {C.grey500}; font-size: 13px; padding-left: 4px;")
        root.addWidget(self.footer)

        self.range.changed.connect(lambda *_: self.refresh())
        self.result.currentIndexChanged.connect(lambda *_: self.refresh())
        self.limit.valueChanged.connect(lambda *_: self.refresh())
        self.keyword.returnPressed.connect(self.refresh)
        self.keyword.textChanged.connect(lambda t: self.refresh() if not t else None)
        self.d_from.dateChanged.connect(lambda *_: self.refresh())
        self.d_to.dateChanged.connect(lambda *_: self.refresh())
        self.btn_refresh.clicked.connect(self.refresh)
        self.btn_csv.clicked.connect(self.on_export)
        self.table.cellDoubleClicked.connect(self.on_detail)
        ctx.rang.connect(lambda *_: self.refresh())
        ctx.scheduler_event.connect(lambda *_: self.refresh())
        self.refresh()

    def on_enter(self):
        self.refresh()

    def _dates(self):
        today = QDate.currentDate()
        i = self.range.current()
        self.dates_bar.set_open(i == 4)
        if i == 0:
            return today.toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
        if i == 1:
            return today.addDays(-6).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
        if i == 2:
            return today.addDays(-29).toString("yyyy-MM-dd"), today.toString("yyyy-MM-dd")
        if i == 3:
            return "", ""
        return self.d_from.date().toString("yyyy-MM-dd"), self.d_to.date().toString("yyyy-MM-dd")

    def refresh(self):
        a, b = self._dates()
        rows = repo.list_logs(self.conn, a, b, self.result.currentData(), self.keyword.text().strip(), self.limit.value())
        self._rows = rows
        t = self.table
        t.setUpdatesEnabled(False)
        t.setRowCount(len(rows))
        counts = {}
        for i, l in enumerate(rows):
            res = str(l["result"])
            counts[res] = counts.get(res, 0) + 1
            fg, bg = RESULT_STYLE.get(res, (C.neutral, C.neutral_soft))
            t.set_cell(i, 0, "")
            t.set_row_id(i, int(l["id"]))
            t.set_cell(i, 1, str(l["occurred_at"])[:16], fg=C.grey600)
            t.set_cell(i, 2, "", data=(RESULT_TEXT.get(res, res), fg, bg))
            t.set_cell(i, 3, str(l["schedule_name"] or ""))
            t.set_cell(i, 4, str(l["sound_name"] or ""), fg=C.grey600)
            detail = str(l["detail"] or "")
            detail = {"forced": "수동 타종"}.get(detail, detail)
            t.set_cell(i, 5, detail, fg=C.grey400, tooltip=detail or None)
        t.setUpdatesEnabled(True)
        parts = [f"{RESULT_TEXT.get(k, k)} {v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])]
        self.footer.setText(f"{len(rows)}건" + (" · " + " · ".join(parts) if parts else ""))

    def on_detail(self, row, col):
        if row >= len(self._rows):
            return
        l = self._rows[row]
        notify(self, l["schedule_name"] or "기록",
               f"{l['occurred_at']}\n{RESULT_TEXT.get(l['result'], l['result'])} · {l['sound_name'] or '-'}"
               + (f"\n\n{l['detail']}" if l["detail"] else ""))

    def on_export(self):
        from datetime import datetime
        path, _ = QFileDialog.getSaveFileName(self, "기록 내보내기", f"타종기록_{datetime.now():%Y%m%d}.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            export_logs_csv(self._rows, path)
        except Exception as e:
            notify(self, "내보내지 못했어요", str(e))
            return
        self.ctx.toast(f"{len(self._rows)}건을 저장했어요", "success")
