import os
from pathlib import Path
import random
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QRect,QRectF,Qt
from PySide6.QtGui import QColor,QFont,QFontDatabase,QImage,QPainter
from PySide6.QtWidgets import QApplication,QWidget
from document_assistant.long_stitch import VerticalStitcher


def make_page(width=900,height=6500,seed=42):
    # The offscreen Qt plugin may have no fonts. Load a real font instead of
    # silently turning this document fixture into identical missing-glyph boxes.
    if not QFontDatabase.families():
        font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts/segoeui.ttf'
        if font.exists():QFontDatabase.addApplicationFont(str(font))
    image=QImage(width,height,QImage.Format.Format_RGB32);image.fill(QColor('#f7f8fb'))
    painter=QPainter(image);painter.setFont(QFont('Segoe UI',12));rng=random.Random(seed)
    words='capture document testing scroll source page review frame content report reliable preview analysis'.split()
    for index,y in enumerate(range(25,height-25,28)):
        painter.setPen(QColor('#16324b'))
        painter.drawText(24,y,f'{index:04}  '+ ' '.join(rng.choices(words,k=rng.randint(5,10))))
        if index%7==0:
            painter.fillRect(24,y+4,rng.randint(80,width-60),4,QColor(rng.randrange(40,180),rng.randrange(60,150),190))
    painter.end();return image


class LongStitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        cls.page=make_page()

    def frame(self,offset):return self.page.copy(0,offset,900,900)

    def test_fast_scroll_with_small_real_overlap_is_pixel_exact(self):
        for step in (100,740,800):
            with self.subTest(step=step):
                stitcher=VerticalStitcher(self.frame(0))
                for offset in (step,step*2,step*3):
                    result=stitcher.append(self.frame(offset))
                    self.assertEqual((result.status,result.added),('appended',step))
                self.assertEqual(stitcher.image(),self.page.copy(0,0,900,900+step*3))

    def test_gap_is_rejected_without_inventing_a_shorter_scroll(self):
        stitcher=VerticalStitcher(self.frame(0));before=stitcher.image()
        self.assertEqual(stitcher.append(self.frame(1500)).status,'no_overlap')
        self.assertEqual(stitcher.image(),before)
        self.assertEqual(stitcher.append(self.frame(400)).added,400)

    def test_unrelated_page_and_periodic_patterns_are_not_seams(self):
        stitcher=VerticalStitcher(self.frame(0))
        other=make_page(seed=921)
        self.assertEqual(stitcher.append(other.copy(0,350,900,900)).status,'no_overlap')
        stripes=QImage(900,1800,QImage.Format.Format_RGB32);stripes.fill(QColor('white'))
        p=QPainter(stripes)
        for y in range(0,1800,40):p.fillRect(20,y,860,15,QColor('#336699'))
        p.end();stitcher=VerticalStitcher(stripes.copy(0,0,900,900))
        self.assertEqual(stitcher.append(stripes.copy(0,13,900,900)).status,'no_overlap')

    def test_upward_and_repeated_frames_do_not_duplicate_content(self):
        stitcher=VerticalStitcher(self.frame(400))
        self.assertEqual(stitcher.append(self.frame(400)).status,'unchanged')
        result=stitcher.append(self.frame(100))
        self.assertEqual((result.status,result.added),('prepended',300))
        self.assertEqual(stitcher.append(self.frame(700)).added,300)
        self.assertEqual(stitcher.image(),self.page.copy(0,100,900,1500))

    def test_local_animation_does_not_hide_a_real_scroll(self):
        stitcher=VerticalStitcher(self.frame(0))
        frame=self.frame(220);p=QPainter(frame)
        p.fillRect(600,300,85,70,QColor('#3b94d1'));p.end()
        self.assertEqual(stitcher.append(frame).added,220)

    def test_size_changes_and_limits_preserve_existing_parts(self):
        stitcher=VerticalStitcher(self.frame(0),max_height=1000)
        self.assertEqual(stitcher.append(self.frame(220)).status,'limit')
        self.assertEqual(stitcher.height,900)
        self.assertEqual(stitcher.append(QImage(800,900,QImage.Format.Format_RGB32)).status,'size_changed')


class LongSessionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.page=make_page()

    def session(self,offset=0,**kwargs):
        from document_assistant.long_capture import LongCaptureSession
        current=[self.page.copy(0,offset,900,900)]
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,900,900),availableGeometry=lambda:QRect(0,0,900,1100))
        session=LongCaptureSession(screen,QRectF(0,0,900,900),'Alt+S',grabber=lambda:current[0],**kwargs)
        keys=patch('document_assistant.long_capture.CaptureKeys');keys.start();self.addCleanup(keys.stop)
        session.start();session.timer.stop();self.addCleanup(session.cancel)
        return session,current

    def test_capture_cadence_keeps_intermediate_wheel_frames(self):
        session,_=self.session()
        self.assertLessEqual(session.timer.interval(),50)
        self.assertEqual(session.timer.timerType(),Qt.TimerType.PreciseTimer)

    def test_finish_includes_last_reliably_matched_frame_without_a_pause(self):
        session,current=self.session();completed=[];session.completed.connect(lambda *args:completed.append(args))
        current[0]=self.page.copy(0,220,900,900)
        session.finish()
        self.assertEqual(completed[0][0],self.page.copy(0,0,900,1120))
        self.assertFalse(completed[0][1]);self.assertEqual(completed[0][2],2)

    def test_selection_snapshot_preserves_first_screen_during_startup(self):
        initial=self.page.copy(0,0,900,900)
        session,_=self.session(220,initial_frame=initial)
        self.assertEqual(session.stitcher.image(),self.page.copy(0,0,900,1120))

    def test_no_overlap_warns_and_returning_to_seam_resumes(self):
        session,current=self.session()
        current[0]=self.page.copy(0,1500,900,900);session.poll()
        self.assertEqual(session.stitcher.height,900)
        self.assertIn('未',session.controls.status.text())
        current[0]=self.page.copy(0,400,900,900);session.poll()
        self.assertEqual(session.stitcher.height,1300)
        self.assertIn('已拼接',session.controls.status.text())

    def test_failed_final_overlap_is_explicit_and_cancel_is_idempotent(self):
        session,current=self.session();completed=[];session.completed.connect(lambda *args:completed.append(args))
        current[0]=self.page.copy(0,1500,900,900);session.finish()
        self.assertEqual(completed[0][0].height(),900);self.assertIn('只有一屏',completed[0][1])
        self.assertIn('最后',completed[0][1]);session.cancel();session.finish()
        self.assertEqual(len(completed),1)

    def test_controller_keeps_overlay_snapshot_before_destroying_selection(self):
        from document_assistant.screen_capture import CaptureController
        first=self.page.copy(0,0,900,900)
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,900,900),availableGeometry=lambda:QRect(0,0,900,1100))
        window=QWidget();delayed=[]
        controller=SimpleNamespace(long_capture=None,recording=None,hotkey=SimpleNamespace(ident=None),
            window=window,overlays=[SimpleNamespace(screen_ref=screen,image=first)],
            long_stop=None,tray=None,from_hotkey=False,long_completed=lambda *args:None,
            long_failed=lambda value:self.fail(value),long_cancelled=lambda:None)
        controller.close_overlays=lambda:controller.overlays.clear()
        with patch('document_assistant.screen_capture.QTimer.singleShot',side_effect=lambda ms,fn:delayed.append((ms,fn))):
            CaptureController.begin_long(controller,screen,QRectF(0,0,900,900))
        self.addCleanup(controller.long_capture.cancel);self.addCleanup(window.close)
        self.assertFalse(controller.overlays)
        self.assertEqual(controller.long_capture.initial_frame,first)
        self.assertLessEqual(delayed[0][0],100)

    def test_finish_adds_last_upward_frame_and_finishing_on_covered_content_is_safe(self):
        for last in (0,350):
            with self.subTest(last=last):
                session,current=self.session(400);completed=[]
                session.completed.connect(lambda *args:completed.append(args))
                current[0]=self.page.copy(0,200,900,900);session.poll()
                current[0]=self.page.copy(0,last,900,900);session.finish()
                top=min(200,last)
                self.assertEqual(completed[0][0],self.page.copy(0,top,900,1300-top))
                self.assertFalse(completed[0][1])


if __name__=='__main__':unittest.main()
