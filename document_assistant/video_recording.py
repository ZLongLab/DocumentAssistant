"""Region-only MP4 capture, optionally including Windows playback audio."""
import os
import shutil
import uuid
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, QElapsedTimer, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtMultimedia import (QAudioBuffer, QAudioBufferInput, QMediaCaptureSession,
    QMediaFormat, QMediaRecorder, QVideoFrame, QVideoFrameInput)

from .capture_pixels import crop_selection
from .video_audio import normalize_audio_mode, PcmTimeline, SystemAudioCapture


def save_video(source, directory, now=None):
    """Copy a finalized recording without replacing any existing file."""
    source=Path(source);directory=Path(directory).expanduser().resolve()
    if not source.is_file() or source.stat().st_size<128:raise OSError('视频文件尚未生成，请重新录制')
    directory.mkdir(parents=True,exist_ok=True)
    stamp=(now or datetime.now()).strftime('%Y%m%d_%H%M%S')
    for index in range(10000):
        target=directory/f'录屏_{stamp}{"_"+str(index) if index else ""}.mp4'
        try:handle=target.open('xb')
        except FileExistsError:continue
        try:
            with handle,source.open('rb') as original:
                shutil.copyfileobj(original,handle,1024*1024);handle.flush();os.fsync(handle.fileno())
        except Exception:
            target.unlink(missing_ok=True);raise
        return target
    raise OSError('同名视频过多，请更换保存目录')


