"""Windows playback loopback, with a bounded PCM queue and a shared video clock."""
from collections import deque
import queue
import time
from PySide6.QtMultimedia import QAudioFormat


def normalize_audio_mode(mode):
    return 'system' if mode == 'system' else 'silent'


def audio_label(mode):
    return '有声 · 电脑声音' if mode == 'system' else '无声'


class PcmTimeline:
    """Keep silence and late-starting playback at their real recording positions."""
    def __init__(self, rate, channels):
        self.rate=rate;self.stride=channels*2;self.cursor=0;self.blocks=deque()

    def push(self, start_frame, data):
        data=bytes(data[:len(data)//self.stride*self.stride])
        if data:self.blocks.append((max(0,start_frame),data))

    def packet(self, limit, chunk_frames):
        if self.cursor>=limit:return None
        begin=self.cursor;end=min(limit,begin+chunk_frames)
        result=bytearray((end-begin)*self.stride)
        while self.blocks:
            start,data=self.blocks[0];stop=start+len(data)//self.stride
            if stop<=begin:self.blocks.popleft();continue
            if start>=end:break
            left,right=max(start,begin),min(stop,end)
            result[(left-begin)*self.stride:(right-begin)*self.stride]=data[(left-start)*self.stride:(right-start)*self.stride]
            if stop<=end:self.blocks.popleft()
            else:break
        self.cursor=end
        return begin*1_000_000//self.rate,bytes(result)


class SystemAudioCapture:
    """WASAPI output loopback only. A microphone is never opened."""
    def __init__(self):
        self.manager=None;self.stream=None;self.device_name='';self.error=''
        self.packets=queue.Queue(maxsize=200);self.running=False

    def open(self):
        try:
            import pyaudiowpatch as pa
        except ImportError as exc:
            raise OSError('有声录屏组件未安装，请运行 setup.ps1 更新依赖') from exc
        self.pa=pa
        try:
            self.manager=pa.PyAudio()
            device=self.manager.get_default_wasapi_loopback()
            if not device.get('isLoopbackDevice'):
                raise OSError('没有可用的电脑声音回录设备')
            self.device_name=device['name'].removesuffix(' [Loopback]')
            self.rate=int(device['defaultSampleRate']);self.channels=min(2,int(device['maxInputChannels']))
            if self.channels<1:raise OSError('当前播放设备不支持声音回录')
            self.format=QAudioFormat();self.format.setSampleRate(self.rate)
            self.format.setChannelCount(self.channels);self.format.setSampleFormat(QAudioFormat.SampleFormat.Int16)
            self.stream=self.manager.open(format=pa.paInt16,channels=self.channels,rate=self.rate,
                input=True,input_device_index=int(device['index']),frames_per_buffer=max(128,self.rate//50),
                stream_callback=self._receive,start=False)
            return self.format
        except Exception as exc:
            self.stop()
            raise OSError('无法录制电脑声音，请检查默认播放设备：'+str(exc)) from exc

    def start(self, epoch):
        self.epoch=epoch;self.portaudio_origin=self.stream.get_time()
        self.origin_offset=time.monotonic()-epoch;self.running=True
        try:self.stream.start_stream()
        except Exception:
            self.running=False;raise

    def _receive(self, data, frame_count, times, status):
        if not self.running:return None,self.pa.paComplete
        try:
            if status & self.pa.paInputOverflow:
                self.error='电脑声音采集缓冲区溢出，录制已停止';return None,self.pa.paAbort
            elapsed=time.monotonic()-self.epoch
            timestamp=times.get('input_buffer_adc_time',0)-self.portaudio_origin+self.origin_offset
            if not -.2<=timestamp<=elapsed+.2:timestamp=elapsed-frame_count/self.rate
            start=max(0,round(timestamp*self.rate))
            self.packets.put_nowait((start,bytes(data or bytes(frame_count*self.channels*2))))
        except queue.Full:
            self.error='电脑声音处理跟不上采集速度，录制已停止';return None,self.pa.paAbort
        except Exception as exc:
            self.error='电脑声音采集失败：'+str(exc);return None,self.pa.paAbort
        return None,self.pa.paContinue

    def read_packets(self):
        result=[]
        while True:
            try:result.append(self.packets.get_nowait())
            except queue.Empty:return result

    def check(self):
        if self.error:raise OSError(self.error)
        if self.running and not self.stream.is_active():
            raise OSError('电脑声音采集已停止，请检查播放设备')

    def stop(self):
        self.running=False
        stream,self.stream=self.stream,None
        manager,self.manager=self.manager,None
        try:
            if stream:
                try:stream.stop_stream()
                finally:stream.close()
        finally:
            if manager:manager.terminate()
