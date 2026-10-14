"""Small native decorations for the library heading and action menus."""
from PySide6.QtCore import QRectF,Qt
from PySide6.QtGui import QColor,QFont,QPainter,QPen
from PySide6.QtWidgets import QMenu,QWidget

class ActionMenu(QMenu):
    def __init__(self,title='',parent=None):
        super().__init__(title,parent);self.caption=title or '工作台工具'
        self.setObjectName('actionMenu');self.setMinimumWidth(222)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint,True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground,True)
    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self);font=QFont(self.font());font.setPixelSize(11);font.setBold(True)
        p.setFont(font);p.setPen(QColor('#71897b'))
        p.drawText(self.rect().adjusted(16,8,-12,0),Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignLeft,self.caption)
        p.end()

class LibraryFlourish(QWidget):
    def __init__(self):
        super().__init__();self.setFixedSize(116,72);self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setToolTip('文档库装饰图案')
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#dcebdc'));p.drawEllipse(QRectF(12,8,66,60))
        for x,y,angle,color in ((55,13,14,'#e3e9d8'),(43,11,-10,'#d2e3d5'),(37,10,0,'#fffdf9')):
            p.save();p.translate(x,y);p.rotate(angle);p.setBrush(QColor(color));p.setPen(QPen(QColor('#b7cdbd'),1))
            p.drawRoundedRect(QRectF(0,0,39,50),5,5)
            p.setPen(QPen(QColor('#9bb6a4'),1.5))
            for line,width in ((14,23),(21,19),(28,23)):p.drawLine(8,line,width+8,line)
            p.restore()
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(QColor('#ed8a4b'));p.drawEllipse(QRectF(18,51,10,10))
        p.setBrush(QColor('#85ad91'));p.drawEllipse(QRectF(91,12,5,5));p.end()
