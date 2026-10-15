"""Scrollable long-image preview, annotations, copy and optional PNG save."""
import copy
import math
from pathlib import Path
from PySide6.QtCore import QEvent, QPointF, Qt, QTimer, QSize
from PySide6.QtGui import QColor, QCursor, QKeySequence, QPainter, QPen, QShortcut
from PySide6.QtWidgets import QButtonGroup, QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget
from .capture_canvas import AnnotationCanvas
from .capture_markup import style_of
from .capture_style import CAPTURE_QSS
from .capture_tools import COLORS, normalize_tools
from .presentation import line_icon
from .selection_overlay import PANEL_STYLE


class LongCanvas(AnnotationCanvas):
    def __init__(self, image, scroll):
        super().__init__(image); self.scroll = scroll; self.brush_position = None
        self.setMinimumSize(1, 1); self.setMouseTracking(True); self.zoom = 1.

    def set_zoom(self, value=None, anchor=None):
        fraction = self.scroll.verticalScrollBar().value() / max(1, self.height())
        width = max(1, self.scroll.viewport().width() - 32)
        self.zoom = min(1., width / self.image.width()) if value is None else max(.05, min(4., value))
        self.pan = QPointF(); self.resize(math.ceil(self.image.width() * self.zoom) + 24,
                                         math.ceil(self.image.height() * self.zoom) + 24)
        self.scroll.verticalScrollBar().setValue(round(fraction * self.height()))
        self.zoom_changed.emit(self.zoom); self.update()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.set_zoom(self.scale() * 1.2 ** (event.angleDelta().y() / 120))
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        self.brush_position = event.position()
        if self.drag_position is not None:
            delta = event.position() - self.drag_position
            bar = self.scroll.verticalScrollBar(); bar.setValue(bar.value() - round(delta.y()))
            self.drag_position = event.position(); self.update(); return
        super().mouseMoveEvent(event); self.update()

    def leaveEvent(self, event):
        self.brush_position = None; self.update(); super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.tool == 'mask' and self.brush_position is not None and self.image_point(self.brush_position) is not None:
            p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
            radius = self.brush_size * self.scale() / 2
            p.setPen(QPen(QColor('#172b32'), 3)); p.drawEllipse(self.brush_position, radius, radius)
            p.setPen(QPen(QColor('white'), 1)); p.drawEllipse(self.brush_position, radius, radius); p.end()


