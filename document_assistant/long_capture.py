"""User-controlled scrolling capture with a click-through region outline."""
import ctypes
import sys
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .capture_pixels import crop_selection
from .long_stitch import VerticalStitcher, frames_settled
from .video_ui import controls_position


class CaptureKeys(QAbstractNativeEventFilter):
    def __init__(self, finish, cancel):
        super().__init__(); self.app = QApplication.instance(); self.registered = {}
        if sys.platform == 'win32':
            self.user32 = ctypes.WinDLL('user32', use_last_error=True)
            self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            for ident, key, callback in ((0x4DA0, 0x0D, finish), (0x4DA1, 0x1B, cancel)):
                if self.user32.RegisterHotKey(None, ident, 0x4000, key):
                    self.registered[ident] = callback
            self.app.installNativeEventFilter(self)

    def nativeEventFilter(self, event_type, message):
        if sys.platform == 'win32':
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == 0x0312 and int(msg.wParam) in self.registered:
                QTimer.singleShot(0, self.registered[int(msg.wParam)])
                return True, 0
        return False, 0

    def shutdown(self):
        if sys.platform == 'win32':
            for ident in self.registered:
                self.user32.UnregisterHotKey(None, ident)
            self.app.removeNativeEventFilter(self)
        self.registered.clear()


class RegionOutline(QWidget):
    def __init__(self, region):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.WindowTransparentForInput)
        self.setWindowTitle('长截图区域 · DocumentAssistant')
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setGeometry(region.toAlignedRect().adjusted(-4, -4, 4, 4))

    def paintEvent(self, event):
        p = QPainter(self); p.setPen(QPen(QColor('#41d4a5'), 2)); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(self.rect().adjusted(1, 1, -2, -2)); p.end()


class LongControls(QWidget):
    finish_requested = Signal()
    cancel_requested = Signal()

    def __init__(self, hotkey):
        super().__init__(None, Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('正在采集长截图 · DocumentAssistant'); self.stopping = False
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet('QWidget{background:#20292b;color:#edf5f0;font-family:"Microsoft YaHei UI";font-size:12px;border-radius:12px;}'
                          'QLabel#longCount{font-size:15px;font-weight:600;color:#71f3c6;}'
                          'QPushButton{padding:8px 14px;border:0;border-radius:8px;background:#354448;}'
                          'QPushButton:hover{background:#42565a;} QPushButton#longFinish{background:#148968;color:white;font-weight:600;}')
        layout = QVBoxLayout(self); layout.setContentsMargins(16, 12, 12, 12); layout.setSpacing(8)
        top = QHBoxLayout(); self.count = QLabel('长截图 · 准备采集'); self.count.setObjectName('longCount'); top.addWidget(self.count)
        top.addStretch(); cancel = QPushButton('取消'); cancel.clicked.connect(self.cancel_requested.emit); top.addWidget(cancel)
        self.finish_button = QPushButton('完成采集'); self.finish_button.setObjectName('longFinish')
        self.finish_button.clicked.connect(self.finish_requested.emit); top.addWidget(self.finish_button); layout.addLayout(top)
        self.status = QLabel('在选区内向下滚动，自动采集中间画面'); layout.addWidget(self.status)
        hint = QLabel(hotkey + ' 完成采集  ·  只框选正文，避开固定导航'); layout.addWidget(hint)
        self.setFixedWidth(460); self.adjustSize()

    def closeEvent(self, event):
        if not self.stopping:
            self.cancel_requested.emit()
        event.accept()


class LongCaptureSession(QObject):
    completed = Signal(object, str, int)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, screen, rect, hotkey, parent=None, grabber=None):
        super().__init__(parent); self.screen = screen; self.rect = QRectF(rect); self.geometry = screen.geometry()
        self.grabber = grabber; self.stitcher = None; self.pending = None; self.done = False
        self.controls = LongControls(hotkey); self.outline = None; self.keys = None
        self.controls.finish_requested.connect(self.finish); self.controls.cancel_requested.connect(self.cancel)
        global_rect = QRectF(rect); global_rect.translate(self.geometry.topLeft())
        self.position = controls_position(screen.availableGeometry(), global_rect, self.controls.size())
        self.global_rect = global_rect
        self.timer = QTimer(self); self.timer.setInterval(200); self.timer.timeout.connect(self.poll)

    def frame(self):
        if self.screen.geometry() != self.geometry:
            raise OSError('屏幕尺寸或缩放发生变化，已停止继续拼接')
        image = self.grabber() if self.grabber else self.screen.grabWindow(0).toImage()
        return crop_selection(image, self.rect, self.geometry.size())

    def start(self):
        if self.done or self.stitcher:
            return
        try:
            self.stitcher = VerticalStitcher(self.frame())
            self.keys = CaptureKeys(self.finish, self.cancel)
            self.outline = RegionOutline(self.global_rect); self.outline.show()
            if self.position is not None:
                self.controls.move(self.position); self.controls.show()
            self.update_count(); self.timer.start()
        except Exception as exc:
            self.done = True; self.teardown(); self.failed.emit(str(exc))

    def update_count(self):
        if self.stitcher:
            count = len(self.stitcher.parts)
            self.controls.count.setText(f'{count} 段 · {self.stitcher.width} × {self.stitcher.height} px' + (' · 尚未拼接' if count == 1 else ''))

    def poll(self):
        if self.done:
            return
        try:
            image = self.frame()
            # Verify every captured overlap, including frames during a scroll.
            # Waiting for two stationary frames loses the intermediate screens.
            self.pending = image
            result = self.stitcher.append(image)
            messages = {'appended': '已拼接新内容，继续向下滚动', 'unchanged': '等待向下滚动；到页底后点完成',
                        'upward': '暂不拼接向上滚动的内容，请回到已采集位置再向下',
                        'no_overlap': '未找到可靠重叠，请向上回一点，再小幅向下滚动',
                        'size_changed': '画面大小改变，已保留当前长图'}
            if result.status == 'limit':
                self.finish('已达到长图大小上限，保留已采集内容'); return
            if result.status == 'size_changed':
                self.finish(messages[result.status]); return
            self.controls.status.setText(messages[result.status]); self.update_count()
        except Exception as exc:
            self.finish(str(exc))

    def finish(self, warning=''):
        if self.done:
            return
        self.done = True; self.timer.stop()
        try:
            if not self.stitcher:
                raise ValueError('尚未获取长截图画面')
            # Only accept a final frame that had already stopped moving.
            if not warning and self.pending is not None:
                try:
                    frame = self.frame()
                    if frames_settled(self.pending, frame):
                        result = self.stitcher.append(frame)
                        if result.status in ('no_overlap', 'upward'):
                            warning = '最后一屏未能可靠拼接，已保留此前采集的内容'
                except Exception as exc:
                    warning = str(exc)
            image = self.stitcher.image(); count = len(self.stitcher.parts)
            if count == 1:
                warning = '尚未拼接到新内容，当前只有一屏。请重新采集：框选正文，每次向下滚动约半屏后停一下。' + (' ' + warning if warning else '')
            self.teardown(); self.completed.emit(image, warning, count)
        except Exception as exc:
            self.teardown(); self.failed.emit(str(exc))

    def cancel(self):
        if self.done:
            return
        self.done = True; self.teardown(); self.cancelled.emit()

    def teardown(self):
        self.timer.stop()
        if self.keys:
            self.keys.shutdown(); self.keys = None
        if self.outline:
            self.outline.close(); self.outline.deleteLater(); self.outline = None
        self.controls.stopping = True; self.controls.close(); self.controls.deleteLater()
