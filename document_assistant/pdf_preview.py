"""Local PDF page rendering with bounded memory and explicit password entry."""
from pathlib import Path

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QPointF, Qt
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView
from PySide6.QtWidgets import (QComboBox, QDialog, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)


class PdfPreview(QWidget):
    LIMIT = 50 * 1024 * 1024

    def __init__(self, parent=None):
        super().__init__(parent)
        self.path = None
        self.fingerprint = None
        self.buffer = None
        self.document = QPdfDocument(self)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        self.message = QLabel('选择 PDF 查看原始页面')
        self.message.setWordWrap(True)
        outer.addWidget(self.message)
        controls = QHBoxLayout()
        controls.setSpacing(4)
        self.previous = QPushButton('‹')
        self.previous.setAccessibleName('PDF 上一页')
        self.next = QPushButton('›')
        self.previous.setFixedWidth(32)
        self.next.setFixedWidth(32)
        self.next.setAccessibleName('PDF 下一页')
        self.page = QSpinBox()
        self.page.setRange(1, 1)
        self.page.setMaximumWidth(68)
        self.page.setAccessibleName('PDF 页码')
        self.total = QLabel('/ 0')
        self.total.setFixedWidth(30)
        self.zoom = QComboBox()
        self.zoom.setMaximumWidth(150)
        self.zoom.addItems(['适应宽度', '适应页面', '100%', '150%'])
        for widget in (self.previous, self.page, self.total, self.next, self.zoom):
            controls.addWidget(widget)
        controls.addStretch(1)
        outer.addLayout(controls)
        self.password_button = QPushButton('输入 PDF 密码')
        self.password_button.hide()
        self.password_button.clicked.connect(self.enter_password)
        outer.addWidget(self.password_button)
        self.view = QPdfView()
        self.view.setMinimumHeight(210)
        self.view.setDocument(self.document)
        self.view.setPageMode(QPdfView.PageMode.SinglePage)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        outer.addWidget(self.view, 1)
        self.page.valueChanged.connect(self.jump)
        self.previous.clicked.connect(lambda: self.page.setValue(self.page.value() - 1))
        self.next.clicked.connect(lambda: self.page.setValue(self.page.value() + 1))
        self.zoom.currentIndexChanged.connect(self.change_zoom)
        self.document.statusChanged.connect(self.update_status)
        self.view.pageNavigator().currentPageChanged.connect(self.navigator_changed)
        self.update_status()

    def load_path(self, path, password=None):
        path = Path(path) if path else None
        try:
            info = path.stat() if path else None
            fingerprint = (str(path), info.st_size, info.st_mtime_ns) if info else None
            if password is None and fingerprint and fingerprint == self.fingerprint:
                return
            self.view.setDocument(None)
            self.document.close()
            if self.buffer:
                self.buffer.close()
                self.buffer.deleteLater()
                self.buffer = None
            self.path, self.fingerprint = path, fingerprint
            self.password_button.hide()
            if not path:
                self.message.setText('选择 PDF 查看原始页面')
                return
            if info.st_size > self.LIMIT:
                self.message.setText('PDF 超过 50 MB，请使用“打开文件”查看。')
                return
            with path.open('rb') as stream:
                data = stream.read(self.LIMIT + 1)
            after = path.stat()
            if len(data) > self.LIMIT or (info.st_size, info.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                raise ValueError('读取时文件发生变化，请重新选择')
            # Keep an immutable buffer so preview never holds the original file open.
            self.buffer = QBuffer(self)
            self.buffer.setData(QByteArray(data))
            self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            self.document.setPassword(password or '')
            self.document.load(self.buffer)
            self.view.setDocument(self.document)
            self.update_status()
        except (OSError, ValueError) as exc:
            self.document.close()
            self.fingerprint = None
            self.message.setText('无法预览：' + str(exc))

    def update_status(self, *_):
        ready = self.document.status() == QPdfDocument.Status.Ready
        count = self.document.pageCount() if ready else 0
        self.page.blockSignals(True)
        self.page.setRange(1, max(1, count))
        self.page.setValue(1)
        self.page.blockSignals(False)
        self.total.setText(f'/ {count}')
        self.page.setEnabled(ready)
        self.zoom.setEnabled(ready)
        self.view.setVisible(ready)
        self.password_button.setVisible(self.document.error() == QPdfDocument.Error.IncorrectPassword)
        if ready:
            self.message.setText('原始 PDF 页面')
            self.jump(1)
        elif self.document.error() == QPdfDocument.Error.IncorrectPassword:
            self.message.setText('此 PDF 受密码保护，输入密码后预览。')
        elif self.document.status() == QPdfDocument.Status.Error:
            self.message.setText('无法渲染 PDF，可用“打开文件”检查原文件。')
        self.update_navigation()

    def update_navigation(self):
        self.previous.setEnabled(self.document.pageCount() > 0 and self.page.value() > 1)
        self.next.setEnabled(self.document.pageCount() > 0 and self.page.value() < self.document.pageCount())

    def jump(self, number):
        if self.document.status() == QPdfDocument.Status.Ready:
            self.view.pageNavigator().jump(number - 1, QPointF(0, 0), 0)
        self.update_navigation()

    def navigator_changed(self, page):
        self.page.blockSignals(True)
        self.page.setValue(page + 1)
        self.page.blockSignals(False)
        self.update_navigation()

    def change_zoom(self, index):
        if index < 2:
            self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth if index == 0 else QPdfView.ZoomMode.FitInView)
        else:
            self.view.setZoomMode(QPdfView.ZoomMode.Custom)
            self.view.setZoomFactor(1.0 if index == 2 else 1.5)

    def enter_password(self):
        password, accepted = QInputDialog.getText(self, '预览加密 PDF', '密码：', QLineEdit.EchoMode.Password)
        if accepted and self.path:
            self.load_path(self.path, password=password)

    def shutdown(self):
        self.view.setDocument(None)
        self.document.close()
        self.fingerprint = None
        if self.buffer:
            self.buffer.close()

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


class DocumentPreviewDialog(QDialog):
    def __init__(self, path, body='', parent=None):
        super().__init__(parent)
        self.setWindowTitle('文档预览 · ' + Path(path).name)
        self.resize(820, 760)
        outer = QVBoxLayout(self)
        tabs = QTabWidget()
        self.pdf = None
        if Path(path).suffix.lower() == '.pdf':
            self.pdf = PdfPreview()
            tabs.addTab(self.pdf, 'PDF 页面')
            self.pdf.load_path(path)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlainText(body[:6000] or '没有可提取正文。PDF 扫描页可直接预览；本版尚无 OCR。')
        tabs.addTab(self.text, '提取文字')
        outer.addWidget(tabs, 1)
        close = QPushButton('关闭')
        close.clicked.connect(self.accept)
        outer.addWidget(close)

    def closeEvent(self, event):
        if self.pdf:
            self.pdf.shutdown()
        super().closeEvent(event)

    def done(self, result):
        if self.pdf:
            self.pdf.shutdown()
        super().done(result)
