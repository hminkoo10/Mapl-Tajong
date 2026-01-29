from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFileDialog,
    QCheckBox, QSpinBox, QComboBox, QWidget
)
from pathlib import Path

WEEKDAYS = [
    ("월", 1), ("화", 2), ("수", 4), ("목", 8), ("금", 16), ("토", 32), ("일", 64)
]

def weekday_mask_from_checks(checks):
    mask = 0
    for cb, bit in checks:
        if cb.isChecked():
            mask |= bit
    return mask

def set_checks_from_mask(checks, mask):
    for cb, bit in checks:
        cb.setChecked((mask & bit) != 0)

class AddSoundDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("종소리 추가")
        self.selected_path = None

        root = QVBoxLayout(self)

        self.name_edit = QLineEdit()
        root.addWidget(QLabel("이름"))
        root.addWidget(self.name_edit)

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(True)
        btn = QPushButton("파일 선택")
        btn.clicked.connect(self.pick_file)
        row.addWidget(self.path_edit)
        row.addWidget(btn)
        root.addWidget(QLabel("파일"))
        root.addLayout(row)

        self.vol = QSpinBox()
        self.vol.setRange(0, 200)
        self.vol.setSingleStep(5)
        self.vol.setValue(100)
        self.vol.setSuffix("%")
        root.addWidget(QLabel("기본 음량"))
        root.addWidget(self.vol)

        actions = QHBoxLayout()
        ok = QPushButton("추가")
        cancel = QPushButton("취소")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        actions.addWidget(ok)
        actions.addWidget(cancel)
        root.addLayout(actions)

    def pick_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "종소리 파일 선택", "", "Audio Files (*.wav *.mp3)")
        if path:
            self.selected_path = path
            self.path_edit.setText(path)
            if not self.name_edit.text().strip():
                self.name_edit.setText(Path(path).stem)

    def get_value(self):
        name = self.name_edit.text().strip()
        return name, self.selected_path, int(self.vol.value())

class ScheduleDialog(QDialog):
    def __init__(self, sounds, data=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("스케줄")
        self.sounds = sounds

        root = QVBoxLayout(self)

        self.name_edit = QLineEdit()
        root.addWidget(QLabel("이벤트명"))
        root.addWidget(self.name_edit)

        wrow = QHBoxLayout()
        wwrap = QWidget()
        wlayout = QHBoxLayout(wwrap)
        wlayout.setContentsMargins(0, 0, 0, 0)
        self.day_checks = []
        for label, bit in WEEKDAYS:
            cb = QCheckBox(label)
            self.day_checks.append((cb, bit))
            wlayout.addWidget(cb)
        wrow.addWidget(wwrap)
        root.addWidget(QLabel("요일"))
        root.addLayout(wrow)

        root.addWidget(QLabel("시간"))
        trow = QHBoxLayout()

        self.hour_spin = QSpinBox()
        self.hour_spin.setRange(0, 23)
        self.hour_spin.setFixedWidth(90)

        self.min_spin = QSpinBox()
        self.min_spin.setRange(0, 59)
        self.min_spin.setFixedWidth(90)
        self.min_spin.setSingleStep(5)

        trow.addWidget(self.hour_spin)
        trow.addWidget(QLabel(":"))
        trow.addWidget(self.min_spin)
        trow.addStretch(1)
        root.addLayout(trow)

        self.hour_spin.setValue(9)
        self.min_spin.setValue(0)

        self.sound_combo = QComboBox()
        for s in sounds:
            self.sound_combo.addItem(f'{s["name"]}', int(s["id"]))
        root.addWidget(QLabel("종소리"))
        root.addWidget(self.sound_combo)

        self.vol_override = QSpinBox()
        self.vol_override.setRange(0, 200)
        self.vol_override.setSingleStep(5)
        self.vol_override.setSpecialValueText("기본값 사용")
        self.vol_override.setValue(0)
        self.vol_override.setSuffix("%")
        root.addWidget(QLabel("이벤트 음량(선택)"))
        root.addWidget(self.vol_override)

        self.enabled = QCheckBox("활성")
        self.enabled.setChecked(True)
        root.addWidget(self.enabled)

        actions = QHBoxLayout()
        ok = QPushButton("저장")
        cancel = QPushButton("취소")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.reject)
        actions.addWidget(ok)
        actions.addWidget(cancel)
        root.addLayout(actions)

        if data:
            self.name_edit.setText(str(data["name"]))
            set_checks_from_mask(self.day_checks, int(data["weekday_mask"]))
            hh, mm = str(data["time_hhmm"]).split(":")
            self.hour_spin.setValue(int(hh))
            self.min_spin.setValue(int(mm))
            self.enabled.setChecked(int(data["enabled"]) == 1)

            sid = int(data["sound_id"])
            idx = self.sound_combo.findData(sid)
            if idx >= 0:
                self.sound_combo.setCurrentIndex(idx)

            if data["volume_override"] is None:
                self.vol_override.setValue(0)
            else:
                self.vol_override.setValue(int(float(data["volume_override"]) * 100))

    def get_value(self):
        name = self.name_edit.text().strip()
        mask = weekday_mask_from_checks(self.day_checks)
        t = f"{int(self.hour_spin.value()):02d}:{int(self.min_spin.value()):02d}"
        sound_id = self.sound_combo.currentData()
        enabled = 1 if self.enabled.isChecked() else 0

        v = int(self.vol_override.value())
        volume_override = None if v == 0 else (v / 100.0)

        return name, mask, t, sound_id, volume_override, enabled

class EditSoundDialog(QDialog):
    def __init__(self, name, volume, parent=None):
        super().__init__(parent)
        self.setWindowTitle("종소리 수정")

        layout = QVBoxLayout(self)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("이름"))
        self.name_edit = QLineEdit()
        self.name_edit.setText(name)
        row1.addWidget(self.name_edit)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("음량"))
        self.vol = QSpinBox()
        self.vol.setRange(0, 200)
        self.vol.setSingleStep(5)
        self.vol.setSuffix("%")
        try:
            self.vol.setValue(int(float(volume) * 100))
        except:
            self.vol.setValue(100)
        row2.addWidget(self.vol)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        btn_ok = QPushButton("저장")
        btn_cancel = QPushButton("취소")
        row3.addWidget(btn_ok)
        row3.addWidget(btn_cancel)
        layout.addLayout(row3)

        btn_ok.clicked.connect(self.accept)
        btn_cancel.clicked.connect(self.reject)

    def get_value(self):
        return self.name_edit.text().strip(), (int(self.vol.value()) / 100.0)