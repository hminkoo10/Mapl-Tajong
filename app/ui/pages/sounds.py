from pathlib import Path

from PyQt6.QtCore import QSize, QStandardPaths, Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QHeaderView, QLabel, QProgressBar, QVBoxLayout,
                             QWidget)

from app.core import sound_files
from app.core.paths import sound_file_path
from app.data import repo
from app.ui.dialogs import SoundInfoDialog, confirm, notify
from app.ui.messages import error_message
from app.ui.select import Menu
from app.ui.sound_editor import open_editor_for_sound
from app.ui.tables import PillDelegate, SmartTable, TextDelegate
from app.ui.theme import C
from app.ui.widgets import Button, EqualizerBars, IconButton, PageHeader
from app.ui.workers import ProgressThread, keep_alive, run_async
from app.ui.youtube_dialog import YoutubeDialog


class _RowButton(Button):
    """창을 가장 작게 해도 단추 줄이 한 줄에 들어가게, 양옆 여백만 4px까지 고르게 줄어드는 단추.
    (보통 Button 은 최소 크기가 제 크기라, 자리가 모자라면 Qt 가 가장 큰 단추부터 깎아 글자가 테두리에 붙는다)"""

    def minimumSizeHint(self):
        s = self.sizeHint()
        return QSize(s.width() - 8, s.height())


class SoundsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.conn = ctx.conn
        self._mp3 = None       # MP3로 저장하는 작업 (한 번에 하나)
        self._mp3_id = None    # 저장하고 있는 종소리
        self._mp3_text = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 20)
        root.setSpacing(16)

        header = PageHeader("종소리", " ")
        root.addWidget(header)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        self.btn_yt = _RowButton("인터넷에서 찾기", icon_name="search", variant="primary")
        self.btn_add = _RowButton("파일 추가", variant="white")
        bar.addWidget(self.btn_yt)
        bar.addWidget(self.btn_add)
        bar.addStretch(1)
        self.eq = EqualizerBars()
        bar.addWidget(self.eq)
        bar.addSpacing(4)
        self.btn_play = _RowButton("들어보기", icon_name="play", variant="white")
        self.btn_stop = IconButton("stop", "정지", "white")
        self.btn_editor = _RowButton("자르기·다듬기", variant="white")
        self.btn_info = _RowButton("이름·음량", variant="white")
        self.btn_mp3 = _RowButton("MP3로 저장", variant="white")
        self.btn_del = _RowButton("삭제", variant="danger")
        for b in (self.btn_play, self.btn_stop, self.btn_editor, self.btn_info, self.btn_mp3, self.btn_del):
            bar.addWidget(b)
        root.addLayout(bar)

        # MP3로 저장하는 동안 보이는 줄 (금방 끝나면 나타나지 않고 끝났다는 안내만 나온다)
        self.mp3_strip = QWidget()
        sl = QHBoxLayout(self.mp3_strip)
        sl.setContentsMargins(4, 0, 0, 0)
        sl.setSpacing(12)
        self.mp3_label = QLabel("")
        self.mp3_label.setStyleSheet(f"color: {C.grey700}; font-size: 14px;")
        self.mp3_bar = QProgressBar()
        self.mp3_bar.setRange(0, 1000)
        self.mp3_bar.setStyleSheet(f"QProgressBar {{ background: {C.grey200}; }}")   # 회색 화면 위에서도 남은 길이가 보이게
        self.btn_mp3_cancel = Button("취소", variant="subtle", size="sm")
        sl.addWidget(self.mp3_label)
        sl.addWidget(self.mp3_bar, 1)
        sl.addWidget(self.btn_mp3_cancel)
        self.mp3_strip.hide()
        root.addWidget(self.mp3_strip)

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
        self.btn_mp3.clicked.connect(self.on_save_mp3)
        self.btn_mp3_cancel.clicked.connect(self.on_cancel_mp3)
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
        self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self._eq_timer.start()

    def hideEvent(self, e):
        super().hideEvent(e)
        self._eq_timer.stop()

    def refresh(self):
        keep = self.table.selected_ids()
        sounds = repo.list_sounds(self.conn)
        usage = repo.sound_usage_counts(self.conn)
        t = self.table
        t.setUpdatesEnabled(False)
        t.blockSignals(True)
        t.setRowCount(len(sounds))
        unknown = []
        for i, s in enumerate(sounds):
            sid = int(s["id"])
            path = sound_file_path(str(s["file_name"]))
            exists = path.exists()
            dur = sound_files.cached_duration(path) if exists else None
            if exists and dur is None:
                unknown.append((sid, str(path)))
            t.set_cell(i, 0, "")
            t.set_row_id(i, sid)
            t.set_cell(i, 1, str(s["name"]), fg=C.grey900 if exists else C.danger)
            t.set_cell(i, 2, "…" if exists and dur is None else sound_files.format_duration(dur), fg=C.grey600)
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
        self.footer.setText(f"{len(sounds)}개 · 두 번 클릭하면 들어요")
        self._sync_buttons()
        if unknown:
            # mp3 등은 길이를 읽는 데 시간이 걸릴 수 있어 화면을 멈추지 않도록 뒤에서 계산한다
            self._dur_seq = getattr(self, "_dur_seq", 0) + 1
            seq = self._dur_seq
            run_async(lambda items: [(sid, sound_files.sound_duration(pth)) for sid, pth in items], unknown,
                      on_done=lambda res: self._durations_ready(seq, res))

    def _durations_ready(self, seq, results):
        if seq != getattr(self, "_dur_seq", 0):
            return
        t = self.table
        rows = {t.row_id(i): i for i in range(t.rowCount())}
        for sid, dur in results:
            r = rows.get(sid)
            if r is not None:
                t.set_cell(r, 2, sound_files.format_duration(dur), fg=C.grey600)

    def _selected(self):
        ids = self.table.selected_ids()
        return repo.get_sound(self.conn, ids[0]) if ids else None

    def _saving_mp3_of(self, sound_id):
        return self._mp3 is not None and sound_id == self._mp3_id

    def _sync_buttons(self):
        ids = self.table.selected_ids()
        on = bool(ids)
        # MP3로 저장하는 동안 그 종소리 파일은 고치거나 지우지 않는다 (읽고 있는 파일이라 꼬인다)
        busy = on and self._saving_mp3_of(ids[0])
        for b in (self.btn_info, self.btn_play):
            b.setEnabled(on)
        for b in (self.btn_editor, self.btn_del):
            b.setEnabled(on and not busy)
        self.btn_mp3.setEnabled(on and self._mp3 is None)

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
        self.btn_add.setEnabled(False)
        self.ctx.toast("종소리를 넣고 있어요")

        def done(dst):
            self.btn_add.setEnabled(True)
            new_id = repo.insert_sound(self.conn, (name or Path(path).stem).strip(), Path(dst).name, float(vol))
            self._done(new_id, f"{name} 종소리를 추가했어요")

        def fail(msg):
            self.btn_add.setEnabled(True)
            notify(self, "추가하지 못했어요", error_message(
                "파일이 열리는지 확인한 뒤 다시 고르세요.", msg))

        run_async(sound_files.import_file, path, on_done=done, on_fail=fail)

    def on_editor(self):
        s = self._selected()
        if not s or self._saving_mp3_of(int(s["id"])):
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

    def on_save_mp3(self):
        s = self._selected()
        if not s or self._mp3 is not None:
            return
        start = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DownloadLocation))
        path, _ = QFileDialog.getSaveFileName(self, "MP3로 저장", str(start / f"{sound_files.safe_stem(s['name'])}.mp3"),
                                              "MP3 (*.mp3)")
        if not path or self._mp3 is not None:
            return
        if not path.lower().endswith(".mp3"):
            path += ".mp3"
        name = str(s["name"])
        th = ProgressThread(sound_files.export_mp3, sound_file_path(str(s["file_name"])), path)
        self._mp3, self._mp3_id = th, int(s["id"])
        self._mp3_text = f"‘{name if len(name) <= 20 else name[:19] + '…'}’ MP3로 저장하고 있어요"
        th.progress.connect(self._mp3_progress)
        th.done.connect(self._mp3_done)
        th.failed.connect(self._mp3_failed)
        th.cancelled.connect(self._mp3_cancelled)
        keep_alive(th)
        self.mp3_bar.setValue(0)
        self.mp3_label.setText(self._mp3_text)
        self.btn_mp3_cancel.setEnabled(True)
        self._sync_buttons()
        th.start()
        QTimer.singleShot(300, self._mp3_reveal)

    def _mp3_reveal(self):
        if self._mp3 is not None:
            self.mp3_strip.show()

    def _mp3_progress(self, frac):
        if self._mp3 is None or self._mp3.cancel_event.is_set():
            return
        self.mp3_bar.setValue(int(frac * 1000))
        self.mp3_label.setText(f"{self._mp3_text} {int(frac * 100)}%")

    def on_cancel_mp3(self):
        if self._mp3 is not None:
            self._mp3.cancel()
            self.btn_mp3_cancel.setEnabled(False)
            self.mp3_label.setText("취소하고 있어요")

    def _mp3_finish(self):
        self._mp3, self._mp3_id = None, None
        self.mp3_strip.hide()
        self._sync_buttons()

    def _mp3_done(self, _):
        self._mp3_finish()
        self.ctx.toast("MP3로 저장했어요", "success")

    def _mp3_cancelled(self):
        self._mp3_finish()
        self.ctx.toast("저장을 취소했어요")

    def _mp3_failed(self, msg):
        self._mp3_finish()
        notify(self, "저장하지 못했어요", error_message(
            "저장할 폴더와 남은 공간을 확인하세요.", msg))

    def on_delete(self):
        s = self._selected()
        if not s or self._saving_mp3_of(int(s["id"])):
            return
        n = repo.sound_usage_counts(self.conn).get(int(s["id"]), 0)
        if n:
            notify(self, "지금은 삭제할 수 없어요",
                   f"시간표에서 다른 종소리로 바꾼 뒤 삭제하세요. (사용 중: {n}개)")
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
            notify(self, "재생하지 못했어요", error_message(
                "스피커 연결과 종소리 파일을 확인하세요.", e))

    def on_stop(self):
        self.ctx.player.stop()
        self.eq.set_active(False)

    def _context_menu(self, pos):
        r = self.table.rowAt(pos.y())
        if r >= 0:
            self.table.selectRow(r)
        m = Menu(self)
        if r >= 0:
            m.addAction("들어보기", self.on_play)
            busy = self._saving_mp3_of(self.table.row_id(r))
            m.addAction("자르기·다듬기", self.on_editor).setEnabled(not busy)
            m.addAction("이름·음량", self.on_info)
            m.addAction("MP3로 저장", self.on_save_mp3).setEnabled(self._mp3 is None)
            m.addSeparator()
            m.addAction("삭제", self.on_delete).setEnabled(not busy)
            m.addSeparator()
        m.addAction("인터넷에서 찾기", self.on_youtube)
        m.addAction("파일 추가", self.on_add)
        m.exec(self.table.viewport().mapToGlobal(pos))
