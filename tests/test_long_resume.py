"""Pause/repaint/resume must keep the current viewport as the match reference."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QRect,QRectF
from PySide6.QtGui import QColor,QPainter
from PySide6.QtWidgets import QApplication
from document_assistant.long_stitch import VerticalStitcher
from document_assistant.long_capture import LongCaptureSession
from tests.test_long_capture import make_page


class LongResumeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.page=make_page()

    def frame(self,offset,tint=0,hover=False):
        image=self.page.copy(0,offset,900,900)
        p=QPainter(image)
        if tint:p.fillRect(image.rect(),QColor(255,255,255,tint))
        if hover:p.fillRect(600,300,70,50,QColor('#3b94d1'))
        p.end();return image

    def test_pause_repaint_then_resume_in_both_directions(self):
        for direction in (1,-1):
            with self.subTest(direction=direction):
                start=1200;paused=start+direction*220;resumed=paused+direction*220
                stitcher=VerticalStitcher(self.frame(start))
                self.assertEqual(stitcher.append(self.frame(paused)).added,220)
                before=stitcher.image();position=stitcher.position;count=len(stitcher.parts)
                for tint in range(2,25,2):
                    self.assertEqual(stitcher.append(self.frame(paused,tint)).status,'unchanged')
                    self.assertEqual(stitcher.position,position)
                    self.assertEqual(len(stitcher.parts),count)
                self.assertEqual(stitcher.image(),before,'Pause must not rewrite archived pixels')
                result=stitcher.append(self.frame(resumed,24))
                self.assertEqual(result.added,220)
                self.assertEqual(stitcher.height,1340)
                image=stitcher.image();latest=self.frame(resumed,24)
                if direction==1:
                    self.assertEqual(image.copy(0,0,900,1120),before)
                    self.assertEqual(image.copy(0,1120,900,220),latest.copy(0,680,900,220))
                else:
                    self.assertEqual(image.copy(0,220,900,1120),before)
                    self.assertEqual(image.copy(0,0,900,220),latest.copy(0,0,900,220))

    def test_hover_appears_and_disappears_during_pause(self):
        stitcher=VerticalStitcher(self.frame(0))
        stitcher.append(self.frame(220));before=stitcher.image()
        for hover in (True,True,False,True,False):
            self.assertEqual(stitcher.append(self.frame(220,hover=hover)).status,'unchanged')
        self.assertEqual(stitcher.image(),before)
        self.assertEqual(stitcher.append(self.frame(440)).added,220)

    def chat_frame(self,offset,buttons):
        image=self.frame(offset)
        if buttons:
            p=QPainter(image);p.fillRect(40,700-offset,360,42,QColor('#eeeeee'))
            for x in range(52,380,38):p.fillRect(x,710-offset,16,18,QColor('#575757'))
            p.end()
        return image

    def test_chat_message_action_row_can_disappear_during_pause(self):
        stitcher=VerticalStitcher(self.chat_frame(0,True))
        self.assertEqual(stitcher.append(self.chat_frame(220,True)).added,220)
        before=stitcher.image()
        self.assertEqual(stitcher.append(self.chat_frame(220,False)).status,'unchanged')
        self.assertEqual(stitcher.image(),before)
        self.assertEqual(stitcher.append(self.chat_frame(440,False)).added,220)

    def test_chat_message_action_row_can_appear_during_pause_then_hide_on_scroll(self):
        stitcher=VerticalStitcher(self.chat_frame(0,False))
        self.assertEqual(stitcher.append(self.chat_frame(220,False)).added,220)
        self.assertEqual(stitcher.append(self.chat_frame(220,True)).status,'unchanged')
        self.assertEqual(stitcher.append(self.chat_frame(440,False)).added,220)

    def test_compact_chat_viewport_at_multiple_scales(self):
        for ratio in (1,1.5,2):
            with self.subTest(ratio=ratio):
                def frame(offset,buttons):
                    return self.chat_frame(offset,buttons).copy(0,0,760,500).scaled(round(760*ratio),round(500*ratio))
                stitcher=VerticalStitcher(frame(480,True))
                self.assertEqual(stitcher.append(frame(600,True)).added,round(120*ratio))
                self.assertEqual(stitcher.append(frame(600,False)).status,'unchanged')
                self.assertEqual(stitcher.append(frame(720,False)).added,round(120*ratio))

    def test_large_page_replacement_is_not_a_hover_action_row(self):
        stitcher=VerticalStitcher(self.frame(0));stitcher.append(self.frame(220))
        before=stitcher.image();changed=self.frame(220)
        p=QPainter(changed);p.fillRect(0,300,900,250,QColor('#28374d'));p.end()
        self.assertEqual(stitcher.append(changed).status,'no_overlap')
        self.assertEqual(stitcher.image(),before)

    def test_real_one_pixel_scroll_is_not_treated_as_stationary_repaint(self):
        for ratio in (1,1.5,2):
            with self.subTest(ratio=ratio):
                width,height=round(760*ratio),round(500*ratio)
                page=self.page.copy(0,0,760,1000).scaled(width,round(1000*ratio))
                stitcher=VerticalStitcher(page.copy(0,100,width,height))
                for offset in range(101,109):
                    self.assertEqual(stitcher.append(page.copy(0,offset,width,height)).added,1)
                self.assertEqual(stitcher.image(),page.copy(0,100,width,height+8))

    def test_unrelated_stationary_page_cannot_replace_reference(self):
        stitcher=VerticalStitcher(self.frame(0));stitcher.append(self.frame(220))
        before=stitcher.image();reference=stitcher.previous.copy()
        other=make_page(seed=911).copy(0,220,900,900)
        for _ in range(8):self.assertEqual(stitcher.append(other).status,'no_overlap')
        self.assertEqual(stitcher.previous,reference);self.assertEqual(stitcher.image(),before)
        self.assertEqual(stitcher.append(self.frame(440)).added,220)

    def test_session_can_finish_after_pause_and_last_scroll(self):
        current=[self.frame(0)];completed=[]
        geometry=QRect(0,0,900,900)
        screen=SimpleNamespace(geometry=lambda:geometry,availableGeometry=lambda:QRect(0,0,900,1100))
        session=LongCaptureSession(screen,QRectF(0,0,900,900),'测试',grabber=lambda:current[0])
        self.addCleanup(session.cancel)
        session.completed.connect(lambda *args:completed.append(args))
        with patch('document_assistant.long_capture.CaptureKeys'):
            session.start()
        current[0]=self.frame(220);session.poll()
        for tint in range(2,25,2):
            current[0]=self.frame(220,tint);session.poll()
            self.assertTrue(session.timer.isActive())
            self.assertFalse(session.done)
        current[0]=self.frame(440,24);session.finish()
        self.assertEqual(len(completed),1)
        self.assertEqual(completed[0][0].height(),1340)
        self.assertEqual(completed[0][1],'')


if __name__=='__main__':unittest.main()
