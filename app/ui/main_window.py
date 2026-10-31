from datetime import datetime

from PyQt6.QtCore import QDateTime, Qt, QTimer
from PyQt6.QtGui import QAction, QCursor, QIcon
from PyQt6.QtWidgets import QHBoxLayout, QMainWindow, QSystemTrayIcon, QWidget

from app.core.paths import asset_path
from app.core.player import SoundPlayer
from app.core.scheduler import Scheduler
from app.core.timeutil import ampm
from app.core.version import APP_TITLE, APP_VERSION
from app.ui import icons
from app.ui.context import AppContext
from app.core.updater import notes_to_text
from app.ui.dialogs import confirm, notify
from app.ui.fullscreen_clock import FullscreenClock
from app.ui.nav import NavSidebar
from app.ui.select import Menu
from app.ui.pages.dashboard import DashboardPage
from app.ui.pages.logs import LogsPage
from app.ui.pages.schedules import SchedulesPage
from app.ui.pages.settings import SettingsPage
from app.ui.pages.sounds import SoundsPage
from app.ui.theme import C
from app.ui.update_manager import UpdateManager
from app.ui.widgets import AnimatedStack, Button, ToastManager

NAV = [("dashboard", "홈"), ("calendar", "시간표"), ("bell", "종소리"), ("logs", "기록"), ("settings", "설정")]


