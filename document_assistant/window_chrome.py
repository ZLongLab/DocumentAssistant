"""Theme Windows' native caption without replacing native window interactions."""
import ctypes
import sys
from ctypes import wintypes
from PySide6.QtCore import QEvent,QObject,QTimer
from PySide6.QtGui import QGuiApplication


def colorref(hex_color):
    value=hex_color.lstrip('#')
    red,green,blue=(int(value[i:i+2],16) for i in (0,2,4))
    return red|(green<<8)|(blue<<16)


def caption_palette(theme):
    from .theme import THEME_COLORS,normalize_theme
    theme=normalize_theme(theme);colors=THEME_COLORS[theme]
    return {'dark':theme=='starry',
            'caption':'#0b1b2a' if theme=='starry' else colors['page_bg'],
            'text':colors['text'],
            'border':0xfffffffe if theme=='starry' else 0xffffffff}


def apply_native_caption(hwnd,theme):
    if sys.platform!='win32':return {}
    palette=caption_palette(theme)
    api=ctypes.WinDLL('dwmapi',use_last_error=True)
    setter=api.DwmSetWindowAttribute
    setter.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    setter.restype=ctypes.c_long
    values={20:int(palette['dark']),34:palette['border'],35:colorref(palette['caption']),36:colorref(palette['text'])}
    result={}
    for attribute,value in values.items():
        data=wintypes.DWORD(value)
        result[attribute]=int(setter(hwnd,attribute,ctypes.byref(data),ctypes.sizeof(data)))
    if result[20]<0:
        # Older Windows 10 versions expose the earlier dark-caption attribute.
        data=wintypes.DWORD(int(palette['dark']))
        result[19]=int(setter(hwnd,19,ctypes.byref(data),ctypes.sizeof(data)))
    # No style/geometry change: native resize, snap, drag, system menu and caption
    # buttons retain their Windows behavior. Unsupported attributes degrade safely.
    return result


class WindowChrome(QObject):
    def __init__(self,window,theme):
        super().__init__(window)
        self.window=window;self.theme=theme;self.last_result={}
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.timeout.connect(self.apply)
        window.installEventFilter(self)
        self.timer.start(0)

    def set_theme(self,theme):
        self.theme=theme;self.timer.start(0)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Show:
            self.apply()  # Theme the native caption before the first visible paint.
        elif event.type() in (QEvent.Type.WinIdChange,QEvent.Type.WindowActivate,
                QEvent.Type.WindowDeactivate,QEvent.Type.WindowStateChange,QEvent.Type.PaletteChange,
                QEvent.Type.ApplicationPaletteChange):
            self.timer.start(0)
        return False

    def apply(self):
        if sys.platform!='win32' or QGuiApplication.platformName()!='windows':return
        handle=self.window.windowHandle()
        if handle is None:return
        self.last_result=apply_native_caption(int(handle.winId()),self.theme)
