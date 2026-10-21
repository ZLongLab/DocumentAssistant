"""Select, annotate and copy a screenshot in one native screen overlay."""
import copy,math
from PySide6.QtCore import QPointF,QRectF,Qt,Signal,QSize
from PySide6.QtGui import QColor,QPainter,QPen,QFont,QShortcut,QKeySequence
from PySide6.QtWidgets import QWidget,QPushButton,QHBoxLayout,QVBoxLayout,QFrame,QButtonGroup,QLabel,QSpinBox,QComboBox
from .capture_pixels import crop_selection, pixel_scale, selection_pixels
from .presentation import line_icon
from .inline_capture import InlineAnnotationCanvas
from .capture_tools import COLORS,normalize_tools
from .video_audio import normalize_audio_mode, audio_label

from .capture_material import (CaptureGlassPanel, PANEL_STYLE, SELECTION_COLOR,
    CORNER_COLOR, HANDLE_COLOR, ICON_COLOR, MUTED_ICON_COLOR, paint_panel_shadows)

class SelectionOverlay(QWidget):
    selected=Signal(object)
    save_selected=Signal(object)
    video_selected=Signal(object)
    long_selected=Signal(object)
    mode_changed=Signal(str)
    video_audio_changed=Signal(str)
    cancelled=Signal()
    preferences_changed=Signal(object)
    def __init__(self,screen,image,preferences=None):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.screen_ref,self.image=screen,image;self.start=self.end=None;self.drag=None;self.origin=None;self.press=None
        self.setCursor(Qt.CursorShape.CrossCursor);self.setMouseTracking(True)
        self.setWindowTitle('DocumentAssistant · 框选截图');self.setGeometry(screen.geometry())
        self.mode='photo';self.stop_key='Alt+S';self.selection_locked=False
        self.video_audio_mode='silent'
        self.canvas=None;self.crop_origin=None;self.tool='view';self.error_text=''
        self.saved_path=self.saved_image=None
        self.tool_preferences=normalize_tools(preferences)
        self.actions=CaptureGlassPanel(self)
        self.actions.setCursor(Qt.CursorShape.ArrowCursor)
        self.toolbar_layout=QVBoxLayout(self.actions);self.toolbar_layout.setContentsMargins(9,9,9,9);self.toolbar_layout.setSpacing(6)
        self.action_layout=QHBoxLayout();self.action_layout.setContentsMargins(0,0,0,0);self.action_layout.setSpacing(5)
        self.toolbar_layout.addLayout(self.action_layout)
        self._modes_stacked=False
        self.modes=QWidget(self.actions);self.modes.setObjectName('captureModes')
        modes=QHBoxLayout(self.modes);modes.setContentsMargins(0,0,0,0);modes.setSpacing(4)
        self.mode_group=QButtonGroup(self);self.mode_buttons={}
        for key,label in [('photo','截图'),('long','长截图'),('video','视频')]:
            button=QPushButton(label);button.setCheckable(True);button.setMinimumWidth(72);button.setFixedHeight(34)
            self.mode_group.addButton(button);modes.addWidget(button)
            button.clicked.connect(lambda checked=False,value=key:self.set_mode(value,True));self.mode_buttons[key]=button
        self.mode_buttons['photo'].setChecked(True)
        self.video_audio_combo=QComboBox();self.video_audio_combo.setObjectName('captureAudio')
        self.video_audio_combo.addItem('无声','silent');self.video_audio_combo.addItem('有声（电脑声音）','system')
        self.video_audio_combo.setAccessibleName('录屏声音')
        self.video_audio_combo.setToolTip('有声：录入默认播放设备的电脑声音，不录麦克风；无声：只录画面')
        self.video_audio_combo.setFixedHeight(34);self.video_audio_combo.setMinimumWidth(130)
        self.video_audio_combo.currentIndexChanged.connect(lambda:self.set_video_audio_mode(self.video_audio_combo.currentData(),True))
        modes.addWidget(self.video_audio_combo);self.video_audio_combo.hide()
        divider=QFrame();divider.setObjectName('selectionDivider');divider.setFixedSize(1,22);modes.addSpacing(7);modes.addWidget(divider);modes.addSpacing(7)
        self.hint_label=QLabel();self.hint_label.setObjectName('selectionHint');modes.addWidget(self.hint_label)
        self.action_layout.addWidget(self.modes)
        self.action_layout.setSizeConstraint(QHBoxLayout.SizeConstraint.SetNoConstraint)
        self.style_groups=[];self.option_groups={}
        self.photo_controls=[];self.tool_buttons={};self.tool_group=QButtonGroup(self)
        for key,title,icon in [('view','调整选区','capture'),('select','选择 / 移动标注','cursor'),
                              ('rectangle','矩形','rectangle'),('arrow','箭头','arrow'),('text','文字','text'),('mask','马赛克 · 按住拖动自由涂抹','mask')]:
            button=QPushButton();button.setFixedSize(34,34);button.setCheckable(True)
            button.setToolTip(title);button.setAccessibleName(title);button.setIcon(line_icon(icon,ICON_COLOR));button.setIconSize(QSize(21,21))
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
        for title,attr,minimum,maximum,value in [('线宽','width_spin',1,16,3),('字号','size_spin',12,64,22),
                                               ('笔刷','brush_spin',4,64,12),('颗粒','block_spin',2,32,6)]:
            group=QWidget();row=QHBoxLayout(group);row.setContentsMargins(4,0,0,0);row.setSpacing(4)
            group.setFixedHeight(34);caption=QLabel(title);row.addWidget(caption)
            spin=QSpinBox();spin.setRange(minimum,maximum);spin.setValue(value);spin.setFixedSize(54,28);spin.setAccessibleName(title)
            row.addWidget(spin);self.action_layout.addWidget(group);self.photo_controls.append(group);setattr(self,attr,spin)
            self.style_groups.append((caption,title,spin))
            self.option_groups[attr]=group
        self.width_spin.valueChanged.connect(lambda value:self.change_style(width=value))
        self.width_spin.setToolTip('矩形或箭头的线宽')
        self.size_spin.valueChanged.connect(lambda value:self.change_style(size=value))
        self.brush_spin.valueChanged.connect(lambda value:self.change_style(brush=value))
        self.block_spin.valueChanged.connect(lambda value:self.change_style(block=value))
        self.brush_spin.setToolTip('马赛克涂抹范围的直径')
        self.block_spin.setToolTip('马赛克像素块的大小')
        for title,icon,attr,handler in [('撤销','undo','undo_button',self.undo),('重做','redo','redo_button',self.redo)]:
            button=QPushButton();button.setFixedSize(34,34);button.setIcon(line_icon(icon,ICON_COLOR));button.setIconSize(QSize(21,21))
            button.setToolTip(title+' · '+('Ctrl+Z' if icon=='undo' else 'Ctrl+Y'));button.setAccessibleName(title)
            button.clicked.connect(handler);self.action_layout.addWidget(button);self.photo_controls.append(button);setattr(self,attr,button)
        self.save_button=QPushButton('保存到桌面');self.save_button.setToolTip('保存 PNG，并复制到剪贴板')
        self.save_label='保存到桌面'
        self.save_button.setFixedHeight(34)
        self.save_button.clicked.connect(self.save);self.action_layout.addWidget(self.save_button);self.photo_controls.append(self.save_button)
        cancel=QPushButton();cancel.setFixedSize(34,34);cancel.setIcon(line_icon('close','#ff827c'));cancel.setIconSize(QSize(22,22))
        self.cancel_button=cancel
        cancel.setToolTip('取消 · Esc');cancel.setAccessibleName('取消截图');cancel.clicked.connect(self.cancelled.emit);self.action_layout.addWidget(cancel)
        self.confirm_button=QPushButton('完成 · 复制');self.confirm_button.setObjectName('confirmSelection')
        self.confirm_button.setFixedHeight(34)
        self.confirm_button.setIcon(line_icon('check','#ffffff'));self.confirm_button.setIconSize(QSize(18,18))
        self.confirm_button.setToolTip('仅复制，不创建图片文件 · Enter')
        self.confirm_button.clicked.connect(lambda:self.confirm());self.action_layout.addWidget(self.confirm_button)
        for index in range(self.action_layout.count()):
            self.action_layout.setAlignment(self.action_layout.itemAt(index).widget(),Qt.AlignmentFlag.AlignVCenter)
        for key,handler in [('Return',lambda:self.confirm(True)),('Enter',lambda:self.confirm(True)),('Escape',self.cancelled.emit),('Ctrl+Z',self.undo),('Ctrl+Y',self.redo)]:
            shortcut=QShortcut(QKeySequence(key),self);shortcut.activated.connect(handler)
        self.shortcuts=self.findChildren(QShortcut)
        self.actions.hide();self.refresh_options();self.refresh_toolbar();self.position_actions()
    def refresh_toolbar(self):
        if not hasattr(self,'hint_label'):return
        hint='框选后直接标注  ·  Enter 复制  ·  Esc 取消'
        if self.mode=='video':hint=audio_label(self.video_audio_mode)+'  ·  '+self.stop_key+' 停止'
        if self.mode=='long':hint='框选正文后上下滚动  ·  Enter 开始'
        if self.selection_locked:hint='区域已锁定  ·  Esc 取消'
        if self.error_text:hint=self.error_text
        self.hint_label.setToolTip('拖动选取区域；拖动边缘调整大小，内部移动。'+hint)
        width=max(70,min(320,self.width()-(500 if self.mode=='video' else 350)))
        self.hint_label.setText(self.hint_label.fontMetrics().elidedText(hint,Qt.TextElideMode.ElideRight,width))
        self.hint_label.setMaximumWidth(width)
        for mode,button in self.mode_buttons.items():
            button.setIcon(line_icon('video' if mode=='video' else 'capture','#ffffff' if button.isChecked() else MUTED_ICON_COLOR))
            button.setIconSize(QSize(16,16))
        if hasattr(self,'confirm_button'):self.position_actions()
    def set_video_audio_mode(self,mode,announce=False):
        if self.selection_locked:return
        self.video_audio_mode=normalize_audio_mode(mode)
        blocked=self.video_audio_combo.blockSignals(True)
        self.video_audio_combo.setCurrentIndex(1 if self.video_audio_mode=='system' else 0)
        self.video_audio_combo.blockSignals(blocked)
        self.refresh_toolbar()
        if self.mode=='video':self.confirm_button.setToolTip('开始'+audio_label(self.video_audio_mode)+'录屏')
        if announce:self.video_audio_changed.emit(self.video_audio_mode)
    def resizeEvent(self,event):
        super().resizeEvent(event);self.refresh_toolbar()
        if hasattr(self,'actions') and self.actions.isVisible():self.position_actions()
    def set_mode(self,mode,announce=False):
        if self.selection_locked:return
        if mode not in self.mode_buttons:return
        self.mode=mode;self.mode_buttons[mode].setChecked(True)
        self.video_audio_combo.setVisible(mode=='video')
        if self.canvas:self.canvas.finish_text();self.canvas.setVisible(mode=='photo')
        self.refresh_options()
        self.confirm_button.setText('开始录制  ↵' if mode=='video' else '开始长截图  ↵' if mode=='long' else '完成 · 复制')
        self.confirm_button.setToolTip('开始'+audio_label(self.video_audio_mode)+'录屏' if mode=='video' else '框选区域内上下滚动，自动拼接并去重' if mode=='long' else '仅复制，不创建图片文件 · Enter')
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
        if not hasattr(self,'confirm_button'):return
        r=self.selection_rect()
        selected=self.start is not None
        self.confirm_button.setVisible(selected)
        self.hint_label.setVisible(not selected or bool(self.error_text))
        available=max(1,self.width()-24)
        # One glass panel: inline modes on wide screens, a second internal row
        # on narrow screens. The completion action is never clipped or wrapped.
        if self._modes_stacked:
            self.toolbar_layout.removeWidget(self.modes)
            self.action_layout.insertWidget(0,self.modes);self._modes_stacked=False
        icons=[*self.tool_buttons.values(),self.undo_button,self.redo_button,self.cancel_button]
        for button in icons:button.setFixedSize(34,34)
        for button in self.color_buttons:button.setFixedSize(22,22)
        for caption,title,spin in self.style_groups:caption.setText(title);spin.setFixedWidth(54)
        self.action_layout.setSpacing(5)
        self.save_button.setText(self.save_label)
        if self.mode=='photo':self.confirm_button.setText('完成 · 复制')
        self.action_layout.invalidate()
        border=self.actions.frameWidth()*2
        margins=self.toolbar_layout.contentsMargins();padding=margins.left()+margins.right()+border
        self.modes.adjustSize()
        if self.action_layout.sizeHint().width()+padding>available:
            self.action_layout.removeWidget(self.modes)
            self.toolbar_layout.insertWidget(0,self.modes,0,Qt.AlignmentFlag.AlignLeft);self._modes_stacked=True
            self.action_layout.invalidate()
        if self.action_layout.sizeHint().width()+padding>available:
            for button in icons:button.setFixedSize(24,34)
            for button in self.color_buttons:button.setFixedSize(16,16)
            for caption,title,spin in self.style_groups:caption.setText(title[0]);spin.setFixedWidth(36)
            self.action_layout.setSpacing(2)
            self.save_button.setText('保存')
            if self.mode=='photo':self.confirm_button.setText('复制')
            self.action_layout.invalidate()
        self.toolbar_layout.invalidate()
        hint=self.toolbar_layout.sizeHint()
        self.actions.resize(min(available,hint.width()+border),hint.height()+border)
        self.toolbar_layout.activate()
        x=int(r.right())-self.actions.width() if selected else (self.width()-self.actions.width())//2
        x=max(8,min(self.width()-self.actions.width()-8,x))
        y=int(r.bottom())+12 if selected else self.height()-self.actions.height()-20
        if y+self.actions.height()>self.height()-8:y=int(r.top())-self.actions.height()-12
        y=max(8,min(self.height()-self.actions.height()-8,y))
        self.actions.move(x,y);self.actions.show();self.actions.raise_()

    def show_error(self,text):
        self.error_text=text;self.refresh_toolbar();self.hint_label.setToolTip(text)

    def set_tool(self,tool):
        self.tool=tool;self.tool_buttons[tool].setChecked(True)
        if self.canvas:self.canvas.set_tool(tool)
        self.refresh_options()

    def change_style(self,**style):
        kind=self.effective_tool()
        if kind in self.tool_preferences:
            self.tool_preferences[kind].update({k:v for k,v in style.items() if k in self.tool_preferences[kind]})
        if self.canvas:self.canvas.apply_style(**style)
        self.preferences_changed.emit(copy.deepcopy(self.tool_preferences))
        self.refresh_options()

    def effective_tool(self):
        if self.tool=='select' and self.canvas and self.canvas.selected_index is not None:
            return self.canvas.marks[self.canvas.selected_index][0]
        return self.tool

    def refresh_options(self):
        if not hasattr(self,'block_spin'):return
        kind=self.effective_tool();photo=self.mode=='photo' and self.start is not None
        for widget in self.photo_controls:widget.setVisible(photo)
        for button in self.color_buttons:button.setVisible(photo and kind in ('rectangle','arrow','text'))
        visible={'width_spin':kind in ('rectangle','arrow'),'size_spin':kind=='text',
                 'brush_spin':kind=='mask','block_spin':kind=='mask'}
        for attr,group in self.option_groups.items():group.setVisible(photo and visible[attr])
        values=dict(self.tool_preferences.get(kind,{}))
        if self.canvas and self.canvas.selected_index is not None:
            from .capture_markup import style_of
            mark=self.canvas.marks[self.canvas.selected_index];values.update(style_of(mark));values['color']=mark[4]
            if kind=='mask':values['brush']=values.get('brush',values.get('width',3)*4)
        for key,attr in [('width','width_spin'),('size','size_spin'),('brush','brush_spin'),('block','block_spin')]:
            if key in values:
                spin=getattr(self,attr);blocked=spin.blockSignals(True);spin.setValue(values[key]);spin.blockSignals(blocked)
        color=values.get('color','#e34f45')
        for button,choice in zip(self.color_buttons,COLORS):button.setChecked(choice==color)
        if self.canvas:
            self.canvas.color=color;self.canvas.line_width=self.width_spin.value();self.canvas.text_size=self.size_spin.value()
            self.canvas.brush_size=self.brush_spin.value();self.canvas.mosaic_block=self.block_spin.value();self.canvas.update()
        if self.actions.isVisible():self.position_actions()

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
        r=self.selection_rect();sx,sy=pixel_scale(self.image,self.size())
        origin=QPointF(selection_pixels(self.image,r,self.size()).topLeft())
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
        self.canvas.setGeometry(r.toRect())
        self.canvas.pixel_mapping=(sx,sy,origin.x()/sx-self.canvas.x(),origin.y()/sy-self.canvas.y())
        self.canvas.set_tool(self.tool)
        self.canvas.setVisible(self.mode=='photo');self.canvas.update();self.update_annotation_controls()
        self.actions.raise_();self.modes.raise_()

    def update_annotation_controls(self):
        self.undo_button.setEnabled(bool(self.canvas and self.canvas.history) and not self.selection_locked)
        self.redo_button.setEnabled(bool(self.canvas and self.canvas.future) and not self.selection_locked)
        self.refresh_options()
    def paintEvent(self,event):
        sx,sy=pixel_scale(self.image,self.size())
        snapshot_rect=QRectF(0,0,self.image.width()/sx,self.image.height()/sy)
        p=QPainter(self);p.drawImage(snapshot_rect,self.image);p.fillRect(self.rect(),QColor(7,15,26,112))
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if self.start is not None:
            r=self.selection_rect()
            p.save();p.setClipRect(r);p.drawImage(snapshot_rect,self.image);p.restore()
            p.setPen(QPen(QColor(SELECTION_COLOR),1.5));p.setBrush(Qt.BrushStyle.NoBrush);p.drawRect(r)
            corner=min(15,r.width()/3,r.height()/3)
            p.setPen(QPen(QColor(CORNER_COLOR),2,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
            for point,dx,dy in [(r.topLeft(),1,1),(r.topRight(),-1,1),(r.bottomLeft(),1,-1),(r.bottomRight(),-1,-1)]:
                p.drawLine(point,point+QPointF(dx*corner,0));p.drawLine(point,point+QPointF(0,dy*corner))
            p.setPen(QPen(QColor(HANDLE_COLOR),1.2));p.setBrush(QColor('#e5f5ff'))
            for point in self.handles().values():p.drawEllipse(point,3.5,3.5)
            font=QFont('Microsoft YaHei UI');font.setPixelSize(12);p.setFont(font)
            pixels=selection_pixels(self.image,r,self.size()) if r.width()>=2 and r.height()>=2 else None
            pixel_width=pixels.width() if pixels else 0
            pixel_height=pixels.height() if pixels else 0
            text=f'{pixel_width} × {pixel_height} px'
            badge_width=p.fontMetrics().horizontalAdvance(text)+26
            x=max(8,min(self.width()-badge_width-8,r.left()));y=max(8,r.top()-38)
            badge=QRectF(x,y,badge_width,28)
            if self.actions.isVisible() and badge.intersects(QRectF(self.actions.geometry())):badge.moveTop(max(8,r.top()+12))
            p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor(17,36,53,235));p.drawRoundedRect(badge,8,8)
            p.setPen(QColor('#e5f5ff'));p.drawText(badge,Qt.AlignmentFlag.AlignCenter,text)
        paint_panel_shadows(p,(self.actions,))
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
        if r.width()<2 or r.height()<2:
            self.start=self.end=None;self.refresh_options();self.position_actions();self.update();return
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
        if self.mode=='long':
            if self.selection_rect().width()>=80 and self.selection_rect().height()>=80:
                self.long_selected.emit(self.selection_rect())
            else:self.show_error('长截图请框选至少 80 × 80 的正文区域')
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
