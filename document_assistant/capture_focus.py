"""Remember and restore the application the user was capturing on Windows."""
import ctypes
import sys
from ctypes import wintypes

def foreground_window():
    if sys.platform!='win32':return None
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.GetForegroundWindow.restype=wintypes.HWND
    return api.GetForegroundWindow()

def window_owner(handle):
    """Treat a transient native popup and its owner as the same foreground app."""
    if not handle or sys.platform!='win32':return handle
    api=ctypes.WinDLL('user32',use_last_error=True)
    api.GetAncestor.argtypes=[wintypes.HWND,wintypes.UINT]
    api.GetAncestor.restype=wintypes.HWND
    return api.GetAncestor(handle,3) or handle

def restore_foreground(handle):
    if not handle or sys.platform!='win32':return False
    api=ctypes.WinDLL('user32',use_last_error=True)
    for name in ('IsWindow','IsWindowVisible','SetForegroundWindow'):
        function=getattr(api,name);function.argtypes=[wintypes.HWND];function.restype=wintypes.BOOL
    if not api.IsWindow(handle) or not api.IsWindowVisible(handle):return False
    return bool(api.SetForegroundWindow(handle))
