"""Compact cards reuse the existing selection, preview, metadata and status behavior."""
from PySide6.QtCore import QSize, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy
from .cards import CardGrid as WorkbenchGrid, DetailPane, FileCard, DocumentArtwork


class StarryDocumentPreview(DocumentArtwork):
    def paintEvent(self, event):
        from .theme import CURRENT_THEME
        if CURRENT_THEME != 'starry':
            return super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#263c4e'), 1))
        painter.setBrush(QColor('#101f2d'))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5), 10, 10)
        left = 12
        if self.preview is not None and not self.preview.isNull():
            image = self.preview
            factor = min(48 / image.width(), (self.height() - 12) / image.height())
            painter.drawImage(QRectF(8,6,image.width()*factor,image.height()*factor),image)
            left = 66
        font = QFont(self.font());font.setPixelSize(11);painter.setFont(font)
        painter.setPen(QColor('#c1d9e9'))
        suffix = self.item.path.suffix[1:].upper() if self.item else ''
        painter.drawText(QRectF(left,9,self.width()-left-10,20),suffix + ' · 内容预览')
        font.setPixelSize(10);painter.setFont(font);painter.setPen(QColor('#a5bdce'))
        excerpt = (' '.join(self.item.body.split())[:100] if self.item and self.item.body else '无可提取正文，请检查原文件')
        painter.drawText(QRectF(left,30,self.width()-left-10,self.height()-36), Qt.TextFlag.TextWordWrap,excerpt)


class MinimalFileCard(FileCard):
    def __init__(self, window, row, parent=None):
        super().__init__(window, row, parent)
        # Release the old fixed height; the complete layout determines its minimum.
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)
        self.setMinimumWidth(220)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.layout().setContentsMargins(12, 10, 12, 10)
        self.layout().setSpacing(6)
        previous = self.artwork
        self.artwork = StarryDocumentPreview(window.items[row], self)
        self.artwork.setFixedHeight(80)
        self.layout().replaceWidget(previous, self.artwork)
        previous.hide()
        previous.deleteLater()
        for label in (self.filename, self.meta, self.state):
            label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.badge.setMaximumWidth(112)
        self.updateGeometry()

    def refresh(self):
        super().refresh()
        from .theme import CURRENT_THEME
        if CURRENT_THEME == 'starry':
            self.badge.setStyleSheet('background:#233f53;color:#d6edfc;border:1px solid transparent;border-radius:8px;padding:3px 8px;font-size:11px;')
            self.combo.setStyleSheet('QComboBox {background:#1a3041;color:#d6eaf6;border:1px solid transparent;border-radius:8px;padding:5px 8px;}')
            self.state.setStyleSheet('color:#a9bfce;font-size:11px;')
        if self.property('iconTheme') != CURRENT_THEME:
            from .cards import COLORS
            from .presentation import line_icon
            for index in range(self.combo.count()):
                category = self.combo.itemText(index)
                _, ink, symbol = COLORS.get(category, COLORS['其他'])
                self.combo.setItemIcon(index, line_icon(symbol, '#badff4' if CURRENT_THEME == 'starry' else ink))
            self.setProperty('iconTheme', CURRENT_THEME)

    def sizeHint(self):
        hint = super().sizeHint()
        return QSize(max(220, hint.width()), max(248, hint.height()))

    def paintEvent(self, event):
        from .theme_starry import paint_glass
        if not paint_glass(self):
            super().paintEvent(event)


class CardGrid(WorkbenchGrid):
    card_class = MinimalFileCard

    def __init__(self, window):
        super().__init__(window)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(12)

    def reflow(self):
        columns = max(1, min(4, max(1, len(self.cards)), (self.viewport().width() + 12) // 242))
        if columns == self.columns:
            return
        for i in range(4):
            self.grid.setColumnStretch(i, 0)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // columns, i % columns)
        for i in range(columns):
            self.grid.setColumnStretch(i, 1)
        self.columns = columns


class MinimalDetailPane(DetailPane):
    def __init__(self, window):
        super().__init__(window)
        self.setMinimumWidth(280)
        self.setMaximumWidth(350)

    def paintEvent(self, event):
        from .theme_starry import paint_glass
        if not paint_glass(self):
            super().paintEvent(event)

    def show_item(self, row):
        super().show_item(row)
        from .theme import CURRENT_THEME
        if CURRENT_THEME == 'starry':
            self.banner.setStyleSheet('background:#213d50;color:#d2ebfa;border:1px solid transparent;border-radius:12px;padding:12px;font-size:13px;font-weight:600;')
