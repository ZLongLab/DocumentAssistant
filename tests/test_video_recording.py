import unittest
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPoint,QPointF,QRect,QRectF,QSize,Qt
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from test_upgrade import Fixture
from document_assistant.selection_overlay import SelectionOverlay
from document_assistant.video_recording import save_video,RegionRecorder
from document_assistant.screen_capture import CaptureController
from document_assistant.gui import MainWindow
from document_assistant.video_ui import controls_position,VideoPreview


class VideoTests(Fixture):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_capture_mode_defaults_to_photo_and_video_emits_region(self):
        screen=SimpleNamespace(geometry=lambda:QRect(-800,0,800,600))
        image=QImage(1200,900,QImage.Format.Format_RGB32);image.fill(QColor('blue'))
        overlay=SelectionOverlay(screen,image);photos=[];videos=[]
        overlay.selected.connect(photos.append);overlay.video_selected.connect(videos.append)
        overlay.start=QPointF(300,250);overlay.end=QPointF(100,150)
        self.assertEqual(overlay.mode,'photo');overlay.confirm();self.assertEqual(photos[0].size(),QSize(300,150))
        overlay.mode_buttons['video'].click();overlay.confirm()
        self.assertEqual(len(photos),1);self.assertEqual(videos[0],overlay.selection_rect())
        second=SelectionOverlay(screen,image);self.assertEqual(second.mode,'photo')
        overlay.close();second.close()

    def test_control_bar_never_overlaps_region_on_negative_origin_screen(self):
        area=QRect(-1920,0,1920,1080);region=QRect(-1500,200,800,400);size=QSize(380,58)
        point=controls_position(area,region,size);self.assertIsNotNone(point)
        self.assertFalse(region.intersects(QRect(point,size)));self.assertTrue(area.contains(QRect(point,size)))
        self.assertIsNone(controls_position(area,area,size))

    def test_video_save_collision_and_write_failure_preserve_source(self):
        source=self.root/'temporary.mp4';source.write_bytes(b'synthetic-video'*100)
        when=datetime(2026,10,14,10,0,0);folder=self.root/'saved'
        first=save_video(source,folder,when);second=save_video(source,folder,when)
        self.assertNotEqual(first,second);self.assertEqual(source.read_bytes(),first.read_bytes())
        with patch('document_assistant.video_recording.shutil.copyfileobj',side_effect=OSError('disk full')):
            with self.assertRaises(OSError):save_video(source,folder,when)
        self.assertEqual(len(list(folder.glob('*.mp4'))),2);self.assertTrue(source.is_file())

    def test_failed_save_keeps_preview_open_for_retry(self):
        source=self.root/'temporary.mp4';source.write_bytes(b'synthetic-video'*100)
        controller=SimpleNamespace(settings={'directory':str(self.root/'saved')},notify=lambda *args:None)
        preview=VideoPreview(source,controller);preview.show();self.app.processEvents()
        with patch('document_assistant.video_ui.save_video',side_effect=OSError('busy')):preview.save()
        self.assertTrue(preview.isVisible());self.assertIn('保存失败',preview.error.text());self.assertTrue(source.exists())
        preview.save();self.assertFalse(preview.isVisible());self.assertTrue(controller.last_video.is_file())
        preview.release_player();preview.deleteLater();self.app.processEvents()

    def test_countdown_locks_visible_selection_but_escape_still_cancels(self):
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,800,600),availableGeometry=lambda:QRect(0,0,800,580))
        image=QImage(800,600,QImage.Format.Format_RGB32);image.fill(QColor('blue'))
        window=MainWindow(self.root/'home');controller=CaptureController(window,activate=False)
        overlay=SelectionOverlay(screen,image);controller.overlays=[overlay];controller.capturing=True
        overlay.start=QPointF(100,180);overlay.end=QPointF(400,380)
        before=overlay.selection_rect();overlay.cancelled.connect(controller.cancel)
        emitted=[];overlay.video_selected.connect(emitted.append);overlay.set_mode('video');overlay.show()
        try:
            controller.begin_video(screen,before)
            QTest.mousePress(overlay,Qt.MouseButton.LeftButton,pos=QPoint(200,250))
            QTest.mouseMove(overlay,QPoint(250,300));QTest.mouseRelease(overlay,Qt.MouseButton.LeftButton,pos=QPoint(250,300))
            self.assertEqual(overlay.selection_rect(),before)
            QTest.keyClick(overlay,Qt.Key.Key_Return);self.assertFalse(emitted)
            QTest.keyClick(overlay,Qt.Key.Key_Escape);self.assertFalse(controller.capturing)
        finally:
            controller.cancel();QTest.qWait(300);controller.shutdown();window.close()

    def test_encoder_failure_preserves_partial_file_during_cleanup(self):
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,800,600))
        recorder=RegionRecorder(screen,QRectF(0,0,20,20),self.root)
        recorder.path=self.root/'partial.mp4';payload=b'partially-written-recording'*20;recorder.path.write_bytes(payload)
        recorder.fail('synthetic encoder error');recorder.discard()
        self.assertTrue(recorder.path.is_file(),'Failure cleanup must preserve recorded bytes')
        self.assertEqual(recorder.path.read_bytes(),payload)

    def test_recording_rejects_hotkey_changes_before_registration(self):
        window=MainWindow(self.root/'home');controller=CaptureController(window,activate=False)
        controller.capturing=True;controller.recording=SimpleNamespace(done=False)
        try:
            with patch.object(controller.hotkey,'prepare') as prepare:
                with self.assertRaisesRegex(ValueError,'完成'):controller.configure('Alt+R',str(self.root/'saved'))
                prepare.assert_not_called()
        finally:controller.capturing=False;controller.recording=None;controller.shutdown();window.close()

    def test_cancel_stops_pending_capture_before_deferred_cleanup(self):
        window=MainWindow(self.root/'home');controller=CaptureController(window,activate=False)
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,800,600))
        captures=[]
        recorder=RegionRecorder(screen,QRectF(0,0,20,20),self.root,grabber=lambda:captures.append('late-frame'))
        controller.recording=recorder;controller.capturing=True;recorder.clock.start();recorder.timer.start(10)
        try:
            controller.cancel()
            self.assertFalse(recorder.timer.isActive(),'Cancellation must stop screen sampling immediately')
            self.assertTrue(recorder.done)
            # A new capture can begin while old file cleanup is pending.
            controller.capturing=True;QTest.qWait(300)
            self.assertTrue(controller.capturing);self.assertFalse(captures)
        finally:controller.capturing=False;controller.shutdown();window.close()

if __name__=='__main__':unittest.main()
