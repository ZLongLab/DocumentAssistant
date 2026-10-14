"""Compact recording controls and a local video preview/save dialog."""
from pathlib import Path
from PySide6.QtCore import QRect, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget
from PySide6.QtMultimedia import QMediaPlayer, QVideoSink
from .capture_style import CAPTURE_QSS
from .video_recording import save_video


def controls_position(area,region,size):
    """Find room fully outside the captured area; return None for a full screen."""
    gap=12;w,h=size.width(),size.height()
    candidates=[(region.right()-w,region.bottom()+gap),(region.right()-w,region.top()-h-gap),
                (region.right()+gap,region.top()),(region.left()-w-gap,region.top())]
    for x,y in candidates:
        x=max(area.left()+8,min(area.right()-w-8,x));y=max(area.top()+8,min(area.bottom()-h-8,y))
        rect=QRect(int(x),int(y),w,h)
        if area.contains(rect) and not region.intersects(rect):return rect.topLeft()
    return None


class RecordingControls(QWidget):
    stop_requested=Signal()
    cancel_requested=Signal()
    def __init__(self,hotkey):
        super().__init__(None,Qt.WindowType.Tool|Qt.WindowType.FramelessWindowHint|Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('视频录制 · DocumentAssistant');self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setStyleSheet('QWidget{background:#173f32;color:#effaf4;font-family:"Microsoft YaHei UI";font-size:13px;border-radius:13px;} QLabel#recordClock{font-size:18px;font-weight:600;} QPushButton{background:#fb765e;color:#fff;border:0;border-radius:9px;padding:9px 15px;font-weight:600;} QPushButton:disabled{background:#426859;color:#b8d2c3;}')
        layout=QHBoxLayout(self);layout.setContentsMargins(16,12,12,12);layout.setSpacing(14)
        self.clock=QLabel('3 秒后开始');self.clock.setObjectName('recordClock');layout.addWidget(self.clock)
        self.hint=QLabel('无声 · '+hotkey+' 停止');layout.addWidget(self.hint)
        self.stop_button=QPushButton('取消');self.stop_button.clicked.connect(self.action);layout.addWidget(self.stop_button)
        self.live=False;self.adjustSize()
    def action(self):
        if self.live:self.stop_requested.emit()
        else:self.cancel_requested.emit()
    def countdown(self,value):self.clock.setText(f'{value} 秒后开始')
    def started(self):self.live=True;self.stop_button.setText('■  停止');self.clock.setText('●  00:00')
    def progress(self,millis):
        if self.live:self.clock.setText(f'●  {millis//60000:02d}:{millis//1000%60:02d}')
    def stopping(self):self.clock.setText('正在生成视频');self.stop_button.setEnabled(False)


class VideoCanvas(QWidget):
    """Paint decoded frames directly so native previews and snapshots agree."""
    def __init__(self):
        super().__init__();self.image=None;self.sink=QVideoSink(self)
        self.sink.videoFrameChanged.connect(self.receive)
    def receive(self,frame):
        image=frame.toImage()
        if not image.isNull():self.image=image;self.update()
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        clip=QPainterPath();clip.addRoundedRect(QRectF(self.rect()),14,14)
        painter.setClipPath(clip);painter.fillRect(self.rect(),QColor('#172630'))
        if self.image is not None:
            size=self.image.size().scaled(self.size(),Qt.AspectRatioMode.KeepAspectRatio)
            target=QRectF((self.width()-size.width())/2,(self.height()-size.height())/2,size.width(),size.height())
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform);painter.drawImage(target,self.image)
        else:
            painter.setPen(QColor('#9cafb7'));painter.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'正在加载视频…')
        painter.end()


class VideoPreview(QDialog):
    def __init__(self,path,controller,warning=''):
        super().__init__(None)
        self.path=Path(path);self.controller=controller;self.saved_path=None
        self.setWindowTitle('视频预览 · DocumentAssistant');self.resize(900,650);self.setMinimumSize(560,420)
        self.setStyleSheet(CAPTURE_QSS)
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(12)
        header=QFrame();header.setObjectName('captureHeader');row=QHBoxLayout(header);row.setContentsMargins(22,18,22,18)
        title=QLabel('录制完成');title.setObjectName('captureTitle');row.addWidget(title);row.addStretch()
        badge=QLabel('无声视频 · MP4');badge.setObjectName('captureBadge');row.addWidget(badge);layout.addWidget(header)
        self.video=VideoCanvas();self.video.setMinimumHeight(200)
        body=QHBoxLayout();body.setContentsMargins(20,0,20,0);body.addWidget(self.video);layout.addLayout(body,1)
        self.player=QMediaPlayer(self);self.player.setVideoSink(self.video.sink)
        self.player.errorOccurred.connect(lambda code,message:self.error.setText('预览失败：'+message+'。仍可保存视频。'))
        tools=QHBoxLayout();tools.setContentsMargins(22,0,22,0)
        self.play_button=QPushButton('播放');self.play_button.setAutoDefault(False);self.play_button.clicked.connect(self.toggle_play)
        tools.addWidget(self.play_button);self.time=QLabel('00:00 / 00:00');tools.addWidget(self.time);tools.addStretch();layout.addLayout(tools)
        self.player.positionChanged.connect(self.update_time);self.player.durationChanged.connect(self.update_time)
        self.player.playbackStateChanged.connect(lambda state:self.play_button.setText('暂停' if state==QMediaPlayer.PlaybackState.PlayingState else '播放'))
        self.error=QLabel('');self.error.setWordWrap(True);self.error.setObjectName('captureError');self.error.hide();layout.addWidget(self.error)
        if warning:self.error.setText('录制提前结束：'+warning+'。已录内容可以预览和保存。');self.error.show()
        self.player.errorOccurred.connect(lambda *args:self.error.show())
        foot=QHBoxLayout();foot.setContentsMargins(22,8,22,20)
        label=QLabel('保存到 '+str(controller.settings['directory']));label.setObjectName('captureHint');label.setToolTip(label.text())
        label.setWordWrap(True);foot.addWidget(label,1)
        self.discard_button=QPushButton('不保存');self.discard_button.setObjectName('cancelCapture');self.discard_button.setAutoDefault(False)
        self.discard_button.clicked.connect(self.reject);foot.addWidget(self.discard_button)
        self.save_button=QPushButton('保存视频');self.save_button.setObjectName('copyCapture');self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save);foot.addWidget(self.save_button);layout.addLayout(foot)
        self.player.setSource(QUrl.fromLocalFile(str(self.path)))
        self.player.play()
        self.finished.connect(lambda *_:self.release_player())

    def update_time(self,*_):
        def time(value):return f'{value//60000:02d}:{value//1000%60:02d}'
        self.time.setText(time(self.player.position())+' / '+time(self.player.duration()))

    def toggle_play(self):
        if self.player.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.player.pause()
        else:
            if self.player.mediaStatus()==QMediaPlayer.MediaStatus.EndOfMedia:self.player.setPosition(0)
            self.player.play()

    def release_player(self):self.player.stop();self.player.setSource(QUrl())

    def save(self):
        try:
            self.saved_path=save_video(self.path,self.controller.settings['directory'])
        except Exception as exc:self.error.setText('保存失败：'+str(exc)+'。视频仍在，请重试。');self.error.show();return
        self.controller.last_video=self.saved_path
        self.controller.notify('视频已保存',str(self.saved_path));self.accept()

    def reject(self):
        if not self.saved_path and QMessageBox.question(self,'不保存视频','丢弃这次录制的视频？',QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Cancel)!=QMessageBox.StandardButton.Discard:return
        super().reject()
