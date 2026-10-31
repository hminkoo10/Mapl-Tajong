"""업데이트 기록: 프로그램에 함께 들어 있는 CHANGELOG.md 를 버전별로 보여 준다."""
import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from app.core.paths import resource_path
from app.core.version import APP_VERSION
from app.ui.dialogs import BaseDialog
from app.ui.theme import C
from app.ui.widgets import Pill


def _clean(text):
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    s = re.sub(r"`([^`]+)`", r"\1", s)
    return re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s).strip()


def parse_changelog(md):
    """[(버전, 날짜 또는 '', [항목...])] — 최신 버전이 먼저."""
    out = []
    cur = None
    for line in (md or "").splitlines():
        m = re.match(r"^##\s*\[?(\d+(?:\.\d+){1,3})\]?\s*(?:[-–—·(]\s*([^)]*)\)?)?\s*$", line.strip())
        if m:
            cur = (m.group(1), (m.group(2) or "").strip(), [])
            out.append(cur)
            continue
        if cur is None:
            continue
        s = line.strip()
        if re.match(r"^[-*]\s+", s):
            cur[2].append(_clean(re.sub(r"^[-*]\s+", "", s)))
        elif s and cur[2] and line.startswith(("  ", "\t")):
            cur[2][-1] += " " + _clean(s)
    return out


def load_changelog():
    p = resource_path("CHANGELOG.md")
    try:
        return parse_changelog(p.read_text(encoding="utf-8"))
    except OSError:
        return []


def notes_for(version):
    for v, _, items in load_changelog():
        if v == version:
            return items
    return []


class _Version(QWidget):
    def __init__(self, version, date, items, current=False, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 4, 0, 18)
        lay.setSpacing(8)
        head = QHBoxLayout()
        head.setSpacing(8)
        t = QLabel(f"버전 {version}")
        t.setStyleSheet(f"font-size: 17px; font-weight: 700; color: {C.grey900};")
        head.addWidget(t)
        if current:
            head.addWidget(Pill("지금 쓰는 버전", C.accent_text, C.accent_softer))
        head.addStretch(1)
        if date:
            d = QLabel(date)
            d.setStyleSheet(f"font-size: 13px; color: {C.grey500};")
            head.addWidget(d)
        lay.addLayout(head)
        for it in items or ["더 안정적으로 다듬었어요."]:
            row = QHBoxLayout()
            row.setSpacing(10)
            dot = QLabel("•")
            dot.setStyleSheet(f"font-size: 15px; color: {C.accent if current else C.grey400};")
            dot.setFixedWidth(10)
            row.addWidget(dot, 0, Qt.AlignmentFlag.AlignTop)
            txt = QLabel(it)
            txt.setWordWrap(True)
            txt.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            txt.setStyleSheet(f"font-size: 14.5px; color: {C.grey700}; line-height: 150%;")
            row.addWidget(txt, 1)
            lay.addLayout(row)


class ChangelogDialog(BaseDialog):
    def __init__(self, parent=None, only_version=None, title=None):
        entries = load_changelog()
        if only_version:
            entries = [e for e in entries if e[0] == only_version] or entries[:1]
        super().__init__(title or "업데이트 기록", "버전마다 무엇이 바뀌었는지 볼 수 있어요." if not only_version else "",
                         None, parent, 560)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        holder = QWidget()
        lay = QVBoxLayout(holder)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(0)
        if not entries:
            empty = QLabel("기록을 찾지 못했어요.")
            empty.setStyleSheet(f"color: {C.grey500}; font-size: 14px; padding: 30px;")
            lay.addWidget(empty)
        for i, (v, date, items) in enumerate(entries):
            if i:
                line = QWidget()
                line.setFixedHeight(1)
                line.setStyleSheet(f"background: {C.grey100};")
                lay.addWidget(line)
                lay.addSpacing(14)
            lay.addWidget(_Version(v, date, items, current=(v == APP_VERSION)))
        lay.addStretch(1)
        scroll.setWidget(holder)
        scroll.setMinimumHeight(220 if only_version else 420)
        self.body.addWidget(scroll, 1)
        self.btn_ok.setText("확인")
        self.btn_cancel.hide()
        self.resize(640, 420 if only_version else 640)
