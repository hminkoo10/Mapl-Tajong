from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QHeaderView, QLabel, QMenu, QVBoxLayout, QWidget

from app.core import sound_files
from app.core.paths import sound_file_path
from app.data import repo
from app.ui.dialogs import SoundInfoDialog, confirm, notify
from app.ui.sound_editor import open_editor_for_sound
from app.ui.tables import PillDelegate, SmartTable, TextDelegate
from app.ui.theme import C
from app.ui.widgets import Button, EqualizerBars, IconButton, PageHeader
from app.ui.youtube_dialog import YoutubeDialog


class SoundsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.conn = ctx.conn
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 20)
        root.setSpacing(16)

        header = PageHeader("종소리", "파일을 넣거나 YouTube에서 찾아 받고, 필요한 부분만 잘라 쓸 수 있어요.")
        root.addWidget(header)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_yt = Button("YouTube에서 찾기", icon_name="search", variant="primary")
        self.btn_add = Button("파일 추가", variant="white")
        bar.addWidget(self.btn_yt)
        bar.addWidget(self.btn_add)
        bar.addStretch(1)
        self.eq = EqualizerBars()
        bar.addWidget(self.eq)
        bar.addSpacing(4)
        self.btn_play = Button("들어보기", icon_name="play", variant="white")
        self.btn_stop = IconButton("stop", "정지", "white")
        self.btn_editor = Button("자르기·다듬기", variant="white")
        self.btn_info = Button("이름·음량", variant="white")
        self.btn_del = Button("삭제", variant="danger")
        for b in (self.btn_play, self.btn_stop, self.btn_editor, self.btn_info, self.btn_del):
            bar.addWidget(b)
        root.addLayout(bar)

        self.table = SmartTable(["", "이름", "길이", "기본 음량", "쓰는 곳", "파일"], check_col=False)
        self.table.setItemDelegateForColumn(1, TextDelegate(self.table, px=15))
        self.table.setItemDelegateForColumn(4, PillDelegate(self.table))
        self.table.setColumnHidden(0, True)
        hdr = self.table.horizontalHeader()
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        for c, w in ((2, 90), (3, 96), (4, 110)):
            hdr.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(c, w)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        root.addWidget(self.table, 1)

        self.footer = QLabel("")
        self.footer.setStyleSheet(f"color: {C.grey500}; font-size: 13px; padding-left: 4px;")
        root.addWidget(self.footer)

        self.btn_yt.clicked.connect(self.on_youtube)
        self.btn_add.clicked.connect(self.on_add)
        self.btn_editor.clicked.connect(self.on_editor)
        self.btn_info.clicked.connect(self.on_info)
        self.btn_del.clicked.connect(self.on_delete)
        self.btn_play.clicked.connect(self.on_play)
        self.btn_stop.clicked.connect(self.on_stop)
        self.table.cellDoubleClicked.connect(lambda r, c: self.on_play())
        self.table.itemSelectionChanged.connect(self._sync_buttons)
        self.table.customContextMenuRequested.connect(self._context_menu)
        ctx.data_changed.connect(lambda w: self.refresh() if w in ("all", "sounds", "schedules", "sets") else None)

        self._eq_timer = QTimer(self)
        self._eq_timer.setInterval(250)
        self._eq_timer.timeout.connect(lambda: self.eq.set_active(self.ctx.player.is_playing()))
        self._eq_timer.start()
        self.refresh()

    def refresh(self):
        keep = self.table.selected_ids()
        sounds = repo.list_sounds(self.conn)
        usage = repo.sound_usage_counts(self.conn)
        t = self.table
        t.setUpdatesEnabled(False)
        t.blockSignals(True)
        t.setRowCount(len(sounds))
        for i, s in enumerate(sounds):
            sid = int(s["id"])
            path = sound_file_path(str(s["file_name"]))
            exists = path.exists()
            dur = sound_files.sound_duration(path) if exists else None
            t.set_cell(i, 0, "")
            t.set_row_id(i, sid)
            t.set_cell(i, 1, str(s["name"]), fg=C.grey900 if exists else C.danger)
            t.set_cell(i, 2, sound_files.format_duration(dur), fg=C.grey600)
            t.set_cell(i, 3, f"{int(round(float(s['volume']) * 100))}%", fg=C.grey600)
            n = usage.get(sid, 0)
            t.set_cell(i, 4, "", data=(f"일정 {n}개", C.accent_text, C.accent_softer) if n
                       else ("안 씀", C.grey500, C.grey100))
            t.set_cell(i, 5, str(s["file_name"]) if exists else "파일을 찾을 수 없어요",
                       fg=C.grey400 if exists else C.danger)
        t.blockSignals(False)
        t.setUpdatesEnabled(True)
        if not keep and t.rowCount():
            keep = [t.row_id(0)]
        t.select_ids(keep[:1])
        self.footer.setText(f"{len(sounds)}개 · 두 번 클릭하면 들어볼 수 있어요")
        self._sync_buttons()

    def _selected(self):
        ids = self.table.selected_ids()
        return repo.get_sound(self.conn, ids[0]) if ids else None

    def _sync_buttons(self):
        on = bool(self.table.selected_ids())
        for b in (self.btn_editor, self.btn_info, self.btn_del, self.btn_play):
            b.setEnabled(on)

    def _done(self, new_id, msg):
        self.ctx.changed("sounds")
        if new_id:
            self.table.select_ids([new_id])
            self.table.flash_ids([new_id])
            r = next((i for i in range(self.table.rowCount()) if self.table.row_id(i) == new_id), None)
            if r is not None:
                self.table.scrollToItem(self.table.item(r, 1))
        self.ctx.toast(msg, "success")

    def on_youtube(self):
        dlg = YoutubeDialog(self.ctx, self)
        if dlg.exec() == QDialog.DialogCode.Accepted and dlg.result_id:
            self._done(dlg.result_id, "종소리를 추가했어요")

    def on_add(self):
        dlg = SoundInfoDialog(self.ctx, "", 1.0, pick_file=True, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, path, vol = dlg.get_value()
        try:
            new_id = sound_files.add_sound_from_file(self.conn, path, name, vol)
        except Exception as e:
            notify(self, "추가하지 못했어요", str(e))
            return
        self._done(new_id, f"{name} 종소리를 추가했어요")

    def on_editor(self):
        s = self._selected()
        if not s:
            return
        rid = open_editor_for_sound(self.ctx, s, self)
        if rid:
            self._done(rid, "저장했어요")

    def on_info(self):
        s = self._selected()
        if not s:
            return
        dlg = SoundInfoDialog(self.ctx, str(s["name"]), float(s["volume"]), pick_file=False, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        name, _, vol = dlg.get_value()
        repo.update_sound(self.conn, int(s["id"]), name, vol)
        self._done(int(s["id"]), "저장했어요")

    def on_delete(self):
        s = self._selected()
        if not s:
            return
        n = repo.sound_usage_counts(self.conn).get(int(s["id"]), 0)
        if n:
            notify(self, "지금은 삭제할 수 없어요",
                   f"{s['name']}은(는) 일정 {n}개에서 쓰고 있어요.\n시간표에서 다른 종소리로 바꾼 뒤 삭제해 주세요.")
            return
        if not confirm(self, f"{s['name']}을(를) 삭제할까요?", "종소리 파일도 함께 지워져요.", "삭제"):
            return
        self.ctx.player.release(str(sound_file_path(str(s["file_name"]))))
        repo.delete_sound(self.conn, int(s["id"]))
        sound_files.remove_sound_files(s)
        self.ctx.changed("sounds")
        self.ctx.toast("삭제했어요")

    def on_play(self):
        s = self._selected()
        if not s:
            return
        try:
            self.ctx.player.play(str(sound_file_path(str(s["file_name"]))), float(s["volume"]), str(s["name"]))
            self.eq.set_active(True)
        except Exception as e:
            notify(self, "재생하지 못했어요", str(e))

    def on_stop(self):
        self.ctx.player.stop()
        self.eq.set_active(False)

    def _context_menu(self, pos):
        r = self.table.rowAt(pos.y())
        if r >= 0:
            self.table.selectRow(r)
        m = QMenu(self)
        if r >= 0:
            m.addAction("들어보기", self.on_play)
            m.addAction("자르기·다듬기", self.on_editor)
            m.addAction("이름·음량", self.on_info)
            m.addSeparator()
            m.addAction("삭제", self.on_delete)
            m.addSeparator()
        m.addAction("YouTube에서 찾기", self.on_youtube)
        m.addAction("파일 추가", self.on_add)
        m.exec(self.table.viewport().mapToGlobal(pos))
