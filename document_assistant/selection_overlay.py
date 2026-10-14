"""Select, annotate and copy a screenshot in one native screen overlay."""
import copy,math
from PySide6.QtCore import QPointF,QRectF,Qt,Signal,QSize
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QShortcut,QKeySequence
from PySide6.QtWidgets import QWidget,QPushButton,QHBoxLayout,QFrame,QButtonGroup,QLabel,QGraphicsDropShadowEffect,QSpinBox
from .capture_pixels import crop_selection
from .presentation import line_icon
from .inline_capture import InlineAnnotationCanvas
from .ui_flow import FlowLayout

PANEL_STYLE='''
QFrame#selectionPanel { background:#20292b; border:1px solid #425357; border-radius:14px; }
QPushButton { font-family:"Microsoft YaHei UI"; font-size:12px; color:#edf5f0; background:transparent; border:1px solid transparent; border-radius:8px; padding:7px 10px; }
QPushButton:hover { background:#354448; }
QPushButton:focus { border-color:#4ba681; }
QPushButton:checked, QPushButton#confirmSelection { color:white; background:#148968; font-weight:600; }
QPushButton:checked:hover, QPushButton#confirmSelection:hover { background:#0f825f; }
QPushButton:disabled { color:#66787b; background:transparent; }
QPushButton#colorChoice { border:2px solid transparent; border-radius:10px; padding:0; }
QPushButton#colorChoice:checked { border-color:#ffffff; }
QLabel, QLabel#selectionHint { font-family:"Microsoft YaHei UI"; font-size:12px; color:#c0d0c7; background:transparent; border:0; }
QSpinBox { color:#edf5f0; background:#354448; border:1px solid #4a5b60; border-radius:6px; padding:3px; }
QFrame#selectionDivider { background:#425357; border:0; }
'''

def panel_shadow(panel):
    effect=QGraphicsDropShadowEffect(panel);effect.setBlurRadius(22);effect.setOffset(0,5)
    effect.setColor(QColor(8,30,20,45));panel.setGraphicsEffect(effect)

