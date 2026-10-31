"""코드로 그리는 라인 아이콘 세트 (24x24 그리드)."""
from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap


def _pen(p, color, w=2.0):
    p.setPen(QPen(QColor(color), w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)


def _fill(p, color):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(QColor(color)))


def _line(p, *pts):
    p.drawPolyline([QPointF(x, y) for x, y in pts])


def _draw(name, p, color):
    _pen(p, color)
    if name == "dashboard":
        for x, y in ((3.5, 3.5), (13, 3.5), (3.5, 13), (13, 13)):
            p.drawRoundedRect(QRectF(x, y, 7.5, 7.5), 2.2, 2.2)
    elif name == "calendar":
        p.drawRoundedRect(QRectF(3.5, 5, 17, 15.5), 3, 3)
        _line(p, (3.5, 10), (20.5, 10))
        _line(p, (8, 3), (8, 6.5))
        _line(p, (16, 3), (16, 6.5))
        _fill(p, color)
        for x, y in ((8, 14), (12, 14), (16, 14), (8, 17.2), (12, 17.2)):
            p.drawEllipse(QPointF(x, y), 1.1, 1.1)
    elif name == "bell":
        path = QPainterPath()
        path.moveTo(12, 3.2)
        path.cubicTo(8.4, 3.2, 6.2, 6, 6.2, 9.4)
        path.lineTo(6.2, 13.2)
        path.lineTo(4.4, 16.6)
        path.lineTo(19.6, 16.6)
        path.lineTo(17.8, 13.2)
        path.lineTo(17.8, 9.4)
        path.cubicTo(17.8, 6, 15.6, 3.2, 12, 3.2)
        p.drawPath(path)
        clap = QPainterPath()
        clap.moveTo(9.6, 19.2)
        clap.quadTo(12, 21.8, 14.4, 19.2)
        p.drawPath(clap)
    elif name == "logs":
        for y in (6.5, 12, 17.5):
            _line(p, (9, y), (20, y))
        _fill(p, color)
        for y in (6.5, 12, 17.5):
            p.drawEllipse(QPointF(4.6, y), 1.4, 1.4)
    elif name == "settings":
        _line(p, (4, 7), (20, 7))
        _line(p, (4, 17), (20, 17))
        _fill(p, "#FFFFFF")
        p.setPen(QPen(QColor(color), 2))
        p.drawEllipse(QPointF(9, 7), 2.6, 2.6)
        p.drawEllipse(QPointF(15, 17), 2.6, 2.6)
    elif name == "play":
        _fill(p, color)
        path = QPainterPath()
        path.moveTo(8, 5.2)
        path.lineTo(18.6, 12)
        path.lineTo(8, 18.8)
        path.closeSubpath()
        p.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(path)
    elif name == "stop":
        _fill(p, color)
        p.drawRoundedRect(QRectF(6.5, 6.5, 11, 11), 2.4, 2.4)
    elif name == "pause":
        _fill(p, color)
        p.drawRoundedRect(QRectF(6.8, 5.5, 3.6, 13), 1.2, 1.2)
        p.drawRoundedRect(QRectF(13.6, 5.5, 3.6, 13), 1.2, 1.2)
    elif name == "skip":
        _fill(p, color)
        path = QPainterPath()
        path.moveTo(5.5, 6)
        path.lineTo(14, 12)
        path.lineTo(5.5, 18)
        path.closeSubpath()
        p.drawPath(path)
        p.drawRoundedRect(QRectF(15.6, 6, 2.8, 12), 1, 1)
    elif name == "ring":  # 종 + 울림
        _draw("bell", p, color)
        _pen(p, color, 1.8)
        p.drawArc(QRectF(0.6, 4, 5, 9), 110 * 16, 140 * 16)
        p.drawArc(QRectF(18.4, 4, 5, 9), -70 * 16, 140 * 16)
    elif name == "plus":
        _line(p, (12, 5), (12, 19))
        _line(p, (5, 12), (19, 12))
    elif name == "edit":
        path = QPainterPath()
        path.moveTo(14.8, 5.2)
        path.lineTo(18.8, 9.2)
        path.lineTo(9, 19)
        path.lineTo(4.6, 19.4)
        path.lineTo(5, 15)
        path.closeSubpath()
        p.drawPath(path)
        _line(p, (12.6, 7.4), (16.6, 11.4))
    elif name == "batch":  # 여러 줄 + 체크
        _line(p, (11, 6.5), (20, 6.5))
        _line(p, (11, 12), (20, 12))
        _line(p, (11, 17.5), (20, 17.5))
        _line(p, (3.5, 6.5), (5, 8), (7.6, 5))
        _line(p, (3.5, 12), (5, 13.5), (7.6, 10.5))
        _line(p, (3.5, 17.5), (5, 19), (7.6, 16))
    elif name == "trash":
        _line(p, (4, 7), (20, 7))
        _line(p, (9, 7), (9.6, 4.4), (14.4, 4.4), (15, 7))
        path = QPainterPath()
        path.moveTo(6.2, 7)
        path.lineTo(7.2, 19.6)
        path.lineTo(16.8, 19.6)
        path.lineTo(17.8, 7)
        p.drawPath(path)
        _line(p, (10.2, 10.5), (10.4, 16.4))
        _line(p, (13.8, 10.5), (13.6, 16.4))
    elif name == "search":
        p.drawEllipse(QPointF(10.5, 10.5), 6, 6)
        _line(p, (15, 15), (20, 20))
    elif name == "download":
        _line(p, (12, 4), (12, 15))
        _line(p, (7.5, 10.5), (12, 15), (16.5, 10.5))
        _line(p, (4.5, 16.5), (4.5, 19.5), (19.5, 19.5), (19.5, 16.5))
    elif name == "upload":
        _line(p, (12, 15), (12, 4))
        _line(p, (7.5, 8.5), (12, 4), (16.5, 8.5))
        _line(p, (4.5, 16.5), (4.5, 19.5), (19.5, 19.5), (19.5, 16.5))
    elif name == "youtube":
        _fill(p, color)
        p.drawRoundedRect(QRectF(2.5, 5.5, 19, 13), 4.2, 4.2)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
        _fill(p, "#000000")
        path = QPainterPath()
        path.moveTo(10, 9)
        path.lineTo(15.2, 12)
        path.lineTo(10, 15)
        path.closeSubpath()
        p.drawPath(path)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    elif name == "wave":
        for x, h in ((4, 4), (8, 10), (12, 16), (16, 9), (20, 5)):
            _line(p, (x, 12 - h / 2), (x, 12 + h / 2))
    elif name == "scissors":
        p.drawEllipse(QPointF(6.5, 17.5), 2.6, 2.6)
        p.drawEllipse(QPointF(17.5, 17.5), 2.6, 2.6)
        _line(p, (8.4, 15.6), (18, 4.5))
        _line(p, (15.6, 15.6), (6, 4.5))
    elif name == "copy":
        p.drawRoundedRect(QRectF(8.5, 8.5, 11.5, 11.5), 2.5, 2.5)
        path = QPainterPath()
        path.moveTo(15.5, 8.5)
        path.lineTo(15.5, 6.5)
        path.quadTo(15.5, 4, 13, 4)
        path.lineTo(6.5, 4)
        path.quadTo(4, 4, 4, 6.5)
        path.lineTo(4, 13)
        path.quadTo(4, 15.5, 6.5, 15.5)
        path.lineTo(8.5, 15.5)
        p.drawPath(path)
    elif name == "fullscreen":
        _line(p, (4, 9), (4, 4), (9, 4))
        _line(p, (15, 4), (20, 4), (20, 9))
        _line(p, (20, 15), (20, 20), (15, 20))
        _line(p, (9, 20), (4, 20), (4, 15))
    elif name == "power":
        p.drawArc(QRectF(4.5, 5, 15, 15), 125 * 16, -250 * 16)
        _line(p, (12, 3.5), (12, 11))
    elif name == "check":
        _line(p, (5, 12.5), (10, 17), (19, 7.5))
    elif name == "x":
        _line(p, (6.5, 6.5), (17.5, 17.5))
        _line(p, (17.5, 6.5), (6.5, 17.5))
    elif name == "folder":
        path = QPainterPath()
        path.moveTo(3.5, 7)
        path.quadTo(3.5, 5, 5.5, 5)
        path.lineTo(9.5, 5)
        path.lineTo(11.5, 7.2)
        path.lineTo(18.5, 7.2)
        path.quadTo(20.5, 7.2, 20.5, 9.2)
        path.lineTo(20.5, 17.5)
        path.quadTo(20.5, 19.5, 18.5, 19.5)
        path.lineTo(5.5, 19.5)
        path.quadTo(3.5, 19.5, 3.5, 17.5)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "clock":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        _line(p, (12, 7.5), (12, 12), (15.2, 14))
    elif name == "music":
        p.drawEllipse(QPointF(7.5, 17), 2.5, 2.2)
        p.drawEllipse(QPointF(17, 15), 2.5, 2.2)
        _line(p, (10, 17), (10, 6), (19.5, 4), (19.5, 15))
    elif name == "volume":
        path = QPainterPath()
        path.moveTo(4, 9.5)
        path.lineTo(7.5, 9.5)
        path.lineTo(12, 5.5)
        path.lineTo(12, 18.5)
        path.lineTo(7.5, 14.5)
        path.lineTo(4, 14.5)
        path.closeSubpath()
        p.drawPath(path)
        p.drawArc(QRectF(11, 8, 6, 8), -60 * 16, 120 * 16)
        p.drawArc(QRectF(11, 5, 10, 14), -60 * 16, 120 * 16)
    elif name == "more":
        _fill(p, color)
        for x in (6, 12, 18):
            p.drawEllipse(QPointF(x, 12), 1.7, 1.7)
    elif name == "layers":
        path = QPainterPath()
        path.moveTo(12, 4)
        path.lineTo(20.5, 8.5)
        path.lineTo(12, 13)
        path.lineTo(3.5, 8.5)
        path.closeSubpath()
        p.drawPath(path)
        _line(p, (3.5, 12.5), (12, 17), (20.5, 12.5))
        _line(p, (3.5, 16), (12, 20.5), (20.5, 16))
    elif name == "export":
        _line(p, (12, 14), (12, 3.5))
        _line(p, (8, 7.5), (12, 3.5), (16, 7.5))
        p.drawRoundedRect(QRectF(4.5, 10, 15, 10.5), 2.5, 2.5)
    elif name == "restore":
        p.drawArc(QRectF(4, 4, 16, 16), 90 * 16, 270 * 16)
        _line(p, (12, 4), (8.6, 1.8))
        _line(p, (12, 4), (8.8, 6.6))
        _line(p, (12, 8.5), (12, 12), (14.8, 13.8))
    elif name == "refresh":
        p.drawArc(QRectF(4.5, 4.5, 15, 15), 40 * 16, 290 * 16)
        _line(p, (18.4, 3.6), (18.6, 8), (14.3, 7.8))
    elif name == "sparkle":
        path = QPainterPath()
        path.moveTo(12, 3)
        path.quadTo(13, 11, 21, 12)
        path.quadTo(13, 13, 12, 21)
        path.quadTo(11, 13, 3, 12)
        path.quadTo(11, 11, 12, 3)
        _fill(p, color)
        p.drawPath(path)
    elif name == "filter":
        path = QPainterPath()
        path.moveTo(4, 5)
        path.lineTo(20, 5)
        path.lineTo(14, 12.5)
        path.lineTo(14, 19)
        path.lineTo(10, 17)
        path.lineTo(10, 12.5)
        path.closeSubpath()
        p.drawPath(path)
    elif name == "info":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        _line(p, (12, 11), (12, 16.5))
        _fill(p, color)
        p.drawEllipse(QPointF(12, 7.8), 1.2, 1.2)
    elif name == "warning":
        path = QPainterPath()
        path.moveTo(12, 4)
        path.lineTo(21, 19.5)
        path.lineTo(3, 19.5)
        path.closeSubpath()
        p.drawPath(path)
        _line(p, (12, 9.5), (12, 14))
        _fill(p, color)
        p.drawEllipse(QPointF(12, 16.8), 1.1, 1.1)
    else:  # 알 수 없는 이름: 점
        _fill(p, color)
        p.drawEllipse(QPointF(12, 12), 3, 3)


@lru_cache(maxsize=512)
def pixmap(name, color="#2F221B", size=18, dpr=None):
    if dpr is None:
        app = QGuiApplication.instance()
        dpr = app.devicePixelRatio() if app else 1.0
        dpr = max(2.0, dpr)
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(size / 24.0, size / 24.0)
    _draw(name, p, color)
    p.end()
    return pm


def icon(name, color="#2F221B", size=18):
    return QIcon(pixmap(name, color, size))
