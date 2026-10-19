"""Blue night sky and cached, in-app frosted glass. No desktop capture is used."""
import math
import random
import time
from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QFrame, QWidget

STARRY_PALETTE = {
 'sidebar':'#101d2b','sidebar_hover':'#243b50','sidebar_footer':'#142536',
 'sidebar_footer_border':'#283e50','sidebar_separator':'#2a3c4d','footer_text':'#afc1d1',
 'footer_hover':'#263e52','nav_active':'#264860','nav_text':'#bbccda','nav_active_text':'#ffffff',
 'accent':'#8acdf5','accent_hover':'#b6e5ff','accent_light':'#203f54',
 'capture_start':'#267fae','capture_end':'#3d9ac2','text':'#eef6fc','muted':'#adbfce',
 'page_bg':'#070e19','card_bg':'#132332','card_border':'#2b4356','card_active_border':'#85c9ee',
 'card_active_bg':'#203e51','border':'#2d4253','input_focus':'#85c9ee',
 'primary_bg':'#287fad','primary_hover':'#399ac7','addfile_bg':'#287fad','addfile_hover':'#399ac7',
 'disabled_bg':'#1c2c3a','disabled_text':'#718699','check_bg':'#338eb9','selection_bg':'#294e68',
 'header_bg':'#1c2e3d','topbar_gradient_start':'#101c29','topbar_gradient_mid':'#101d2b',
 'topbar_gradient_end':'#172b3e','library_icon_bg':'#223e52','library_icon_border':'#43667e',
 'chip_bg':'#22394b','chip_border':'#436075','chip_text':'#c8e5f7','scrollbar':'#58748c',
 'statusbar_bg':'#0d1723','statusbar_text':'#a5b8c9','brand_mark_bg':'#28495c','sidebar_note':'#adbfce',
 'menu_bg':'#162838','menu_border':'#385368','menu_selected':'#2c4b62','tooltip_border':'#49677f',
 'step_active':'#338fbd','step_done':'#426b83','step_inactive_bg':'#243a4b',
 'step_inactive_text':'#c5d8e6','reason_bg':'#20394a','reason_text':'#d2e9f6',
 'table_selected_text':'#ffffff','table_selected_muted':'#d0e8f8',
 'warning_text':'#f3c98a','match_bg':'#3d617b',
}