class SelectionOverlay(QWidget):
    selected=Signal(object)
    save_selected=Signal(object)
    video_selected=Signal(object)
    mode_changed=Signal(str)
    cancelled=Signal()
    def __init__(self,screen,image):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.screen_ref,self.image=screen,image;self.start=self.end=None;self.drag=None;self.origin=None;self.press=None
        self.setCursor(Qt.CursorShape.CrossCursor);self.setMouseTracking(True)
        self.setWindowTitle('DocumentAssistant · 框选截图');self.setGeometry(screen.geometry())
        self.mode='photo';self.stop_key='Alt+S';self.selection_locked=False
        self.canvas=None;self.crop_origin=None;self.tool='view';self.error_text=''
        self.saved_path=self.saved_image=None
        self.modes=QFrame(self);self.modes.setObjectName('selectionPanel');self.modes.setStyleSheet(PANEL_STYLE);panel_shadow(self.modes)
        modes=QHBoxLayout(self.modes);modes.setContentsMargins(7,7,14,7);modes.setSpacing(5)
        self.mode_group=QButtonGroup(self);self.mode_buttons={}
        for key,label in [('photo','拍照'),('video','视频')]:
            button=QPushButton(label);button.setCheckable(True);button.setMinimumWidth(72);button.setFixedHeight(38)
            self.mode_group.addButton(button);modes.addWidget(button)
            button.clicked.connect(lambda checked=False,value=key:self.set_mode(value,True));self.mode_buttons[key]=button
        self.mode_buttons['photo'].setChecked(True)
        divider=QFrame();divider.setObjectName('selectionDivider');divider.setFixedSize(1,22);modes.addSpacing(7);modes.addWidget(divider);modes.addSpacing(7)
        self.hint_label=QLabel();self.hint_label.setObjectName('selectionHint');modes.addWidget(self.hint_label)
        self.actions=QFrame(self);self.actions.setObjectName('selectionPanel');self.actions.setStyleSheet(PANEL_STYLE);panel_shadow(self.actions)
        self.action_layout=FlowLayout(self.actions,5);self.action_layout.setContentsMargins(9,9,9,9)
        self.photo_controls=[];self.tool_buttons={};self.tool_group=QButtonGroup(self)
        for key,title,icon in [('view','调整选区','capture'),('select','选择 / 移动标注','cursor'),
                              ('rectangle','矩形','rectangle'),('arrow','箭头','arrow'),('text','文字','text'),('mask','遮挡','mask')]:
            button=QPushButton();button.setFixedSize(34,34);button.setCheckable(True)
            button.setToolTip(title);button.setAccessibleName(title);button.setIcon(line_icon(icon,'#edf5f0'));button.setIconSize(QSize(21,21))
            button.clicked.connect(lambda checked=False,value=key:self.set_tool(value))
            self.tool_group.addButton(button);self.tool_buttons[key]=button
            self.action_layout.addWidget(button);self.photo_controls.append(button)
        self.tool_buttons['view'].setChecked(True)
        self.color_group=QButtonGroup(self);self.color_buttons=[]
        for color,title in [('#e34f45','红色'),('#ec9b21','橙色'),('#377fde','蓝色'),('#24825c','绿色')]:
            button=QPushButton();button.setObjectName('colorChoice');button.setFixedSize(22,22);button.setCheckable(True)
            button.setStyleSheet(f'QPushButton#colorChoice {{ background:{color}; }}');button.setToolTip(title);button.setAccessibleName(title)
            button.clicked.connect(lambda checked=False,value=color:self.change_style(color=value))
            self.color_group.addButton(button);self.color_buttons.append(button);self.action_layout.addWidget(button);self.photo_controls.append(button)
        self.color_buttons[0].setChecked(True)
        for title,attr,minimum,maximum,value in [('线宽','width_spin',1,16,3),('字号','size_spin',12,64,22)]:
            group=QWidget();row=QHBoxLayout(group);row.setContentsMargins(4,0,0,0);row.setSpacing(4)
            row.addWidget(QLabel(title));spin=QSpinBox();spin.setRange(minimum,maximum);spin.setValue(value);spin.setFixedWidth(54);spin.setAccessibleName(title)
            row.addWidget(spin);self.action_layout.addWidget(group);self.photo_controls.append(group);setattr(self,attr,spin)
        self.width_spin.valueChanged.connect(lambda value:self.change_style(width=value))
        self.size_spin.valueChanged.connect(lambda value:self.change_style(size=value))
        for title,icon,attr,handler in [('撤销','undo','undo_button',self.undo),('重做','redo','redo_button',self.redo)]:
            button=QPushButton();button.setFixedSize(34,34);button.setIcon(line_icon(icon,'#edf5f0'));button.setIconSize(QSize(21,21))
            button.setToolTip(title+' · '+('Ctrl+Z' if icon=='undo' else 'Ctrl+Y'));button.setAccessibleName(title)
            button.clicked.connect(handler);self.action_layout.addWidget(button);self.photo_controls.append(button);setattr(self,attr,button)
        self.save_button=QPushButton('保存到桌面');self.save_button.setToolTip('保存 PNG，并复制到剪贴板')
        self.save_button.clicked.connect(self.save);self.action_layout.addWidget(self.save_button);self.photo_controls.append(self.save_button)
        cancel=QPushButton();cancel.setFixedSize(34,34);cancel.setIcon(line_icon('close','#ff827c'));cancel.setIconSize(QSize(22,22))
        cancel.setToolTip('取消 · Esc');cancel.setAccessibleName('取消截图');cancel.clicked.connect(self.cancelled.emit);self.action_layout.addWidget(cancel)
        self.confirm_button=QPushButton('完成 · 复制');self.confirm_button.setObjectName('confirmSelection')
        self.confirm_button.setIcon(line_icon('check','#ffffff'));self.confirm_button.setIconSize(QSize(18,18))
        self.confirm_button.setToolTip('仅复制，不创建图片文件 · Enter')
        self.confirm_button.clicked.connect(lambda:self.confirm());self.action_layout.addWidget(self.confirm_button)
        for key,handler in [('Return',lambda:self.confirm(True)),('Enter',lambda:self.confirm(True)),('Escape',self.cancelled.emit),('Ctrl+Z',self.undo),('Ctrl+Y',self.redo)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(handler)
        self.shortcuts=self.findChildren(QShortcut)
        self.actions.hide();self.refresh_toolbar()
    def refresh_toolbar(self):
        if not hasattr(self,'hint_label'):return
        hint='框选后直接标注  ·  Enter 复制  ·  Esc 取消'
        if self.mode=='video':hint='无声录屏  ·  '+self.stop_key+' 停止'
        if self.selection_locked:hint='区域已锁定  ·  Esc 取消'
        if self.error_text:hint=self.error_text
        self.hint_label.setToolTip('拖动选取区域；拖动边缘调整大小，内部移动。'+hint)
        width=max(70,min(320,self.width()-260))
        self.hint_label.setText(self.hint_label.fontMetrics().elidedText(hint,Qt.TextElideMode.ElideRight,width))
        self.hint_label.setMaximumWidth(width)
        for mode,button in self.mode_buttons.items():
            button.setIcon(line_icon('capture' if mode=='photo' else 'video','#ffffff' if button.isChecked() else '#6a8574'))
            button.setIconSize(QSize(16,16))
        self.modes.adjustSize();self.modes.move(max(12,(self.width()-self.modes.width())//2),22)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.refresh_toolbar()
        if hasattr(self,'actions') and self.actions.isVisible():self.position_actions()
    def set_mode(self,mode,announce=False):
        if self.selection_locked:return
        if mode not in self.mode_buttons:return
        self.mode=mode;self.mode_buttons[mode].setChecked(True)
        if self.canvas:self.canvas.finish_text();self.canvas.setVisible(mode=='photo')
        for widget in self.photo_controls:widget.setVisible(mode=='photo')
        self.confirm_button.setText('开始录制  ↵' if mode=='video' else '完成 · 复制')
        self.confirm_button.setToolTip('开始无声录屏' if mode=='video' else '仅复制，不创建图片文件 · Enter')
        self.confirm_button.setIcon(line_icon('video' if mode=='video' else 'check','#ffffff'))
        self.refresh_toolbar()
        if self.actions.isVisible():self.position_actions()
        self.update()
        if announce:self.mode_changed.emit(mode)
    def lock_selection(self):
        self.selection_locked=True;self.drag=None
        self.modes.setEnabled(False);self.confirm_button.setEnabled(False)
        for widget in self.photo_controls:widget.setEnabled(False)
        if self.canvas:self.canvas.setEnabled(False)
        self.setCursor(Qt.CursorShape.ArrowCursor);self.refresh_toolbar();self.update()
    def selection_rect(self):
        return QRectF(self.start,self.end).normalized() if self.start is not None else QRectF()
    def handles(self):
        r=self.selection_rect();x,y=r.center().x(),r.center().y()
        return {'nw':r.topLeft(),'n':QPointF(x,r.top()),'ne':r.topRight(),'e':QPointF(r.right(),y),
            'se':r.bottomRight(),'s':QPointF(x,r.bottom()),'sw':r.bottomLeft(),'w':QPointF(r.left(),y)}
    def position_actions(self):
        r=self.selection_rect()
        width=min(self.width()-24,850 if self.mode=='photo' else 210)
        self.actions.resize(width,self.action_layout.heightForWidth(width))
        x=max(8,min(self.width()-self.actions.width()-8,int(r.right())-self.actions.width()))
        y=int(r.bottom())+12
        if y+self.actions.height()>self.height()-8:y=max(8,int(r.top())-self.actions.height()-12)
        candidate=QRectF(x,y,self.actions.width(),self.actions.height())
        if candidate.intersects(QRectF(self.modes.geometry())):
            y=min(self.height()-self.actions.height()-8,self.modes.geometry().bottom()+12)
        self.actions.move(x,y);self.actions.show();self.actions.raise_();self.modes.raise_()

    def show_error(self,text):
        self.error_text=text;self.refresh_toolbar();self.hint_label.setToolTip(text)

    def set_tool(self,tool):
        self.tool=tool;self.tool_buttons[tool].setChecked(True)
        if self.canvas:self.canvas.set_tool(tool)

    def change_style(self,**style):
        if self.canvas:self.canvas.apply_style(**style)

    def undo(self):
        if self.canvas:
            if self.canvas.text_editor is not None:self.canvas.text_editor.undo()
            else:self.canvas.undo()

    def redo(self):
        if self.canvas:
            if self.canvas.text_editor is not None:self.canvas.text_editor.redo()
            else:self.canvas.redo()

    def refresh_canvas(self,reset=False):
        image=crop_selection(self.image,self.selection_rect(),self.size())
        r=self.selection_rect();sx,sy=self.image.width()/self.width(),self.image.height()/self.height()
        origin=QPointF(math.floor(r.left()*sx),math.floor(r.top()*sy))
        previous=self.canvas
        if previous is None:
            self.canvas=InlineAnnotationCanvas(image,self)
            self.canvas.changed.connect(self.update_annotation_controls)
            self.canvas.selection_changed.connect(self.update_annotation_controls)
        else:
            previous.finish_text()
            delta=(self.crop_origin-origin) if self.crop_origin is not None else QPointF()
            def shifted(marks):
                result=[]
                for old in marks:
                    mark=list(copy.deepcopy(old));mark[1]+=delta;mark[2]+=delta;result.append(tuple(mark))
                return result
            if reset:previous.marks=[];previous.history=[];previous.future=[]
            else:
                previous.marks=shifted(previous.marks)
                previous.history=[shifted(m) for m in previous.history];previous.future=[shifted(m) for m in previous.future]
            previous.image=image;previous.cached_image=previous.cached_marks=None;previous.selected_index=None
        self.crop_origin=origin
        self.canvas.setGeometry(r.toRect());self.canvas.set_tool(self.tool)
        self.canvas.color=('#e34f45','#ec9b21','#377fde','#24825c')[next((i for i,b in enumerate(self.color_buttons) if b.isChecked()),0)]
        self.canvas.line_width=self.width_spin.value();self.canvas.text_size=self.size_spin.value()
        self.canvas.setVisible(self.mode=='photo');self.canvas.update();self.update_annotation_controls()
        self.actions.raise_();self.modes.raise_()

    def update_annotation_controls(self):
        self.undo_button.setEnabled(bool(self.canvas and self.canvas.history) and not self.selection_locked)
        self.redo_button.setEnabled(bool(self.canvas and self.canvas.future) and not self.selection_locked)
        if self.canvas and self.canvas.selected_index is not None:
            from .capture_markup import style_of
            mark=self.canvas.marks[self.canvas.selected_index];style=style_of(mark)
            for spin,value in ((self.width_spin,style['width']),(self.size_spin,style['size'])):
                blocked=spin.blockSignals(True);spin.setValue(value);spin.blockSignals(blocked)
            self.canvas.color=mark[4];self.canvas.line_width=self.width_spin.value();self.canvas.text_size=self.size_spin.value()
            for button,color in zip(self.color_buttons,('#e34f45','#ec9b21','#377fde','#24825c')):button.setChecked(color==mark[4])
    def paintEvent(self,event):
        p=QPainter(self);p.drawImage(QRectF(self.rect()),self.image);p.fillRect(self.rect(),QColor(12,25,21,112))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.start is not None:
            r=self.selection_rect();sx,sy=self.image.width()/self.width(),self.image.height()/self.height()
            p.drawImage(r,self.image,QRectF(r.x()*sx,r.y()*sy,r.width()*sx,r.height()*sy))
            p.setPen(QPen(QColor('#41d4a5'),1.5));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(r)
            corner=min(15,r.width()/3,r.height()/3)
            p.setPen(QPen(QColor('#71f3c6'),3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            for point,dx,dy in [(r.topLeft(),1,1),(r.topRight(),-1,1),(r.bottomLeft(),1,-1),(r.bottomRight(),-1,-1)]:
                p.drawLine(point,point+QPointF(dx*corner,0));p.drawLine(point,point+QPointF(0,dy*corner))
            p.setPen(QPen(QColor('#199774'),1.5));p.setBrush(QColor('#ffffff'))
            for point in self.handles().values():p.drawEllipse(point,3.5,3.5)
            font=QFont('Microsoft YaHei UI');font.setPixelSize(12);p.setFont(font)
            pixel_width=max(0,min(self.image.width(),math.ceil(r.right()*sx))-max(0,math.floor(r.left()*sx)))
            pixel_height=max(0,min(self.image.height(),math.ceil(r.bottom()*sy))-max(0,math.floor(r.top()*sy)))
            text=f'{pixel_width} × {pixel_height} px'
            badge_width=p.fontMetrics().horizontalAdvance(text)+26
            x=max(8,min(self.width()-badge_width-8,r.left()));y=max(8,r.top()-38)
            badge=QRectF(x,y,badge_width,28)
            if badge.intersects(QRectF(self.modes.geometry())):badge.moveTop(max(8,r.top()+12))
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#173f32'));p.drawRoundedRect(badge,10,10)
            p.setPen(QColor('#f1fff6'));p.drawText(badge,Qt.AlignmentFlag.AlignCenter,text)
        p.end()
    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.RightButton:self.cancelled.emit();return
        if self.selection_locked:return
        if event.button()!=Qt.MouseButton.LeftButton:return
        self.begin_drag(event.position())

    def begin_drag(self,point):
        if self.selection_locked:return
        if self.canvas:self.canvas.finish_text()
        self.press=point;self.origin=self.selection_rect();self.drag='new'
        if self.start is not None:
            self.drag=next((key for key,p in self.handles().items() if (p-point).manhattanLength()<=10),None)
            if self.drag is None:self.drag='move' if self.origin.contains(point) else 'new'
        if self.drag=='new':self.start=self.end=point
        if self.canvas:self.canvas.hide()
        self.actions.hide();self.update()
    def mouseMoveEvent(self,event):
        if self.selection_locked:return
        if self.drag is None:return
        self.move_drag(event.position())

    def move_drag(self,position):
        if self.selection_locked or self.drag is None:return
        point=QPointF(max(0,min(self.width(),position.x())),max(0,min(self.height(),position.y())))
        if self.drag=='new':self.end=point
        else:
            r=QRectF(self.origin)
            if self.drag=='move':
                delta=point-self.press;delta=QPointF(max(-r.left(),min(self.width()-r.right(),delta.x())),max(-r.top(),min(self.height()-r.bottom(),delta.y())));r.translate(delta)
            else:
                if 'w' in self.drag:r.setLeft(min(point.x(),r.right()-2))
                if 'e' in self.drag:r.setRight(max(point.x(),r.left()+2))
                if 'n' in self.drag:r.setTop(min(point.y(),r.bottom()-2))
                if 's' in self.drag:r.setBottom(max(point.y(),r.top()+2))
            self.start,self.end=r.topLeft(),r.bottomRight()
        self.update()
    def mouseReleaseEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.drag is None:return
        self.end_drag(event.position())

    def end_drag(self,point):
        if self.drag is None:return
        reset=self.drag=='new';self.move_drag(point);self.drag=None
        r=self.selection_rect()
        if r.width()<2 or r.height()<2:self.start=self.end=None;self.update();return
        r=QRectF(r.toAlignedRect()).intersected(QRectF(self.rect()))
        self.start,self.end=r.topLeft(),r.bottomRight();self.refresh_canvas(reset);self.position_actions();self.update()

    def rendered(self):
        if self.canvas:
            self.canvas.finish_text();return self.canvas.rendered()
        return crop_selection(self.image,self.selection_rect(),self.size())

    def save(self):
        if self.mode=='photo' and not self.selection_locked and self.start is not None:
            self.save_selected.emit(self.rendered())

    def confirm(self,keyboard=False):
        if self.selection_locked:return
        if self.start is None:return
        if self.mode=='video':
            if self.selection_rect().width()>=2 and self.selection_rect().height()>=2:self.video_selected.emit(self.selection_rect())
            return
        if keyboard and self.canvas and self.canvas.text_editor is not None:
            self.canvas.finish_text();self.setFocus();return
        try:image=self.rendered()
        except ValueError:return
        self.selected.emit(image)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.confirm()
        elif event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace) and self.canvas:self.canvas.delete_selected()
