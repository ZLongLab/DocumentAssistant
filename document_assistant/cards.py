"""Native file cards, document excerpt artwork, and the persistent detail pane."""
from datetime import datetime
from PySide6.QtCore import QEvent, QPoint, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QMenu,
    QPlainTextEdit, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)
from .presentation import SUBTEXT, line_icon
from .rules import CATEGORIES

COLORS = {
    "实验报告": ("#e6f1f8", "#145888", "document"),
    "研究文献": ("#fff0e3", "#a34513", "library"),
    "课程资料": ("#f0e8f7", "#704793", "document"),
    "其他": ("#eaf1e9", "#315d45", "folder"),
    "项目资料": ("#e5efe9", "#236450", "folder"),
    "个人资料": ("#fae9ed", "#965365", "document"),
    "待整理": ("#fff2d7", "#92591b", "folder"),
}


def size_text(size):
    return f"{size / 1048576:.1f} MB" if size >= 1048576 else f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} 字节"


def text_label(text="", name=None):
    result = QLabel(text)
    result.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        result.setObjectName(name)
    return result


class DocumentArtwork(QWidget):
    """Real PDF cover or a readable extracted-text summary."""
    def __init__(self,item=None,parent=None):
        super().__init__(parent);self.item=item;self.preview=None;self.request=None;self.fingerprint=None
        self.setMinimumHeight(90);self.setMaximumHeight(112)
    def showEvent(self,event):
        super().showEvent(event)
        if not self.item or self.item.path.suffix.casefold()!='.pdf':return
        fingerprint=(str(self.item.path),self.item.size,self.item.mtime_ns)
        if self.fingerprint==fingerprint:return
        self.fingerprint=fingerprint;self.preview=None
        if self.request:self.request.close()
        from .document_thumbnail import ThumbnailRequest
        self.request=ThumbnailRequest(self,self.item.path,self.install_preview)
    def install_preview(self,image):
        self.preview=image;self.setToolTip('PDF 实际首页缩略图；打开文件可查看原始页面');self.update()
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        category=self.item.category if self.item else '其他';background,ink,icon=COLORS.get(category,COLORS['其他'])
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(background));p.drawRoundedRect(QRectF(self.rect()),12,12)
        if self.preview is not None:
            size=self.preview.size();scale=min(76/size.width(),(self.height()-12)/size.height())
            rect=QRectF(12,6,size.width()*scale,size.height()*scale)
            p.fillRect(rect,QColor('white'))
            p.drawImage(rect,self.preview)
            p.setPen(QPen(QColor('#d9ded7'),1));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(rect)
            font=QFont('Microsoft YaHei UI');font.setPixelSize(12);font.setBold(True);p.setFont(font);p.setPen(QColor(ink))
            title=p.fontMetrics().elidedText('PDF · 实际首页',Qt.TextElideMode.ElideRight,max(0,self.width()-108))
            p.drawText(QRectF(96,12,self.width()-108,22),title)
            font.setBold(False);p.setFont(font);p.setPen(QColor('#50645b'))
            excerpt=' '.join(self.item.body.split())[:150] if self.item.body else '此文件暂无可提取正文'
            p.drawText(QRectF(96,42,self.width()-108,46),Qt.TextFlag.TextWordWrap,excerpt)
        else:
            p.drawPixmap(12,12,line_icon(icon,ink).pixmap(22,22))
            suffix=self.item.path.suffix[1:].upper() if self.item else 'DOC'
            font=QFont('Microsoft YaHei UI');font.setPixelSize(12);font.setBold(True);p.setFont(font);p.setPen(QColor(ink))
            p.drawText(QRectF(42,12,self.width()-54,22),suffix+(' · 首页暂不可预览' if suffix=='PDF' else ' · 内容摘录'))
            font.setPixelSize(12);font.setBold(False);p.setFont(font);p.setPen(QColor('#50645b'))
            excerpt=' '.join(self.item.body.split())[:150] if self.item and self.item.body else '无可提取正文，打开原文件查看'
            p.drawText(QRectF(12,42,self.width()-24,46),Qt.TextFlag.TextWordWrap,excerpt)
            self.setToolTip('提取文字摘要；原始排版请打开文件查看')
        p.end()


