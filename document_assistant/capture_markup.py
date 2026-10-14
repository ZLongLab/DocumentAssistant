"""Render editable annotation objects into native screenshot pixels."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen, QPolygonF

def style_of(mark):
    return mark[5] if len(mark)>5 else {'width':3,'size':22}

def mark_bounds(mark,image_size):
    kind,start,end,text,color=mark[:5]
    if kind=='text':
        font=QFont('Microsoft YaHei');font.setPixelSize(style_of(mark).get('size',22))
        return QFontMetricsF(font).boundingRect(QRectF(start.x(),start.y(),max(1,image_size.width()-start.x()),
            max(1,image_size.height()-start.y())),Qt.TextFlag.TextWordWrap,text)
    return QRectF(start,end).normalized()

def draw_annotation(painter,mark,image_size=None):
    kind,start,end,text,color=mark[:5];style=style_of(mark)
    width=style.get('width',3)
    painter.setPen(QPen(QColor(color),width));painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind=='mask':
        painter.fillRect(QRectF(start,end).normalized(),QColor('#162d24'))
    elif kind=='rectangle':painter.drawRect(QRectF(start,end).normalized())
    elif kind=='arrow':
        painter.drawLine(start,end);angle=math.atan2(end.y()-start.y(),end.x()-start.x());length=max(14,width*4)
        head=[end,QPointF(end.x()-length*math.cos(angle-.5),end.y()-length*math.sin(angle-.5)),
            QPointF(end.x()-length*math.cos(angle+.5),end.y()-length*math.sin(angle+.5))]
        painter.setBrush(QColor(color));painter.drawPolygon(QPolygonF(head))
    elif kind=='text':
        font=QFont('Microsoft YaHei');font.setPixelSize(style.get('size',22));painter.setFont(font)
        size=image_size or painter.device().size()
        painter.drawText(QRectF(start.x(),start.y(),max(1,size.width()-start.x()),max(1,size.height()-start.y())),Qt.TextFlag.TextWordWrap,text)

def render_annotations(image,marks):
    from PySide6.QtGui import QImage
    result=image.convertToFormat(QImage.Format.Format_ARGB32);result.setDevicePixelRatio(1)
    painter=QPainter(result);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    for mark in marks:draw_annotation(painter,mark,result.size())
    painter.end();return result
