import time
from PySide6.QtTest import QTest


def settle_search(window, timeout=15):
    deadline = time.monotonic()+timeout
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    while window.search_worker or window.pending_search or window.search_timer.isActive():
        app.processEvents()
        QTest.qWait(10)
        if time.monotonic()>deadline:
            raise AssertionError('Background search did not finish')
    app.processEvents()
