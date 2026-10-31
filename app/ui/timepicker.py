"""알기 쉬운 시각 고르기: [오전|오후]  [ 2 ] : [ 40 ]

- 오전/오후는 눌러서 바꾼다.
- 시·분 칸은 클릭한 뒤 숫자를 바로 치거나(14 처럼 24시간으로 쳐도 된다), 위/아래 화살표·마우스 휠로 바꾼다.
- 칸 오른쪽의 ▲▼ 를 눌러도 된다. 길게 누르면 계속 바뀐다.
"""
from PyQt6.QtCore import QPointF, QRectF, Qt, QTime, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QWidget

from app.ui.theme import C, font, mix, qc
from app.ui.widgets import _anim, ease_out_cubic

SEG_W = 76     # 오전/오후 한 칸
BOX_W = 74     # 시·분 칸
COLON_W = 18
GAP = 10
H = 48


class TimePicker(QWidget):
    timeChanged = pyqtSignal(QTime)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFixedSize(SEG_W * 2 + GAP * 2 + BOX_W * 2 + COLON_W, H)
        self._h = 9
        self._m = 0
        self._seg = 0            # 0: 시, 1: 분
        self._typed = ""
        self._hover = None       # ("ampm", 0|1) / ("box", 0|1, part)
        self._pm_k = 0.0          # 오전(0) ↔ 오후(1) 표시 위치
        self._pm_anim = None
        self._roll = [0.0, 0.0]   # 숫자가 바뀔 때 살짝 굴러가는 효과 (-1 ~ 1)
        self._roll_dir = [0, 0]
        self._roll_anim = [None, None]
        self._repeat = QTimer(self)
        self._repeat.setInterval(90)
        self._repeat.timeout.connect(self._on_repeat)
        self._repeat_delay = QTimer(self)
        self._repeat_delay.setSingleShot(True)
        self._repeat_delay.setInterval(380)
        self._repeat_delay.timeout.connect(self._repeat.start)
        self._repeat_step = None

    # ---------- 값 ----------
    def time(self):
        return QTime(self._h, self._m)

    def setTime(self, t: QTime):
        if not t.isValid():
            return
        self._set(t.hour(), t.minute(), animate=False)

    def _set(self, h, m, animate=True, emit=True):
        h, m = int(h) % 24, int(m) % 60
        if (h, m) == (self._h, self._m):
            return
        old_pm = self._h >= 12
        dh = (h - self._h) % 24
        dm = (m - self._m) % 60
        if animate:
            if h != self._h:
                self._kick_roll(0, 1 if dh <= 12 else -1)
            if m != self._m:
                self._kick_roll(1, 1 if dm <= 30 else -1)
        self._h, self._m = h, m
        new_pm = h >= 12
        if new_pm != old_pm or not animate:
            self._animate_pm(1.0 if new_pm else 0.0, animate)
        self.update()
        if emit:
            self.timeChanged.emit(self.time())

    def add_minutes(self, n):
        total = (self._h * 60 + self._m + int(n)) % (24 * 60)
        self._set(total // 60, total % 60)

    # ---------- 애니메이션 ----------
    def _animate_pm(self, target, animate=True):
        if self._pm_anim:
            self._pm_anim.stop()
        if not animate:
            self._pm_k = target
            return
        self._pm_anim = _anim(self, self._pm_k, target, 220, self._set_pm_k)
        self._pm_anim.start()

    def _set_pm_k(self, v):
        self._pm_k = float(v)
        self.update()

    def _kick_roll(self, i, direction):
        self._roll_dir[i] = direction
        if self._roll_anim[i]:
            self._roll_anim[i].stop()

        def setter(v, i=i):
            self._roll[i] = float(v)
            self.update()
        self._roll_anim[i] = _anim(self, 1.0, 0.0, 180, setter)
        self._roll_anim[i].start()

    # ---------- 위치 ----------
    def _ampm_rect(self, i):
        return QRectF(1 + i * SEG_W, 1, SEG_W - (2 if i else 0), H - 2)

    def _box_rect(self, i):
        x = SEG_W * 2 + GAP * 2 + i * (BOX_W + COLON_W)
        return QRectF(x, 0.5, BOX_W, H - 1)

    def _hit(self, pos):
        for i in (0, 1):
            if self._ampm_rect(i).contains(pos):
                return ("ampm", i)
        for i in (0, 1):
            r = self._box_rect(i)
            if r.contains(pos):
                if pos.x() > r.right() - 24:
                    return ("box", i, "up" if pos.y() < r.center().y() else "down")
                return ("box", i, "text")
        return None

    # ---------- 입력 ----------
    def _change(self, seg, step):
        if seg == 0:
            self._set((self._h + step) % 24, self._m)
        else:
            self._set(self._h, (self._m + step) % 60)

    def _on_repeat(self):
        if self._repeat_step:
            self._change(*self._repeat_step)

    def mouseMoveEvent(self, e):
        hit = self._hit(e.position())
        if hit != self._hover:
            self._hover = hit
            self.setCursor(Qt.CursorShape.PointingHandCursor if hit else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover = None
        self.update()
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        hit = self._hit(e.position())
        if not hit:
            return
        if hit[0] == "ampm":
            want_pm = hit[1] == 1
            if want_pm != (self._h >= 12):
                self._set((self._h + 12) % 24, self._m)
            return
        _, i, part = hit
        self._seg = i
        self._typed = ""
        if part in ("up", "down"):
            step = 1 if part == "up" else -1
            if i == 1:
                step *= 1
            self._change(i, step)
            self._repeat_step = (i, step)
            self._repeat_delay.start()
        self.update()

    def mouseReleaseEvent(self, e):
        self._repeat_delay.stop()
        self._repeat.stop()
        self._repeat_step = None

    def wheelEvent(self, e):
        hit = self._hit(e.position())
        seg = hit[1] if hit and hit[0] == "box" else self._seg
        step = 1 if e.angleDelta().y() > 0 else -1
        if hit and hit[0] == "ampm":
            self._set((self._h + 12) % 24, self._m)
        else:
            self._change(seg, step)
        e.accept()

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            self._typed = ""
            self._change(self._seg, 1 if k == Qt.Key.Key_Up else -1)
            return
        if k in (Qt.Key.Key_PageUp, Qt.Key.Key_PageDown):
            self._typed = ""
            self.add_minutes(10 if k == Qt.Key.Key_PageUp else -10)
            return
        if k == Qt.Key.Key_Left or (k == Qt.Key.Key_Backtab and self._seg == 1):
            self._seg, self._typed = 0, ""
            self.update()
            return
        if k == Qt.Key.Key_Right or (k == Qt.Key.Key_Tab and self._seg == 0):
            self._seg, self._typed = 1, ""
            self.update()
            return
        text = e.text()
        if text and text.lower() in ("a", "ㅁ"):
            if self._h >= 12:
                self._set(self._h - 12, self._m)
            return
        if text and text.lower() in ("p", "ㅔ"):
            if self._h < 12:
                self._set(self._h + 12, self._m)
            return
        if text and text.isdigit():
            self._type_digit(text)
            return
        if k == Qt.Key.Key_Backspace:
            self._typed = self._typed[:-1]
            return
        super().keyPressEvent(e)

    def _type_digit(self, d):
        self._typed += d
        v = int(self._typed)
        if self._seg == 0:
            pm = self._h >= 12
            if len(self._typed) == 1:
                # 한 자리: 지금의 오전/오후를 지키며 그 시로 (0은 12시)
                h12 = v if v else 12
                h = (h12 % 12) + (12 if pm else 0)
                self._set(h, self._m)
                if v >= 3:      # 3~9 로 시작하는 두 자리 시는 없다 → 바로 분으로
                    self._seg, self._typed = 1, ""
            else:
                if v <= 23:
                    if v >= 13 or self._typed.startswith("0"):
                        h = v                      # 24시간으로 친 경우 (08, 14 …)
                    else:
                        h = (v % 12) + (12 if pm else 0)
                    self._set(h, self._m)
                self._seg, self._typed = 1, ""
        else:
            if len(self._typed) == 1:
                self._set(self._h, v)
                if v >= 6:
                    self._typed = ""
            else:
                if v <= 59:
                    self._set(self._h, v)
                self._typed = ""
        self.update()

    def focusInEvent(self, e):
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        super().focusOutEvent(e)
        self._typed = ""
        self.update()

    # ---------- 그리기 ----------
    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on_page = bool(self.property("page"))
        fill = "#FFFFFF" if on_page else C.grey100

        # 오전/오후
        track = QRectF(0.5, 0.5, SEG_W * 2, H - 1)
        p.setPen(QPen(qc(C.grey200), 1) if on_page else Qt.PenStyle.NoPen)
        p.setBrush(qc(fill))
        p.drawRoundedRect(track, 12, 12)
        k = ease_out_cubic(self._pm_k) if 0 < self._pm_k < 1 else self._pm_k
        thumb = QRectF(4 + k * (SEG_W - 4), 4, SEG_W - 4, H - 8)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(C.accent))
        p.drawRoundedRect(thumb, 9, 9)
        for i, label in enumerate(("오전", "오후")):
            r = self._ampm_rect(i)
            active = abs(self._pm_k - i) < 0.5
            hov = self._hover == ("ampm", i) and not active
            p.setPen(qc("#FFFFFF") if active else qc(C.grey800 if hov else C.grey600))
            p.setFont(font(15, QFont.Weight.Bold if active else QFont.Weight.DemiBold))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, label)

        # 시 : 분
        values = (str(self._h % 12 or 12), f"{self._m:02d}")
        for i in (0, 1):
            r = self._box_rect(i)
            focused = self.hasFocus() and self._seg == i
            hov = isinstance(self._hover, tuple) and self._hover[0] == "box" and self._hover[1] == i
            bg = fill if not hov or focused else mix(fill, C.grey200, 0.5)
            p.setPen(QPen(qc(C.accent), 1.5) if focused else (QPen(qc(C.grey200), 1) if on_page else Qt.PenStyle.NoPen))
            p.setBrush(qc("#FFFFFF" if focused else bg))
            p.drawRoundedRect(r, 12, 12)

            # 숫자 (바뀔 때 살짝 굴러감)
            clip = QPainterPath()
            clip.addRoundedRect(r, 12, 12)
            p.save()
            p.setClipPath(clip)
            roll = self._roll[i] * self._roll_dir[i]
            p.translate(0, roll * 14)
            p.setOpacity(1 - abs(self._roll[i]) * 0.6)
            p.setPen(qc(C.grey900))
            p.setFont(font(22, QFont.Weight.Bold))
            tr = QRectF(r.left(), r.top(), r.width() - 20, r.height())
            p.drawText(tr, Qt.AlignmentFlag.AlignCenter, values[i])
            if focused and self._typed:
                fm = QFontMetricsF(p.font())
                tw = fm.horizontalAdvance(values[i])
                p.setPen(QPen(qc(C.accent), 2))
                y = r.center().y() + 14
                p.drawLine(QPointF(tr.center().x() - tw / 2, y), QPointF(tr.center().x() + tw / 2, y))
            p.restore()

            # ▲▼
            ax = r.right() - 14
            for part, cy, d in (("up", r.center().y() - 8, -1), ("down", r.center().y() + 8, 1)):
                act = self._hover == ("box", i, part)
                col = C.accent if act else (C.grey500 if hov or focused else C.grey400)
                p.setPen(QPen(qc(col), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                p.drawPolyline([QPointF(ax - 4, cy - d * 2), QPointF(ax, cy + d * 2), QPointF(ax + 4, cy - d * 2)])

        # 가운데 쌍점
        cx = self._box_rect(0).right() + COLON_W / 2
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(qc(C.grey500))
        p.drawEllipse(QPointF(cx, H / 2 - 6), 2.4, 2.4)
        p.drawEllipse(QPointF(cx, H / 2 + 6), 2.4, 2.4)
