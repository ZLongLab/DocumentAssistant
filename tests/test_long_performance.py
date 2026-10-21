"""Regressions for frequent acquisition and native-pixel region grabs."""
import unittest
from types import SimpleNamespace
from PySide6.QtCore import QRect,QRectF,Qt
from PySide6.QtGui import QColor,QImage,QPainter
from PySide6.QtWidgets import QApplication
from document_assistant.capture_pixels import crop_selection
from document_assistant.long_capture import LongCaptureSession
from document_assistant.long_stitch import VerticalStitcher
from tests.test_long_capture import make_page


class LongPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_session_keeps_a_16ms_precise_acquisition_budget(self):
        geometry=QRect(0,0,900,900)
        screen=SimpleNamespace(geometry=lambda:geometry,availableGeometry=lambda:geometry)
        session=LongCaptureSession(screen,QRectF(20,20,600,500),'测试')
        self.addCleanup(session.cancel)
        self.assertLessEqual(session.timer.interval(),16)
        self.assertEqual(session.timer.timerType(),Qt.TimerType.PreciseTimer)

    def screen(self,ratio,logical=QRect(0,0,800,600)):
        image=QImage(round(logical.width()*ratio),round(logical.height()*ratio),QImage.Format.Format_RGB32)
        p=QPainter(image)
        for y in range(image.height()):
            p.fillRect(0,y,image.width(),1,QColor(y%251,y*3%251,y*7%251))
        for x in range(0,image.width(),7):p.fillRect(x,0,2,image.height(),QColor(x%251,80,130))
        p.end();image.setDevicePixelRatio(ratio);calls=[]
        def grab(window,*area):
            calls.append(area)
            if area:
                x,y,w,h=area
                result=image.copy(round(x*ratio),round(y*ratio),round(w*ratio),round(h*ratio))
            else:result=image.copy()
            result.setDevicePixelRatio(ratio)
            return SimpleNamespace(toImage=lambda:result)
        return SimpleNamespace(devicePixelRatio=lambda:ratio,grabWindow=grab),image,calls

    def test_region_grab_matches_full_crop_at_fractional_scales(self):
        from document_assistant.long_capture import capture_region
        for ratio in (1,1.25,1.5,1.75,2):
            with self.subTest(ratio=ratio):
                geometry=QRect(-800,30,800,600);rect=QRectF(13.25,21.75,260.5,203.25)
                screen,image,calls=self.screen(ratio,geometry)
                result=capture_region(screen,rect,geometry)
                self.assertEqual(result,crop_selection(image,rect,geometry.size()))
                self.assertTrue(calls[0],'Interior selection should not grab the entire screen')
                self.assertEqual(result.devicePixelRatio(),1)

    def test_rounded_screen_edge_stays_inside_native_pixels(self):
        from document_assistant.long_capture import capture_region
        geometry=QRect(0,0,1707,800);rect=QRectF(1400.5,600.5,306.5,199.5)
        screen,image,_=self.screen(1.5,geometry)
        self.assertEqual(capture_region(screen,rect,geometry),crop_selection(image,rect,geometry.size()))

    def test_exact_anchors_cannot_accept_an_unrelated_page_with_a_matching_patch(self):
        page=make_page();other=make_page(seed=838)
        first=page.copy(0,0,900,900);frame=other.copy(0,160,900,900)
        p=QPainter(frame);p.drawImage(0,0,first.copy(0,160,900,120));p.end()
        stitcher=VerticalStitcher(first)
        self.assertEqual(stitcher.append(frame).status,'no_overlap')
        self.assertEqual(stitcher.height,900)

    def test_small_brightness_change_uses_robust_matching_without_exact_rows(self):
        page=make_page();first=page.copy(0,0,900,900);frame=page.copy(0,240,900,900)
        # A slight compositing tint changes every row without changing layout.
        p=QPainter(frame);p.fillRect(frame.rect(),QColor(255,255,255,2));p.end()
        stitcher=VerticalStitcher(first)
        self.assertEqual(stitcher.append(frame).added,240)


if __name__=='__main__':unittest.main()