class RegionRecorder(QObject):
    started=Signal()
    progress=Signal(int)
    completed=Signal(object)
    failed=Signal(str)

    def __init__(self,screen,rect,home,parent=None,grabber=None,*,audio_mode='silent',audio_factory=None):
        super().__init__(parent)
        self.screen=screen;self.rect=QRectF(rect);self.geometry=screen.geometry()
        self.grabber=grabber;self.home=Path(home);self.path=None
        self.frames=0;self.size=QSize();self.source_size=QSize();self.ready=False;self.stopping=False;self.done=False
        self.keep_file=False;self.interruption=''
        self.audio_mode=normalize_audio_mode(audio_mode);self.audio_factory=audio_factory or SystemAudioCapture
        self.audio_source=None;self.audio_input=None;self.audio_timeline=None;self.audio_pending=None
        self.audio_stop_frame=None;self.audio_stop_sent=False;self.audio_device=''
        self.audio_pumping=False
        self.audio_timer=QTimer(self);self.audio_timer.setInterval(20);self.audio_timer.timeout.connect(self.pump_audio)
        self.clock=QElapsedTimer();self.last_accepted=0;self.last_timestamp=-1
        self.timer=QTimer(self);self.timer.setTimerType(Qt.TimerType.PreciseTimer);self.timer.setInterval(50)
        self.timer.timeout.connect(self.tick)
        self.guard=QTimer(self);self.guard.setSingleShot(True);self.guard.timeout.connect(lambda:self.fail('视频编码超时，请重试'))
        self.session=QMediaCaptureSession(self);self.recorder=QMediaRecorder(self);self.input=QVideoFrameInput(self)
        self.session.setRecorder(self.recorder);self.session.setVideoFrameInput(self.input)
        self.recorder.errorOccurred.connect(lambda code,message:self.fail(message or '视频编码失败'))
        self.recorder.recorderStateChanged.connect(self.state_changed)

    def image(self):
        if self.grabber:return self.grabber()
        if self.screen.geometry()!=self.geometry:raise OSError('屏幕配置已改变，请重新选择录制区域')
        frame=self.screen.grabWindow(0).toImage()
        if frame.isNull():raise OSError('无法获取屏幕画面')
        return crop_selection(frame,self.rect,self.geometry.size())

    def start(self):
        if self.path is not None or self.done:return
        try:
            directory=self.home/'recordings';directory.mkdir(parents=True,exist_ok=True)
            if shutil.disk_usage(directory).free<256*1024*1024:raise OSError('临时目录剩余空间不足 256 MB')
            self.path=directory/f'recording-{uuid.uuid4().hex}.mp4'
            first=self.image()
            if first.isNull() or min(first.width(),first.height())<2:raise OSError('录制区域太小')
            self.source_size=first.size()
            # H.264 requires even dimensions. Pad at most one pixel, never stretch the region.
            self.size=QSize(first.width()+(first.width()%2),first.height()+(first.height()%2))
            fmt=QMediaFormat(QMediaFormat.FileFormat.MPEG4);fmt.setVideoCodec(QMediaFormat.VideoCodec.H264)
            if QMediaFormat.VideoCodec.H264 not in fmt.supportedVideoCodecs(QMediaFormat.ConversionMode.Encode):
                raise OSError('本机没有可用的 H.264 编码器')
            if self.audio_mode=='system':
                if QMediaFormat.AudioCodec.AAC not in fmt.supportedAudioCodecs(QMediaFormat.ConversionMode.Encode):
                    raise OSError('本机没有可用的 AAC 音频编码器')
                self.audio_source=self.audio_factory();audio_format=self.audio_source.open()
                self.audio_device=self.audio_source.device_name
                self.audio_timeline=PcmTimeline(audio_format.sampleRate(),audio_format.channelCount())
                self.audio_input=QAudioBufferInput(audio_format,self)
                self.session.setAudioBufferInput(self.audio_input)
                self.audio_input.readyToSendAudioBuffer.connect(self.pump_audio)
                fmt.setAudioCodec(QMediaFormat.AudioCodec.AAC)
                self.recorder.setAudioSampleRate(audio_format.sampleRate())
                self.recorder.setAudioChannelCount(audio_format.channelCount())
                self.recorder.setEncodingMode(QMediaRecorder.EncodingMode.ConstantBitRateEncoding)
                self.recorder.setAudioBitRate(128000)
                self.recorder.setVideoBitRate(max(600000,min(16000000,self.size.width()*self.size.height()*20//7)))
            self.recorder.setMediaFormat(fmt);self.recorder.setVideoResolution(self.size)
            self.recorder.setVideoFrameRate(20);self.recorder.setQuality(QMediaRecorder.Quality.HighQuality)
            self.recorder.setOutputLocation(QUrl.fromLocalFile(str(self.path)))
            self.clock.start()
            if self.audio_source:self.audio_source.start(time.monotonic())
            self.recorder.record()
            if not self.done:
                self.timer.start();self.guard.start(10000)
                if self.audio_source:self.audio_timer.start()
        except Exception as exc:self.fail(str(exc))

    def tick(self):
        if self.done or self.stopping:return
        try:
            now=self.clock.elapsed()
            if now-self.last_accepted>5000:raise OSError('视频编码器连续 5 秒未接收画面')
            image=self.image().convertToFormat(QImage.Format.Format_RGB32)
            if image.size()!=self.source_size:raise OSError('屏幕缩放已改变，请重新录制')
            if image.size()!=self.size:
                padded=QImage(self.size,QImage.Format.Format_RGB32);padded.fill(Qt.GlobalColor.black)
                painter=QPainter(padded);painter.drawImage(0,0,image);painter.end();image=padded
            frame=QVideoFrame(image)
            timestamp=max(self.last_timestamp+1,now*1000)
            frame.setStartTime(timestamp);frame.setEndTime(timestamp+50000)
            if self.input.sendVideoFrame(frame):
                self.frames+=1;self.last_accepted=now;self.last_timestamp=timestamp
                if not self.ready:self.ready=True;self.guard.stop();self.started.emit()
            self.progress.emit(now)
            if self.frames%100==0 and shutil.disk_usage(self.home).free<128*1024*1024:
                raise OSError('磁盘空间不足，录制已停止')
        except Exception as exc:
            # Capture/disk trouble can still leave a healthy encoder. Finalize the
            # accepted frames and let the user save them instead of losing the clip.
            if self.frames:
                self.interruption=str(exc);self.stop()
            else:self.fail(str(exc))

    def pump_audio(self):
        if self.audio_pumping:return
        self.audio_pumping=True
        try:self._pump_audio()
        finally:self.audio_pumping=False

    def _pump_audio(self):
        if self.done or self.audio_timeline is None or not self.clock.isValid():return
        try:
            if self.audio_source:
                if not self.stopping:self.audio_source.check()
                for start,data in self.audio_source.read_packets():self.audio_timeline.push(start,data)
            rate=self.audio_timeline.rate
            if not self.stopping and self.clock.elapsed()-self.audio_timeline.cursor*1000/rate>5000:
                raise OSError('音频编码器连续 5 秒未处理完声音')
            limit=(self.audio_stop_frame if self.stopping else max(0,self.clock.elapsed()-100)*rate//1000)
            # Keep at most one unsent buffer; never drop packets on encoder backpressure.
            for _ in range(20):
                if self.audio_pending is None:
                    packet=self.audio_timeline.packet(limit,max(1,rate//50))
                    if packet is None:break
                    timestamp,data=packet
                    self.audio_pending=QAudioBuffer(data,self.audio_input.format(),timestamp)
                if not self.audio_input.sendAudioBuffer(self.audio_pending):break
                self.audio_pending=None
            if self.stopping and self.audio_timeline.cursor>=limit and self.audio_pending is None and not self.audio_stop_sent:
                self.audio_stop_sent=True;self.audio_timer.stop();self.recorder.stop()
        except Exception as exc:
            message='声音录制失败：'+str(exc)
            if self.frames and not self.stopping:
                self.interruption=message;self.stop()
            else:self.fail(message)

    def close_audio(self):
        self.audio_timer.stop()
        if self.audio_source:
            self.audio_source.stop()

    def stop(self):
        if self.done or self.stopping:return
        if not self.frames:self.fail('尚未录到画面，请重试');return
        self.stopping=True;self.timer.stop();self.guard.start(15000)
        if self.audio_source:
            self.audio_stop_frame=self.clock.elapsed()*self.audio_timeline.rate//1000
            try:self.audio_source.stop()
            except Exception as exc:self.fail('停止声音采集失败：'+str(exc));return
            self.pump_audio()
        else:self.recorder.stop()

    def state_changed(self,state):
        if state!=QMediaRecorder.RecorderState.StoppedState or self.done:return
        if not self.stopping:
            self.fail(self.recorder.errorString() or '录制意外停止');return
        self.guard.stop()
        if not self.path or not self.path.is_file() or self.path.stat().st_size<128:
            self.fail('视频未能正常写入，请重试');return
        self.done=True;self.close_audio();self.completed.emit(self.path)

    def fail(self,message):
        if self.done:return
        self.keep_file=True
        self.done=True;self.timer.stop();self.guard.stop()
        try:self.close_audio()
        except Exception:pass
        self.recorder.stop()
        # Detach before removing a file so the encoder cannot continue writing.
        self.session.setRecorder(None);self.session.setVideoFrameInput(None)
        self.session.setAudioBufferInput(None)
        self.failed.emit(message)

    def quiesce(self):
        # Stop producing frames now; the preview may release its file handle later.
        # Set done first so encoder shutdown cannot send a late failure/completion.
        self.done=True;self.timer.stop();self.guard.stop()
        try:self.close_audio()
        except Exception:pass
        self.recorder.stop()

    def discard(self):
        self.quiesce()
        self.session.setRecorder(None);self.session.setVideoFrameInput(None)
        self.session.setAudioBufferInput(None)
        if self.path and self.path.is_file() and not self.keep_file:self.path.unlink()
