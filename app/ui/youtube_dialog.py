"""YouTube에서 종소리 검색 → 오디오만 다운로드 → (편집 후) 종소리로 등록."""
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt, QTimer, QUrl, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QFont, QFontMetricsF, QPainter, QPainterPath, QPixmap
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QScrollArea, QSizePolicy,
                             QVBoxLayout, QWidget)

from app.core import ffmpeg, sound_files, youtube
from app.core.paths import download_tmp_dir
from app.ui import icons
from app.ui.dialogs import BaseDialog
from app.ui.sound_editor import SoundEditorDialog
from app.ui.theme import C, font, mix, qc
from app.ui.widgets import Button, ChipButton, Spinner, _anim, ease_out_cubic
from app.ui.workers import DownloadThread, ThumbThread, keep_alive, run_async

SUGGESTIONS = ["학교 종소리", "수업 시작종", "차임벨 효과음", "띵동댕동", "쉬는 시간 종", "알림음 효과음"]


def _dur(sec):
    if not sec:
        return "길이 정보 없음"
    sec = int(sec)
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class ResultCard(QWidget):
    clicked = pyqtSignal(object)
    doubleClicked = pyqtSignal(object)

    def __init__(self, data, delay=0.0, parent=None):
        super().__init__(parent)
        self.data = data
        self.thumb = None
        self.selected = False
        self._hover = 0.0
        self._k = 0.0
        self._ha = None
        self.setFixedHeight(92)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._ia = _anim(self, 0.0, 1.0, 420, self._set_k)
        QTimer.singleShot(int(delay * 1000), self._ia.start)

    def _set_k(self, v):
        self._k = float(v)
        self.update()

    def _set_h(self, v):
        self._hover = float(v)
        self.update()

    def set_thumb(self, pm):
        self.thumb = pm
        self.update()

    def set_selected(self, on):
        self.selected = on
        self.update()

    def enterEvent(self, e):
        self._ha = _anim(self, self._hover, 1.0, 160, self._set_h)
        self._ha.start()

    def leaveEvent(self, e):
        self._ha = _anim(self, self._hover, 0.0, 220, self._set_h)
        self._ha.start()

    def mousePressEvent(self, e):
        self.clicked.emit(self)

    def mouseDoubleClickEvent(self, e):
        self.doubleClicked.emit(self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        k = ease_out_cubic(self._k)
        p.setOpacity(k)
        p.translate(0, 8 * (1 - k))
        r = QRectF(self.rect()).adjusted(0, 2, 0, -2)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(C.accent_softer) if self.selected else mix("#00FFFFFF", C.grey50, self._hover))
        p.drawRoundedRect(r, 14, 14)

        th = QRectF(r.left() + 8, r.top() + 8, 124, r.height() - 16)
        path = QPainterPath()
        path.addRoundedRect(th, 9, 9)
        p.save()
        p.setClipPath(path)
        if self.thumb is not None and not self.thumb.isNull():
            pm = self.thumb.scaled(int(th.width() * 2), int(th.height() * 2), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                   Qt.TransformationMode.SmoothTransformation)
            sx = (pm.width() - th.width() * 2) / 2
            sy = (pm.height() - th.height() * 2) / 2
            p.drawPixmap(th, pm, QRectF(sx, sy, th.width() * 2, th.height() * 2))
        else:
            p.fillRect(th, qc(C.neutral_soft))
            p.drawPixmap(int(th.center().x() - 14), int(th.center().y() - 14), icons.pixmap("youtube", "#E0574B", 28))
        p.restore()
        d = _dur(self.data.get("duration"))
        p.setFont(font(11, QFont.Weight.Bold))
        dw = QFontMetricsF(p.font()).horizontalAdvance(d) + 10
        badge = QRectF(th.right() - dw - 4, th.bottom() - 20, dw, 16)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc("#000000", 0.7))
        p.drawRoundedRect(badge, 5, 5)
        p.setPen(qc("#FFFFFF"))
        p.drawText(badge, Qt.AlignmentFlag.AlignCenter, d)

        tx = th.right() + 14
        tw = r.right() - tx - 14
        p.setPen(qc(C.grey900))
        p.setFont(font(13.5, QFont.Weight.Bold))
        p.drawText(QRectF(tx, r.top() + 10, tw, 40), Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                   QFontMetricsF(p.font()).elidedText(self.data.get("title", ""), Qt.TextElideMode.ElideRight, tw * 1.9))
        meta = self.data.get("channel") or ""
        dur = self.data.get("duration")
        if dur and dur > 20 * 60:
            meta += "  ·  긴 영상"
        p.setPen(qc(C.grey500))
        p.setFont(font(12))
        p.drawText(QRectF(tx, r.bottom() - 28, tw, 20), Qt.AlignmentFlag.AlignVCenter, meta)
        if self.selected:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(qc(C.accent))
            p.drawEllipse(QRectF(r.right() - 30, r.center().y() - 10, 20, 20))
            p.drawPixmap(int(r.right() - 27), int(r.center().y() - 7), icons.pixmap("check", "#FFFFFF", 14))


