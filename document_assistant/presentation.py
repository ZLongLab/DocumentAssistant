"""Native table presentation; no document or database operations."""
from PySide6.QtCore import QByteArray, QRect, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QStyle, QStyledItemDelegate, QTableWidget

TEXT, MUTED, ACCENT, WARNING, SUCCESS = "#202733", "#596574", "#285fbe", "#8a5618", "#32674b"
SUBTEXT = Qt.ItemDataRole.UserRole + 1
GLYPH = Qt.ItemDataRole.UserRole + 2
MATCH_TERMS = Qt.ItemDataRole.UserRole + 3
PATHS = {
    'close': '<path d="m6 6 12 12M18 6 6 18"/>',
    'redo': '<path d="m16 5 5 5-5 5M21 10H10a6 6 0 0 0 0 12"/>',
    'mask': '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M8 4v16m4-16v16m4-16v16M4 8h16M4 12h16M4 16h16"/>',
    'video': '<rect x="3" y="6" width="12" height="12" rx="3"/><path d="m15 10 6-3v10l-6-3z"/>',
    "settings": '<circle cx="12" cy="12" r="3"/><path d="M10 3h4l1 3 3 1 3 3v4l-3 1-1 3-3 3h-4l-1-3-3-1-3-3v-4l3-1 1-3z"/>',
    'capture': '<path d="M8 3H4a1 1 0 0 0-1 1v4m13-5h4a1 1 0 0 1 1 1v4M3 16v4a1 1 0 0 0 1 1h4m8 0h4a1 1 0 0 0 1-1v-4"/><rect x="7" y="7" width="10" height="10" rx="2"/>',
    'cursor': '<path d="m5 3 14 10-7 1-3 7z"/>',
    'rectangle': '<rect x="4" y="5" width="16" height="14" rx="2"/>',
    'arrow': '<path d="m5 19 14-14M9 5h10v10"/>',
    'text': '<path d="M4 6V4h16v2M12 4v16M8 20h8"/>',
    'undo': '<path d="m8 5-5 5 5 5M3 10h11a6 6 0 0 1 0 12"/>',
    'copy': '<rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3"/>',

    "document": '<path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5M8 12h8M8 16h6"/>',
    "import": '<path d="M4 14v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5M12 3v12m-4-4 4 4 4-4"/>',
    "library": '<rect x="3" y="4" width="5" height="16" rx="1"/><rect x="8" y="4" width="5" height="16" rx="1"/><path d="m15 5 4-1 3 15-4 1zM5 8h1M10 8h1"/>',
    "folder": '<path d="M3 7V5a1 1 0 0 1 1-1h6l2 3h8a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "more": '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    "check": '<path d="m5 12 4 4L19 6"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "open": '<path d="M14 3h7v7m0-7L10 14M10 5H4a1 1 0 0 0-1 1v14a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-6"/>',
}


class HintTable(QTableWidget):
    """Honest empty state inside the native table's own viewport."""
    def paintEvent(self, event):
        super().paintEvent(event)
        if self.rowCount() or not self.property("emptyText"):
            return
        painter = QPainter(self.viewport())
        painter.setPen(QColor(MUTED))
        painter.drawText(self.viewport().rect().adjusted(24, 36, -24, -24),
                         Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop | Qt.TextFlag.TextWordWrap,
                         self.property("emptyText"))
        painter.end()


def line_icon(name, color=MUTED):
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           f'stroke="{color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>')
    renderer = QSvgRenderer(QByteArray(svg.encode()))
    icon = QIcon()
    for size in (18, 24, 36):
        image = QPixmap(size, size)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(image)
    return icon


