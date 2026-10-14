"""Zoomable canvas with reversible annotation selection and editing."""
import copy,math
from PySide6.QtCore import QPointF,QRectF,Qt,Signal
from PySide6.QtGui import QColor,QPainter,QPainterPath,QPen
from PySide6.QtWidgets import QWidget,QInputDialog
from .capture_markup import draw_annotation,render_annotations,mark_bounds,style_of

class AnnotationCanvas(QWidget):
    changed=Signal()
    zoom_changed=Signal(float)
    selection_changed=Signal()
    def __init__(self,image):
        super().__init__();self.image=image;self.setObjectName('captureCanvas');self.setMinimumSize(240,120)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.marks=[];self.tool='view';self.color='#e34f45';self.line_width=3;self.text_size=22
        self.start=self.end=None;self.zoom=None;self.pan=QPointF();self.drag_position=None
        self.selected_index=None;self.moving=None;self.move_before=None
        self.history=[];self.future=[];self.cached_marks=None;self.cached_image=None
    def image_rect(self):
        scale=self.scale()
        return QRectF((self.width()-self.image.width()*scale)/2+self.pan.x(),(self.height()-self.image.height()*scale)/2+self.pan.y(),self.image.width()*scale,self.image.height()*scale)
    def scale(self):
        return self.zoom if self.zoom is not None else min(max(1,self.width()-48)/self.image.width(),max(1,self.height()-48)/self.image.height(),1)
    def clamp_pan(self):
        lx=max(0,(self.image.width()*self.scale()-self.width()+48)/2);ly=max(0,(self.image.height()*self.scale()-self.height()+48)/2)
        self.pan=QPointF(max(-lx,min(lx,self.pan.x())),max(-ly,min(ly,self.pan.y())))
    def set_zoom(self,value=None,anchor=None):
        old=self.scale();point=anchor or QPointF(self.rect().center());offset=point-QPointF(self.width()/2,self.height()/2)
        self.zoom=None if value is None else max(.05,min(4.,value))
        self.pan=QPointF() if value is None else offset-(offset-self.pan)*(self.scale()/old)
        self.clamp_pan();self.zoom_changed.emit(self.scale());self.update()
    def wheelEvent(self,event):
        if event.angleDelta().y():self.set_zoom(self.scale()*1.2**(event.angleDelta().y()/120),event.position())
        event.accept()
    def resizeEvent(self,event):super().resizeEvent(event);self.clamp_pan();self.zoom_changed.emit(self.scale())
    def image_point(self,point):
        rect=self.image_rect()
        if not rect.contains(point):return None
        return QPointF((point.x()-rect.x())/self.scale(),(point.y()-rect.y())/self.scale())
    def rendered(self):
        if self.cached_image is None or self.marks!=self.cached_marks:
            self.cached_image=render_annotations(self.image,self.marks);self.cached_marks=copy.deepcopy(self.marks)
        return self.cached_image
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),14,14);p.setClipPath(clip);p.fillRect(self.rect(),QColor('#182630'))
        rect=self.image_rect();p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#0c1821'));p.drawRoundedRect(rect.adjusted(-5,-5,5,7),5,5)
        p.fillRect(rect,QColor('white'));p.drawImage(rect,self.rendered())
        p.save();p.setClipRect(rect);p.translate(rect.topLeft());p.scale(self.scale(),self.scale())
        if self.start is not None and self.end is not None:draw_annotation(p,self.new_mark(self.start,self.end),self.image.size())
        if self.selected_index is not None and self.selected_index<len(self.marks):
            p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#48e0b1'),1.5/self.scale(),Qt.PenStyle.DashLine))
            p.drawRect(mark_bounds(self.marks[self.selected_index],self.image.size()).adjusted(-4,-4,4,4))
        p.restore();p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#65717b'),1));p.drawRect(rect);p.end()
    def new_mark(self,start,end,text=''):
        return (self.tool,QPointF(start),QPointF(end),text,self.color,{'width':self.line_width,'size':self.text_size})
    def commit(self,marks,before=None):
        before=copy.deepcopy(self.marks) if before is None else before
        if before==marks:return
        self.history.append(before);self.future.clear();self.marks=copy.deepcopy(marks)
        self.changed.emit();self.update()
    def append_mark(self,mark):self.commit(self.marks+[mark])
    def pick(self,point):
        for index in range(len(self.marks)-1,-1,-1):
            mark=self.marks[index];bounds=mark_bounds(mark,self.image.size()).adjusted(-8/self.scale(),-8/self.scale(),8/self.scale(),8/self.scale())
            if not bounds.contains(point):continue
            if mark[0]=='arrow':
                a,b=mark[1:3];dx,dy=b.x()-a.x(),b.y()-a.y();length=dx*dx+dy*dy
                t=max(0,min(1,((point.x()-a.x())*dx+(point.y()-a.y())*dy)/max(length,1)))
                if math.hypot(point.x()-a.x()-t*dx,point.y()-a.y()-t*dy)>max(8/self.scale(),style_of(mark).get('width',3)*2):continue
            return index
        return None
    def mousePressEvent(self,event):
        self.setFocus()
        if event.button()==Qt.MouseButton.MiddleButton or event.button()==Qt.MouseButton.LeftButton and self.tool=='view':
            self.drag_position=event.position();self.setCursor(Qt.CursorShape.ClosedHandCursor);return
        if event.button()!=Qt.MouseButton.LeftButton:return
        point=self.image_point(event.position())
        if point is None:return
        if self.tool=='select':
            self.selected_index=self.pick(point);self.selection_changed.emit();self.update()
            if self.selected_index is not None:self.moving=point;self.move_before=copy.deepcopy(self.marks)
        elif self.tool=='text':
            text,ok=QInputDialog.getText(self,'添加文字','文字内容（最多 500 字）')
            if ok and text.strip():self.append_mark(self.new_mark(point,point,text[:500]))
        else:self.start=self.end=point;self.update()
    def mouseMoveEvent(self,event):
        if self.drag_position is not None:
            self.pan+=event.position()-self.drag_position;self.drag_position=event.position();self.clamp_pan();self.update();return
        point=self.image_point(event.position())
        if self.moving is not None and point is not None:
            mark=list(self.move_before[self.selected_index]);delta=point-self.moving
            bounds=mark_bounds(mark,self.image.size())
            delta=QPointF(max(-bounds.left(),min(self.image.width()-bounds.right(),delta.x())),max(-bounds.top(),min(self.image.height()-bounds.bottom(),delta.y())))
            mark[1]=QPointF(mark[1])+delta;mark[2]=QPointF(mark[2])+delta;self.marks[self.selected_index]=tuple(mark);self.update()
        elif self.start is not None:self.end=point or self.end;self.update()
    def mouseReleaseEvent(self,event):
        if self.drag_position is not None and event.button() in (Qt.MouseButton.LeftButton,Qt.MouseButton.MiddleButton):
            self.drag_position=None;self.unsetCursor();return
        if event.button()!=Qt.MouseButton.LeftButton:return
        if self.moving is not None:
            self.mouseMoveEvent(event);self.commit(self.marks,self.move_before);self.moving=self.move_before=None
        elif self.start is not None:
            self.end=self.image_point(event.position()) or self.end
            if math.hypot(self.end.x()-self.start.x(),self.end.y()-self.start.y())>=2:self.append_mark(self.new_mark(self.start,self.end))
            self.start=self.end=None;self.update()
    def mouseDoubleClickEvent(self,event):
        if self.tool=='select':
            point=self.image_point(event.position())
            if point is not None:self.selected_index=self.pick(point);self.edit_text()
    def delete_selected(self):
        if self.selected_index is None:return
        marks=list(self.marks);marks.pop(self.selected_index);self.selected_index=None;self.commit(marks);self.selection_changed.emit()
    def edit_text(self):
        if self.selected_index is None or self.marks[self.selected_index][0]!='text':return
        mark=list(self.marks[self.selected_index]);text,ok=QInputDialog.getText(self,'修改文字','文字内容（最多 500 字）',text=mark[3])
        if ok and text.strip():mark[3]=text[:500];marks=list(self.marks);marks[self.selected_index]=tuple(mark);self.commit(marks)
    def apply_style(self,color=None,width=None,size=None):
        if color is not None:self.color=color
        if width is not None:self.line_width=width
        if size is not None:self.text_size=size
        if self.selected_index is None:return
        mark=list(self.marks[self.selected_index]);style=dict(style_of(mark))
        if color is not None:mark[4]=color
        if width is not None:style['width']=width
        if size is not None:style['size']=size
        mark=mark[:5]+[style];marks=list(self.marks);marks[self.selected_index]=tuple(mark);self.commit(marks)
    def undo(self):
        if self.history:self.future.append(copy.deepcopy(self.marks));self.marks=self.history.pop()
        elif self.marks:self.future.append(copy.deepcopy(self.marks));self.marks=self.marks[:-1]
        else:return
        self.selected_index=None;self.changed.emit();self.selection_changed.emit();self.update()
    def redo(self):
        if not self.future:return
        self.history.append(copy.deepcopy(self.marks));self.marks=self.future.pop();self.selected_index=None
        self.changed.emit();self.selection_changed.emit();self.update()
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Delete,Qt.Key.Key_Backspace):self.delete_selected()
        else:super().keyPressEvent(event)
