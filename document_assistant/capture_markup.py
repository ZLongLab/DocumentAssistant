"""Render editable annotation objects into native screenshot pixels."""
import math
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPainterPathStroker, QPen, QPolygonF

def style_of(mark):
    return mark[5] if len(mark)>5 else {'width':3,'size':22}

def mosaic_path(mark):
    """A rounded brush stroke; offsets remain valid when the crop or mark moves."""
    style=style_of(mark);points=style.get('path')
    path=QPainterPath()
    if not points:
        path.addRect(QRectF(mark[1],mark[2]).normalized())
        return path
    start=mark[1];diameter=max(4,style.get('brush',style.get('width',3)*4))
    first=start+QPointF(*points[0])
    if len(points)==1:
        path.addEllipse(first,diameter/2,diameter/2)
        return path
    path.moveTo(first)
    for x,y in points[1:]:path.lineTo(start+QPointF(x,y))
    stroker=QPainterPathStroker();stroker.setWidth(diameter)
    stroker.setCapStyle(Qt.PenCapStyle.RoundCap);stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return stroker.createStroke(path)

def pixelated_image(image,block=6):
    """Average small cells, then enlarge without smoothing to retain mosaic blocks."""
    tiny=image.scaled(max(1,math.ceil(image.width()/block)),max(1,math.ceil(image.height()/block)),
        Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
    result=tiny.scaled(image.size(),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.FastTransformation)
    result.setDevicePixelRatio(1)
    return result

def mark_bounds(mark,image_size):
    kind,start,end,text,color=mark[:5]
    if kind=='mask':return mosaic_path(mark).boundingRect()
    if kind=='text':
        font=QFont('Microsoft YaHei');font.setPixelSize(style_of(mark).get('size',22))
        return QFontMetricsF(font).boundingRect(QRectF(start.x(),start.y(),max(1,image_size.width()-start.x()),
            max(1,image_size.height()-start.y())),Qt.TextFlag.TextWordWrap,text)
    return QRectF(start,end).normalized()

def draw_annotation(painter,mark,image_size=None,mosaic=None):
    kind,start,end,text,color=mark[:5];style=style_of(mark)
    width=style.get('width',3)
    painter.setPen(QPen(QColor(color),width));painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind=='mask':
        if mosaic is not None:
            painter.save();painter.setClipPath(mosaic_path(mark),Qt.ClipOperation.IntersectClip)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform,False)
            painter.drawImage(QPointF(),mosaic);painter.restore()
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
    mosaic=None;block=None
    for mark in marks:
        if mark[0]=='mask':
            requested=style_of(mark).get('block',6)
            if requested!=block:mosaic=pixelated_image(image,requested);block=requested
        draw_annotation(painter,mark,result.size(),mosaic)
    painter.end();return result
