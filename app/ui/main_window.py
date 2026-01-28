from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QMessageBox, QComboBox,
    QCheckBox, QLineEdit, QDateEdit, QSpinBox, QFrame, QToolBar,
    QGroupBox, QHeaderView, QAbstractItemView, QSystemTrayIcon, QMenu
)
from PyQt6.QtCore import QTimer, QDate, Qt
from PyQt6.QtGui import QIcon, QAction
from app.core.paths import asset_path

from pathlib import Path

import shutil
from datetime import datetime

from app.data import repo
from app.core.paths import sound_file_path, sounds_dir, asset_path
from app.ui.dialogs import AddSoundDialog, ScheduleDialog, EditSoundDialog
from app.core.player import SoundPlayer
from app.core.scheduler import Scheduler
from app.core.startup import is_startup_enabled, enable_startup, disable_startup

class MainWindow(QMainWindow):
    def __init__(self, conn, app):
        super().__init__()
        self.conn = conn
        self.app = app
        self.player = SoundPlayer()
        self.scheduler = Scheduler(self.conn, self.player)

        self.setWindowTitle("마고수학학원 타종 프로그램 - 구현민 개발")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self.tab_ops = QWidget()
        self.tab_sounds = QWidget()
        self.tab_schedules = QWidget()
        self.tab_logs = QWidget()
        self.tab_settings = QWidget()

        self.tabs.addTab(self.tab_ops, "운영")
        self.tabs.addTab(self.tab_sounds, "종소리")
        self.tabs.addTab(self.tab_schedules, "시간표")
        self.tabs.addTab(self.tab_ops, "운영")
        self.tabs.addTab(self.tab_sounds, "종소리")
        self.tabs.addTab(self.tab_schedules, "시간표")
        self.tabs.addTab(self.tab_logs, "로그")
        self.tabs.addTab(self.tab_settings, "설정")

        self._build_logs()
        self._build_ops()
        self._build_sounds()
        self._build_schedules()
        self._build_settings()

        self._apply_style()
        self._build_topbar()
        self._init_tray()
        self._init_window_icon()

        self.refresh_all()

        self.scheduler.start()

        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.on_tick)
        self.timer.start()
        self.setMinimumSize(980, 720)
    
    def _apply_style(self):
        self.setStyleSheet("""
        * {
            font-family: "Segoe UI", "Malgun Gothic";
        }

        QMainWindow {
            background: #f6f7fb;
        }

        QTabWidget::pane {
            border: 0;
            background: transparent;
        }

        QTabBar::tab {
            background: transparent;
            padding: 10px 16px;
            margin-right: 6px;
            border-radius: 12px;
            color: #333;
        }

        QTabBar::tab:selected {
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.12);
            color: #111;
        }

        QTabBar::tab:hover {
            background: rgba(255,255,255,0.6);
        }

        QFrame#Card {
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.12);
            border-radius: 16px;
        }

        QGroupBox {
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.12);
            border-radius: 16px;
            margin-top: 22px;
            padding: 18px 14px 14px 14px;
        }

        QGroupBox::title {
            subcontrol-origin: margin;
            left: 14px;
            top: 10px;
            padding: 2px 8px;
            background: #ffffff;
            color: #444;
            font-weight: 650;
        }

        QLabel#BigTime {
            font-size: 22px;
            font-weight: 700;
            color: #111;
        }

        QLabel#BigNext {
            font-size: 16px;
            font-weight: 650;
            color: #111;
        }

        QLabel#Muted {
            color: #666;
        }

        QPushButton {
            background: #ffffff;
            color: #111;
            border: 1px solid rgba(0,0,0,0.16);
            padding: 10px 14px;
            border-radius: 12px;
        }

        QPushButton:hover {
            background: rgba(0,0,0,0.04);
        }

        QPushButton:pressed {
            background: rgba(0,0,0,0.08);
            padding-top: 11px;
            padding-bottom: 9px;
        }

        QPushButton:disabled {
            color: rgba(0,0,0,0.35);
            border-color: rgba(0,0,0,0.10);
            background: rgba(0,0,0,0.03);
        }
                           
        QMenuBar {
            background: #f6f7fb;
            padding: 2px 6px;
            border: 0;
        }

        QMenuBar::item {
            background: transparent;
            padding: 0px 6px;
        }

        QPushButton#MenuExit {
            background: #ffffff;
            border: 1px solid rgba(200, 0, 0, 0.35);
            color: rgb(150, 0, 0);
            padding: 6px 12px;
            border-radius: 10px;
        }

        QPushButton#MenuExit:hover {
            background: rgba(200, 0, 0, 0.06);
        }

        QPushButton#MenuExit:pressed {
            background: rgba(200, 0, 0, 0.12);
        }

        QPushButton#Ghost {
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.16);
        }

        QComboBox, QDateEdit, QDateTimeEdit, QLineEdit {
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.16);
            border-radius: 12px;
            padding: 8px 10px;
        }

        QComboBox:hover, QDateEdit:hover, QDateTimeEdit:hover, QLineEdit:hover {
            border-color: rgba(0,0,0,0.28);
        }

        QTableWidget {
            background: #ffffff;
            border: 1px solid rgba(0,0,0,0.12);
            border-radius: 16px;
            gridline-color: rgba(0,0,0,0.08);
            selection-background-color: rgba(0,0,0,0.08);
            selection-color: #111;
        }

        QHeaderView::section {
            background: rgba(0,0,0,0.04);
            color: #222;
            padding: 10px;
            border: 0;
            border-bottom: 1px solid rgba(0,0,0,0.12);
            font-weight: 650;
        }

        QTableWidget::item {
            padding: 8px 10px;
        }

        QTableWidget::item:hover {
            background: rgba(0,0,0,0.03);
        }

        QMessageBox QPushButton {
            min-width: 90px;
        }
        
        QPushButton#Danger {
            border: 1px solid rgba(200, 0, 0, 0.35);
            color: rgb(150, 0, 0);
        }

        QPushButton#Danger:hover {
            background: rgba(200, 0, 0, 0.06);
        }

        QPushButton#Danger:pressed {
            background: rgba(200, 0, 0, 0.12);
        }
        
        QToolBar {
            background: #f6f7fb;
            border: 0;
            border-bottom: 1px solid rgba(0,0,0,0.12);
            spacing: 0px;
        }

        QToolBar::separator {
            background: transparent;
            width: 0px;
        }

        QPushButton#TopExit {
            background: #ffffff;
            border: 1px solid rgba(200, 0, 0, 0.35);
            color: rgb(150, 0, 0);
            padding: 6px 12px;
            border-radius: 10px;
        }

        QPushButton#TopExit:hover {
            background: rgba(200, 0, 0, 0.06);
        }

        QPushButton#TopExit:pressed {
            background: rgba(200, 0, 0, 0.12);
        }
        """)

    
    def _format_remaining(self, seconds):
        if seconds < 0:
            seconds = 0

        days = seconds // 86400
        seconds = seconds % 86400
        hours = seconds // 3600
        seconds = seconds % 3600
        minutes = seconds // 60
        secs = seconds % 60

        if days > 0:
            return f"{days}일 {hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"

    def clear_transient_overrides(conn, date_yyyymmdd):
        conn.execute(
            "DELETE FROM overrides WHERE date_yyyymmdd=? AND action IN ('SKIP_ONCE','FIRED_ONCE')",
            (date_yyyymmdd,)
        )
        conn.commit()

    def _mask_to_days(self, mask):
        items = [("월",1),("화",2),("수",4),("목",8),("금",16),("토",32),("일",64)]
        m = int(mask)
        s = []
        for name, bit in items:
            if (m & bit) != 0:
                s.append("[" + name + "]")
        return " ".join(s) if s else "-"

    def _build_ops(self):
        layout = QVBoxLayout(self.tab_ops)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        top = QFrame()
        top.setObjectName("Card")
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(16, 16, 16, 16)
        top_layout.setSpacing(8)

        self.label_now = QLabel("")
        self.label_now.setObjectName("BigTime")

        self.label_next = QLabel("")
        self.label_next.setObjectName("BigNext")
        self.label_next.setWordWrap(True)

        self.label_state = QLabel("상태: 실행중")
        self.label_state.setObjectName("Muted")

        self.chk_pause_today = QCheckBox("오늘만 자동 타종 정지")
        self.chk_pause_today.stateChanged.connect(self.on_toggle_pause_today)

        top_layout.addWidget(self.label_now)
        top_layout.addWidget(self.label_next)
        top_layout.addWidget(self.label_state)
        top_layout.addSpacing(4)
        top_layout.addWidget(self.chk_pause_today)

        layout.addWidget(top)

        box_manual = QGroupBox("수동 재생")
        b1 = QVBoxLayout(box_manual)
        b1.setContentsMargins(14, 16, 14, 14)
        b1.setSpacing(10)

        row1 = QHBoxLayout()
        self.ops_sound_combo = QComboBox()
        row1.addWidget(self.ops_sound_combo)
        b1.addLayout(row1)

        row2 = QHBoxLayout()
        btn_test = QPushButton("선택 종 지금 치기")
        btn_stop = QPushButton("정지")
        btn_stop.setObjectName("Ghost")
        row2.addWidget(btn_test)
        row2.addWidget(btn_stop)
        b1.addLayout(row2)

        btn_test.clicked.connect(self.on_ring_selected_sound)
        btn_stop.clicked.connect(self.player.stop)

        layout.addWidget(box_manual)

        box_next = QGroupBox("다음 이벤트 제어")
        b2 = QVBoxLayout(box_next)
        b2.setContentsMargins(14, 16, 14, 14)
        b2.setSpacing(10)

        row3 = QHBoxLayout()
        btn_next = QPushButton("다음 종 지금 치기")
        btn_skip = QPushButton("다음 종 패스(1회)")
        btn_skip.setObjectName("Ghost")
        row3.addWidget(btn_next)
        row3.addWidget(btn_skip)
        b2.addLayout(row3)

        row4 = QHBoxLayout()
        btn_pause = QPushButton("일시정지")
        btn_pause.setObjectName("Ghost")
        btn_resume = QPushButton("재개")
        row4.addWidget(btn_pause)
        row4.addWidget(btn_resume)
        b2.addLayout(row4)

        btn_next.clicked.connect(self.on_ring_next)
        btn_skip.clicked.connect(self.on_skip_next)
        btn_pause.clicked.connect(self.on_pause)
        btn_resume.clicked.connect(self.on_resume)

        layout.addWidget(box_next)
        layout.addStretch(1)

    def on_toggle_pause_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        repo.set_pause_today(self.conn, today, self.chk_pause_today.isChecked())

    def _build_sounds(self):
        layout = QVBoxLayout(self.tab_sounds)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        bar = QFrame()
        bar.setObjectName("Card")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 12, 12, 12)
        bar_layout.setSpacing(10)

        btn_add = QPushButton("추가")
        btn_edit = QPushButton("수정")
        btn_edit.setObjectName("Ghost")
        btn_del = QPushButton("삭제")
        btn_del.setObjectName("Ghost")

        bar_layout.addWidget(btn_add)
        bar_layout.addWidget(btn_edit)
        bar_layout.addWidget(btn_del)
        bar_layout.addStretch(1)

        layout.addWidget(bar)

        self.sound_table = QTableWidget()
        self.sound_table.setColumnCount(4)
        self.sound_table.setHorizontalHeaderLabels(["ID", "이름", "파일", "음량"])
        self.sound_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.sound_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.sound_table.setAlternatingRowColors(True)
        self.sound_table.horizontalHeader().setStretchLastSection(True)
        self.sound_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.sound_table.cellDoubleClicked.connect(lambda r, c: self.on_edit_sound())
        hdr = self.sound_table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)        
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)         
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)           

        self.sound_table.setColumnWidth(3, 90)
        self.sound_table.setColumnHidden(0, True)

        layout.addWidget(self.sound_table)

        btn_add.clicked.connect(self.on_add_sound)
        btn_edit.clicked.connect(self.on_edit_sound)
        btn_del.clicked.connect(self.on_delete_sound)

    def _build_schedules(self):
        layout = QVBoxLayout(self.tab_schedules)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        bar = QFrame()
        bar.setObjectName("Card")
        bar_layout = QHBoxLayout(bar)
        bar_layout.setContentsMargins(12, 12, 12, 12)
        bar_layout.setSpacing(10)

        btn_add = QPushButton("추가")
        btn_edit = QPushButton("수정")
        btn_del = QPushButton("삭제")

        bar_layout.addWidget(btn_add)
        bar_layout.addWidget(btn_edit)
        bar_layout.addWidget(btn_del)

        bar_layout.addStretch(1)

        bar_layout.addWidget(QLabel("요일"))
        self.sch_day_filter = QComboBox()
        self.sch_day_filter.addItem("전체", 0)
        self.sch_day_filter.addItem("월", 1)
        self.sch_day_filter.addItem("화", 2)
        self.sch_day_filter.addItem("수", 4)
        self.sch_day_filter.addItem("목", 8)
        self.sch_day_filter.addItem("금", 16)
        self.sch_day_filter.addItem("토", 32)
        self.sch_day_filter.addItem("일", 64)
        bar_layout.addWidget(self.sch_day_filter)

        layout.addWidget(bar)

        self.schedule_table = QTableWidget()
        self.schedule_table.setColumnCount(8)
        self.schedule_table.setHorizontalHeaderLabels(
            ["ID", "활성", "요일", "시간", "이벤트명", "종소리", "음량", "정렬"]
        )
        self.schedule_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.schedule_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.schedule_table.setAlternatingRowColors(True)
        self.schedule_table.verticalHeader().setDefaultSectionSize(44)

        self.schedule_table.horizontalHeader().setStretchLastSection(True)
        self.schedule_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        self.schedule_table.setColumnHidden(0, True)
        self.schedule_table.setColumnHidden(7, True)
        self.schedule_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        hdr = self.schedule_table.horizontalHeader()
        hdr.setStretchLastSection(False)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents) 
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents) 
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)          
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)         
        hdr.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents) 

        layout.addWidget(self.schedule_table)

        btn_add.clicked.connect(self.on_add_schedule)
        btn_edit.clicked.connect(self.on_edit_schedule)
        btn_del.clicked.connect(self.on_delete_schedule)

        self.schedule_table.cellDoubleClicked.connect(lambda r, c: self.on_edit_schedule())
        self.sch_day_filter.currentIndexChanged.connect(self.refresh_schedules)

    def on_tick(self):
        self.scheduler.tick()

        now = datetime.now()
        self.label_now.setText(now.strftime("현재: %Y-%m-%d %H:%M:%S"))

        ev = self.scheduler.next_event
        if ev:
            remain = int((ev.run_at - now).total_seconds())
            self.label_next.setText(
                f'다음: {ev.run_at.strftime("%Y-%m-%d %H:%M:%S")}  {ev.name}  ({ev.sound_name})  남은시간 {self._format_remaining(remain)}'
            )
        else:
            self.label_next.setText("다음: 없음")

        state = "실행중"
        if repo.is_pause_today(self.conn, datetime.now().strftime("%Y-%m-%d")):
            state = "오늘 자동정지"
        elif self.scheduler.paused:
            state = "일시정지"
        self.label_state.setText(f"상태: {state}")


    def refresh_all(self):
        self.refresh_logs()
        self.refresh_sounds()
        self.refresh_schedules()
        self.refresh_ops_sounds()
        self.scheduler.recompute_next()
        today = datetime.now().strftime("%Y-%m-%d")
        self.chk_pause_today.blockSignals(True)
        self.chk_pause_today.setChecked(repo.is_pause_today(self.conn, today))
        self.chk_pause_today.blockSignals(False)

    def refresh_ops_sounds(self):
        self.ops_sound_combo.clear()
        sounds = repo.list_sounds(self.conn)

        pick_index = 0
        for i, s in enumerate(sounds):
            name = str(s["name"])
            self.ops_sound_combo.addItem(name, int(s["id"]))
            if name.lower().startswith("bell"):
                pick_index = i

        if sounds:
            self.ops_sound_combo.setCurrentIndex(pick_index)

    def refresh_sounds(self):
        sounds = repo.list_sounds(self.conn)
        self.sound_table.setRowCount(len(sounds))
        for r, s in enumerate(sounds):
            self.sound_table.setItem(r, 0, QTableWidgetItem(str(s["id"])))
            self.sound_table.setItem(r, 1, QTableWidgetItem(str(s["name"])))
            self.sound_table.setItem(r, 2, QTableWidgetItem(str(s["file_name"])))
            self.sound_table.setItem(r, 3, QTableWidgetItem(str(s["volume"])))

    def refresh_schedules(self):
        schedules = repo.list_schedules(self.conn)
        day_bit = int(self.sch_day_filter.currentData() or 0)
        if day_bit != 0:
            schedules = [s for s in schedules if (int(s["weekday_mask"]) & day_bit) != 0]
        self.schedule_table.setRowCount(len(schedules))
        for r, s in enumerate(schedules):
            self.schedule_table.setItem(r, 0, QTableWidgetItem(str(s["id"])))
            self.schedule_table.setItem(r, 1, QTableWidgetItem("ON" if int(s["enabled"]) == 1 else "OFF"))
            self.schedule_table.setItem(r, 2, QTableWidgetItem(self._mask_to_days(s["weekday_mask"])))
            self.schedule_table.setItem(r, 3, QTableWidgetItem(str(s["time_hhmm"])))
            self.schedule_table.setItem(r, 4, QTableWidgetItem(str(s["name"])))
            self.schedule_table.setItem(r, 5, QTableWidgetItem(str(s["sound_name"])))
            v = s["volume_override"] if s["volume_override"] is not None else s["sound_volume"]
            self.schedule_table.setItem(r, 6, QTableWidgetItem(str(v)))
            self.schedule_table.setItem(r, 7, QTableWidgetItem(str(s["sort_order"])))

    def _selected_row_id(self, table):
        row = table.currentRow()
        if row < 0:
            return None
        item = table.item(row, 0)
        if not item:
            return None
        try:
            return int(item.text())
        except:
            return None

    def on_add_sound(self):
        dlg = AddSoundDialog(self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        name, src_path, volume = dlg.get_value()
        if not name or not src_path:
            QMessageBox.warning(self, "오류", "이름과 파일을 선택해 주세요.")
            return

        ext = Path(src_path).suffix.lower()
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        file_name = f"{stamp}{ext}"
        dst = sounds_dir() / file_name
        shutil.copy2(src_path, dst)

        repo.insert_sound(self.conn, name, file_name, volume)
        self.refresh_all()

    def on_edit_sound(self):
        sound_id = self._selected_row_id(self.sound_table)
        if not sound_id:
            return

        s = self.conn.execute("SELECT * FROM sounds WHERE id=?", (int(sound_id),)).fetchone()
        if not s:
            return

        dlg = EditSoundDialog(str(s["name"]), float(s["volume"]), self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return

        name, vol = dlg.get_value()
        if not name:
            QMessageBox.warning(self, "오류", "이름을 입력해 주세요.")
            return

        repo.update_sound(self.conn, sound_id, name, vol)
        self.scheduler.recompute_next()
        self.refresh_all()

    def on_delete_sound(self):
        sound_id = self._selected_row_id(self.sound_table)
        if not sound_id:
            return
        row = self.sound_table.currentRow()
        file_name = self.sound_table.item(row, 2).text()

        ok = QMessageBox.question(self, "확인", "삭제할까요?")
        if ok != QMessageBox.StandardButton.Yes:
            return

        repo.delete_sound(self.conn, sound_id)

        p = sound_file_path(file_name)
        if p.exists():
            try:
                p.unlink()
            except:
                pass

        self.refresh_all()
        repo.clear_transient_overrides(self.conn, self._today_str())
        self.scheduler.recompute_next()
        self.refresh_all()

    def on_add_schedule(self):
        sounds = repo.list_sounds(self.conn)
        if not sounds:
            QMessageBox.warning(self, "오류", "종소리를 먼저 추가해 주세요.")
            return
        dlg = ScheduleDialog(sounds, None, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        name, mask, t, sound_id, v_override, enabled, sort_order = dlg.get_value()
        if not name or mask == 0:
            QMessageBox.warning(self, "오류", "이벤트명과 요일을 설정해 주세요.")
            return
        repo.insert_schedule(self.conn, name, mask, t, sound_id, v_override, enabled, sort_order)
        self.refresh_all()
        repo.clear_transient_overrides(self.conn, self._today_str())
        self.scheduler.recompute_next()
        self.refresh_all()

    def on_edit_schedule(self):
        schedule_id = self._selected_row_id(self.schedule_table)
        if not schedule_id:
            return

        schedules = repo.list_schedules(self.conn)
        data = None
        for s in schedules:
            if int(s["id"]) == int(schedule_id):
                data = s
                break
        if not data:
            return

        sounds = repo.list_sounds(self.conn)
        dlg = ScheduleDialog(sounds, data, self)
        if dlg.exec() != dlg.DialogCode.Accepted:
            return
        name, mask, t, sound_id, v_override, enabled, sort_order = dlg.get_value()
        repo.update_schedule(self.conn, schedule_id, name, mask, t, sound_id, v_override, enabled, sort_order)
        self.refresh_all()
        repo.clear_transient_overrides(self.conn, self._today_str())
        self.scheduler.recompute_next()
        self.refresh_all()

    def on_delete_schedule(self):
        schedule_id = self._selected_row_id(self.schedule_table)
        if not schedule_id:
            return
        ok = QMessageBox.question(self, "확인", "삭제할까요?")
        if ok != QMessageBox.StandardButton.Yes:
            return
        repo.delete_schedule(self.conn, schedule_id)
        self.refresh_all()

    def on_ring_selected_sound(self):
        sid = self.ops_sound_combo.currentData()
        if sid is None:
            return
        s = self.conn.execute("SELECT * FROM sounds WHERE id=?", (int(sid),)).fetchone()
        if not s:
            return
        p = sound_file_path(str(s["file_name"]))
        try:
            self.player.play(str(p), float(s["volume"]))
        except Exception as e:
            QMessageBox.warning(self, "오류", str(e))

    def _build_logs(self):
        layout = QVBoxLayout(self.tab_logs)

        top = QHBoxLayout()

        self.log_range = QComboBox()
        self.log_range.addItems(["오늘", "7일", "30일", "전체", "직접"])
        top.addWidget(self.log_range)

        self.log_from = QDateEdit()
        self.log_from.setCalendarPopup(True)
        self.log_from.setDisplayFormat("yyyy-MM-dd")
        top.addWidget(self.log_from)

        self.log_to = QDateEdit()
        self.log_to.setCalendarPopup(True)
        self.log_to.setDisplayFormat("yyyy-MM-dd")
        top.addWidget(self.log_to)

        self.log_result = QComboBox()
        self.log_result.addItem("전체", "ALL")
        self.log_result.addItem("PLAYED", "PLAYED")
        self.log_result.addItem("SKIPPED", "SKIPPED")
        self.log_result.addItem("FAILED", "FAILED")
        top.addWidget(self.log_result)

        self.log_keyword = QLineEdit()
        self.log_keyword.setPlaceholderText("검색: 이벤트/종소리/상세")
        top.addWidget(self.log_keyword)

        self.log_limit = QSpinBox()
        self.log_limit.setRange(50, 5000)
        self.log_limit.setValue(500)
        top.addWidget(self.log_limit)

        self.btn_log_refresh = QPushButton("새로고침")
        top.addWidget(self.btn_log_refresh)

        layout.addLayout(top)

        self.log_table = QTableWidget()
        self.log_table.setColumnCount(6)
        self.log_table.setHorizontalHeaderLabels(["ID", "시간", "결과", "이벤트", "종소리", "상세"])
        self.log_table.setSelectionBehavior(self.log_table.SelectionBehavior.SelectRows)
        self.log_table.setEditTriggers(self.log_table.EditTrigger.NoEditTriggers)
        self.btn_log_refresh.setObjectName("Ghost")
        self.log_table.setAlternatingRowColors(True)
        self.log_table.horizontalHeader().setStretchLastSection(True)
        self.log_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.log_table.cellDoubleClicked.connect(self.on_log_detail)
        layout.addWidget(self.log_table)

        self.btn_log_refresh.clicked.connect(self.refresh_logs)
        self.log_range.currentIndexChanged.connect(self.refresh_logs)
        self.log_result.currentIndexChanged.connect(self.refresh_logs)
        self.log_limit.valueChanged.connect(self.refresh_logs)
        self.log_keyword.returnPressed.connect(self.refresh_logs)
        self.log_from.setDate(QDate.currentDate().addDays(-6))
        self.log_to.setDate(QDate.currentDate())
        self.log_from.setEnabled(False)
        self.log_to.setEnabled(False)

    def refresh_logs(self):
        mode = self.log_range.currentText()
        if mode == "직접":
            self.log_from.setEnabled(True)
            self.log_to.setEnabled(True)
        else:
            self.log_from.setEnabled(False)
            self.log_to.setEnabled(False)

        start_date, end_date = self._log_dates_from_range()
        result_value = self.log_result.currentData()
        keyword = self.log_keyword.text().strip()
        limit_count = self.log_limit.value()

        logs = repo.list_logs(self.conn, start_date, end_date, result_value, keyword, limit_count)

        self.log_table.setRowCount(len(logs))
        for r, l in enumerate(logs):
            self.log_table.setItem(r, 0, QTableWidgetItem(str(l["id"])))
            self.log_table.setItem(r, 1, QTableWidgetItem(str(l["occurred_at"])))
            self.log_table.setItem(r, 2, QTableWidgetItem(str(l["result"])))
            self.log_table.setItem(r, 3, QTableWidgetItem(str(l["schedule_name"] or "")))
            self.log_table.setItem(r, 4, QTableWidgetItem(str(l["sound_name"] or "")))
            self.log_table.setItem(r, 5, QTableWidgetItem(str(l["detail"] or "")))

    
    def _log_dates_from_range(self):
        today = QDate.currentDate()
        mode = self.log_range.currentText()

        if mode == "오늘":
            d1 = today
            d2 = today
            return d1.toString("yyyy-MM-dd"), d2.toString("yyyy-MM-dd")

        if mode == "7일":
            d1 = today.addDays(-6)
            d2 = today
            return d1.toString("yyyy-MM-dd"), d2.toString("yyyy-MM-dd")

        if mode == "30일":
            d1 = today.addDays(-29)
            d2 = today
            return d1.toString("yyyy-MM-dd"), d2.toString("yyyy-MM-dd")

        if mode == "전체":
            return "", ""

        self.log_from.setEnabled(True)
        self.log_to.setEnabled(True)
        return self.log_from.date().toString("yyyy-MM-dd"), self.log_to.date().toString("yyyy-MM-dd")

    def on_log_detail(self, row, col):
        id_item = self.log_table.item(row, 0)
        if not id_item:
            return

        log_id = id_item.text()
        log = self.conn.execute(
            "SELECT * FROM logs WHERE id=?",
            (log_id,)
        ).fetchone()

        if not log:
            return

        text = (
            f"시간: {log['occurred_at']}\n"
            f"결과: {log['result']}\n"
            f"이벤트: {log['schedule_name'] or '-'}\n"
            f"종소리: {log['sound_name'] or '-'}\n\n"
            f"상세:\n{log['detail'] or ''}"
        )

        QMessageBox.information(self, "로그 상세", text)

    def on_ring_next(self):
        self.scheduler.ring_next_now()

    def on_skip_next(self):
        self.scheduler.skip_next_once()

    def on_pause(self):
        self.scheduler.pause()

    def on_resume(self):
        self.scheduler.paused = False
        self.scheduler.recompute_next()
        self.refresh_all()

    def _init_window_icon(self):
        icon_path = asset_path("ui", "app.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _init_tray(self):
        icon_path = asset_path("ui", "app.ico")
        icon = QIcon(str(icon_path)) if icon_path.exists() else QIcon()

        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Mapl Tajong")

        menu = QMenu()

        act_show = QAction("열기", self)
        act_hide = QAction("숨기기", self)
        act_exit = QAction("종료", self)

        act_show.triggered.connect(self._tray_show)
        act_hide.triggered.connect(self._tray_hide)
        act_exit.triggered.connect(self.on_exit_app)

        menu.addAction(act_show)
        menu.addAction(act_hide)
        menu.addSeparator()
        menu.addAction(act_exit)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def _tray_show(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _tray_hide(self):
        self.hide()

    def closeEvent(self, event):
        if getattr(self, "_really_quit", False):
            event.accept()
            return

        self.hide()
        try:
            self.tray.showMessage(
                "마고수학학원 타종 프로그램",
                "트레이로 이동했습니다. 프로그램이 완전히 종료되지 않았습니다. (숨김)",
                QSystemTrayIcon.MessageIcon.Information,
                1200
            )
        except:
            pass
        event.ignore()

    def _tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            if self.isVisible():
                self.hide()
            else:
                self._tray_show()
    
    def _today_str(self):
        return datetime.now().strftime("%Y-%m-%d")
    
    def on_exit_app(self):
        from PyQt6.QtWidgets import QMessageBox

        ret = QMessageBox.question(
            self,
            "프로그램 종료",
            "프로그램을 완전히 종료할까요?\n(창 숨김을 원하신다면 오른쪽 상단 X버튼을 눌러주세요.)",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )

        if ret != QMessageBox.StandardButton.Yes:
            return

        try:
            self.scheduler.stop()
        except:
            pass

        try:
            self.tray.hide()
        except:
            pass

        self._really_quit = True
        self.app.quit()
    
    def on_toggle_startup(self, state):
        if self.chk_startup.isChecked():
            enable_startup()
        else:
            disable_startup()

    def _build_settings(self):
        layout = QVBoxLayout(self.tab_settings)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.chk_startup = QCheckBox("Windows 시작 시 자동 실행")
        self.chk_startup.setChecked(is_startup_enabled())
        self.chk_startup.stateChanged.connect(self.on_toggle_startup)

        layout.addWidget(self.chk_startup)
        layout.addStretch(1)

    def _build_topbar(self):
        self.menuBar().hide()

        tb = QToolBar()
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tb)

        holder = QWidget()
        lay = QHBoxLayout(holder)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(8)

        lay.addStretch(1)

        btn_exit = QPushButton("프로그램 종료")
        btn_exit.setObjectName("TopExit")
        btn_exit.clicked.connect(self.on_exit_app)
        lay.addWidget(btn_exit)

        tb.addWidget(holder)

        self._topbar = tb