"""Windows taskbar/shortcut identity using only the Python standard library."""
import ctypes
import os
import subprocess
import sys
import uuid
from contextlib import contextmanager
from pathlib import Path

APP_ID = 'DocumentAssistant.Workbench'
ICON_PATH = Path(__file__).with_name('documentassistant.ico')


def configure_process():
    if sys.platform == 'win32':
        result = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        if result < 0:
            raise OSError(f'Windows AppUserModelID: {result:#x}')


class GUID(ctypes.Structure):
    _fields_ = [('data', ctypes.c_ubyte * 16)]

    def __init__(self, value):
        super().__init__()
        self.data[:] = uuid.UUID(value).bytes_le


class PropertyKey(ctypes.Structure):
    _fields_ = [('fmtid', GUID), ('pid', ctypes.c_ulong)]


class VariantValue(ctypes.Union):
    _fields_ = [('text', ctypes.c_void_p), ('storage', ctypes.c_ulonglong * 2)]


class PropVariant(ctypes.Structure):
    _fields_ = [('vt', ctypes.c_ushort), ('reserved', ctypes.c_ushort * 3), ('value', VariantValue)]


def check(result):
    if result < 0:
        raise OSError(f'Windows property store: {result:#x}')


def method(pointer, index, result_type, *argument_types):
    address = ctypes.cast(pointer, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents[index]
    return ctypes.WINFUNCTYPE(result_type, ctypes.c_void_p, *argument_types)(address)


def release(pointer):
    if pointer:
        method(pointer, 2, ctypes.c_ulong)(pointer)


@contextmanager
def com():
    result = ctypes.windll.ole32.CoInitializeEx(None, 2)
    if result < 0 and result != -2147417850:  # Already initialized in another apartment.
        check(result)
    try:
        yield
    finally:
        if result >= 0:
            ctypes.windll.ole32.CoUninitialize()


def put(store, pid, text):
    key = PropertyKey(GUID('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'), pid)
    value = PropVariant()
    value.vt = 31  # VT_LPWSTR; SetValue copies the string.
    buffer = ctypes.create_unicode_buffer(text)
    value.value.text = ctypes.cast(buffer, ctypes.c_void_p)
    check(method(store, 6, ctypes.c_long, ctypes.POINTER(PropertyKey), ctypes.POINTER(PropVariant))(
        store, ctypes.byref(key), ctypes.byref(value)))


def get_app_id(store):
    key = PropertyKey(GUID('9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3'), 5)
    value = PropVariant()
    check(method(store, 5, ctypes.c_long, ctypes.POINTER(PropertyKey), ctypes.POINTER(PropVariant))(
        store, ctypes.byref(key), ctypes.byref(value)))
    try:
        return ctypes.wstring_at(value.value.text) if value.vt == 31 and value.value.text else ''
    finally:
        ctypes.windll.ole32.PropVariantClear(ctypes.byref(value))


def tag_shortcut(path):
    with com():
        persist, store = ctypes.c_void_p(), ctypes.c_void_p()
        clsid = GUID('00021401-0000-0000-c000-000000000046')
        iid = GUID('0000010b-0000-0000-c000-000000000046')  # IPersistFile
        check(ctypes.windll.ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(persist)))
        try:
            check(method(persist, 5, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_ulong)(persist, str(path), 2))
            iid_store = GUID('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
            check(method(persist, 0, ctypes.c_long, ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
                persist, ctypes.byref(iid_store), ctypes.byref(store)))
            put(store, 5, APP_ID)
            check(method(store, 7, ctypes.c_long)(store))
            check(method(persist, 6, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_int)(persist, str(path), 1))
            if get_app_id(store) != APP_ID:
                raise OSError('Shortcut AppUserModelID verification failed')
        finally:
            release(store)
            release(persist)
    # Notify Explorer of this individual shortcut update; do not clear global caches.
    ctypes.windll.shell32.SHChangeNotify(0x2000, 0x1005, ctypes.c_wchar_p(str(path)), None)


def tag_window(hwnd):
    if sys.platform != 'win32':
        return
    with com():
        store = ctypes.c_void_p()
        iid = GUID('886d8eeb-8cf2-4446-8d02-cdba1dbdcf99')
        check(ctypes.windll.shell32.SHGetPropertyStoreForWindow(ctypes.c_void_p(hwnd), ctypes.byref(iid), ctypes.byref(store)))
        try:
            target = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
            launcher = Path(__file__).resolve().parents[1] / 'start.ps1'
            command = subprocess.list2cmdline([str(target), '-NoProfile', '-ExecutionPolicy', 'Bypass',
                                               '-WindowStyle', 'Hidden', '-File', str(launcher), '-Windowed'])
            if getattr(sys, 'frozen', False):
                arguments = [sys.executable]
                if os.environ.get('DOCUMENTASSISTANT_HOME'):
                    arguments += ['--home', os.environ['DOCUMENTASSISTANT_HOME']]
                command = subprocess.list2cmdline(arguments)
            put(store, 2, command)
            put(store, 3, str(ICON_PATH) + ',0')
            put(store, 4, 'DocumentAssistant')
            put(store, 5, APP_ID)
            if get_app_id(store) != APP_ID:
                raise OSError('Window AppUserModelID verification failed')
        finally:
            release(store)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == 'shortcut':
        tag_shortcut(Path(sys.argv[2]).resolve())
        print(APP_ID)
    elif len(sys.argv) == 3 and sys.argv[1] == 'window':
        tag_window(int(sys.argv[2]))
        print(APP_ID)
    else:
        raise SystemExit('Usage: python -m document_assistant.windows_identity shortcut PATH | window HWND')