STARRY_QSS = '''
QMainWindow, QDialog { background:#0b1521; }
QFrame#sidebar, QFrame#sidebarFooter, QFrame#list, QFrame#workflowBand, QFrame#actionbar {
 background:transparent; border:0; border-radius:16px;
}
QFrame#topbar, QFrame#topbar[library="true"] { background:transparent; border:0; }
QLabel#pageTitle { color:#f2f8fc; font-size:28px; font-weight:700; }
QLabel#subtitle { color:#adbfce; font-size:13px; }
QLabel#brand { font-size:12px; color:#ffffff; }
QPushButton { background:rgba(186,215,236,20); border:1px solid transparent; color:#e5f0f8; border-radius:9px; }
QPushButton:hover { background:rgba(186,215,236,38); }
QPushButton:pressed { background:rgba(100,170,213,55); }
QPushButton:focus { border-color:#85c9ee; }
QPushButton#nav { background:transparent; border:0; color:#bbccda; font-size:14px; padding:12px; }
QPushButton#nav:hover { background:rgba(177,213,238,18); }
QPushButton#nav:checked { background:rgba(133,201,238,38); border:0; color:white; }
QPushButton#primary, QPushButton#addFile, QPushButton#captureLaunch, QPushButton[prominent="true"] {
 background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #308bb7,stop:1 #266c9b);
 color:white; border:1px solid transparent; border-radius:10px;
}
QPushButton#primary:hover, QPushButton#addFile:hover, QPushButton#captureLaunch:hover, QPushButton[prominent="true"]:hover { background:#3b98c5; }
QPushButton:disabled, QPushButton#primary:disabled, QPushButton#addFile:disabled, QPushButton[prominent="true"]:disabled {
 background:rgba(164,190,209,12); border-color:transparent; color:#718699;
}
QPushButton#captureLaunch[secondary="true"] { background:rgba(186,215,236,18); border:0; color:#cbdfed; }
QPushButton#captureLaunch[secondary="true"]:hover { background:rgba(186,215,236,36); }
QFrame#dropzone { background:rgba(188,220,244,10); border:0; border-radius:12px; }
QFrame#fileCard { background:rgba(23,42,59,165); border:1px solid transparent; border-radius:14px; }
QFrame#fileCard:hover { background:rgba(48,76,98,180); border-color:transparent; }
QFrame#fileCard[active="true"] { border:1px solid #85c9ee; background:rgba(43,77,101,200); }
QFrame#detailPane, QWidget#detailContent { background:transparent; border:0; border-radius:14px; }
QFrame#emptyState { background:rgba(26,46,64,150); border:0; }
QLineEdit, QPlainTextEdit, QSpinBox, QComboBox, QPlainTextEdit#bodyPreview {
 background:rgba(9,21,33,145); color:#eef6fc; border:1px solid rgba(191,221,242,24); selection-color:white; selection-background-color:#376581;
}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus, QComboBox:focus { border:1px solid #85c9ee; }
QComboBox QAbstractItemView { background:#182c3d; color:#eef6fc; selection-background-color:#315771; }
QTabWidget::pane { background:transparent; border:0; }
QTabBar::tab { background:rgba(180,215,238,12); color:#adbfce; border:0; padding:7px 12px; }
QTabBar::tab:selected { background:rgba(133,201,238,38); color:white; }
QTableWidget, QTableWidget#libraryTable { background:transparent; alternate-background-color:rgba(191,221,242,7); color:#eef6fc; border:0; gridline-color:transparent; }
QTableWidget::item, QTableWidget#libraryTable::item { border:0; padding:10px 12px; }
QTableWidget::item:hover, QTableWidget#libraryTable::item:hover { background:rgba(159,208,239,15); }
QTableWidget::item:selected, QTableWidget#libraryTable::item:selected { background:rgba(101,178,225,52); color:white; }
QHeaderView, QTableCornerButton::section { background:transparent; border:0; }
QHeaderView::section, QTableWidget#libraryTable QHeaderView::section {
 background:rgba(190,220,241,12); color:#b4c9d9; border:0; padding:10px;
}
QCheckBox::indicator { background:#172d3e; border-color:#58768b; }
QScrollBar::handle:horizontal, QScrollBar::handle:vertical { background:rgba(155,189,212,90); }
QScrollBar:vertical, QScrollBar:horizontal { background:transparent; border:0; }
QScrollArea#cardScroll, QWidget#cardContent { background:transparent; }
QFrame#topbar[library="true"] QLabel#pageTitle { font-size:26px; }
QFrame#sidebarFooter QPushButton { background:transparent; border:0; }
QFrame#sidebarFooter QPushButton:hover { background:rgba(177,213,238,18); }
QStatusBar { background:#0d1723; color:#a5b8c9; border:0; }
'''