class YoutubeDialog(BaseDialog):
    def __init__(self, ctx, parent=None):
        super().__init__("YouTube에서 종소리 찾기", "영상에서 소리만 받아 종소리로 만들어요.", None, parent, 760)
        self.ctx = ctx
        self.result_id = None
        self.cards = []
        self.selected = None
        self._thumbs = None
        self._dl = None
        self._search_seq = 0

        row = QHBoxLayout()
        row.setSpacing(8)
        self.query = QLineEdit()
        self.query.setPlaceholderText("검색어나 YouTube 주소를 입력하세요")
        self.query.addAction(icons.icon("search", C.grey500, 16), QLineEdit.ActionPosition.LeadingPosition)
        self.query.returnPressed.connect(self.search)
        self.btn_search = Button("검색", variant="primary")
        self.btn_search.clicked.connect(self.search)
        row.addWidget(self.query, 1)
        row.addWidget(self.btn_search)
        self.body.addLayout(row)

        chips = QHBoxLayout()
        chips.setSpacing(6)
        for s in SUGGESTIONS:
            c = ChipButton(s, checkable=False)
            c.clicked.connect(lambda _=False, q=s: (self.query.setText(q), self.search()))
            chips.addWidget(c)
        chips.addStretch(1)
        self.body.addLayout(chips)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setMinimumHeight(340)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.list_holder = QWidget()
        self.list_lay = QVBoxLayout(self.list_holder)
        self.list_lay.setContentsMargins(0, 0, 4, 0)
        self.list_lay.setSpacing(2)
        self.list_lay.addStretch(1)
        self.scroll.setWidget(self.list_holder)
        self.body.addWidget(self.scroll, 1)

        self.state = QWidget()
        sl = QHBoxLayout(self.state)
        sl.setContentsMargins(0, 0, 0, 0)
        self.spinner = Spinner(22)
        self.spinner.hide()
        self.state_label = QLabel("")
        self.state_label.setStyleSheet(f"color: {C.grey600};")
        sl.addWidget(self.spinner)
        sl.addWidget(self.state_label, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setFixedWidth(220)
        self.progress.hide()
        sl.addWidget(self.progress)
        self.btn_cancel_dl = Button("취소", variant="subtle", size="sm")
        self.btn_cancel_dl.hide()
        self.btn_cancel_dl.clicked.connect(self._cancel_download)
        sl.addWidget(self.btn_cancel_dl)
        self.body.addWidget(self.state)

        note = QLabel("저작권이 있는 소리는 허락된 범위에서만 써 주세요. 받은 소리는 이 컴퓨터에만 저장돼요.")
        note.setStyleSheet(f"color: {C.grey400}; font-size: 12.5px;")
        self.body.addWidget(note)

        self.btn_open = Button("미리 듣기", variant="subtle", size="lg")
        self.btn_open.setToolTip("받기 전에 브라우저에서 들어볼 수 있어요")
        self.btn_open.clicked.connect(self._open_in_browser)
        self.footer_left.addWidget(self.btn_open)
        self.btn_direct = Button("바로 추가", variant="secondary", size="lg")
        self.btn_direct.clicked.connect(lambda: self.download(edit=False))
        self.footer_left.addWidget(self.btn_direct)
        self.btn_ok.setText("받아서 다듬기")
        self.btn_cancel.setText("닫기")
        self._set_actions_enabled(False)

        self._empty("무엇을 찾을까요?\n위의 추천 검색어를 눌러도 돼요.")
        if not youtube.available():
            self._set_state("yt-dlp가 설치되어 있지 않아 YouTube 기능을 쓸 수 없어요.", error=True)
            self.btn_search.setEnabled(False)
        elif not ffmpeg.available():
            self._set_state("ffmpeg를 찾을 수 없어 소리를 변환할 수 없어요.", error=True)
        self.resize(820, 720)
        QTimer.singleShot(0, self.query.setFocus)

    # ---------------- 상태 ----------------
    def _set_state(self, text, busy=False, error=False):
        self.state_label.setText(text)
        self.state_label.setStyleSheet(f"color: {C.danger if error else C.grey600}; font-weight: {600 if error else 400};")
        self.spinner.setVisible(busy)

    def _set_actions_enabled(self, on):
        busy = self._dl is not None
        for b in (self.btn_ok, self.btn_direct, self.btn_open):
            b.setEnabled(on and not busy)

    def _clear(self):
        if self._thumbs:
            self._thumbs.stop()
            self._thumbs = None
        for c in self.cards:
            c.deleteLater()
        self.cards = []
        self.selected = None
        while self.list_lay.count() > 1:
            it = self.list_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._set_actions_enabled(False)

    def _empty(self, text):
        self._clear()
        lab = QLabel(text)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lab.setStyleSheet(f"color: {C.grey500}; font-size: 15px; padding: 70px 10px;")
        lab.setWordWrap(True)
        self.list_lay.insertWidget(0, lab)

    # ---------------- 검색 ----------------
    def search(self):
        q = self.query.text().strip()
        if not q or self._dl is not None:
            return
        self._search_seq += 1
        seq = self._search_seq
        self._empty("")
        self._set_state("찾고 있어요", busy=True)
        self.btn_search.setEnabled(False)
        fn = youtube.probe if youtube.looks_like_url(q) else youtube.search
        run_async(fn, q, on_done=lambda res: self._results(seq, res), on_fail=lambda m: self._search_failed(seq, m))

    def _search_failed(self, seq, msg):
        try:
            if seq != self._search_seq:
                return
            self.btn_search.setEnabled(True)
            self._empty("결과를 가져오지 못했어요")
            self._set_state(msg, error=True)
        except RuntimeError:
            pass

    def _results(self, seq, results):
        try:
            if seq != self._search_seq:
                return
        except RuntimeError:
            return
        self.btn_search.setEnabled(True)
        if not results:
            self._empty("찾는 영상이 없어요\n다른 말로 검색해 보세요")
            self._set_state("")
            return
        self._clear()
        for i, r in enumerate(results):
            c = ResultCard(r, delay=i * 0.045)
            c.clicked.connect(self._select)
            c.doubleClicked.connect(lambda card: (self._select(card), self.download(edit=True)))
            self.cards.append(c)
            self.list_lay.insertWidget(self.list_lay.count() - 1, c)
        self._set_state(f"{len(results)}개를 찾았어요")
        self._select(self.cards[0])
        self._thumbs = keep_alive(ThumbThread([(i, r.get("thumbnail")) for i, r in enumerate(results)]))
        self._thumbs.loaded.connect(self._thumb_loaded)
        self._thumbs.start()

    def _thumb_loaded(self, i, data):
        if 0 <= i < len(self.cards):
            pm = QPixmap()
            if pm.loadFromData(data):
                try:
                    self.cards[i].set_thumb(pm)
                except RuntimeError:
                    pass

    def _select(self, card):
        self.selected = card
        for c in self.cards:
            c.set_selected(c is card)
        self._set_actions_enabled(True)

    def _open_in_browser(self):
        if self.selected:
            QDesktopServices.openUrl(QUrl(self.selected.data["url"]))

    # ---------------- 다운로드 ----------------
    def _try_accept(self):
        self.download(edit=True)

    def download(self, edit=True):
        if not self.selected or self._dl is not None:
            return
        data = self.selected.data
        self._dl = DownloadThread(data["url"], download_tmp_dir())
        self._dl_edit = edit
        self._dl_title = data.get("title") or "YouTube 종소리"
        self._dl.progress.connect(self._dl_progress)
        self._dl.done.connect(self._dl_done)
        self._dl.failed.connect(self._dl_failed)
        self._dl.cancelled.connect(self._dl_cancelled)
        keep_alive(self._dl)
        self.progress.setValue(0)
        self.progress.show()
        self.btn_cancel_dl.show()
        self._set_state("받을 준비를 하고 있어요", busy=True)
        self._set_actions_enabled(False)
        self.btn_search.setEnabled(False)
        self._dl.start()

    def _dl_progress(self, frac, status):
        self.progress.setValue(int(frac * 1000))
        self._set_state(f"{status} {int(frac * 100)}%", busy=True)

    def _dl_reset(self):
        self._dl = None
        self.progress.hide()
        self.btn_cancel_dl.hide()
        self.btn_search.setEnabled(True)
        self._set_actions_enabled(self.selected is not None)

    def _dl_failed(self, msg):
        try:
            self._dl_reset()
            self._set_state(msg, error=True)
        except RuntimeError:
            pass

    def _dl_cancelled(self):
        try:
            self._dl_reset()
            self._set_state("받기를 취소했어요")
        except RuntimeError:
            pass

    def _cancel_download(self):
        if self._dl:
            self._dl.cancel()
            self._set_state("취소하고 있어요", busy=True)

    def _dl_done(self, path, title):
        try:
            self._dl_reset()
        except RuntimeError:
            return
        self._set_state("다 받았어요")
        name = title.strip()[:40] or "YouTube 종소리"
        src = Path(path)
        try:
            if self._dl_edit:
                ed = SoundEditorDialog(self.ctx, src, name, "new", None, self)
                if ed.exec() != QDialog.DialogCode.Accepted:
                    self._set_state("다듬기를 취소했어요")
                    return
                self.result_id = ed.result_id
            else:
                self.result_id = sound_files.add_sound_from_file(self.ctx.conn, src, name, 1.0)
        except Exception as e:
            self._set_state(f"추가하지 못했어요: {e}", error=True)
            return
        finally:
            try:
                src.unlink()
            except OSError:
                pass
        self.accept()

    def reject(self):
        if self._dl is not None:
            self._dl.cancel()
        if self._thumbs:
            self._thumbs.stop()
        super().reject()