class LongImageEditor(QDialog):
    def __init__(self, image, controller, warning='', segments=1):
        super().__init__(None); self.controller = controller
        self.preferences = normalize_tools(controller.tool_preferences)
        self.saved_path = self.saved_image = None; self.fit_width = True
        self.setWindowTitle('长截图 · 标注与复制'); self.resize(1000, 760); self.setMinimumSize(640, 460)
        self.setStyleSheet(CAPTURE_QSS)
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 14, 16, 14); layout.setSpacing(12)
        header = QHBoxLayout(); title = QLabel('长截图'); title.setObjectName('captureTitle'); header.addWidget(title)
        meta = QLabel(f'{image.width()} × {image.height()} px · {segments} 段'); meta.setObjectName('captureMeta'); header.addWidget(meta)
        header.addStretch(); fit = QPushButton('适应宽度'); fit.clicked.connect(self.fit); header.addWidget(fit)
        actual = QPushButton('100%'); actual.clicked.connect(self.actual); header.addWidget(actual); layout.addLayout(header)
        self.toolbar = QFrame(); self.toolbar.setObjectName('selectionPanel'); self.toolbar.setStyleSheet(PANEL_STYLE)
        tools = QHBoxLayout(self.toolbar); tools.setContentsMargins(9, 7, 9, 7); tools.setSpacing(5)
        self.tool_group = QButtonGroup(self); self.tool_buttons = {}
        for kind, title, icon in [('view','浏览 · 拖动上下查看','cursor'),('select','选择 / 移动标注','cursor'),
                                  ('rectangle','矩形','rectangle'),('arrow','箭头','arrow'),('text','文字','text'),('mask','马赛克','mask')]:
            b = QPushButton('浏览' if kind == 'view' else ''); b.setCheckable(True); b.setFixedHeight(34)
            if kind != 'view':
                b.setIcon(line_icon(icon, '#edf5f0')); b.setIconSize(QSize(20, 20)); b.setFixedWidth(32)
            b.setToolTip(title); b.setAccessibleName(title); b.clicked.connect(lambda checked=False, value=kind:self.set_tool(value))
            self.tool_group.addButton(b); self.tool_buttons[kind] = b; tools.addWidget(b)
        self.color_group = QButtonGroup(self); self.color_buttons = []
        for color in COLORS:
            b = QPushButton(); b.setObjectName('colorChoice'); b.setCheckable(True); b.setFixedSize(20, 20)
            b.setStyleSheet(f'background:{color};'); b.setAccessibleName(color)
            b.clicked.connect(lambda checked=False,value=color:self.style(color=value))
            self.color_group.addButton(b); self.color_buttons.append(b); tools.addWidget(b)
        self.option_groups = {}; self.spins = {}
        for key, title, low, high, value in [('width','线宽',1,16,3),('size','字号',12,64,22),('brush','笔刷',4,64,12),('block','颗粒',2,32,6)]:
            group = QWidget(); row = QHBoxLayout(group); row.setContentsMargins(4,0,0,0); row.setSpacing(3)
            row.addWidget(QLabel(title)); spin = QSpinBox(); spin.setRange(low,high); spin.setValue(value); spin.setFixedWidth(54)
            spin.setAccessibleName(title); spin.valueChanged.connect(lambda val,name=key:self.style(**{name:val}))
            row.addWidget(spin); tools.addWidget(group); self.option_groups[key] = group; self.spins[key] = spin
        tools.addStretch()
        self.undo_button = QPushButton(); self.redo_button = QPushButton()
        for b, icon, title in [(self.undo_button,'undo','撤销'),(self.redo_button,'redo','重做')]:
            b.setIcon(line_icon(icon,'#edf5f0')); b.setIconSize(QSize(20,20)); b.setFixedSize(32,34)
            b.setToolTip(title); b.setAccessibleName(title); tools.addWidget(b)
        layout.addWidget(self.toolbar)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(False)
        self.scroll.viewport().installEventFilter(self)
        self.scroll.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.canvas = LongCanvas(image,self.scroll); self.scroll.setWidget(self.canvas); layout.addWidget(self.scroll,1)
        self.canvas.changed.connect(self.refresh); self.canvas.selection_changed.connect(self.refresh)
        self.undo_button.clicked.connect(self.canvas.undo); self.redo_button.clicked.connect(self.canvas.redo)
        self.message = QLabel(warning); self.message.setObjectName('captureError'); self.message.setWordWrap(True)
        self.message.setVisible(bool(warning)); layout.addWidget(self.message)
        footer = QHBoxLayout(); hint = QLabel('滚轮浏览长图 · Ctrl+滚轮缩放'); hint.setObjectName('captureHint'); footer.addWidget(hint); footer.addStretch()
        cancel = QPushButton('取消'); cancel.setObjectName('cancelCapture'); cancel.clicked.connect(self.reject); footer.addWidget(cancel)
        self.save_button = QPushButton('保存到桌面' if controller.is_desktop_destination() else '保存图片')
        self.save_button.setObjectName('saveCapture'); self.save_button.clicked.connect(self.save); footer.addWidget(self.save_button)
        self.copy_button = QPushButton('完成 · 复制'); self.copy_button.setObjectName('copyCapture'); self.copy_button.setDefault(True)
        self.copy_button.clicked.connect(self.copy); footer.addWidget(self.copy_button); layout.addLayout(footer)
        for button in self.findChildren(QPushButton):button.setAutoDefault(False)
        self.copy_button.setDefault(True)
        for key, handler in [('Ctrl+Z',self.canvas.undo),('Ctrl+Y',self.canvas.redo)]:
            shortcut = QShortcut(QKeySequence(key),self); shortcut.activated.connect(handler)
        self.set_tool('view'); QTimer.singleShot(0,self.fit)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self,'canvas') and self.fit_width:
            QTimer.singleShot(0,self.fit)

    def eventFilter(self,watched,event):
        if hasattr(self,'canvas') and watched is self.scroll.viewport() and event.type()==QEvent.Type.Resize and self.fit_width:
            QTimer.singleShot(0,self.fit)
        return super().eventFilter(watched,event)

    def fit(self):
        self.fit_width = True; self.canvas.set_zoom()

    def actual(self):
        self.fit_width = False; self.canvas.set_zoom(1.)

    def set_tool(self, kind):
        self.canvas.tool = kind; self.canvas.selected_index = None; self.tool_buttons[kind].setChecked(True)
        self.canvas.setCursor(Qt.CursorShape.BlankCursor if kind == 'mask' else Qt.CursorShape.ArrowCursor if kind in ('view','select') else Qt.CursorShape.CrossCursor)
        self.refresh()

    def effective_tool(self):
        if self.canvas.tool == 'select' and self.canvas.selected_index is not None:
            return self.canvas.marks[self.canvas.selected_index][0]
        return self.canvas.tool

    def refresh(self):
        kind = self.effective_tool(); values = dict(self.preferences.get(kind,{}))
        if self.canvas.selected_index is not None:
            mark = self.canvas.marks[self.canvas.selected_index]; values.update(style_of(mark)); values['color'] = mark[4]
        visible={'rectangle':('width',),'arrow':('width',),'text':('size',),'mask':('brush','block')}.get(kind,())
        for key, group in self.option_groups.items():
            group.setVisible(key in visible)
        for key, spin in self.spins.items():
            if key in values:
                blocked = spin.blockSignals(True); spin.setValue(values[key]); spin.blockSignals(blocked)
        color = values.get('color','#e34f45')
        for b, choice in zip(self.color_buttons,COLORS):
            b.setVisible(kind in ('rectangle','arrow','text')); b.setChecked(choice == color)
        self.canvas.color = color; self.canvas.line_width = self.spins['width'].value(); self.canvas.text_size = self.spins['size'].value()
        self.canvas.brush_size = self.spins['brush'].value(); self.canvas.mosaic_block = self.spins['block'].value()
        self.undo_button.setEnabled(bool(self.canvas.history)); self.redo_button.setEnabled(bool(self.canvas.future)); self.canvas.update()

    def style(self, **values):
        kind = self.effective_tool()
        if kind in self.preferences:
            self.preferences[kind].update({key:value for key,value in values.items() if key in self.preferences[kind]})
        self.canvas.apply_style(**values); self.controller.remember_tools(copy.deepcopy(self.preferences)); self.refresh()

    def error(self, text):
        self.message.setText(text); self.message.show()

    def copy(self):
        from .screen_capture import copy_image
        try:
            copy_image(self.canvas.rendered())
        except Exception as exc:
            self.error('复制失败，可重试或保存：'+str(exc)); return
        self.controller.notify('长截图已复制','可以粘贴到 Word 或聊天窗口'); self.accept()

    def save(self):
        from .screen_capture import copy_image, save_png
        image = self.canvas.rendered()
        try:
            if self.saved_image is not None and image == self.saved_image and self.saved_path and self.saved_path.is_file():
                path = self.saved_path
            else:
                path = save_png(image,self.controller.settings['directory']); self.saved_image = image.copy(); self.saved_path = path
            self.controller.last_saved = path
        except Exception as exc:
            self.error('保存失败，可重试或仅复制：'+str(exc)); return
        try:
            copy_image(image)
        except Exception as exc:
            self.error('长图已保存，复制失败，可重试：'+str(exc)); return
        self.controller.notify('长截图已保存并复制',str(path)); self.accept()
