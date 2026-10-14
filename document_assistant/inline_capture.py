"""Edit screenshot annotations directly inside the selected screen region."""
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLineEdit
from .capture_canvas import AnnotationCanvas
from .capture_markup import draw_annotation, mark_bounds


class InlineAnnotationCanvas(AnnotationCanvas):
    def __init__(self, image, parent):
        super().__init__(image)
        self.setParent(parent)
        self.setMinimumSize(0, 0)
        self.setObjectName('inlineCaptureCanvas')
        self.text_editor = None
        self.text_anchor = None
        self.editing_mark = None
        self.set_tool('view')

    def scale(self):
        return min(self.width()/max(1,self.image.width()), self.height()/max(1,self.image.height()))

    def image_rect(self):
        return QRectF(self.rect())

    def image_point(self, point):
        if not self.image_rect().contains(point):
            return None
        return QPointF(point.x()*self.image.width()/max(1,self.width()),
                       point.y()*self.image.height()/max(1,self.height()))

    def set_tool(self, tool):
        self.finish_text()
        self.tool = tool
        self.start = self.end = None
        self.selected_index = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, tool == 'view')
        self.setCursor(Qt.CursorShape.ArrowCursor if tool == 'select' else Qt.CursorShape.CrossCursor)
        self.selection_changed.emit()
        self.update()

    def wheelEvent(self, event):
        event.ignore()

    def resizeEvent(self, event):
        self.zoom_changed.emit(self.scale())

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.drawImage(QRectF(self.rect()), self.rendered())
        painter.save()
        painter.scale(self.width()/max(1,self.image.width()), self.height()/max(1,self.image.height()))
        if self.start is not None and self.end is not None:
            draw_annotation(painter, self.new_mark(self.start,self.end), self.image.size())
        if self.selected_index is not None and self.selected_index < len(self.marks):
            painter.setPen(QPen(QColor('#41d4a5'),1.5/max(.01,self.scale()),Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(mark_bounds(self.marks[self.selected_index],self.image.size()).adjusted(-4,-4,4,4))
        painter.restore()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor('#41d4a5'),1.5))
        painter.drawRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5))
        painter.setBrush(QColor('white'))
        x,y=self.width()/2,self.height()/2
        for point in (QPointF(0,0),QPointF(x,0),QPointF(self.width(),0),QPointF(self.width(),y),
                      QPointF(self.width(),self.height()),QPointF(x,self.height()),QPointF(0,self.height()),QPointF(0,y)):
            painter.drawEllipse(point,3.5,3.5)
        painter.end()

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
        editor.setStyleSheet('QLineEdit { color:#172e25; background:white; border:1px solid #41d4a5; border-radius:4px; padding:4px; }')
        font=editor.font();font.setPixelSize(max(12,round(self.text_size*self.scale())));editor.setFont(font)
        x=round(anchor.x()*self.width()/self.image.width())
        y=round(anchor.y()*self.height()/self.image.height())
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