class ShelfArtwork(QWidget):
    """Refined vector illustration for the sidebar that adapts to active theme."""
    def paintEvent(self, event):
        if self.height() < 130:
            return
        from .theme import get_colors, CURRENT_THEME
        colors = get_colors()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale = min(self.width() / 210, self.height() / 310)
        p.translate(0, self.height() - 310 * scale)
        p.scale(scale, scale)

        # Ambient glow behind top decor
        glow_col = QColor(colors['accent'])
        glow_col.setAlpha(35)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(glow_col)
        p.drawEllipse(QRectF(10, 15, 140, 110))

        # Delicate floating sparkle / star dust
        p.setBrush(QColor(colors['flourish_dot_1']))
        for sx, sy, sr in ((32, 20, 2.5), (95, 30, 2.0), (145, 80, 2.8), (170, 130, 1.8), (20, 140, 2.2)):
            p.drawEllipse(QRectF(sx, sy, sr * 2, sr * 2))

        # Leaves / decorative foliage
        p.setOpacity(0.65)
        leaf_color = QColor(colors['shelf_leaf'])
        for x, y, rotation in ((15, 35, -40), (24, 65, 35), (17, 98, -36), (130, 195, -40), (145, 226, 40)):
            p.save()
            p.translate(x, y)
            p.rotate(rotation)
            leaf = QPainterPath()
            leaf.moveTo(0, 30)
            leaf.cubicTo(-26, -8, -8, -24, 0, -48)
            leaf.cubicTo(24, -18, 25, 4, 0, 30)
            p.setBrush(leaf_color)
            p.drawPath(leaf)
            p.restore()
        p.setOpacity(1.0)

        # Shelves with sleek rounded profile
        shelf_col = QColor(colors['shelf_shelf'])
        p.setBrush(shelf_col)
        p.drawRoundedRect(QRectF(0, 175, 126, 9), 3, 3)
        p.drawRoundedRect(QRectF(0, 292, 194, 8), 3, 3)

        # Books with theme palette
        book_colors = [
            colors['shelf_book_1'], colors['shelf_book_2'], colors['shelf_book_3'],
            colors['shelf_book_4'], colors['shelf_book_5'], colors['shelf_book_1'],
            colors['shelf_book_2'], colors['shelf_book_3'], colors['shelf_book_4']
        ]

        book_defs = [
            (5, 96, 21), (29, 113, 22), (54, 84, 19),
            (76, 109, 25), (104, 130, 18),
            (7, 226, 24), (36, 214, 21), (61, 207, 25), (92, 233, 25)
        ]

        gold_line = QColor('#ffffff' if CURRENT_THEME == 'ocean' else '#f8e0b0')
        gold_line.setAlpha(120)

        for i, (x, top, width) in enumerate(book_defs):
            bottom = 175 if top < 175 else 292
            p.setBrush(QColor(book_colors[i]))
            p.drawRoundedRect(QRectF(x, top, width, bottom - top), 3, 3)
            # Embossed spine foil / bookmark lines
            p.setPen(QPen(gold_line, 0.8))
            p.drawLine(x + 4, top + 10, x + width - 4, top + 10)
            p.drawLine(x + 4, bottom - 12, x + width - 4, bottom - 12)
            # Vertical spine accent
            p.drawLine(x + width // 2, top + 16, x + width // 2, bottom - 18)
            p.setPen(Qt.PenStyle.NoPen)
        p.end()


class FileCard(QFrame):
    def __init__(self, window, row, parent=None):
        super().__init__(parent)
        self.window, self.row = window, row
        self.setObjectName("fileCard")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(206)
        self.setFixedHeight(268)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(6)
        top = QHBoxLayout()
        self.check = QCheckBox()
        self.check.setAccessibleName(f"选择 {window.items[row].path.name}")
        self.check.toggled.connect(self.checked)
        top.addWidget(self.check)
        top.addStretch()
        self.badge = text_label(name="categoryBadge")
        top.addWidget(self.badge)
        self.more = QToolButton()
        self.more.setText("···")
        self.more.setObjectName("cardMore")
        self.more.clicked.connect(self.menu)
        top.addWidget(self.more)
        layout.addLayout(top)
        self.artwork = DocumentArtwork(window.items[row])
        self.artwork.setFixedHeight(104)
        layout.addWidget(self.artwork)
        self.filename = text_label(name="cardFilename")
        layout.addWidget(self.filename)
        self.meta = text_label(name="muted")
        layout.addWidget(self.meta)
        self.combo = QComboBox()
        self.combo.addItems(window.categories)
        for index, category in enumerate(window.categories):
            self.combo.setItemIcon(index, line_icon(COLORS.get(category,COLORS["其他"])[2], COLORS.get(category,COLORS["其他"])[1]))
        self.combo.setAccessibleName(f"{window.items[row].path.name} 的分类")
        self.combo.currentTextChanged.connect(self.changed)
        layout.addWidget(self.combo)
        self.state = text_label(name="cardState")
        layout.addWidget(self.state)
        self.refresh()

    def select(self):
        self.window.scan_table.selectRow(self.row)
        self.window.show_scan_detail()

    def checked(self, checked):
        self.select()
        self.window.scan_table.item(self.row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def changed(self, category):
        self.select()
        self.window.category_combo(self.row).setCurrentText(category)
        self.refresh()

    def mousePressEvent(self, event):
        self.select()
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        self.select()
        self.window.open_source()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.select()
        elif event.key() == Qt.Key.Key_Space:
            self.check.toggle()
        else:
            super().keyPressEvent(event)

    def menu(self):
        self.select()
        popup = QMenu(self)
        popup.addAction("文件详情", self.window.show_details)
        popup.addAction("打开原文件", self.window.open_source)
        popup.exec(self.more.mapToGlobal(QPoint(0, self.more.height())))

    def refresh(self):
        if self.row >= len(self.window.items):
            return
        item = self.window.items[self.row]
        checked = self.window.scan_table.item(self.row, 0)
        status = self.window.scan_table.item(self.row, 4)
        if checked is None or status is None:
            return
        self.check.blockSignals(True)
        self.check.setChecked(checked.checkState() == Qt.CheckState.Checked)
        self.check.blockSignals(False)
        self.combo.blockSignals(True)
        self.combo.setCurrentText(item.category)
        self.combo.blockSignals(False)
        bg, ink, _ = COLORS.get(item.category,COLORS['其他'])
        self.badge.setText(item.category)
        self.artwork.update()
        self.badge.setStyleSheet(f"background:{bg}; color:{ink}; border:0; border-radius:10px; padding:3px 9px; font-size:11px;")
        self.combo.setStyleSheet(f"QComboBox {{background:{COLORS.get(item.category,COLORS['其他'])[0]}; color:{COLORS.get(item.category,COLORS['其他'])[1]}; border:1px solid #e0e3da; border-radius:9px; padding:5px 8px; font-weight:600;}}")
        self.filename.setText(self.filename.fontMetrics().elidedText(item.display_title or item.path.name, Qt.TextElideMode.ElideRight, max(150, self.width() - 26)))
        self.filename.setToolTip(str(item.path))
        self.meta.setText(self.meta.fontMetrics().elidedText(item.path.name, Qt.TextElideMode.ElideRight, max(150,self.width()-26)) if item.display_title else f"{item.path.suffix[1:].upper()}   {size_text(item.size)}")
        self.meta.setToolTip(item.path.name+'\n'+item.title_source+'\n'+' · '.join(value for value in (item.course,item.project,item.tags) if value))
        self.state.setText(f"{status.text()} · {status.data(SUBTEXT)}")
        self.state.setToolTip(f"{item.status}\n{item.reason}\n{status.toolTip()}")
        self.state.setStyleSheet("color:#91581c; font-size:10px;" if not item.status.startswith("已提取") else "color:#65716b; font-size:10px;")
        self.setToolTip(item.reason)
        active = self.window.scan_table.currentRow() == self.row
        if self.property("active") != active:
            self.setProperty("active", active)
            self.style().unpolish(self)
            self.style().polish(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'state'):
            self.refresh()


class CardGrid(QScrollArea):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.cards = []
        self.page = 0
        self.page_size = 60
        self.page_controls = QWidget()
        controls = QHBoxLayout(self.page_controls)
        controls.setContentsMargins(0, 0, 0, 0)
        self.previous = QPushButton('上一批')
        self.next = QPushButton('下一批')
        self.page_label = QLabel()
        self.page_label.setWordWrap(True)
        controls.addWidget(self.previous)
        controls.addWidget(self.page_label, 1)
        controls.addWidget(self.next)
        self.previous.clicked.connect(lambda:self.change_page(-1))
        self.next.clicked.connect(lambda:self.change_page(1))
        self.columns = 0
        self.setObjectName("cardScroll")
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setWidgetResizable(True)
        self.content = QWidget()
        self.content.setObjectName("cardContent")
        self.grid = QGridLayout(self.content)
        self.grid.setContentsMargins(0, 0, 4, 4)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(14)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setWidget(self.content)
        self.viewport().installEventFilter(self)

    def rebuild(self):
        while self.grid.count():
            child = self.grid.takeAt(0).widget()
            if child:
                child.hide()
                child.deleteLater()
        count = len(self.window.items)
        self.page = min(self.page, max(0,(count-1)//self.page_size))
        first, last = self.page*self.page_size, min(count,(self.page+1)*self.page_size)
        self.cards = [] if self.window.review_mode=='list' else [FileCard(self.window, row, self.content) for row in range(first,last)]
        self.page_label.setText(f'显示 {first+1}–{last} / {count} 个文件 · 勾选与归档作用于全部列表')
        self.previous.setEnabled(self.page>0)
        self.next.setEnabled(last<count)
        self.page_controls.setVisible(count>self.page_size and self.window.review_mode=='cards')
        self.columns = 0
        self.reflow()

    def change_page(self, delta):
        pages = max(1,(len(self.window.items)+self.page_size-1)//self.page_size)
        self.page = max(0,min(pages-1,self.page+delta))
        self.rebuild()
        self.verticalScrollBar().setValue(0)
        if self.cards:
            self.window.scan_table.selectRow(self.cards[0].row)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self.reflow)
        return False

    def reflow(self):
        columns = max(1, min(3, (self.viewport().width() + 14) // 228))
        if columns == self.columns:
            return
        for i in range(3):
            self.grid.setColumnStretch(i, 0)
        for i, card in enumerate(self.cards):
            self.grid.addWidget(card, i // columns, i % columns)
        for i in range(columns):
            self.grid.setColumnStretch(i, 1)
        self.columns = columns

    def sync(self, row=None):
        for card in self.cards if row is None else (c for c in self.cards if c.row==row):
            card.refresh()


class DetailPane(QFrame):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self.row = -1
        self.setObjectName("detailPane")
        self.setMinimumWidth(290)
        self.setMaximumWidth(380)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName('detailContent')
        scroll.setWidget(content)
        outer.addWidget(scroll)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        heading = QHBoxLayout()
        heading.addWidget(text_label("文件详情", "detailHeading"), 1)
        close = QPushButton("×")
        close.setObjectName("detailClose")
        close.setAccessibleName("收起文件详情")
        close.clicked.connect(self.hide)
        heading.addWidget(close)
        layout.addLayout(heading)
        self.banner = text_label("选择文件，检查分类建议", "detailBanner")
        self.banner.setWordWrap(True)
        layout.addWidget(self.banner)
        self.preview = QPlainTextEdit()
        self.preview.setObjectName("bodyPreview")
        self.preview.setReadOnly(True)
        self.preview.setMinimumHeight(140)
        self.preview.setPlaceholderText("添加文件后，在这里查看已提取的正文。")
        self.preview.setAccessibleName("选中文件的正文预览")
        from PySide6.QtWidgets import QTabWidget
        from .pdf_preview import PdfPreview
        self.preview_tabs = QTabWidget()
        self.pdf = PdfPreview()
        self.preview_tabs.addTab(self.pdf, 'PDF 页面')
        self.preview_tabs.addTab(self.preview, '提取文字')
        layout.addWidget(self.preview_tabs, 1)
        self.title = text_label("尚未选择文件", "detailFilename")
        self.title.setWordWrap(True)
        layout.addWidget(self.title)
        self.meta = text_label(name="muted")
        self.meta.setWordWrap(True)
        layout.addWidget(self.meta)
        category_row = QHBoxLayout()
        category_row.addWidget(text_label("确认分类", "fieldTitle"))
        self.combo = QComboBox()
        self.combo.addItems(window.categories)
        self.combo.setAccessibleName("详情中的确认分类")
        self.combo.currentTextChanged.connect(self.changed)
        category_row.addWidget(self.combo, 1)
        layout.addLayout(category_row)
        layout.addWidget(text_label("分类依据", "fieldTitle"))
        self.reason = text_label("分类依据将在这里显示。", "reasonBox")
        from .theme import get_colors
        _c = get_colors()
        self.reason.setStyleSheet(f'background:{_c["reason_bg"]}; border-radius:12px; padding:10px; color:{_c["reason_text"]}; font-size:12px;')
        self.reason.setWordWrap(True)
        self.reason.setMaximumHeight(112)
        layout.addWidget(self.reason)
        self.status = text_label(name="detailStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.open_button = QPushButton("打开原文件")
        self.open_button.setIcon(line_icon("open", _c['primary_bg']))
        self.open_button.clicked.connect(window.open_source)
        layout.addWidget(self.open_button)
        self.remember_button = QPushButton('记住此文件夹的课程 / 项目')
        self.remember_button.clicked.connect(window.remember_folder_rule)
        layout.addWidget(self.remember_button)
        self.category_rule_button=QPushButton('记住这种分类方式')
        self.category_rule_button.clicked.connect(window.remember_category)
        layout.addWidget(self.category_rule_button)
        self.combo.setEnabled(False)
        self.open_button.setEnabled(False)

    def refresh_theme(self):
        from .theme import get_colors
        c = get_colors()
        self.reason.setStyleSheet(f'background:{c["reason_bg"]}; border-radius:12px; padding:10px; color:{c["reason_text"]}; font-size:12px;')
        self.open_button.setIcon(line_icon("open", c['primary_bg']))

    def changed(self, category):
        if 0 <= self.row < len(self.window.items):
            self.window.category_combo(self.row).setCurrentText(category)
            self.show_item(self.row)

    def show_item(self, row):
        if not 0 <= row < len(self.window.items):
            self.row = -1
            self.title.setText("尚未选择文件")
            self.meta.clear()
            self.preview.clear()
            self.pdf.load_path(None)
            self.preview_tabs.setTabVisible(0,False)
            self.remember_button.setEnabled(False)
            self.category_rule_button.setEnabled(False)
            self.reason.setText("分类依据将在这里显示。")
            self.banner.setText("选择文件，检查分类建议")
            self.status.clear()
            self.combo.setEnabled(False)
            self.open_button.setEnabled(False)
            return
        self.row = row
        item = self.window.items[row]
        is_pdf = item.path.suffix.lower()=='.pdf'
        changed_path = self.pdf.path != item.path
        self.preview_tabs.setTabVisible(0,is_pdf)
        self.pdf.load_path(item.path if is_pdf else None)
        if is_pdf and changed_path:
            self.preview_tabs.setCurrentIndex(0)
        elif not is_pdf:
            self.preview_tabs.setCurrentIndex(1)
        bg, ink, _ = COLORS.get(item.suggested,COLORS["其他"])
        archived = self.window.archive_statuses.get(str(item.path), (False, ''))[0]
        self.banner.setText(f"建议分类：{item.suggested}\n" + ('已归档 · 原文件保留' if archived else '该文件将按你确认的分类归档'))
        self.banner.setStyleSheet(f"background:{bg};color:{ink};border-radius:14px;padding:12px;font-size:13px;font-weight:600;")
        body = item.body[:6000] or "无法提取正文。\n\n可以打开原文件查看，并根据文件名和分类依据确认归档。"
        if self.preview.toPlainText() != body:
            self.preview.setPlainText(body)
            self.preview.verticalScrollBar().setValue(0)
        self.title.setText((item.display_title+"\n" if item.display_title else "")+item.path.name)
        self.title.setToolTip(str(item.path))
        modified = datetime.fromtimestamp(item.mtime_ns / 1e9).strftime("%Y-%m-%d %H:%M")
        labels = '\n'.join(f'{name}：{getattr(item,key) or "未设置"}' for key,name in (('course','课程'),('project','项目'),('tags','标签')))
        self.meta.setText(f"{item.path.suffix[1:].upper()}   {size_text(item.size)}\n修改时间：{modified}\n{labels}")
        self.combo.blockSignals(True)
        self.combo.setCurrentText(item.category)
        self.combo.blockSignals(False)
        self.reason.setText(item.reason[:220] + ("…" if len(item.reason) > 220 else ""))
        self.reason.setToolTip(item.reason)
        status = self.window.scan_table.item(row, 4)
        self.status.setText(f"{status.text()} · {status.data(SUBTEXT)}")
        self.status.setToolTip(status.toolTip())
        self.combo.setEnabled(self.window.worker is None)
        self.open_button.setEnabled(self.window.worker is None)
        self.remember_button.setEnabled(self.window.worker is None)
        self.category_rule_button.setEnabled(self.window.worker is None and self.window.catalog is not None)
