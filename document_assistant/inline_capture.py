"""Edit screenshot annotations directly inside the selected screen region."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QLineEdit
from .capture_canvas import AnnotationCanvas
from .capture_markup import draw_annotation, mark_bounds
from .capture_material import SELECTION_COLOR, HANDLE_COLOR


class InlineAnnotationCanvas(AnnotationCanvas):
    def __init__(self, image, parent):
        super().__init__(image)
        self.setParent(parent)
        self.setMinimumSize(0, 0)
        self.setObjectName('inlineCaptureCanvas')
        self.text_editor = None
        self.text_anchor = None
        self.editing_mark = None
        self.brush_position = None
        self.setMouseTracking(True)
        self.set_tool('view')

    def scale(self):
        if hasattr(self,'pixel_mapping'):
            sx,sy,_,_=self.pixel_mapping
            return min(1/sx,1/sy)
        return min(self.width()/max(1,self.image.width()), self.height()/max(1,self.image.height()))

    def image_rect(self):
        if hasattr(self,'pixel_mapping'):
            sx,sy,x,y=self.pixel_mapping
            return QRectF(x,y,self.image.width()/sx,self.image.height()/sy)
        return QRectF(self.rect())

    def image_point(self, point):
        if not QRectF(self.rect()).contains(point):
            return None
        rect=self.image_rect()
        return QPointF((point.x()-rect.x())*self.image.width()/max(.01,rect.width()),
                       (point.y()-rect.y())*self.image.height()/max(.01,rect.height()))

    def set_tool(self, tool):
        self.finish_text()
        self.tool = tool
        self.start = self.end = None
        self.stroke = []
        self.selected_index = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, tool == 'view')
        self.brush_position = None
        if tool == 'mask':
            point=self.mapFromGlobal(QCursor.pos())
            if self.rect().contains(point):self.brush_position=QPointF(point)
        self.setCursor(Qt.CursorShape.BlankCursor if tool == 'mask' else
                       Qt.CursorShape.ArrowCursor if tool == 'select' else Qt.CursorShape.CrossCursor)
        self.selection_changed.emit()
        self.update()

    def wheelEvent(self, event):
        event.ignore()

    def resizeEvent(self, event):
        self.zoom_changed.emit(self.scale())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=self.image_rect()
        painter.drawImage(rect, self.rendered())
        painter.save()
        painter.translate(rect.topLeft())
        painter.scale(rect.width()/max(1,self.image.width()), rect.height()/max(1,self.image.height()))
        if self.start is not None and self.end is not None:
            draw_annotation(painter, self.new_mark(self.start,self.end), self.image.size(),
                            self.mosaic_source() if self.tool == 'mask' else None)
        if self.selected_index is not None and self.selected_index < len(self.marks):
            painter.setPen(QPen(QColor(SELECTION_COLOR),1.5/max(.01,self.scale()),Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(mark_bounds(self.marks[self.selected_index],self.image.size()).adjusted(-4,-4,4,4))
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(SELECTION_COLOR),1.5))
        painter.drawRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5))
        painter.setPen(QPen(QColor(HANDLE_COLOR),1.2))
        painter.setBrush(QColor('#e5f5ff'))
        x,y=self.width()/2,self.height()/2
        for point in (QPointF(0,0),QPointF(x,0),QPointF(self.width(),0),QPointF(self.width(),y),
                      QPointF(self.width(),self.height()),QPointF(x,self.height()),QPointF(0,self.height()),QPointF(0,y)):
            painter.drawEllipse(point,3.5,3.5)
        if self.tool == 'mask' and self.brush_position is not None:
            radius=self.brush_size*self.scale()/2
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(QColor('#16232c'),3))
            painter.drawEllipse(self.brush_position,radius,radius)
            painter.setPen(QPen(QColor('white'),1))
            painter.drawEllipse(self.brush_position,radius,radius)
        painter.end()

    def enterEvent(self,event):
        if self.tool=='mask':self.brush_position=QPointF(self.mapFromGlobal(QCursor.pos()));self.update()
        super().enterEvent(event)

    def leaveEvent(self,event):
        self.brush_position=None;self.update();super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button()==Qt.MouseButton.RightButton:
            self.parentWidget().cancelled.emit()
            return
        # Region handles remain available while an annotation tool is selected.
        point=event.position()+QPointF(self.pos())
        if any((handle-point).manhattanLength()<=10 for handle in self.parentWidget().handles().values()):
            self.parentWidget().begin_drag(point)
            return
        if self.tool=='text' and event.button()==Qt.MouseButton.LeftButton:
            self.finish_text()
            anchor=self.image_point(event.position())
            if anchor is not None:self.begin_text(anchor)
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.tool == 'mask':self.brush_position=event.position();self.update()
        if self.parentWidget().drag is not None:
            self.parentWidget().move_drag(event.position()+QPointF(self.pos()))
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.parentWidget().drag is not None:
            self.parentWidget().end_drag(event.position()+QPointF(self.pos()))
            return
        super().mouseReleaseEvent(event)

    def begin_text(self, anchor, text='', index=None):
        self.finish_text()
        self.text_anchor=QPointF(anchor)
        self.editing_mark=index
        editor=QLineEdit(self)
        editor.setMaxLength(500)
        editor.setText(text)
        editor.setPlaceholderText('输入文字，Enter 确认')
        editor.setStyleSheet('QLineEdit { color:#e8f2fa; background:#172a3b; border:1px solid #85c9ee; border-radius:4px; padding:4px; selection-background-color:#2c81ac; }')
        font=editor.font();font.setPixelSize(max(12,round(self.text_size*self.scale())));editor.setFont(font)
        rect=self.image_rect()
        x=round(rect.x()+anchor.x()*rect.width()/self.image.width())
        y=round(rect.y()+anchor.y()*rect.height()/self.image.height())
        editor.setGeometry(max(0,min(x,self.width()-60)),max(0,min(y,self.height()-30)),
                           max(30,min(300,self.width()-x)),max(24,min(40,self.height())))
        self.text_editor=editor
        editor.editingFinished.connect(self.finish_text)
        editor.show();editor.setFocus();editor.selectAll()

    def finish_text(self):
        editor=self.text_editor
        if editor is None:return
        self.text_editor=None
        text=editor.text().strip()
        editor.blockSignals(True);editor.hide();editor.deleteLater()
        if text:
            if self.editing_mark is None:
                mark=('text',QPointF(self.text_anchor),QPointF(self.text_anchor),text,self.color,
                      {'width':self.line_width,'size':self.text_size})
                self.append_mark(mark)
            elif self.editing_mark < len(self.marks):
                marks=list(self.marks);mark=list(marks[self.editing_mark]);mark[3]=text
                marks[self.editing_mark]=tuple(mark);self.commit(marks)
        self.text_anchor=self.editing_mark=None
        self.update()

    def edit_text(self):
        if self.selected_index is not None and self.marks[self.selected_index][0]=='text':
            mark=self.marks[self.selected_index]
            self.begin_text(mark[1],mark[3],self.selected_index)
