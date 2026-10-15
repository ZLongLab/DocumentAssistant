"""Freeze a shortcut's modifier edge before it dismisses an application menu."""
import ctypes
import sys
from ctypes import wintypes


class ModifierCapture:
    def __init__(self, shortcut, freeze, clear):
        self.shortcut, self.freeze, self.clear = shortcut, freeze, clear
        self.handle = self.proc = None
        self.down = set()

    def start(self):
        if sys.platform != 'win32' or self.handle:
            return
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        result = ctypes.c_ssize_t
        callback = ctypes.WINFUNCTYPE(result, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        self.api.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        self.api.CallNextHookEx.restype = result
        self.api.SetWindowsHookExW.argtypes = [ctypes.c_int, callback, wintypes.HINSTANCE, wintypes.DWORD]
        self.api.SetWindowsHookExW.restype = wintypes.HANDLE
        self.api.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        self.api.UnhookWindowsHookEx.restype = wintypes.BOOL
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        self.proc = callback(self.event)
        self.handle = self.api.SetWindowsHookExW(13, self.proc, kernel.GetModuleHandleW(None), 0)
        if not self.handle:
            self.proc = None  # Normal RegisterHotKey capture remains available.

    def event(self, code, event, pointer):
        try:
            if code >= 0:
                # Only modifier state is retained; ordinary key presses are ignored.
                key = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD)).contents.value
                group = {0x12: 'Alt', 0xA4: 'Alt', 0xA5: 'Alt',
                         0x11: 'Ctrl', 0xA2: 'Ctrl', 0xA3: 'Ctrl',
                         0x10: 'Shift', 0xA0: 'Shift', 0xA1: 'Shift'}.get(key)
                if group:
                    if event in (0x101, 0x105):
                        self.down.discard(key)
                    elif event in (0x100, 0x104) and key not in self.down:
                        first = not self.down
                        self.down.add(key)
                        if group in self.shortcut().split('+')[:-1]:
                            self.freeze(first)
                elif self.down and event in (0x100, 0x104):
                    name = chr(key) if 0x30 <= key <= 0x5A else 'F'+str(key-0x6F) if 0x70 <= key <= 0x87 else ''
                    if name != self.shortcut().split('+')[-1]:
                        self.clear()
        except Exception:
            pass  # A failed preview must never block keyboard input.
        return self.api.CallNextHookEx(self.handle, code, event, pointer)

    def shutdown(self):
        if self.handle:
            self.api.UnhookWindowsHookEx(self.handle)
            self.handle = None
        self.down.clear()
        self.proc = None