class TwoLineDelegate(QStyledItemDelegate):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.icons = {"check": line_icon("check"), "info": line_icon("info", WARNING)}

    def paint(self, painter, option, index):
        self.initStyleOption(option, index)
        painter.save()
        painter.setClipRect(option.rect)
        option.widget.style().drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem,
                                            option, painter, option.widget)
        rect = option.rect.adjusted(12, 7, -12, -7)
        title, subtitle = index.data(Qt.ItemDataRole.DisplayRole) or "", index.data(SUBTEXT) or ""
        foreground = index.data(Qt.ItemDataRole.ForegroundRole)
        color = foreground.color() if foreground else QColor(TEXT)
        font = QFont(option.font)
        font.setPixelSize(13)
        painter.setFont(font)
        painter.setPen(color)
        if self.kind == "file":
            badge = QRect(rect.left(), rect.center().y() - 16, 28, 32)
            suffix=str(index.data(GLYPH) or 'DOC')
            bg,ink={'PDF':('#fff0e8','#b45f36'),'DOCX':('#e9effb','#396caf'),'DOC':('#e9effb','#396caf'),'TXT':('#eaf2ed','#448063')}.get(suffix,('#eef0ed','#617267'))
            painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(bg))
            painter.drawRoundedRect(badge,7,7)
            badge_font = QFont(font)
            badge_font.setPixelSize(9)
            painter.setFont(badge_font)
            painter.setPen(QColor(ink))
            badge_font.setBold(True);painter.setFont(badge_font)
            painter.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(index.data(GLYPH) or "DOC"))
            rect.setLeft(rect.left() + 38)
            painter.setFont(font)
            painter.setPen(color)
        elif self.kind == "status":
            icon = self.icons["info" if color.name() == WARNING else "check"]
            icon.paint(painter, QRect(rect.left(), rect.top() + 4, 14, 14))
            rect.setLeft(rect.left() + 20)
        if self.kind == "reason":
            main_rect = QRect(rect.left(), rect.top(), rect.width(), 34)
            painter.save()
            painter.setClipRect(main_rect, Qt.ClipOperation.IntersectClip)
            title = painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, max(0, rect.width() * 2 - 12))
            painter.drawText(main_rect, Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, title)
            painter.restore()
            subtitle_y = rect.top() + 35
        else:
            text = painter.fontMetrics().elidedText(title, Qt.TextElideMode.ElideRight, max(0, rect.width()))
            from .search_text import paint_matches
            paint_matches(painter, QRect(rect.left(), rect.top(), rect.width(), 23), text,
                          index.data(MATCH_TERMS) or [])
            subtitle_y = rect.top() + 25
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(QColor(MUTED))
        text = painter.fontMetrics().elidedText(subtitle, Qt.TextElideMode.ElideRight, max(0, rect.width()))
        from .search_text import paint_matches
        paint_matches(painter, QRect(rect.left(), subtitle_y, rect.width(), 16), text,
                      index.data(MATCH_TERMS) or [])
        painter.restore()

    def sizeHint(self, option, index):
        return QSize(140, 68)


class CategoryDelegate(QStyledItemDelegate):
    def paint(self,painter,option,index):
        self.initStyleOption(option,index);painter.save();painter.setClipRect(option.rect)
        option.widget.style().drawPrimitive(QStyle.PrimitiveElement.PE_PanelItemViewItem,option,painter,option.widget)
        from .cards import COLORS
        text=str(index.data(Qt.ItemDataRole.DisplayRole) or '')
        background,ink,_=COLORS.get(text,COLORS['其他'])
        font=QFont(option.font);font.setPixelSize(12);painter.setFont(font)
        width=min(option.rect.width()-20,painter.fontMetrics().horizontalAdvance(text)+20)
        rect=QRect(option.rect.x()+10,option.rect.center().y()-13,max(1,width),26)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing);painter.setPen(Qt.PenStyle.NoPen);painter.setBrush(QColor(background))
        painter.drawRoundedRect(rect,10,10);painter.setPen(QColor(ink))
        text=painter.fontMetrics().elidedText(text,Qt.TextElideMode.ElideRight,max(1,rect.width()-14))
        painter.drawText(rect,Qt.AlignmentFlag.AlignCenter,text);painter.restore()
