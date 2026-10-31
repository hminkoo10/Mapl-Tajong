"""디자인 토큰과 공통 스타일.

회색 계열 + 주황 포인트 하나. 그라데이션은 진행 표시 같은 곳에만 은은하게 쓴다.
"""
from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap


class C:
    # 회색
    grey50 = "#F9FAFB"
    grey100 = "#F2F4F6"
    grey200 = "#E5E8EB"
    grey300 = "#D1D6DB"
    grey400 = "#B0B8C1"
    grey500 = "#8B95A1"
    grey600 = "#6B7684"
    grey700 = "#4E5968"
    grey800 = "#333D4B"
    grey900 = "#191F28"

    # 주황
    accent = "#F76B15"
    accent_hover = "#EB600D"
    accent_pressed = "#DD5605"
    accent_text = "#E05A00"
    accent_soft = "#FFE9D9"
    accent_softer = "#FFF4EC"
    g0 = "#FFA352"   # 자연스러운 그라데이션 시작 (살구)
    g1 = "#FF8A33"
    g2 = "#F76B15"   # 끝 (주황)

    # 상태
    success = "#0E9F6E"
    success_soft = "#E5F6EE"
    danger = "#F04452"
    danger_soft = "#FFEEEF"
    warning = "#E08A00"
    warning_soft = "#FFF4DE"
    neutral = "#8B95A1"
    neutral_soft = "#F2F4F6"

    # 의미 이름
    bg = "#F2F4F6"
    surface = "#FFFFFF"
    surface_alt = grey50
    border = grey200
    border_strong = grey300
    divider = grey100
    text = grey900
    text_muted = grey600
    text_subtle = grey400

    shadow = QColor(0, 29, 58)


def qc(hex_or_color, alpha=None):
    c = QColor(hex_or_color)
    if alpha is not None:
        c.setAlphaF(max(0.0, min(1.0, float(alpha))))
    return c


def mix(a, b, t):
    a, b = QColor(a), QColor(b)
    t = max(0.0, min(1.0, float(t)))
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def accent_gradient(x1, y1, x2, y2, stops=None):
    g = QLinearGradient(QPointF(x1, y1), QPointF(x2, y2))
    stops = stops or (C.g0, C.g2)
    n = len(stops) - 1
    for i, col in enumerate(stops):
        g.setColorAt(i / n if n else 0, QColor(col))
    return g


FONT_FAMILY = "Pretendard"


def load_fonts(font_dir):
    """번들된 Pretendard를 등록. 실패하면 시스템 글꼴 사용."""
    global FONT_FAMILY
    loaded = []
    try:
        for f in sorted(font_dir.glob("*.otf")) + sorted(font_dir.glob("*.ttf")):
            fid = QFontDatabase.addApplicationFont(str(f))
            if fid >= 0:
                loaded += QFontDatabase.applicationFontFamilies(fid)
    except Exception:
        pass
    if loaded:
        FONT_FAMILY = loaded[0]
    return bool(loaded)


def app_font():
    f = QFont()
    f.setFamilies([FONT_FAMILY, "Pretendard", "Malgun Gothic", "맑은 고딕", "Apple SD Gothic Neo", "Noto Sans KR",
                   "Noto Sans CJK KR", "WenQuanYi Zen Hei", "Segoe UI"])
    f.setPixelSize(14)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def font(px, weight=QFont.Weight.Normal, base=None):
    f = QFont(base or QGuiApplication.font())
    f.setPixelSize(max(1, int(round(px))))
    f.setWeight(weight)
    return f


def rounded(rect, r):
    p = QPainterPath()
    p.addRoundedRect(QRectF(rect), r, r)
    return p


def paint_soft_shadow(p: QPainter, rect: QRectF, radius, strength=1.0, spread=10, dy=4):
    """아주 옅은 그림자 (팝업/떠 있는 요소에만 사용)."""
    p.save()
    p.setPen(Qt.PenStyle.NoPen)
    layers = 12
    for i in range(layers):
        k = (i + 1) / layers
        grow = spread * (1 - k)
        col = QColor(C.shadow)
        col.setAlphaF(min(1.0, 0.004 * strength * k ** 1.5))
        p.setBrush(col)
        r = QRectF(rect).adjusted(-grow, -grow + dy * k, grow, grow + dy * k)
        p.drawRoundedRect(r, radius + grow, radius + grow)
    p.restore()


def paint_app_background(p: QPainter, rect: QRectF):
    p.fillRect(rect, QColor(C.bg))


