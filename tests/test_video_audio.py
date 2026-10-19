import struct
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPointF,QRect,QRectF
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtMultimedia import QAudioFormat
from test_upgrade import Fixture
from tests.gui_wait import settle_search
from document_assistant.video_audio import PcmTimeline
from document_assistant.video_recording import RegionRecorder
from document_assistant.screen_capture import CaptureController
from document_assistant.gui import MainWindow


class VideoAudioTests(Fixture):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_timestamped_packets_keep_leading_and_middle_silence(self):
        timeline=PcmTimeline(1000,1)
        timeline.push(10,struct.pack('<hhhh',100,200,300,400))
        timeline.push(20,struct.pack('<hh',500,600))
        stamp,data=timeline.packet(24,24)
        self.assertEqual(stamp,0)
        self.assertEqual(struct.unpack('<'+'h'*24,data),(0,)*10+(100,200,300,400)+(0,)*6+(500,600)+(0,)*2)

    def test_late_packets_do_not_shift_future_sound_earlier(self):
        timeline=PcmTimeline(1000,1);timeline.packet(20,20)
        timeline.push(5,struct.pack('<hh',99,99))
        timeline.push(25,struct.pack('<hh',111,222))
        stamp,data=timeline.packet(30,10)
        self.assertEqual(stamp,20000)
        self.assertEqual(struct.unpack('<'+'h'*10,data),(0,)*5+(111,222)+(0,)*3)

    def test_encoder_backpressure_retries_identical_unsent_buffer(self):
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,800,600))
        recorder=RegionRecorder(screen,QRectF(0,0,20,20),self.root)
        fmt=QAudioFormat();fmt.setSampleRate(1000);fmt.setChannelCount(1);fmt.setSampleFormat(QAudioFormat.SampleFormat.Int16)
        accepted=[];allow=[False]
        def send(buffer):
            if not allow[0]:return False
            accepted.append((buffer.startTime(),bytes(buffer.constData())));return True
        recorder.audio_input=SimpleNamespace(format=lambda:fmt,sendAudioBuffer=send)
        recorder.audio_timeline=PcmTimeline(1000,1)
        recorder.audio_timeline.push(0,struct.pack('<'+'h'*100,*range(100)))
        recorder.clock=SimpleNamespace(isValid=lambda:True,elapsed=lambda:200)
        try:
            recorder.pump_audio();pending=recorder.audio_pending
            self.assertIsNotNone(pending);self.assertFalse(accepted)
            allow[0]=True;recorder.pump_audio()
            self.assertIsNone(recorder.audio_pending)
            self.assertEqual([stamp for stamp,data in accepted],[0,20000,40000,60000,80000])
            self.assertEqual(b''.join(data for stamp,data in accepted),struct.pack('<'+'h'*100,*range(100)))
        finally:recorder.discard()

    def test_audio_open_failure_does_not_fall_back_to_silent_recording(self):
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,800,600))
        image=QImage(20,20,QImage.Format.Format_RGB32);image.fill(QColor('blue'))
        source=SimpleNamespace(device_name='',stop=lambda:None,open=lambda:(_ for _ in ()).throw(OSError('device unavailable')))
        recorder=RegionRecorder(screen,QRectF(0,0,20,20),self.root,grabber=lambda:image,audio_mode='system',audio_factory=lambda:source)
        failures=[];recorder.failed.connect(failures.append)
        recorder.start();self.assertTrue(recorder.done);self.assertIn('device unavailable',failures[0])
        self.assertFalse(recorder.timer.isActive());self.assertFalse(recorder.audio_timer.isActive())
        self.assertEqual(recorder.frames,0);recorder.discard()

    def test_audio_choice_syncs_overlays_and_reaches_countdown_then_cancel(self):
        window=MainWindow(self.root/'settings');settle_search(window)
        controller=CaptureController(window,activate=False)
        screens=[SimpleNamespace(geometry=lambda:QRect(0,0,800,600),availableGeometry=lambda:QRect(0,0,800,580)),
                 SimpleNamespace(geometry=lambda:QRect(-800,0,800,600),availableGeometry=lambda:QRect(-800,0,800,580))]
        image=QImage(800,600,QImage.Format.Format_RGB32);image.fill(QColor('#223344'))
        try:
            controller.capturing=True;controller.snapshot([(screen,image) for screen in screens]);self.app.processEvents()
            overlay=controller.overlays[0]
            self.assertTrue(overlay.video_audio_combo.isHidden())
            overlay.mode_buttons['video'].click()
            self.assertTrue(all(o.video_audio_combo.isVisible() for o in controller.overlays))
            overlay.video_audio_combo.setCurrentIndex(1)
            self.assertEqual(controller.video_audio_mode,'system')
            self.assertTrue(all(o.video_audio_mode=='system' for o in controller.overlays))
            self.assertIn('电脑声音',overlay.hint_label.text())
            self.assertTrue(overlay.rect().contains(overlay.modes.geometry()))
            overlay.start=QPointF(100,180);overlay.end=QPointF(400,380);overlay.confirm()
            self.assertEqual(controller.recording.audio_mode,'system')
            self.assertIn('电脑声音',controller.record_controls.hint.text())
            self.assertFalse(overlay.video_audio_combo.isEnabled())
            self.assertIsNone(controller.recording.audio_source,'Countdown must not start audio capture')
            controller.cancel();self.assertFalse(controller.capturing)
            self.assertFalse(list((window.home/'recordings').glob('*.mp4')))
        finally:
            controller.cancel();controller.shutdown();window.close();self.app.processEvents()


if __name__=='__main__':unittest.main()
