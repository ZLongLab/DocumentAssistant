"""Adjust a screen selection before opening the annotation editor."""
from PySide6.QtCore import QPointF,QRectF,Qt,Signal,QSize
from PySide6.QtGui import QColor,QPainter,QPen,QFont
from PySide6.QtWidgets import QWidget,QPushButton,QHBoxLayout,QFrame,QButtonGroup,QLabel,QGraphicsDropShadowEffect
from .capture_pixels import crop_selection
from .presentation import line_icon

PANEL_STYLE='''
QFrame#selectionPanel { background:#fffefb; border:1px solid #dce9e0; border-radius:16px; }
QPushButton { font-family:"Microsoft YaHei UI"; font-size:13px; color:#506c5b; background:transparent; border:1px solid transparent; border-radius:11px; padding:9px 15px; }
QPushButton:hover { background:#edf6f0; }
QPushButton:focus { border-color:#4ba681; }
QPushButton:checked, QPushButton#confirmSelection { color:white; background:#16966f; font-weight:600; }
QPushButton:checked:hover, QPushButton#confirmSelection:hover { background:#0f825f; }
QPushButton:disabled { color:#99ada0; background:#eef4ef; }
QLabel#selectionHint { font-family:"Microsoft YaHei UI"; font-size:12px; color:#7a8c80; background:transparent; border:0; }
QFrame#selectionDivider { background:#e0e9e2; border:0; }
'''

def panel_shadow(panel):
    effect=QGraphicsDropShadowEffect(panel);effect.setBlurRadius(22);effect.setOffset(0,5)
    effect.setColor(QColor(8,30,20,45));panel.setGraphicsEffect(effect)

class SelectionOverlay(QWidget):
    selected=Signal(object)
    video_selected=Signal(object)
    mode_changed=Signal(str)
    cancelled=Signal()
    def __init__(self,screen,image):
        super().__init__(None,Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint|Qt.WindowType.Tool)
        self.screen_ref,self.image=screen,image;self.start=self.end=None;self.drag=None;self.origin=None;self.press=None
        self.setCursor(Qt.CursorShape.CrossCursor);self.setMouseTracking(True)
        self.setWindowTitle('DocumentAssistant · 框选截图');self.setGeometry(screen.geometry())
        self.mode='photo';self.stop_key='Alt+S';self.selection_locked=False
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
        row=QHBoxLayout(self.actions);row.setContentsMargins(7,7,7,7);row.setSpacing(5)
        cancel=QPushButton('取消');cancel.setToolTip('Esc 或鼠标右键取消');cancel.clicked.connect(self.cancelled.emit);row.addWidget(cancel)
        self.confirm_button=QPushButton('编辑 / 复制  ↵');self.confirm_button.setObjectName('confirmSelection')
        self.confirm_button.setIcon(line_icon('copy','#ffffff'));self.confirm_button.setIconSize(QSize(16,16))
        self.confirm_button.clicked.connect(self.confirm);row.addWidget(self.confirm_button)
        self.actions.hide();self.refresh_toolbar()
    def refresh_toolbar(self):
        if not hasattr(self,'hint_label'):return
        hint='框选区域  ·  Enter 编辑  ·  Esc 取消'
        if self.mode=='video':hint='无声录屏  ·  '+self.stop_key+' 停止'
        if self.selection_locked:hint='区域已锁定  ·  Esc 取消'
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
        self.confirm_button.setText('开始录制  ↵' if mode=='video' else '编辑 / 复制  ↵')
        self.confirm_button.setIcon(line_icon('video' if mode=='video' else 'copy','#ffffff'))
        self.refresh_toolbar()
        if self.actions.isVisible():self.position_actions()
        self.update()
        if announce:self.mode_changed.emit(mode)
    def lock_selection(self):
        self.selection_locked=True;self.drag=None
        self.modes.setEnabled(False);self.confirm_button.setEnabled(False)
        self.setCursor(Qt.CursorShape.ArrowCursor);self.refresh_toolbar();self.update()
    def selection_rect(self):
        return QRectF(self.start,self.end).normalized() if self.start is not None else QRectF()
    def handles(self):
        r=self.selection_rect();x,y=r.center().x(),r.center().y()
        return {'nw':r.topLeft(),'n':QPointF(x,r.top()),'ne':r.topRight(),'e':QPointF(r.right(),y),
            'se':r.bottomRight(),'s':QPointF(x,r.bottom()),'sw':r.bottomLeft(),'w':QPointF(r.left(),y)}
    def position_actions(self):
        r=self.selection_rect();self.actions.adjustSize()
        x=max(8,min(self.width()-self.actions.width()-8,int(r.right())-self.actions.width()))
        y=int(r.bottom())+12
        if y+self.actions.height()>self.height()-8:y=max(8,int(r.top())-self.actions.height()-12)
        self.actions.move(x,y);self.actions.show()
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
            text=f'{round(r.width()*sx)} × {round(r.height()*sy)} px'
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
        point=event.position();self.press=point;self.origin=self.selection_rect();self.drag='new'
        if self.start is not None:
            self.drag=next((key for key,p in self.handles().items() if (p-point).manhattanLength()<=10),None)
            if self.drag is None:self.drag='move' if self.origin.contains(point) else 'new'
        if self.drag=='new':self.start=self.end=point
        self.actions.hide();self.update()
    def mouseMoveEvent(self,event):
        if self.selection_locked:return
        if self.drag is None:return
        point=QPointF(max(0,min(self.width(),event.position().x())),max(0,min(self.height(),event.position().y())))
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
        self.mouseMoveEvent(event);self.drag=None
        r=self.selection_rect()
        if r.width()<2 or r.height()<2:self.start=self.end=None;self.update();return
        self.start,self.end=r.topLeft(),r.bottomRight();self.position_actions();self.update()
    def confirm(self):
        if self.selection_locked:return
        if self.start is None:return
        if self.mode=='video':
            if self.selection_rect().width()>=2 and self.selection_rect().height()>=2:self.video_selected.emit(self.selection_rect())
            return
        try:image=crop_selection(self.image,self.selection_rect(),self.size())
        except ValueError:return
        self.selected.emit(image)
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.cancelled.emit()
        elif event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter):self.confirm()
