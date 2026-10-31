"""구글 로그인 창: 브라우저를 열어 두고 로그인이 끝나길 기다린다."""
import threading

from PyQt6.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout

from app.core import google_login
from app.ui.dialogs import BaseDialog
from app.ui.theme import C
from app.ui.widgets import Spinner
from app.ui.workers import run_async


class _Bridge(QObject):
    text = pyqtSignal(str)


class GoogleLoginDialog(BaseDialog):
    def __init__(self, parent=None):
        super().__init__("구글 로그인", "YouTube에서 종소리를 받을 때 쓸 구글 계정으로 로그인해요.", None, parent, 460)
        self._cancel = threading.Event()
        self._done = False
        self._bridge = _Bridge(self)
        self._bridge.text.connect(self._set_status)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.spinner = Spinner(24)
        row.addWidget(self.spinner, 0, Qt.AlignmentFlag.AlignVCenter)
        self.status = QLabel("브라우저를 여는 중이에요")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {C.grey900};")
        row.addWidget(self.status, 1)
        self.body.addLayout(row)

        notes = QVBoxLayout()
        notes.setSpacing(6)
        for t in ("로그인을 마치면 브라우저 창이 저절로 닫혀요.",
                  "평소 쓰는 브라우저와는 따로 열리는 창이에요.",
                  "자주 쓰지 않는 구글 계정을 써도 괜찮아요.",
                  "로그인 정보는 이 컴퓨터에만 저장하고 다른 곳으로 보내지 않아요."):
            lab = QLabel("· " + t)
            lab.setWordWrap(True)
            lab.setStyleSheet(f"font-size: 13.5px; color: {C.grey600};")
            notes.addWidget(lab)
        self.body.addLayout(notes)

        self.btn_ok.hide()
        self.btn_cancel.setText("취소")
        QTimer.singleShot(150, self._start)

    def _start(self):
        found = google_login.find_browser()
        if not found:
            self.spinner.hide()
            self.status.setText("Chrome이나 Edge를 찾지 못했어요")
            self.show_error("둘 중 하나를 설치한 뒤 다시 해 주세요.")
            return
        self.status.setText(f"{found[0]} 창에서 구글 계정으로 로그인해 주세요")
        run_async(google_login.run_login, self._cancel, self._bridge.text.emit, 900, found,
                  on_done=self._ok, on_fail=self._fail)

    def _set_status(self, text):
        try:
            self.status.setText(text)
        except RuntimeError:
            pass

    def _ok(self, _n):
        self._done = True
        try:
            self.spinner.hide()
            self.status.setText("로그인했어요")
            QTimer.singleShot(500, self.accept)
        except RuntimeError:
            pass

    def _fail(self, msg):
        try:
            if self._cancel.is_set():
                return
            self.spinner.hide()
            self.status.setText("로그인하지 못했어요")
            self.show_error(msg)
            self.btn_cancel.setText("닫기")
        except RuntimeError:
            pass

    def reject(self):
        self._cancel.set()
        super().reject()


def login(parent):
    """로그인 창을 띄우고 성공 여부를 돌려준다."""
    from PyQt6.QtWidgets import QDialog
    return GoogleLoginDialog(parent).exec() == QDialog.DialogCode.Accepted