class MainWindow(QMainWindow):
    def __init__(self, conn, app):
        super().__init__()
        self.conn = conn
        self.app = app
        self.player = SoundPlayer()
        self.scheduler = Scheduler(self.conn, self.player)
        self.ctx = AppContext(conn, self.player, self.scheduler, self)
        self._fullscreen = None
        self._really_quit = False

        self.setWindowTitle(f"{APP_TITLE} {APP_VERSION}")

        central = QWidget()
        self.setCentralWidget(central)
        lay = QHBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.nav = NavSidebar(NAV)
        lay.addWidget(self.nav)
        self.stack = AnimatedStack()
        lay.addWidget(self.stack, 1)

        self.scheduler.start()
        self.updates = UpdateManager(self.ctx, self.quit_for_update)
        self.ctx.updates = self.updates
        self.dashboard = DashboardPage(self.ctx)
        self.pages = [self.dashboard, SchedulesPage(self.ctx), SoundsPage(self.ctx), LogsPage(self.ctx),
                      SettingsPage(self.ctx)]
        for p in self.pages:
            self.stack.addWidget(p)
        self.nav.currentChanged.connect(lambda i: self.stack.switch_to(i))
        self.updates.changed.connect(lambda: self.nav.list.set_badge(4, self.updates.has_update()))
        self.dashboard.openFullscreen.connect(self.open_fullscreen)

        btn_full = Button("전체화면 시계", variant="secondary")
        btn_full.clicked.connect(self.open_fullscreen)
        btn_exit = Button("프로그램 끄기", variant="subtle")
        btn_exit.clicked.connect(self.on_exit_app)
        self.nav.footer.addWidget(btn_full)
        self.nav.footer.addWidget(btn_exit)

        self.ctx.toasts = ToastManager(central)
        self._init_tray()
        self._init_window_icon()

        # 초가 바뀌는 순간에 맞춰 1초에 한 번 (종 시각에 더 정확하고, 불필요하게 깨어나지 않음)
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._on_timer)
        self._tooltip = ""
        self._on_timer()

        self.setMinimumSize(1060, 700)
        self._revealed = False

    def showEvent(self, e):
        super().showEvent(e)
        if not self._revealed:
            self._revealed = True
            QTimer.singleShot(30, lambda: self.stack.reveal())
            QTimer.singleShot(900, self._show_whats_new)

    def _show_whats_new(self):
        got = self.updates.take_whats_new()
        if not got:
            return
        version, notes = got
        from app.ui.changelog_dialog import ChangelogDialog, notes_for
        if notes_for(version):
            ChangelogDialog(self, only_version=version, title=f"{version} 버전으로 업데이트했어요").exec()
            return
        text = notes_to_text(notes) or "더 안정적으로 다듬었어요."
        notify(self, f"{version} 버전으로 업데이트했어요", text)

    # ---------------- 트레이 ----------------
    def _app_icon(self):
        p = asset_path("ui", "app.ico")
        return QIcon(str(p)) if p.exists() else icons.icon("bell", C.accent, 32)

    def _init_window_icon(self):
        self.setWindowIcon(self._app_icon())

    def _init_tray(self):
        self.tray = QSystemTrayIcon(self._app_icon(), self)
        self.tray.setToolTip("Mapl Tajong")
        menu = Menu()
        for text, ic, fn in (("열기", "dashboard", self._tray_show), ("숨기기", "x", self.hide),
                             ("전체화면 시계", "fullscreen", self.open_fullscreen)):
            a = QAction(icons.icon(ic, C.text), text, self)
            a.triggered.connect(fn)
            menu.addAction(a)
        menu.addSeparator()
        a = QAction(icons.icon("power", C.danger), "종료", self)
        a.triggered.connect(self.on_exit_app)
        menu.addAction(a)
        self._tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_show(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._tray_show()

    def closeEvent(self, event):
        if self._really_quit:
            event.accept()
            return
        self.hide()
        try:
            self.tray.showMessage(APP_TITLE, "창을 닫아도 종은 계속 울려요. 완전히 끄려면 ‘프로그램 끄기’를 눌러 주세요.",
                                  QSystemTrayIcon.MessageIcon.Information, 1500)
        except Exception:
            pass
        event.ignore()

    # ---------------- 주기 작업 ----------------
    def _on_timer(self):
        self.on_tick()
        self.timer.start(1000 - QDateTime.currentDateTime().time().msec() + 10)

    def on_tick(self):
        self.scheduler.tick()
        ev = self.scheduler.next_event
        nxt = (ev.run_at - datetime.now()).total_seconds() if ev else None
        self.player.idle_tick(nxt)
        tip = f"Mapl Tajong\n다음: {ampm(ev.run_at)} {ev.name}" if ev else "Mapl Tajong\n예정된 종 없음"
        if tip != self._tooltip:
            self._tooltip = tip
            self.tray.setToolTip(tip)

    def open_fullscreen(self):
        screens = self.app.screens()
        if len(screens) > 1:
            m = Menu(self)
            for i, s in enumerate(screens):
                g = s.geometry()
                act = m.addAction(icons.icon("fullscreen", C.text), f"화면 {i + 1}  ({g.width()}×{g.height()})")
                act.setData(i)
            chosen = m.exec(QCursor.pos())
            if not chosen:
                return
            screen = screens[int(chosen.data())]
        else:
            screen = self.screen()
        if self._fullscreen is not None:
            try:
                self._fullscreen.close()
            except RuntimeError:
                pass
        w = FullscreenClock(self.ctx, screen)
        w.setGeometry(screen.geometry())
        w.showFullScreen()
        w.activateWindow()
        self._fullscreen = w

    def _shutdown(self):
        try:
            self.scheduler.stop()
            self.player.stop()
        except Exception:
            pass
        try:
            self.tray.hide()
        except Exception:
            pass
        if self._fullscreen is not None:
            try:
                self._fullscreen.close()
            except RuntimeError:
                pass
        self._really_quit = True
        self.app.quit()

    def quit_for_update(self):
        """설치 파일이 프로그램 파일을 바꿀 수 있도록 바로 종료."""
        self._shutdown()

    def on_exit_app(self):
        if self.isHidden():
            self._tray_show()
        if not confirm(self, "프로그램을 끌까요?", "끄면 정해진 시간에 종이 울리지 않아요.\n창만 숨기려면 오른쪽 위 X를 누르세요.",
                       "끄기", danger=True):
            return
        self._shutdown()
