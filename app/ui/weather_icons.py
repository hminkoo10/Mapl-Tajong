"""날씨 그림 (코드로 그림, 어떤 크기에서도 선명). 기준 격자 24x24."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen

SUN = "#FFB020"
MOON = "#FFCF5C"
RAIN = "#4DA3FF"
BOLT = "#FFC93C"


def _cloud_path(cx, cy, s):
    """가운데 아래가 평평한 구름 모양. s 는 너비 기준 크기."""
    w, h = s, s * 0.58
    left, bottom = cx - w / 2, cy + h / 2
    base = QPainterPath()
    base.addRoundedRect(QRectF(left, bottom - h * 0.52, w, h * 0.52), h * 0.26, h * 0.26)
    a = QPainterPath()
    a.addEllipse(QPointF(left + w * 0.34, bottom - h * 0.52), w * 0.21, w * 0.21)
    b = QPainterPath()
    b.addEllipse(QPointF(left + w * 0.62, bottom - h * 0.62), w * 0.27, w * 0.27)
    return base.united(a).united(b)


def _sun(p, c, r, color=SUN, rays=True):
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawEllipse(c, r, r)
    if rays:
        p.setPen(QPen(QColor(color), r * 0.28, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i in range(8):
            a = math.pi / 4 * i
            p.drawLine(QPointF(c.x() + math.cos(a) * r * 1.45, c.y() + math.sin(a) * r * 1.45),
                       QPointF(c.x() + math.cos(a) * r * 1.85, c.y() + math.sin(a) * r * 1.85))


def _moon(p, c, r, bg):
    p.setPen(Qt.PenStyle.NoPen)
    full = QPainterPath()
    full.addEllipse(c, r, r)
    cut = QPainterPath()
    cut.addEllipse(QPointF(c.x() + r * 0.55, c.y() - r * 0.35), r * 0.85, r * 0.85)
    p.setBrush(QColor(MOON))
    p.drawPath(full.subtracted(cut))


def _cloud(p, cx, cy, s, color, edge=None):
    path = _cloud_path(cx, cy, s)
    p.setPen(QPen(QColor(edge), s * 0.035) if edge else Qt.PenStyle.NoPen)
    p.setBrush(QColor(color))
    p.drawPath(path)


def paint_weather(p: QPainter, rect: QRectF, kind, night=False, dark=True):
    """rect 안에 날씨 그림을 그린다."""
    s = min(rect.width(), rect.height())
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.translate(rect.center().x() - s / 2, rect.center().y() - s / 2)
    p.scale(s / 24.0, s / 24.0)
    cloud = "#E8ECF1" if dark else "#CDD5DF"
    cloud2 = "#B9C2CE" if dark else "#AEB8C5"
    edge = None if dark else "#FFFFFF"
    bg = "#121316" if dark else "#FFFFFF"

    def celestial(c, r, rays=True):
        if night:
            _moon(p, c, r, bg)
        else:
            _sun(p, c, r, rays=rays)

    if kind == "clear":
        celestial(QPointF(12, 12), 5.2 if not night else 7.0)
    elif kind == "fair":
        celestial(QPointF(10.5, 9.5), 4.4)
        _cloud(p, 14.5, 16.0, 11.5, cloud, edge)
    elif kind == "partly":
        celestial(QPointF(8.5, 8.5), 4.0, rays=not night)
        _cloud(p, 13.5, 14.5, 16.5, cloud, edge)
    elif kind == "cloudy":
        _cloud(p, 9.5, 10.5, 12, cloud2, edge)
        _cloud(p, 13.5, 14.5, 16.5, cloud, edge)
    elif kind == "fog":
        _cloud(p, 12, 10.0, 16, cloud, edge)
        p.setPen(QPen(QColor(cloud2), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for y, x0, x1 in ((17.0, 4.5, 19.5), (20.2, 7.0, 17.0)):
            p.drawLine(QPointF(x0, y), QPointF(x1, y))
    elif kind in ("rain", "sleet", "snow", "thunder"):
        _cloud(p, 12, 9.5, 17, cloud2 if kind == "thunder" else cloud, edge)
        if kind == "thunder":
            bolt = QPainterPath()
            for i, (x, y) in enumerate(((12.8, 13.2), (9.6, 18.0), (12.0, 18.0), (10.8, 22.4), (15.0, 16.6),
                                         (12.4, 16.6), (13.8, 13.2))):
                bolt.moveTo(x, y) if i == 0 else bolt.lineTo(x, y)
            bolt.closeSubpath()
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(BOLT))
            p.drawPath(bolt)
        else:
            drops = ((8.0, 16.5), (12.0, 17.8), (16.0, 16.5))
            for i, (x, y) in enumerate(drops):
                flake = kind == "snow" or (kind == "sleet" and i == 1)
                if flake:
                    p.setPen(Qt.PenStyle.NoPen)
                    p.setBrush(QColor("#9CCBFF" if not dark else "#DCEBFF"))
                    p.drawEllipse(QPointF(x, y + 1.2), 1.35, 1.35)
                    p.drawEllipse(QPointF(x - 1.6, y + 4.2), 1.1, 1.1)
                else:
                    p.setPen(QPen(QColor(RAIN), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                    p.drawLine(QPointF(x + 0.6, y), QPointF(x - 0.9, y + 3.6))
    else:
        _cloud(p, 12, 13, 17, cloud, edge)
    p.restore()
