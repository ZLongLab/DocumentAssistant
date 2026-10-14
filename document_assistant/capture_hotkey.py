"""Windows global hotkeys scoped to this running process, without keyboard hooks."""
import ctypes
import sys
from ctypes import wintypes
from PySide6.QtCore import QAbstractNativeEventFilter, QTimer


def parse_hotkey(text):
    parts = [p.strip().upper() for p in text.split('+')]
    if len(parts) < 2 or len(set(parts)) != len(parts):
        raise ValueError('例如 Alt+S；请使用 Ctrl 或 Alt 加一个字母、数字或 F 键')
    modifiers = {'CTRL': 2, 'ALT': 1, 'SHIFT': 4}
    if any(p not in modifiers for p in parts[:-1]) or not {'CTRL','ALT'}.intersection(parts[:-1]):
        raise ValueError('快捷键需要 Ctrl 或 Alt；可附加 Shift')
    key = parts[-1]
    if len(key)==1 and key in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789':
        code = ord(key)
    elif key.startswith('F') and key[1:].isdigit() and 1<=int(key[1:])<=24:
        code = 0x70+int(key[1:])-1
    else:
        raise ValueError('快捷键末尾请使用一个字母、数字或 F1–F24')
    flags = sum(modifiers[p] for p in parts[:-1]) | 0x4000  # MOD_NOREPEAT
    canonical = '+'.join([p.title() for p in ('CTRL','ALT','SHIFT') if p in parts[:-1]]+[key])
    return canonical, flags, code


class GlobalHotkey(QAbstractNativeEventFilter):
    def __init__(self, app, callback):
        super().__init__()
        self.app, self.callback = app, callback
        self.ident = None
        self.sequence = 0xDA0  # application IDs must be below 0xC000
        self.text = ''
        if sys.platform=='win32':
            self.user32 = ctypes.WinDLL('user32', use_last_error=True)
            self.user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
            self.user32.RegisterHotKey.restype = wintypes.BOOL
            self.user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
            self.user32.UnregisterHotKey.restype = wintypes.BOOL
            app.installNativeEventFilter(self)

    def prepare(self, text):
        canonical, flags, code = parse_hotkey(text)
        if sys.platform!='win32':raise ValueError('全局截图快捷键目前支持 Windows')
        self.sequence += 1
        ident = self.sequence
        if not self.user32.RegisterHotKey(None, ident, flags, code):
            raise ValueError(f'{canonical} 注册失败，可能已被其他程序占用；请选择其他组合')
        return ident, canonical

    def commit(self, prepared):
        if self.ident is not None:self.user32.UnregisterHotKey(None, self.ident)
        self.ident, self.text = prepared

    def rollback(self, prepared):
        self.user32.UnregisterHotKey(None, prepared[0])

    def nativeEventFilter(self, event_type, message):
        if sys.platform=='win32' and self.ident is not None:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message==0x0312 and int(msg.wParam)==self.ident:
                QTimer.singleShot(0,self.callback)
                return True,0
        return False,0

    def shutdown(self):
        if sys.platform=='win32':
            if self.ident is not None:self.user32.UnregisterHotKey(None,self.ident)
            self.app.removeNativeEventFilter(self)
        self.ident = None
