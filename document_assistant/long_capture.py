"""User-controlled scrolling capture with a click-through region outline."""
import ctypes
from collections import deque
from datetime import datetime
import hashlib
import json
import math
import marshal
import os
from pathlib import Path
import sys
import time
import uuid
from fractions import Fraction
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget
from .capture_pixels import crop_selection
from .long_stitch import VerticalStitcher
from .video_ui import controls_position


def capture_region(screen, rect, geometry):
    """Grab a padded region with the same physical origin as a full snapshot.

    Qt's grab offsets are logical integers. Align them to the DPR denominator
    first (e.g. multiples of 2 at 150%) so Qt rounding cannot move the crop.
    """
    ratio=screen.devicePixelRatio()
    fraction=Fraction(ratio).limit_denominator(16)
    if sys.platform!='win32' or abs(float(fraction)-ratio)>1e-6:
        return crop_selection(screen.grabWindow(0).toImage(),rect,geometry.size())
    bounds=QRectF(0,0,geometry.width(),geometry.height())
    rect=QRectF(rect).normalized().intersected(bounds)
    unit=fraction.denominator
    # Rounded logical screen extents can exceed the native framebuffer by one
    # pixel. At those edges let the full-snapshot crop clamp to its actual size.
    if unit>1 and (rect.right()>geometry.width()-unit or rect.bottom()>geometry.height()-unit):
        return crop_selection(screen.grabWindow(0).toImage(),rect,geometry.size())
    left=math.floor(rect.left()/unit)*unit;top=math.floor(rect.top()/unit)*unit
    right=math.ceil(rect.right()/unit)*unit;bottom=math.ceil(rect.bottom()/unit)*unit
    image=screen.grabWindow(0,left,top,right-left,bottom-top).toImage()
    x=math.floor(rect.left()*ratio)-round(left*ratio)
    y=math.floor(rect.top()*ratio)-round(top*ratio)
    width=math.ceil(rect.right()*ratio)-math.floor(rect.left()*ratio)
    height=math.ceil(rect.bottom()*ratio)-math.floor(rect.top()*ratio)
    if image.isNull() or x+width>image.width() or y+height>image.height():
        raise OSError('无法获取完整截图区域，请重新框选')
    image=image.copy(x,y,width,height);image.setDevicePixelRatio(1)
    return image


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
    diagnostic_requested = Signal()

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
        self.status = QLabel('在选区内向上或向下滚动，自动拼接新内容')
        self.status.setWordWrap(True); layout.addWidget(self.status)
        hint = QLabel(hotkey + ' 完成采集  ·  只框选正文，避开固定导航'); layout.addWidget(hint)
        diagnostic_row = QHBoxLayout()
        self.diagnostic_hint = QLabel('断接时可保存诊断，便于排查')
        diagnostic_row.addWidget(self.diagnostic_hint); diagnostic_row.addStretch()
        self.diagnostic_button = QPushButton('保存诊断'); self.diagnostic_button.setEnabled(False)
        self.diagnostic_button.setToolTip('保存断接前后的选区画面、短序列与已采集长图到本机；不会上传')
        self.diagnostic_button.clicked.connect(self.diagnostic_requested.emit)
        diagnostic_row.addWidget(self.diagnostic_button); layout.addLayout(diagnostic_row)
        self.setFixedWidth(460); self.adjustSize()

    def closeEvent(self, event):
        if not self.stopping:
            self.cancel_requested.emit()
        event.accept()


