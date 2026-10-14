"""Small native decorations for the library heading and action menus."""
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QMenu, QWidget

from .theme import get_colors


class ActionMenu(QMenu):
    def __init__(self, title='', parent=None):
        super().__init__(title, parent)
        self.caption = title or '工作台工具'
        self.setObjectName('actionMenu')
        self.setMinimumWidth(222)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

    def paintEvent(self, event):
        super().paintEvent(event)
        colors = get_colors()
        p = QPainter(self)
        font = QFont(self.font())
        font.setPixelSize(11)
        font.setBold(True)
        p.setFont(font)
        p.setPen(QColor(colors['muted']))
        p.drawText(
            self.rect().adjusted(16, 8, -12, 0),
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
            self.caption,
        )
        p.end()


class LibraryFlourish(QWidget):
    def __init__(self):
        super().__init__()
        self.setFixedSize(116, 72)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setToolTip('文档库装饰图案')

    def paintEvent(self, event):  # noqa: C901 – artistic paint routine
        colors = get_colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # --- Decorative ring / arc around the main circle -----------------
        ring_color = QColor(colors['border'])
        ring_color.setAlpha(90)
        ring_pen = QPen(ring_color, 1.2)
        ring_pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(ring_pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(7, 3, 76, 70))

        # --- Main background circle ---------------------------------------
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colors['flourish_circle']))
        p.drawEllipse(QRectF(12, 8, 66, 60))

        # --- Three stacked documents -------------------------------------
        doc_base = QColor(colors['flourish_doc'])
        border_color = QColor(colors['border'])
        line_color = QColor(colors['muted'])

        # Each document: (x, y, rotation, fill_color, tab_color)
        # Back doc – darker tint of the doc base color
        back_fill = QColor(doc_base)
        back_fill.setAlpha(140)
        # Middle doc – slightly lighter
        mid_fill = QColor(doc_base)
        mid_fill.setAlpha(180)
        # Front doc – white page
        front_fill = QColor(colors['card_bg'])

        documents = [
            (55, 13, 14, back_fill, doc_base),
            (43, 11, -10, mid_fill, doc_base),
            (37, 10, 0, front_fill, QColor(colors['accent'])),
        ]

        for x, y, angle, fill, tab_col in documents:
            p.save()
            p.translate(x, y)
            p.rotate(angle)

            # Document body
            p.setBrush(fill)
            p.setPen(QPen(border_color, 1))
            p.drawRoundedRect(QRectF(0, 0, 39, 50), 5, 5)

            # Small coloured tab at the top of the document
            tab = QColor(tab_col)
            tab.setAlpha(200)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(tab)
            p.drawRoundedRect(QRectF(0, 0, 39, 6), 5, 2)

            # Horizontal text lines
            p.setPen(QPen(line_color, 1.5))
            for line_y, width in ((14, 23), (21, 19), (28, 23)):
                p.drawLine(8, line_y, width + 8, line_y)

            p.restore()

        # --- Orange accent dot --------------------------------------------
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colors['flourish_dot_1']))
        p.drawEllipse(QRectF(18, 51, 10, 10))

        # --- Green / secondary accent dot ---------------------------------
        p.setBrush(QColor(colors['flourish_dot_2']))
        p.drawEllipse(QRectF(91, 12, 5, 5))

        # --- Small sparkle / star dots using accent colours ---------------
        sparkle = QColor(colors['accent'])
        sparkle.setAlpha(160)
        p.setBrush(sparkle)
        p.drawEllipse(QRectF(100, 28, 3, 3))

        sparkle2 = QColor(colors['flourish_dot_1'])
        sparkle2.setAlpha(130)
        p.setBrush(sparkle2)
        p.drawEllipse(QRectF(6, 38, 3, 3))

        sparkle3 = QColor(colors['accent'])
        sparkle3.setAlpha(100)
        p.setBrush(sparkle3)
        p.drawEllipse(QRectF(86, 4, 2.5, 2.5))

        p.end()


class WorkbenchFlourish(QWidget):
    """Artistic decorative illustration for the topbar of the workbench page."""
    def __init__(self):
        super().__init__()
        self.setFixedSize(130, 76)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setToolTip('文档整理工作台装饰图案')

    def paintEvent(self, event):
        colors = get_colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Ambient decorative orbit ring
        ring_col = QColor(colors['border'])
        ring_col.setAlpha(100)
        p.setPen(QPen(ring_col, 1.2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(14, 6, 80, 64))

        # Soft glowing backdrop halo
        halo = QColor(colors['flourish_circle'])
        halo.setAlpha(180)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(halo)
        p.drawEllipse(QRectF(22, 10, 68, 56))

        # Background card (tilted)
        p.save()
        p.translate(34, 14)
        p.rotate(-8)
        bg_card_col = QColor(colors['flourish_doc'])
        bg_card_col.setAlpha(120)
        p.setBrush(bg_card_col)
        p.setPen(QPen(QColor(colors['border']), 1))
        p.drawRoundedRect(QRectF(0, 0, 42, 52), 6, 6)
        # Tab accent
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colors['flourish_dot_1']))
        p.drawRoundedRect(QRectF(6, 4, 16, 4), 2, 2)
        p.restore()

        # Foreground card (crisp white with colored header)
        p.save()
        p.translate(46, 16)
        p.rotate(6)
        p.setBrush(QColor(colors['card_bg']))
        p.setPen(QPen(QColor(colors['border']), 1.2))
        p.drawRoundedRect(QRectF(0, 0, 44, 52), 6, 6)

        # Top banner on card
        card_header = QColor(colors['accent'])
        card_header.setAlpha(220)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(card_header)
        p.drawRoundedRect(QRectF(0, 0, 44, 8), 6, 2)

        # Skeleton text lines
        p.setPen(QPen(QColor(colors['muted']), 1.6))
        for ly, lw in ((16, 24), (23, 30), (30, 20), (37, 26)):
            p.drawLine(7, ly, 7 + lw, ly)
        p.restore()

        # Checkmark badge / stamp
        badge_rect = QRectF(78, 40, 22, 22)
        p.setBrush(QColor(colors['accent']))
        p.setPen(QPen(QColor('#ffffff'), 1.5))
        p.drawEllipse(badge_rect)
        # Check glyph
        p.setPen(QPen(QColor('#ffffff'), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawLine(83, 51, 87, 55)
        p.drawLine(87, 55, 94, 46)

        # Floating sparkle stars
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(colors['flourish_dot_1']))
        p.drawEllipse(QRectF(110, 16, 4, 4))
        p.drawEllipse(QRectF(18, 48, 3.5, 3.5))

        p.setBrush(QColor(colors['flourish_dot_2']))
        p.drawEllipse(QRectF(102, 38, 2.5, 2.5))
        p.drawEllipse(QRectF(12, 18, 3, 3))

        p.end()
