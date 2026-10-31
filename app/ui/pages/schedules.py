from PyQt6.QtCore import QEvent, QRectF, Qt
from PyQt6.QtGui import QFont, QPainter
from PyQt6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMenu, QVBoxLayout, QWidget

from app.core.timeutil import WEEKDAYS, mask_to_days
from app.data import repo
from app.ui import icons
from app.ui.dialogs import BatchEditDialog, DuplicateDialog, ScheduleDialog, ask_text, confirm, notify
from app.ui.tables import PillDelegate, SmartTable, TextDelegate
from app.ui.theme import C, font, qc
from app.ui.widgets import Button, PageHeader, SegmentedControl, _anim, ease_out_cubic, page_field


def _vol_text(s):
    if s["volume_override"] is None:
        return "기본"
    return f"{int(round(float(s['volume_override']) * 100))}%"


class _DarkButton(Button):
    """어두운 선택 바 위의 글자 버튼."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.35)
        r = QRectF(self.rect())
        if self._hover > 0.01 or self._press > 0.01:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc("#FFFFFF", 0.10 * self._hover + 0.08 * self._press))
            p.drawRoundedRect(r, 8, 8)
        p.setPen(qc("#FF8A92" if self.variant == "danger" else "#FFFFFF"))
        p.setFont(font(14, QFont.Weight.DemiBold))
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.text())


class _SelectionBar(QWidget):
    """여러 개를 고르면 아래에서 올라오는 어두운 동작 바."""

    def __init__(self, host):
        super().__init__(host)
        self.host = host
        self.k = 0.0
        self._a = None
        self._open = False
        lay = QHBoxLayout(self)
        lay.setContentsMargins(20, 8, 10, 8)
        lay.setSpacing(2)
        self.label = QLabel("")
        self.label.setStyleSheet("color: #FFFFFF; font-size: 14px; font-weight: 600;")
        lay.addWidget(self.label)
        lay.addSpacing(14)
        self.btn_edit = _DarkButton("수정", size="sm")
        self.btn_batch = _DarkButton("한 번에 바꾸기", size="sm")
        self.btn_on = _DarkButton("켜기", size="sm")
        self.btn_off = _DarkButton("끄기", size="sm")
        self.btn_dup = _DarkButton("복제", size="sm")
        self.btn_del = _DarkButton("삭제", variant="danger", size="sm")
        self.btn_close = _DarkButton("선택 해제", size="sm")
        for b in (self.btn_edit, self.btn_batch, self.btn_on, self.btn_off, self.btn_dup, self.btn_del):
            lay.addWidget(b)
        sep = QWidget()
        sep.setFixedSize(1, 18)
        sep.setStyleSheet("background: rgba(255,255,255,0.18);")
        lay.addSpacing(6)
        lay.addWidget(sep)
        lay.addSpacing(6)
        lay.addWidget(self.btn_close)
        self.hide()
        host.installEventFilter(self)

    def eventFilter(self, obj, ev):
        if obj is self.host and ev.type() == QEvent.Type.Resize:
            self._place()
        return False

    def _place(self):
        self.adjustSize()
        k = ease_out_cubic(self.k)
        x = (self.host.width() - self.width()) // 2
        y = int(self.host.height() - 28 - self.height() * k - 12 * k + (1 - k) * 10)
        self.move(x, y)

    def set_open(self, on):
        if on == self._open:
            return
        self._open = on
        if on:
            self.show()
            self.raise_()
        if self._a:
            self._a.stop()

        def step(v):
            self.k = float(v)
            self._place()
            self.update()
        self._a = _anim(self, self.k, 1.0 if on else 0.0, 220 if on else 160, step,
                        on_done=(None if on else self.hide))
        self._a.start()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(C.grey900, 0.96))
        p.drawRoundedRect(QRectF(self.rect()), 14, 14)


class SchedulesPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.conn = ctx.conn
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 20)
        root.setSpacing(16)

        header = PageHeader("시간표", "세트마다 종 치는 시간을 정해요.")
        self.set_combo = page_field(QComboBox())
        self.set_combo.setMinimumWidth(170)
        header.right.addWidget(self.set_combo)
        self.btn_set_menu = Button("세트 관리", variant="white")
        header.right.addWidget(self.btn_set_menu)
        root.addWidget(header)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_add = Button("일정 추가", icon_name="plus", variant="primary")
        bar.addWidget(self.btn_add)
        self.search = page_field(QLineEdit())
        self.search.setPlaceholderText("이름이나 종소리로 찾기")
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icons.icon("search", C.grey500, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setFixedWidth(220)
        bar.addWidget(self.search)
        bar.addStretch(1)
        self.day_filter = SegmentedControl(["전체"] + [d for d, _ in WEEKDAYS], compact=True, on_page=True)
        bar.addWidget(self.day_filter)
        root.addLayout(bar)

        self.table = SmartTable(["", "시간", "이름", "요일", "종소리", "음량", "상태"], check_col=True)
        self.table.setItemDelegateForColumn(1, TextDelegate(self.table, bold=True, px=15))
        self.table.setItemDelegateForColumn(2, TextDelegate(self.table, px=15))
        self.table.setItemDelegateForColumn(6, PillDelegate(self.table))
        hdr = self.table.horizontalHeader()
        for c, w in ((1, 90), (3, 120), (5, 80), (6, 84)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(c, w)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        root.addWidget(self.table, 1)

        self.empty = QWidget()
        el = QVBoxLayout(self.empty)
        el.addStretch(1)
        e1 = QLabel("아직 일정이 없어요")
        e1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e1.setStyleSheet(f"color: {C.grey800}; font-size: 17px; font-weight: 700;")
        e2 = QLabel("‘일정 추가’를 눌러 첫 종을 만들어 보세요")
        e2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        e2.setStyleSheet(f"color: {C.grey500}; font-size: 14px;")
        el.addWidget(e1)
        el.addWidget(e2)
        el.addStretch(1)
        self.empty.setStyleSheet("background: #FFFFFF; border-radius: 16px;")
        self.empty.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        root.addWidget(self.empty, 1)
        self.empty.hide()

        self.footer = QLabel("")
        self.footer.setStyleSheet(f"color: {C.grey500}; font-size: 13px; padding-left: 4px;")
        root.addWidget(self.footer)

        self.selbar = _SelectionBar(self)

        self.btn_add.clicked.connect(self.on_add)
        s = self.selbar
        s.btn_edit.clicked.connect(self.on_edit)
        s.btn_batch.clicked.connect(self.on_batch)
        s.btn_on.clicked.connect(lambda: self.on_set_enabled(1))
        s.btn_off.clicked.connect(lambda: self.on_set_enabled(0))
        s.btn_dup.clicked.connect(self.on_duplicate)
        s.btn_del.clicked.connect(self.on_delete)
        s.btn_close.clicked.connect(self.table.clearSelection)
        self.btn_set_menu.clicked.connect(self._show_set_menu)
        self.set_combo.currentIndexChanged.connect(self.on_change_set)
        self.day_filter.changed.connect(lambda *_: self.refresh())
        self.search.textChanged.connect(lambda *_: self.refresh())
        self.table.selectionCountChanged.connect(self._on_selection)
        self.table.cellDoubleClicked.connect(lambda r, c: self.on_edit_row(r))
        self.table.customContextMenuRequested.connect(self._context_menu)

        ctx.data_changed.connect(self._on_data_changed)
        self.refresh_sets()
        self.refresh()
        self._on_selection(0)

    # ---------------- 데이터 ----------------
    def _on_data_changed(self, what):
        if what in ("all", "sets"):
            self.refresh_sets()
        if what in ("all", "sets", "schedules", "sounds"):
            self.refresh()

    def refresh_sets(self):
        sets = repo.list_schedule_sets(self.conn)
        counts = repo.schedule_counts_by_set(self.conn)
        active = repo.active_set_id(self.conn)
        self.set_combo.blockSignals(True)
        self.set_combo.clear()
        pick = 0
        for i, s in enumerate(sets):
            sid = int(s["id"])
            self.set_combo.addItem(f"{s['name']}  ({counts.get(sid, 0)})", sid)
            if sid == active:
                pick = i
        self.set_combo.setCurrentIndex(pick)
        self.set_combo.blockSignals(False)

    def refresh(self, keep_selection=True):
        keep = set(self.table.selected_ids()) if keep_selection else set()
        rows = repo.list_schedules(self.conn, repo.active_set_id(self.conn))
        all_count = len(rows)
        fi = self.day_filter.current()
        if fi > 0:
            bit = WEEKDAYS[fi - 1][1]
            rows = [r for r in rows if int(r["weekday_mask"]) & bit]
        q = self.search.text().strip().lower()
        if q:
            rows = [r for r in rows if q in str(r["name"]).lower() or q in str(r["sound_name"]).lower()]

        t = self.table
        t.setUpdatesEnabled(False)
        t.blockSignals(True)
        t.clearSelection()
        t.setRowCount(len(rows))
        for i, s in enumerate(rows):
            on = int(s["enabled"]) == 1
            dim = None if on else C.grey400
            t.set_cell(i, 0, "")
            t.set_row_id(i, int(s["id"]))
            t.set_cell(i, 1, str(s["time_hhmm"]), fg=dim or C.grey900)
            t.set_cell(i, 2, str(s["name"]), fg=dim or C.grey900)
            t.set_cell(i, 3, mask_to_days(s["weekday_mask"]), fg=dim or C.grey700)
            t.set_cell(i, 4, str(s["sound_name"]), fg=dim or C.grey600)
            t.set_cell(i, 5, _vol_text(s), fg=dim or C.grey600)
            t.set_cell(i, 6, "", data=("사용", C.success, C.success_soft) if on else ("꺼짐", C.grey500, C.grey100))
        t.blockSignals(False)
        t.setUpdatesEnabled(True)
        t.select_ids(keep)

        enabled = sum(1 for r in rows if int(r["enabled"]) == 1)
        self.empty.setVisible(all_count == 0)
        self.table.setVisible(all_count > 0)
        shown = f"{len(rows)}개 표시 (전체 {all_count}개)" if (fi or q) else f"{all_count}개"
        self.footer.setText(f"{shown} · 사용 중 {enabled}개")

    def _on_selection(self, n):
        self.selbar.set_open(n > 0)
        self.selbar.label.setText(f"{n}개 선택")
        self.selbar.btn_edit.setVisible(n == 1)
        self.selbar._place()

    def _after_change(self, flash_ids=(), what="schedules", select=None):
        self.ctx.changed(what)
        if select is not None:
            self.table.select_ids(select)
        self.table.flash_ids(flash_ids)

    # ---------------- 동작 ----------------
    def on_add(self):
        sounds = repo.list_sounds(self.conn)
        if not sounds:
            notify(self, "종소리가 없어요", "종소리를 먼저 추가해 주세요.")
            return
        dlg = ScheduleDialog(self.ctx, sounds, None, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, mask, t, sound_id, v, enabled = dlg.get_value()
        new_id = repo.insert_schedule(self.conn, repo.active_set_id(self.conn), name, mask, t, sound_id, v, enabled)
        self._after_change([new_id], "sets")
        self.ctx.toast(f"{name} 일정을 추가했어요", "success")

    def on_edit_row(self, row):
        rid = self.table.row_id(row)
        if rid is not None:
            self.table.select_ids([rid])
            self.on_edit()

    def on_edit(self):
        ids = self.table.selected_ids()
        if len(ids) != 1:
            return
        rows = repo.get_schedules(self.conn, ids)
        if not rows:
            return
        dlg = ScheduleDialog(self.ctx, repo.list_sounds(self.conn), rows[0], self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, mask, t, sound_id, v, enabled = dlg.get_value()
        repo.update_schedule(self.conn, ids[0], name, mask, t, sound_id, v, enabled)
        self._after_change(ids)
        self.ctx.toast("저장했어요", "success")

    def on_batch(self):
        ids = self.table.selected_ids()
        if not ids:
            return
        rows = repo.get_schedules(self.conn, ids)
        dlg = BatchEditDialog(self.ctx, rows, repo.list_sounds(self.conn), repo.list_schedule_sets(self.conn),
                              repo.active_set_id(self.conn), self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        ch = dlg.get_changes()
        if not ch:
            return
        n = repo.batch_update_schedules(self.conn, ids, ch)
        moved = "set_id" in ch
        self._after_change([] if moved else ids, "sets", select=None if moved else ids)
        self.ctx.toast(f"일정 {n}개를 다른 세트로 옮겼어요" if moved else f"일정 {n}개를 바꿨어요", "success")

    def on_set_enabled(self, enabled):
        ids = self.table.selected_ids()
        if not ids:
            return
        repo.set_enabled_many(self.conn, ids, enabled)
        self._after_change(ids, select=ids)
        self.ctx.toast(f"일정 {len(ids)}개를 {'켰어요' if enabled else '껐어요'}", "success")

    def on_duplicate(self):
        ids = self.table.selected_ids()
        if not ids:
            return
        cur = repo.active_set_id(self.conn)
        dlg = DuplicateDialog(len(ids), repo.list_schedule_sets(self.conn), cur, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        target, shift, suffix = dlg.get_value()
        new_ids = repo.duplicate_schedules(self.conn, ids, target, shift, suffix)
        same = target == cur
        self._after_change(new_ids if same else [], "sets", select=new_ids if same else None)
        where = "" if same else f" ({dlg.set_combo.currentText()} 세트)"
        self.ctx.toast(f"일정 {len(new_ids)}개를 복제했어요{where}", "success")

    def on_delete(self):
        ids = self.table.selected_ids()
        if not ids:
            return
        if not confirm(self, f"일정 {len(ids)}개를 삭제할까요?", "삭제한 일정은 되돌릴 수 없어요.", "삭제"):
            return
        repo.delete_schedules(self.conn, ids)
        self._after_change([], "sets")
        self.ctx.toast(f"일정 {len(ids)}개를 삭제했어요")

    def _context_menu(self, pos):
        row = self.table.rowAt(pos.y())
        if row >= 0 and row not in self.table.selected_rows():
            self.table.selectRow(row)
        n = len(self.table.selected_ids())
        m = QMenu(self)
        m.addAction("일정 추가", self.on_add)
        if n:
            m.addSeparator()
            a = m.addAction("수정", self.on_edit)
            a.setEnabled(n == 1)
            m.addAction(f"한 번에 바꾸기 ({n}개)", self.on_batch)
            m.addAction("복제", self.on_duplicate)
            m.addSeparator()
            m.addAction("켜기", lambda: self.on_set_enabled(1))
            m.addAction("끄기", lambda: self.on_set_enabled(0))
            m.addSeparator()
            m.addAction("삭제", self.on_delete)
        m.exec(self.table.viewport().mapToGlobal(pos))

    # ---------------- 세트 ----------------
    def _show_set_menu(self):
        m = QMenu(self)
        m.addAction("새 세트 만들기", self.on_add_set)
        m.addAction("지금 세트 복제", self.on_duplicate_set)
        m.addAction("이름 바꾸기", self.on_rename_set)
        m.addSeparator()
        m.addAction("지금 세트 삭제", self.on_delete_set)
        m.exec(self.btn_set_menu.mapToGlobal(self.btn_set_menu.rect().bottomLeft()))

    def _current_set_name(self):
        return repo.active_set_name(self.conn)

    def on_change_set(self):
        sid = self.set_combo.currentData()
        if sid is None:
            return
        repo.set_active_set(self.conn, int(sid))
        self.ctx.changed("sets")
        self.ctx.toast(f"{self._current_set_name()} 세트로 바꿨어요")

    def on_add_set(self):
        name = ask_text(self, "새 세트", "세트 이름", "", ok_text="만들기")
        if not name:
            return
        try:
            sid = repo.insert_schedule_set(self.conn, name)
        except Exception:
            notify(self, "이미 있는 이름이에요", "다른 이름을 입력해 주세요.")
            return
        repo.set_active_set(self.conn, sid)
        self.ctx.changed("sets")
        self.ctx.toast(f"{name} 세트를 만들었어요", "success")

    def on_duplicate_set(self):
        cur_id = repo.active_set_id(self.conn)
        cur = self._current_set_name()
        name = ask_text(self, "세트 복제", "새 세트 이름", repo.unique_set_name(self.conn, f"{cur} 복사본"), ok_text="복제")
        if not name:
            return
        try:
            sid = repo.duplicate_schedule_set(self.conn, cur_id, name)
        except Exception:
            notify(self, "이미 있는 이름이에요", "다른 이름을 입력해 주세요.")
            return
        repo.set_active_set(self.conn, sid)
        self.ctx.changed("sets")
        self.ctx.toast(f"{name} 세트를 만들었어요", "success")

    def on_rename_set(self):
        sid = repo.active_set_id(self.conn)
        name = ask_text(self, "세트 이름 바꾸기", "새 이름", self._current_set_name(), ok_text="바꾸기")
        if not name:
            return
        try:
            repo.rename_schedule_set(self.conn, sid, name)
        except Exception:
            notify(self, "이미 있는 이름이에요", "다른 이름을 입력해 주세요.")
            return
        self.ctx.changed("sets")

    def on_delete_set(self):
        if len(repo.list_schedule_sets(self.conn)) <= 1:
            notify(self, "삭제할 수 없어요", "세트는 하나 이상 있어야 해요.")
            return
        sid = repo.active_set_id(self.conn)
        if not confirm(self, f"{self._current_set_name()} 세트를 삭제할까요?", "이 세트에 있는 일정도 함께 지워져요.", "삭제"):
            return
        repo.delete_schedule_set(self.conn, sid)
        remain = repo.list_schedule_sets(self.conn)
        repo.set_active_set(self.conn, int(remain[0]["id"]))
        self.ctx.changed("sets")
        self.ctx.toast("세트를 삭제했어요")
