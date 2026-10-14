"""Reopen the running tray application when its shortcut is launched again."""
import hashlib
import os
from pathlib import Path
from PySide6.QtCore import QObject, QLockFile, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class AppInstance(QObject):
    activated=Signal()

    def __init__(self,home,parent=None):
        super().__init__(parent)
        home=Path(home).resolve();home.mkdir(parents=True,exist_ok=True)
        identity=os.path.normcase(str(home)).encode('utf-8')
        self.name='DocumentAssistant-'+hashlib.sha256(identity).hexdigest()[:24]
        self.lock=QLockFile(str(home/'app-instance.lock'))
        self.lock.setStaleLockTime(0)
        self.server=QLocalServer(self)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        self.server.newConnection.connect(self.incoming)
        self.owns_lock=False

    def forward(self,timeout=500,activate=True):
        socket=QLocalSocket()
        socket.connectToServer(self.name)
        if not socket.waitForConnected(timeout):return False
        socket.write(b'open\n' if activate else b'ping\n')
        socket.flush()
        if socket.bytesToWrite() and not socket.waitForBytesWritten(timeout):
            socket.abort();return False
        socket.disconnectFromServer()
        return True

    def start(self,activate=True):
        if self.forward(activate=activate):return False
        if not self.lock.tryLock(0):
            if self.forward(2000,activate=activate):return False
            raise RuntimeError('程序已经在启动或退出，请稍后重试；可检查系统托盘中的 DocumentAssistant')
        self.owns_lock=True
        # Only the process holding the lock can remove an abandoned local server.
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            error=self.server.errorString();self.shutdown()
            raise RuntimeError('无法建立本地程序连接：'+error)
        return True

    def incoming(self):
        while self.server.hasPendingConnections():
            socket=self.server.nextPendingConnection()
            socket._instance_data=b''
            socket.readyRead.connect(lambda current=socket:self.receive(current))
            socket.disconnected.connect(socket.deleteLater)
            self.receive(socket)

    def receive(self,socket):
        socket._instance_data+=bytes(socket.readAll())
        if b'\n' in socket._instance_data:
            if socket._instance_data==b'open\n':self.activated.emit()
            socket.disconnectFromServer()
        elif len(socket._instance_data)>16:socket.abort()

    def shutdown(self):
        if self.owns_lock:
            self.server.close();self.lock.unlock();self.owns_lock=False
