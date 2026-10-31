from datetime import datetime

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from app.core import backup, ffmpeg, youtube
from app.core.paths import app_data_dir
from app.core.startup import disable_startup, enable_startup, is_startup_enabled, is_supported
from app.core.version import APP_VERSION, DEVELOPER
from app.ui.dialogs import confirm, notify
from app.ui.theme import C
from app.ui.widgets import Button, Card, PageHeader, ToggleSwitch, hline


def _title(text):
    l = QLabel(text)
    l.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {C.grey900};")
    return l


def _row(title, desc, right):
    w = QWidget()
    lay = QHBoxLayout(w)
    lay.setContentsMargins(0, 12, 0, 12)
    lay.setSpacing(16)
    col = QVBoxLayout()
    col.setSpacing(3)
    t = QLabel(title)
    t.setStyleSheet(f"font-size: 15px; font-weight: 600; color: {C.grey900};")
    col.addWidget(t)
    if desc:
        d = QLabel(desc)
        d.setWordWrap(True)
        d.setStyleSheet(f"font-size: 13px; color: {C.grey500};")
        col.addWidget(d)
    lay.addLayout(col, 1)
    if isinstance(right, QWidget):
        lay.addWidget(right, 0, Qt.AlignmentFlag.AlignVCenter)
    else:
        lay.addLayout(right)
    return w


def _value(text, color=C.grey700):
    l = QLabel(text)
    l.setStyleSheet(f"font-size: 14px; color: {color};")
    return l


class SettingsPage(QWidget):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.conn = ctx.conn
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 26, 28, 20)
        root.setSpacing(16)
        root.addWidget(PageHeader("설정"))

        cols = QHBoxLayout()
        cols.setSpacing(16)
        left = QVBoxLayout()
        left.setSpacing(16)

        gen = Card(padding=24)
        gen.body.setSpacing(0)
        gen.body.addWidget(_title("일반"))
        self.chk_startup = ToggleSwitch("")
        self.chk_startup.setChecked(is_startup_enabled())
        self.chk_startup.setEnabled(is_supported())
        self.chk_startup.toggled.connect(self.on_toggle_startup)
        gen.body.addSpacing(6)
        gen.body.addWidget(_row("컴퓨터를 켜면 자동으로 실행", "트레이에서 조용히 시작해요.", self.chk_startup))
        left.addWidget(gen)

        bk = Card(padding=24)
        bk.body.setSpacing(0)
        bk.body.addWidget(_title("백업"))
        bk.body.addSpacing(6)
        self.btn_backup = Button("백업하기", variant="secondary")
        self.btn_restore = Button("불러오기", variant="secondary")
        self.btn_sched_csv = Button("내보내기", variant="secondary")
        bk.body.addWidget(_row("백업 파일 만들기", "시간표, 세트, 종소리를 파일 하나에 담아요.", self.btn_backup))
        bk.body.addWidget(hline())
        bk.body.addWidget(_row("백업 불러오기", "다른 컴퓨터에서 만든 백업도 그대로 옮길 수 있어요.", self.btn_restore))
        bk.body.addWidget(hline())
        bk.body.addWidget(_row("시간표를 엑셀로", "인쇄하거나 공유할 때 써요.", self.btn_sched_csv))
        left.addWidget(bk)
        left.addStretch(1)
        cols.addLayout(left, 3)

        info = Card(padding=24)
        info.body.setSpacing(0)
        info.body.addWidget(_title("정보"))
        info.body.addSpacing(6)
        info.body.addWidget(_row("버전", "", _value(APP_VERSION)))
        info.body.addWidget(hline())
        info.body.addWidget(_row("만든 사람", "", _value(DEVELOPER)))
        info.body.addWidget(hline())
        ok_ff = ffmpeg.available()
        info.body.addWidget(_row("음원 변환 (ffmpeg)", "", _value("사용 가능" if ok_ff else "없음",
                                                               C.success if ok_ff else C.danger)))
        info.body.addWidget(hline())
        yv = youtube.version()
        info.body.addWidget(_row("YouTube (yt-dlp)", "", _value(yv or "없음", C.grey700 if yv else C.danger)))
        info.body.addWidget(hline())
        self.btn_folder = Button("열기", variant="secondary")
        info.body.addWidget(_row("데이터 폴더", "", self.btn_folder))
        info.body.addStretch(1)
        rcol = QVBoxLayout()
        rcol.addWidget(info)
        rcol.addStretch(1)
        cols.addLayout(rcol, 2)
        root.addLayout(cols, 1)

        self.btn_backup.clicked.connect(self.on_backup)
        self.btn_restore.clicked.connect(self.on_restore)
        self.btn_sched_csv.clicked.connect(self.on_sched_csv)
        self.btn_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir()))))

    def on_toggle_startup(self, on):
        try:
            enable_startup() if on else disable_startup()
            self.ctx.toast("자동 실행을 켰어요" if on else "자동 실행을 껐어요", "success")
        except Exception as e:
            notify(self, "설정하지 못했어요", str(e))

    def on_backup(self):
        path, _ = QFileDialog.getSaveFileName(self, "백업 파일 저장", backup.default_backup_name(), "백업 파일 (*.zip)")
        if not path:
            return
        try:
            m = backup.export_backup(self.conn, path)
        except Exception as e:
            notify(self, "백업하지 못했어요", str(e))
            return
        c = m["counts"]
        self.ctx.toast(f"백업했어요 · 일정 {c.get('schedules', 0)}개, 종소리 {c.get('sounds', 0)}개", "success", 3200)

    def on_restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "백업 파일 선택", "", "백업 파일 (*.zip);;모든 파일 (*)")
        if not path:
            return
        try:
            m = backup.read_manifest(path)
        except backup.BackupError as e:
            notify(self, "불러올 수 없어요", str(e))
            return
        c = m.get("counts", {})
        if not confirm(self, "백업을 불러올까요?",
                       f"{m.get('created_at', '')[:16]}에 만든 백업이에요.\n"
                       f"일정 {c.get('schedules', 0)}개 · 세트 {c.get('schedule_sets', 0)}개 · 종소리 {c.get('sounds', 0)}개\n\n"
                       "지금 시간표와 종소리는 백업 내용으로 바뀌어요. 기록은 그대로예요.", "불러오기", danger=False):
            return
        try:
            backup.import_backup(self.conn, path, before_replace_files=self.ctx.player.stop)
        except Exception as e:
            notify(self, "불러오지 못했어요", str(e))
            return
        self.ctx.changed("all")
        self.ctx.toast("백업을 불러왔어요", "success")

    def on_sched_csv(self):
        path, _ = QFileDialog.getSaveFileName(self, "시간표 내보내기", f"시간표_{datetime.now():%Y%m%d}.csv", "CSV (*.csv)")
        if not path:
            return
        try:
            n = backup.export_schedules_csv(self.conn, path)
        except Exception as e:
            notify(self, "내보내지 못했어요", str(e))
            return
        self.ctx.toast(f"일정 {n}개를 저장했어요", "success")
