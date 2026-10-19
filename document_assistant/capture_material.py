"""Frosted capture controls sampled only from the existing frozen screenshot."""
from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame

SELECTION_COLOR = '#85c9ee'
CORNER_COLOR = '#c4eaff'
HANDLE_COLOR = '#639fc2'
ICON_COLOR = '#d4e5f1'
MUTED_ICON_COLOR = '#9fb8cb'

PANEL_STYLE = '''
QFrame#selectionPanel { background:#172a3b; border:0; border-radius:14px; }
QFrame#selectionPanel[frosted="true"] { background:transparent; }
QPushButton { font-family:"Microsoft YaHei UI"; font-size:12px; color:#e8f2fa; background:transparent; border:1px solid transparent; border-radius:8px; padding:7px 10px; }
QPushButton:hover { background:rgba(185,221,245,24); }
QPushButton:focus { border-color:#85c9ee; }
QPushButton:checked, QPushButton#confirmSelection { color:white; background:#2c81ac; font-weight:600; }
QPushButton:checked:hover, QPushButton#confirmSelection:hover { background:#3897c2; }
QPushButton:pressed { background:#235f83; }
QPushButton:disabled { color:#738c9e; background:transparent; border-color:transparent; }
QPushButton#colorChoice { border:2px solid transparent; border-radius:10px; padding:0; }
QPushButton#colorChoice:checked { border-color:#e4f5ff; }
QLabel, QLabel#selectionHint { font-family:"Microsoft YaHei UI"; font-size:12px; color:#b9cfdf; background:transparent; border:0; }
QSpinBox { color:#e8f2fa; background:rgba(6,19,31,105); border:1px solid rgba(194,222,243,25); border-radius:6px; padding:3px; }
QSpinBox:focus { border-color:#85c9ee; }
QComboBox#captureAudio { font-family:"Microsoft YaHei UI"; font-size:12px; color:#e8f2fa; background:rgba(184,218,242,18); border:1px solid transparent; border-radius:8px; padding:4px 8px; }
QComboBox#captureAudio:focus { border-color:#85c9ee; }
QComboBox#captureAudio QAbstractItemView { background:#172a3b; color:#e8f2fa; selection-background-color:#2c81ac; border:1px solid #37576d; }
QFrame#selectionDivider { background:rgba(187,219,242,35); border:0; }
QToolTip { background:#172a3b; color:#e8f2fa; border:0; padding:6px 9px; }
'''


class CaptureGlassPanel(QFrame):
    def __init__(self, overlay):
        super().__init__(overlay)
        self.setObjectName('selectionPanel')
        self.setProperty('frosted',True)
        self.setStyleSheet(PANEL_STYLE)

    def paintEvent(self, event):
        overlay = self.parentWidget()
        image = overlay.image
        key = (image.cacheKey(),overlay.width(),overlay.height())
        if getattr(overlay,'_capture_frost_key',None) != key:
            # One low-resolution cache per frozen image, shared by both bars.
            # The painter interpolates it at the panel's exact screen position.
            overlay._capture_frost = image.scaled(max(1,overlay.width()//18),max(1,overlay.height()//18),
                Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
            overlay._capture_frost_key = key
        frost = overlay._capture_frost
        origin = self.mapTo(overlay,QPoint(0,0))
        sx,sy = frost.width()/max(1,overlay.width()),frost.height()/max(1,overlay.height())
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        shape = QPainterPath();shape.addRoundedRect(QRectF(self.rect()),14,14)
        painter.setClipPath(shape)
        painter.drawImage(QRectF(self.rect()),frost,QRectF(origin.x()*sx,origin.y()*sy,self.width()*sx,self.height()*sy))
        painter.fillRect(self.rect(),QColor(12,28,43,218))
        shine = QLinearGradient(0,0,0,self.height())
        shine.setColorAt(0,QColor(210,235,255,18))
        shine.setColorAt(1,QColor(210,235,255,0))
        painter.fillRect(self.rect(),shine)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor(193,223,245,30),1))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5,.5,-.5,-.5),14,14)


def paint_panel_shadows(painter, panels):
    """A small shadow painted once, avoiding nested widget effect artifacts."""
    painter.setPen(Qt.PenStyle.NoPen)
    for panel in panels:
        if panel.isHidden():
            continue
        rect = QRectF(panel.geometry()).translated(0,3)
        for spread,alpha in ((8,3),(6,4),(4,5),(2,7),(0,12)):
            painter.setBrush(QColor(2,8,16,alpha))
            painter.drawRoundedRect(rect.adjusted(-spread,-spread,spread,spread),14+spread,14+spread)
