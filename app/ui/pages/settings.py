from datetime import datetime
from urllib.parse import urlparse

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QFileDialog, QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from app.core import backup, ffmpeg, weather, youtube, ytpot
from app.core.paths import app_data_dir
from app.core.version import APP_VERSION, DEVELOPER
from app.data import repo
from app.ui.dialogs import confirm, notify
from app.ui.select import Select
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
        user = ctx.session.user if ctx.session is not None else None
        if user:
            # 어느 통합 클라우드 아이디로 켜졌는지 (계정은 통합 클라우드에서 바꿈)
            username = user.get("username") or ""
            host = urlparse(ctx.session.server or "").hostname or ""
            gen.body.addSpacing(6)
            gen.body.addWidget(_row("로그인한 아이디",
                                    "아이디를 바꾸려면 통합 클라우드에서 로그아웃한 뒤 다시 로그인해 주세요.",
                                    _value(" · ".join(x for x in (f"{user.get('name') or username} ({username})", host) if x),
                                           C.grey900)))
            gen.body.addWidget(hline())
        self.chk_ring = ToggleSwitch("")
        self.chk_ring.setChecked(ctx.scheduler.ring_enabled)
        self.chk_ring.toggled.connect(self.on_toggle_ring)
        gen.body.addSpacing(6)
        gen.body.addWidget(_row("이 기기에서 종 울리기", "끄면 시간표만 맞추고 이 컴퓨터에서는 종이 울리지 않아요.",
                                self.chk_ring))
        left.addWidget(gen)

        fs = Card(padding=24)
        fs.body.setSpacing(0)
        fs.body.addWidget(_title("전체화면 시계"))
        fs.body.addSpacing(6)
        self.chk_weather = ToggleSwitch("")
        self.chk_weather.setChecked(repo.get_setting(self.conn, "weather_on", "1") != "0")
        self.chk_weather.toggled.connect(self._on_weather_toggle)
        fs.body.addWidget(_row("날씨 예보 보이기", "지금 날씨와 앞으로 몇 시간의 예보를 함께 보여 줘요.", self.chk_weather))
        fs.body.addWidget(hline())
        self.weather_city = Button("바꾸기", variant="secondary")
        self.weather_city.clicked.connect(self._on_weather_city)
        self.weather_city.setEnabled(self.chk_weather.isChecked())
        self.place_row = _row("날씨 지역", " ", self.weather_city)
        self.place_desc = self.place_row.findChildren(QLabel)[1]
        self._sync_place()
        fs.body.addWidget(self.place_row)
        fs.body.addWidget(hline())
        self.fs_theme = Select()
        self.fs_theme.setProperty("page", True)
        self.fs_theme.addItem("어둡게", "dark")
        self.fs_theme.addItem("밝게", "light")
        self.fs_theme.setCurrentIndex(1 if repo.get_setting(self.conn, "fs_theme", "dark") == "light" else 0)
        self.fs_theme.setMinimumWidth(120)
        self.fs_theme.currentIndexChanged.connect(
            lambda _i: repo.set_setting(self.conn, "fs_theme", self.fs_theme.currentData()))
        fs.body.addWidget(_row("화면 밝기", "시계 화면에서 버튼이나 T 키로도 바꿀 수 있어요.", self.fs_theme))
        left.addWidget(fs)

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
        self.btn_history = Button("업데이트 기록", variant="secondary")
        info.body.addWidget(_row(f"버전 {APP_VERSION}",
                                 "새 버전은 통합 클라우드가 받아 두고, 종이 멀 때 저절로 다시 켜져요.",
                                 self.btn_history))
        info.body.addWidget(hline())
        info.body.addWidget(_row("만든 사람", "", _value(DEVELOPER)))
        info.body.addWidget(hline())
        ok_ff = ffmpeg.available()
        info.body.addWidget(_row("음원 변환 (ffmpeg)", "", _value("사용 가능" if ok_ff else "없음",
                                                               C.success if ok_ff else C.danger)))
        info.body.addWidget(hline())
        yv = youtube.version()
        ready = bool(yv) and bool(youtube.deno_path())
        pot = ytpot.available()
        ready = ready and pot
        yt_text = "없음" if not yv else (f"{yv} · 준비됨" if ready else f"{yv} · 일부 영상 제한")
        info.body.addWidget(_row("YouTube (yt-dlp)", "", _value(yt_text, C.grey700 if ready else C.danger)))
        info.body.addWidget(hline())
        self.btn_google = Button("로그인", variant="secondary")
        self.btn_google.clicked.connect(self._on_google)
        self.google_row = _row("YouTube 구글 로그인", " ", self.btn_google)
        self.google_desc = self.google_row.findChildren(QLabel)[1]
        info.body.addWidget(self.google_row)
        self._sync_google()
        info.body.addWidget(hline())
        self.btn_folder = Button("열기", variant="secondary")
        info.body.addWidget(_row("데이터 폴더", "", self.btn_folder))
        info.body.addStretch(1)
        rcol = QVBoxLayout()
        rcol.setSpacing(16)
        rcol.addWidget(info)
        rcol.addStretch(1)
        cols.addLayout(rcol, 2)
        # 창이 작아도 잘리지 않도록 스크롤
        holder = QWidget()
        holder.setObjectName("settingsHolder")
        holder.setStyleSheet("#settingsHolder { background: transparent; }")
        hl = QVBoxLayout(holder)
        hl.setContentsMargins(0, 0, 6, 4)
        hl.addLayout(cols)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; } QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.setWidget(holder)
        root.addWidget(scroll, 1)

        self.btn_backup.clicked.connect(self.on_backup)
        self.btn_restore.clicked.connect(self.on_restore)
        self.btn_sched_csv.clicked.connect(self.on_sched_csv)
        self.btn_folder.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(app_data_dir()))))
        self.btn_history.clicked.connect(self._show_history)

    def _on_weather_toggle(self, on):
        repo.set_setting(self.conn, "weather_on", "1" if on else "0")
        self.weather_city.setEnabled(on)

    def _sync_place(self):
        name = weather.place_of(weather.setting_value(lambda k, d: repo.get_setting(self.conn, k, d)))[0]
        self.place_desc.setText(f"{name} · 동네 이름으로 찾을 수 있어요.")

    def _on_weather_city(self):
        from app.ui.place_dialog import pick_place
        name = pick_place(self.conn, self)
        if name:
            self._sync_place()
            self.ctx.toast(f"{name} 날씨를 보여 줄게요", "success")

    def _show_history(self):
        from app.ui.changelog_dialog import ChangelogDialog
        ChangelogDialog(self).exec()

    def showEvent(self, e):
        super().showEvent(e)
        self._sync_google()

    def _sync_google(self):
        from app.core import google_login
        on = google_login.is_logged_in()
        if on:
            ts = google_login.logged_in_at()
            when = datetime.fromtimestamp(ts).strftime("%Y년 %m월 %d일") if ts else ""
            self.google_desc.setText(f"로그인됨{' · ' + when if when else ''}. YouTube에서 받을 때 이 계정을 써요.")
        else:
            self.google_desc.setText("YouTube가 막을 때 로그인하면 받을 수 있어요. 자주 쓰지 않는 계정이어도 돼요.")
        self.btn_google.setText("로그아웃" if on else "로그인")
        self.btn_google.updateGeometry()

    def _on_google(self):
        from app.core import google_login
        if google_login.is_logged_in():
            if confirm(self, "구글 로그아웃할까요?", "이 컴퓨터에 저장한 로그인 정보를 지워요.", "로그아웃", danger=False):
                google_login.logout()
                self.ctx.toast("로그아웃했어요")
        else:
            from app.ui.google_login_dialog import login
            if login(self):
                self.ctx.toast("구글 로그인했어요", "success")
        self._sync_google()

    def on_toggle_ring(self, on):
        self.ctx.scheduler.set_ring_enabled(on)
        self.ctx.data_changed.emit("device")
        self.ctx.toast("이 컴퓨터에서 종을 울려요" if on else "이 컴퓨터에서는 종을 울리지 않아요",
                       "success" if on else "info")

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