# ---------------- 스타일시트용 이미지 ----------------
def _make_png(path, draw, w=16, h=16):
    dpr = 2
    pm = QPixmap(w * dpr, h * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(dpr, dpr)
    draw(p)
    p.end()
    pm.save(str(path), "PNG")


def _chevron(down, color):
    def draw(p):
        p.setPen(QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        if down:
            p.drawPolyline([QPointF(4.5, 6.5), QPointF(8, 10), QPointF(11.5, 6.5)])
        else:
            p.drawPolyline([QPointF(4.5, 9.5), QPointF(8, 6), QPointF(11.5, 9.5)])
    return draw


def _check(p):
    p.setPen(QPen(QColor("#FFFFFF"), 2.0, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.drawPolyline([QPointF(4.5, 8.3), QPointF(7.2, 10.8), QPointF(11.8, 5.6)])


def build_stylesheet(cache_dir):
    imgs = {
        "down": (cache_dir / "v2_chev_down.png", _chevron(True, C.grey600)),
        "up": (cache_dir / "v2_chev_up.png", _chevron(False, C.grey600)),
        "down_dis": (cache_dir / "v2_chev_down_dis.png", _chevron(True, C.grey300)),
        "check": (cache_dir / "v2_check.png", _check),
    }
    for path, fn in imgs.values():
        try:
            _make_png(path, fn)
        except Exception:
            pass
    u = {k: v[0].as_posix() for k, v in imgs.items()}

    return f"""
    QWidget {{ color: {C.text}; font-size: 14px; }}
    QMainWindow {{ background: {C.bg}; }}
    QDialog {{ background: transparent; }}
    QLabel {{ background: transparent; }}
    QLabel[role="title"] {{ font-size: 26px; font-weight: 700; color: {C.grey900}; }}
    QLabel[role="subtitle"] {{ font-size: 14px; color: {C.grey600}; }}
    QLabel[role="section"] {{ font-size: 17px; font-weight: 700; color: {C.grey900}; }}
    QLabel[role="muted"] {{ color: {C.grey600}; font-size: 13px; }}
    QLabel[role="subtle"] {{ color: {C.grey500}; font-size: 12.5px; }}
    QLabel[role="field"] {{ color: {C.grey700}; font-size: 13px; font-weight: 600; }}

    QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QTimeEdit, QDateEdit {{
        background: {C.grey100};
        border: 1px solid {C.grey100};
        border-radius: 10px;
        padding: 8px 12px;
        min-height: 20px;
        color: {C.grey900};
        selection-background-color: {C.accent_soft};
        selection-color: {C.grey900};
    }}
    QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover, QTimeEdit:hover, QDateEdit:hover {{
        background: #EBEEF1; border-color: #EBEEF1;
    }}
    QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QTimeEdit:focus, QDateEdit:focus {{
        background: #FFFFFF; border: 1px solid {C.accent};
    }}
    QLineEdit[page="true"], QComboBox[page="true"], QSpinBox[page="true"], QDateEdit[page="true"] {{
        background: #FFFFFF; border-color: #FFFFFF;
    }}
    QLineEdit[page="true"]:hover, QComboBox[page="true"]:hover, QSpinBox[page="true"]:hover, QDateEdit[page="true"]:hover {{
        background: #FFFFFF; border-color: {C.grey200};
    }}
    QLineEdit[page="true"]:focus, QComboBox[page="true"]:focus, QSpinBox[page="true"]:focus, QDateEdit[page="true"]:focus {{
        border-color: {C.accent};
    }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QTimeEdit:disabled, QDateEdit:disabled {{
        color: {C.grey400}; background: {C.grey50}; border-color: {C.grey50};
    }}
    QComboBox {{ padding-right: 30px; }}
    QComboBox::drop-down, QDateEdit::drop-down {{
        subcontrol-origin: padding; subcontrol-position: center right; width: 28px; border: none;
    }}
    QComboBox::down-arrow, QDateEdit::down-arrow {{ image: url({u['down']}); width: 14px; height: 14px; }}
    QComboBox::down-arrow:disabled {{ image: url({u['down_dis']}); }}
    QComboBox QAbstractItemView {{
        background: #FFFFFF; border: 1px solid {C.grey200}; border-radius: 12px; padding: 6px;
        selection-background-color: {C.grey100}; selection-color: {C.grey900}; outline: 0;
    }}
    QComboBox QAbstractItemView::item {{ min-height: 34px; padding: 0 10px; border-radius: 8px; }}

    QSpinBox, QDoubleSpinBox, QTimeEdit {{ padding-right: 26px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button, QTimeEdit::up-button {{
        subcontrol-origin: border; subcontrol-position: top right; width: 22px; border: none; background: transparent;
        margin-top: 4px; margin-right: 4px;
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button, QTimeEdit::down-button {{
        subcontrol-origin: border; subcontrol-position: bottom right; width: 22px; border: none; background: transparent;
        margin-bottom: 4px; margin-right: 4px;
    }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QTimeEdit::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover, QTimeEdit::down-button:hover {{
        background: {C.grey200}; border-radius: 5px;
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow, QTimeEdit::up-arrow {{ image: url({u['up']}); width: 11px; height: 11px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow, QTimeEdit::down-arrow {{ image: url({u['down']}); width: 11px; height: 11px; }}

    QTableView, QTableWidget {{
        background: #FFFFFF;
        border: none;
        border-radius: 16px;
        gridline-color: transparent;
        selection-background-color: {C.accent_softer};
        selection-color: {C.grey900};
        outline: 0;
    }}
    QTableView::item {{ padding: 4px 12px; border-bottom: 1px solid {C.grey100}; }}
    QTableView::item:selected {{ background: {C.accent_softer}; color: {C.grey900}; }}
    QHeaderView {{ background: transparent; border: none; }}
    QHeaderView::section {{
        background: #FFFFFF; color: {C.grey500}; font-weight: 600; font-size: 12.5px;
        padding: 12px 12px 10px 12px; border: none; border-bottom: 1px solid {C.grey100};
    }}
    QHeaderView::section:first {{ border-top-left-radius: 16px; }}
    QHeaderView::section:last {{ border-top-right-radius: 16px; }}
    QTableCornerButton::section {{ background: #FFFFFF; border: none; }}

    QScrollArea {{ background: transparent; border: none; }}
    QScrollArea > QWidget > QWidget {{ background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 8px; margin: 8px 2px 8px 0; }}
    QScrollBar::handle:vertical {{ background: {C.grey300}; border-radius: 3px; min-height: 40px; }}
    QScrollBar::handle:vertical:hover {{ background: {C.grey400}; }}
    QScrollBar:horizontal {{ background: transparent; height: 8px; margin: 0 8px 2px 8px; }}
    QScrollBar::handle:horizontal {{ background: {C.grey300}; border-radius: 3px; min-width: 40px; }}
    QScrollBar::handle:horizontal:hover {{ background: {C.grey400}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}

    QMenu {{ background: #FFFFFF; border: 1px solid {C.grey200}; border-radius: 14px; padding: 6px; }}
    QMenu::item {{ padding: 9px 26px 9px 12px; border-radius: 8px; color: {C.grey800}; }}
    QMenu::item:selected {{ background: {C.grey100}; color: {C.grey900}; }}
    QMenu::item:disabled {{ color: {C.grey400}; }}
    QMenu::separator {{ height: 1px; background: {C.grey100}; margin: 5px 8px; }}
    QMenu::icon {{ padding-left: 10px; }}

    QToolTip {{ background: {C.grey800}; color: #FFFFFF; border: none; padding: 6px 10px; border-radius: 8px; font-size: 12.5px; }}

    QCheckBox, QRadioButton {{ spacing: 8px; background: transparent; }}
    QCheckBox::indicator {{ width: 20px; height: 20px; border-radius: 10px; border: 1.5px solid {C.grey300}; background: #FFFFFF; }}
    QCheckBox::indicator:hover {{ border-color: {C.grey400}; }}
    QCheckBox::indicator:checked {{ background: {C.accent}; border-color: {C.accent}; image: url({u['check']}); }}
    QRadioButton::indicator {{ width: 18px; height: 18px; border-radius: 10px; border: 1.5px solid {C.grey300}; background: #FFFFFF; }}
    QRadioButton::indicator:checked {{ border: 6px solid {C.accent}; background: #FFFFFF; }}

    QProgressBar {{ background: {C.grey100}; border: none; border-radius: 3px; min-height: 6px; max-height: 6px; text-align: center; color: transparent; }}
    QProgressBar::chunk {{ border-radius: 3px; background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C.g0}, stop:1 {C.g2}); }}

    QSlider::groove:horizontal {{ height: 4px; background: {C.grey200}; border-radius: 2px; }}
    QSlider::sub-page:horizontal {{ background: {C.accent}; border-radius: 2px; }}
    QSlider::handle:horizontal {{ background: #FFFFFF; border: 1px solid {C.grey300}; width: 18px; height: 18px; margin: -8px 0; border-radius: 10px; }}
    QSlider::handle:horizontal:hover {{ border-color: {C.grey400}; }}
    QSlider::groove:horizontal:disabled {{ background: {C.grey100}; }}
    QSlider::sub-page:horizontal:disabled {{ background: {C.grey300}; }}
    QSlider::handle:horizontal:disabled {{ background: #FFFFFF; border: 1px solid {C.grey200}; }}

    QPushButton {{
        background: {C.grey100}; color: {C.grey700}; border: none;
        padding: 8px 18px; border-radius: 10px; min-width: 64px; font-weight: 600;
    }}
    QPushButton:hover {{ background: {C.grey200}; }}
    QPushButton:default {{ background: {C.accent}; color: #FFFFFF; }}
    QPushButton:default:hover {{ background: {C.accent_hover}; }}
    Button {{ min-width: 0px; padding: 0px; border: none; background: transparent; }}
    QMessageBox {{ background: #FFFFFF; }}
    QMessageBox QLabel {{ color: {C.grey800}; font-size: 14px; }}

    QCalendarWidget QWidget {{ alternate-background-color: {C.grey50}; }}
    QCalendarWidget QToolButton {{ color: {C.grey900}; background: transparent; border: none; padding: 6px; border-radius: 6px; font-weight: 700; }}
    QCalendarWidget QToolButton:hover {{ background: {C.grey100}; }}
    QCalendarWidget #qt_calendar_navigationbar {{ background: #FFFFFF; }}
    QCalendarWidget QAbstractItemView:enabled {{ selection-background-color: {C.accent}; selection-color: #FFFFFF; }}
    """