class StarfieldBackground(QWidget):
    """Cache the sky and its blur separately, so text is never blurred."""
    def __init__(self):
        super().__init__()
        self.starry = False
        self.background = '#070e19'
        self.reading_page = False
        self.sky = QImage()
        self.frost = QImage()
        self.cache_size = QSize()
        rng = random.Random(2318)
        self.stars = [(rng.random(), rng.random(), rng.uniform(.35,1.25), rng.random()) for _ in range(420)]
        self.epoch = time.monotonic()
        self.timer = QTimer(self)
        self.timer.setInterval(160)
        self.timer.timeout.connect(self.update)

    def set_theme(self, name, background):
        self.starry = name == 'starry'
        self.background = background
        if self.starry and self.isVisible() and not self.reading_page:
            self.timer.start()
        else:
            self.timer.stop()
        self.update()
        for panel in self.findChildren(GlassFrame):
            panel.update()

    def set_page(self, index):
        self.reading_page = index == 1
        self.set_theme('starry' if self.starry else '', self.background)

    def showEvent(self, event):
        super().showEvent(event)
        if self.starry and not self.reading_page:
            self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def ensure_sky(self):
        if self.cache_size == self.size() and not self.sky.isNull():
            return
        self.cache_size = self.size()
        width, height = max(1,self.width()), max(1,self.height())
        self.sky = QImage(width, height, QImage.Format.Format_ARGB32_Premultiplied)
        self.sky.fill(QColor('#070e19'))
        p = QPainter(self.sky)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        base = QLinearGradient(0, 0, width, height)
        base.setColorAt(0, QColor('#07121e'))
        base.setColorAt(.55, QColor('#122b40'))
        base.setColorAt(1, QColor('#050c16'))
        p.fillRect(self.sky.rect(), base)
        # A diagonal, layered blue/cyan nebula, deterministic across launches.
        rng = random.Random(925)
        for _ in range(46):
            x = rng.uniform(.12, 1.10)
            y = .94 - x*.75 + rng.uniform(-.19,.19)
            radius = rng.uniform(.09,.27)*width
            cloud = QRadialGradient(QPointF(x*width,y*height),radius)
            color = QColor(*rng.choice([(52,113,151),(39,91,136),(59,126,148),(94,136,158)]),rng.randint(12,35))
            cloud.setColorAt(0,color)
            cloud.setColorAt(.45,QColor(color.red(),color.green(),color.blue(),color.alpha()//2))
            cloud.setColorAt(1,QColor(color.red(),color.green(),color.blue(),0))
            p.fillRect(self.sky.rect(),cloud)
        p.setPen(Qt.PenStyle.NoPen)
        for x,y,r,brightness in self.stars:
            point = QPointF(x*width,y*height)
            alpha = int(65+brightness*150)
            if brightness > .92:
                p.setBrush(QColor(151,210,246,28))
                p.drawEllipse(point,r*4,r*4)
            p.setBrush(QColor(212,234,250,alpha))
            p.drawEllipse(point,r,r)
        p.end()
        # Downsample + smooth upsample is a cached spatial low-pass of the real
        # sky, rather than an alpha-only imitation or a blur on foreground text.
        small = self.sky.scaled(max(1,width//24),max(1,height//24),Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)
        self.frost = small.scaled(width,height,Qt.AspectRatioMode.IgnoreAspectRatio,Qt.TransformationMode.SmoothTransformation)

    def paintEvent(self, event):
        p = QPainter(self)
        if not self.starry:
            p.fillRect(self.rect(),QColor(self.background))
            return
        self.ensure_sky()
        p.drawImage(0,0,self.sky)
        if not self.reading_page:
            t = time.monotonic()-self.epoch
            p.setPen(Qt.PenStyle.NoPen)
            for x,y,r,phase in self.stars[::27]:
                p.setBrush(QColor(215,239,255,int(30+25*math.sin(t*.65+phase*6))))
                p.drawEllipse(QPointF(x*self.width(),y*self.height()),r*1.5,r*1.5)


class GlassFrame(QFrame):
    """Sample the root's blurred sky in matching coordinates; preserve native controls."""
    def paintEvent(self, event):
        if not paint_glass(self):
            super().paintEvent(event)


def paint_glass(widget):
    """Shared material for layout frames, file cards and the detail pane."""
    root = widget.parentWidget()
    while root is not None and not isinstance(root,StarfieldBackground):
        root = root.parentWidget()
    if root is None or not root.starry:
        return False
    root.ensure_sky()
    p = QPainter(widget)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    shape = QPainterPath()
    radius = 0 if widget.objectName() == 'sidebar' else 16
    shape.addRoundedRect(QRectF(widget.rect()),radius,radius)
    p.setClipPath(shape)
    origin = widget.mapTo(root,QPoint(0,0))
    p.drawImage(QRectF(widget.rect()),root.frost,QRectF(origin.x(),origin.y(),widget.width(),widget.height()))
    p.fillRect(widget.rect(),QColor(15,29,43,128 if widget.objectName() == 'sidebar' else 112))
    shine = QLinearGradient(0,0,0,min(130,widget.height()))
    shine.setColorAt(0,QColor(215,238,255,15))
    shine.setColorAt(1,QColor(215,238,255,0))
    p.fillRect(widget.rect(),shine)
    if widget.objectName() == 'fileCard':
        if widget.property('active'):
            p.fillRect(widget.rect(),QColor(113,187,233,28))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor('#85c9ee'),1))
            p.drawRoundedRect(QRectF(widget.rect()).adjusted(.5,.5,-.5,-.5),radius,radius)
        elif widget.underMouse():
            p.fillRect(widget.rect(),QColor(190,220,244,12))
    p.end()
    return True