class LongCaptureSession(QObject):
    completed = Signal(object, str, int)
    cancelled = Signal()
    failed = Signal(str)

    def __init__(self, screen, rect, hotkey, parent=None, grabber=None, initial_frame=None):
        super().__init__(parent); self.screen = screen; self.rect = QRectF(rect); self.geometry = screen.geometry()
        self.grabber = grabber; self.stitcher = None; self.pending = None; self.done = False
        self.trace = deque(maxlen=90); self.diagnostic_failure = None
        self.diagnostic_frames = deque(maxlen=6)
        self.started_at = time.monotonic(); self.diagnostic_path = None
        default_home = Path(__file__).resolve().parents[2] / 'DocumentAssistant-local'
        self.diagnostic_home = Path(getattr(parent, 'home', None) or os.environ.get('DOCUMENTASSISTANT_HOME', default_home))
        self.initial_frame = initial_frame.copy() if initial_frame is not None else None
        self.controls = LongControls(hotkey); self.outline = None; self.keys = None
        self.controls.finish_requested.connect(self.finish); self.controls.cancel_requested.connect(self.cancel)
        self.controls.diagnostic_requested.connect(self.save_diagnostics)
        global_rect = QRectF(rect); global_rect.translate(self.geometry.topLeft())
        self.position = controls_position(screen.availableGeometry(), global_rect, self.controls.size())
        self.global_rect = global_rect
        self.timer = QTimer(self); self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16); self.timer.timeout.connect(self.poll)

    def frame(self):
        if self.screen.geometry() != self.geometry:
            raise OSError('屏幕尺寸或缩放发生变化，已停止继续拼接')
        if self.grabber:
            return crop_selection(self.grabber(),self.rect,self.geometry.size())
        return capture_region(self.screen,self.rect,self.geometry)

    def start(self):
        if self.done or self.stitcher:
            return
        try:
            self.stitcher = VerticalStitcher(self.initial_frame if self.initial_frame is not None else self.frame())
            self.initial_frame = None
            self.keys = CaptureKeys(self.finish, self.cancel)
            self.outline = RegionOutline(self.global_rect); self.outline.show()
            if self.position is not None:
                self.controls.move(self.position); self.controls.show()
            self.update_count(); self.timer.start()
            # The initial selection snapshot predates the overlay teardown. Catch
            # any wheel movement during that handoff before waiting another tick.
            self.poll()
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
            reference = self.stitcher.previous
            started = time.monotonic()
            result = self.stitcher.append(image)
            self.record_result(reference, image, result, started)
            messages = {'appended': '已拼接下方新内容，可继续向上或向下滚动',
                        'prepended': '已拼接上方新内容，可继续向上或向下滚动',
                        'covered': '正在查看已采集内容，越过上端或下端后继续扩展',
                        'unchanged': '等待滚动；向上或向下均可，结束时点完成',
                        'no_overlap': '未找到连续内容；可点“保存诊断”，回到最近位置后继续',
                        'size_changed': '画面大小改变，已保留当前长图'}
            if result.status == 'limit':
                self.finish('已达到长图大小上限，保留已采集内容'); return
            if result.status == 'size_changed':
                self.finish(messages[result.status]); return
            self.controls.status.setText(messages[result.status]); self.update_count()
        except Exception as exc:
            self.finish(str(exc))

    def record_result(self, reference, image, result, started):
        entry = {'elapsed_ms': round((time.monotonic()-self.started_at)*1000, 1),
                 'match_ms': round((time.monotonic()-started)*1000, 2),
                 'status': result.status, 'added': result.added,
                 'position': self.stitcher.position, 'height': self.stitcher.height,
                 'top': self.stitcher.top, 'bottom': self.stitcher.bottom,
                 'parts': len(self.stitcher.parts)}
        self.trace.append(entry)
        # Keep a tiny immutable window around the first failure, within 24 MiB
        # for the live and frozen windows together. No disk writes during capture.
        capacity=min(6,(12*1024*1024)//max(1,image.sizeInBytes()))
        changed=not self.diagnostic_frames or image!=self.diagnostic_frames[-1]['image']
        if changed and capacity:
            self.diagnostic_frames.append({'image': QImage(image), 'event': dict(entry)})
            while len(self.diagnostic_frames)>capacity:self.diagnostic_frames.popleft()
            if self.diagnostic_failure is not None and len(self.diagnostic_failure['context'])<capacity:
                self.diagnostic_failure['context'].append({'image': QImage(image), 'event': dict(entry)})
        if result.status == 'no_overlap':
            if self.diagnostic_failure is None:
                # QImage shares immutable buffers here; no full image copy on
                # every timer tick, and nothing is written until the user asks.
                self.diagnostic_failure = {'reference': QImage(reference), 'first': QImage(image),
                                           'first_event': dict(entry),
                                           'context': list(self.diagnostic_frames)[-min(capacity,max(2,(capacity+1)//2)):] if capacity else []}
            self.diagnostic_failure['latest'] = QImage(image)
            self.diagnostic_failure['latest_reference'] = QImage(reference)
            self.diagnostic_failure['latest_event'] = dict(entry)
            self.controls.diagnostic_button.setEnabled(True)

    def save_diagnostics(self):
        failure = self.diagnostic_failure
        if not failure or self.done:
            return
        try:
            target = self.diagnostic_home / 'capture-diagnostics' / (datetime.now().strftime('%Y%m%d_%H%M%S_')+uuid.uuid4().hex[:8])
            target.mkdir(parents=True, exist_ok=False)
            images = {'reference.png': failure['reference'], 'first-failed.png': failure['first'],
                      'latest-reference.png': failure['latest_reference'], 'latest-failed.png': failure['latest'],
                      'captured.png': self.stitcher.image()}
            context=[]
            for index,sample in enumerate(failure['context']):
                filename=f'context-{index:02}.png';images[filename]=sample['image']
                context.append({'file': filename, **sample['event']})
            for name, image in images.items():
                if not image.save(str(target/name), 'PNG'):
                    raise OSError('无法保存诊断画面：'+name)
            from . import long_stitch
            source = Path(long_stitch.__file__)
            report = {'format_version': 1, 'scope': '用户主动保存的长截图选区；不上传',
                      'source': str(source), 'source_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                      'loaded_code_sha256': hashlib.sha256(marshal.dumps(long_stitch.VerticalStitcher.append.__code__)
                                                           +marshal.dumps(long_stitch.vertical_shift.__code__)
                                                           +marshal.dumps(long_stitch._verify_shift.__code__)).hexdigest(),
                      'python': sys.version, 'device_pixel_ratio': self.screen.devicePixelRatio() if hasattr(self.screen, 'devicePixelRatio') else None,
                      'region': [self.rect.x(), self.rect.y(), self.rect.width(), self.rect.height()],
                      'image_size': [failure['first'].width(), failure['first'].height()],
                      'first_failure': failure['first_event'], 'latest_failure': failure['latest_event'],
                      'context': context, 'current_capture': {'file': 'captured.png', 'position': self.stitcher.position,
                          'top': self.stitcher.top, 'bottom': self.stitcher.bottom, 'height': self.stitcher.height},
                      'recent_results': list(self.trace)}
            (target/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            self.diagnostic_path = target
            self.controls.diagnostic_hint.setText('诊断已保存到本机')
            self.controls.diagnostic_hint.setToolTip(str(target))
            self.controls.status.setText('诊断已保存，可继续采集；文件位于 capture-diagnostics')
            self.controls.status.setToolTip(str(target))
        except Exception as exc:
            self.controls.diagnostic_hint.setText('保存失败，请重试')
            self.controls.diagnostic_hint.setToolTip(str(exc))

    def finish(self, warning=''):
        if self.done:
            return
        self.done = True; self.timer.stop()
        try:
            if not self.stitcher:
                raise ValueError('尚未获取长截图画面')
            # A pause is not required: the same strict overlap verifier decides
            # whether the final live frame is safe, even between timer ticks.
            if not warning:
                try:
                    frame = self.frame()
                    reference = self.stitcher.previous
                    started = time.monotonic()
                    result = self.stitcher.append(frame)
                    self.record_result(reference, frame, result, started)
                    if result.status == 'no_overlap':
                        warning = '最后一屏未能可靠拼接，已保留此前采集的内容'
                    elif result.status == 'size_changed':
                        warning = '最后一屏画面大小变化，已保留此前采集的内容'
                    elif result.status == 'limit':
                        warning = '已达到长图大小上限，保留已采集内容'
                except Exception as exc:
                    warning = str(exc)
            image = self.stitcher.image(); count = len(self.stitcher.parts)
            if count == 1:
                warning = '尚未拼接到新内容，当前只有一屏。请重新采集并框选正文；若已跳过整屏，请回到上次位置再继续。' + (' ' + warning if warning else '')
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
