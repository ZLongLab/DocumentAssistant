"""Small real PDF previews, loaded on demand and bounded in memory."""
from pathlib import Path
from PySide6.QtCore import QBuffer,QByteArray,QIODevice,QSize,QTimer
from PySide6.QtPdf import QPdfDocument

class ThumbnailRequest:
    LIMIT=50*1024*1024
    def __init__(self,widget,path,callback):
        self.widget=widget;self.path=Path(path);self.callback=callback;self.document=None;self.buffer=None
        self.closed=False;widget.destroyed.connect(self.close);QTimer.singleShot(0,self.load)
    def load(self):
        if self.closed:return
        try:
            before=self.path.stat()
            if before.st_size>self.LIMIT:return
            with self.path.open('rb') as handle:data=handle.read(self.LIMIT+1)
            after=self.path.stat()
            if len(data)>self.LIMIT or (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns):return
            self.buffer=QBuffer();self.buffer.setData(QByteArray(data));self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
            self.document=QPdfDocument();self.document.statusChanged.connect(self.status)
            document,buffer=self.document,self.buffer
            document.load(buffer)
            if not self.closed:self.status(document.status())
            QTimer.singleShot(2000,self.close)
        except (OSError,RuntimeError):self.close()
    def status(self,status):
        if self.closed or self.document is None:return
        if status==QPdfDocument.Status.Ready:
            size=self.document.pagePointSize(0)
            if size.width()>0 and size.height()>0:
                scale=min(360/size.width(),180/size.height());image=self.document.render(0,QSize(max(1,int(size.width()*scale)),max(1,int(size.height()*scale))))
                if not image.isNull():self.callback(image)
            self.close()
        elif status==QPdfDocument.Status.Error:self.close()
    def close(self,*_):
        if self.closed:return
        self.closed=True
        if self.document:self.document.close();self.document=None
        if self.buffer:self.buffer.close();self.buffer=None
