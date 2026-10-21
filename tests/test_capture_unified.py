import unittest
from types import SimpleNamespace
from PySide6.QtCore import QPoint,QPointF,QRect,Qt
from PySide6.QtGui import QColor,QImage
from PySide6.QtWidgets import QApplication,QWidget
from PySide6.QtTest import QTest
from document_assistant.long_stitch import VerticalStitcher
from document_assistant.selection_overlay import SelectionOverlay
from tests.test_long_capture import make_page


class BidirectionalStitchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.page=make_page()

    def frame(self,y):return self.page.copy(0,y,900,900)

    def test_upward_capture_prepends_content_in_document_order(self):
        stitcher=VerticalStitcher(self.frame(2400))
        for y in (1660,920,180):
            result=stitcher.append(self.frame(y))
            self.assertEqual((result.status,result.added),('prepended',740))
        self.assertEqual(stitcher.image(),self.page.copy(0,180,900,3120))

    def test_reversals_inside_covered_content_do_not_duplicate(self):
        stitcher=VerticalStitcher(self.frame(1600))
        expected=[(1900,'appended',300),(1750,'covered',0),(1400,'prepended',200),
                  (1700,'covered',0),(2000,'appended',100),(1600,'covered',0),(1200,'prepended',200)]
        for y,status,added in expected:
            with self.subTest(y=y):
                result=stitcher.append(self.frame(y))
                self.assertEqual((result.status,result.added),(status,added))
        self.assertEqual(stitcher.image(),self.page.copy(0,1200,900,1700))

    def test_upward_gap_and_top_size_limit_preserve_existing_capture(self):
        stitcher=VerticalStitcher(self.frame(2400),max_height=1100)
        original=stitcher.image()
        self.assertEqual(stitcher.append(self.frame(400)).status,'no_overlap')
        self.assertEqual(stitcher.append(self.frame(2100)).status,'limit')
        self.assertEqual(stitcher.image(),original)
        self.assertEqual(stitcher.append(self.frame(2300)).added,100)


class UnifiedCaptureToolbarTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def overlay(self,width=948,height=650):
        image=QImage(width,height,QImage.Format.Format_RGB32);image.fill(QColor('#203b52'))
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,width,height))
        overlay=SelectionOverlay(screen,image);overlay.show();self.app.processEvents()
        self.addCleanup(overlay.close);self.addCleanup(overlay.deleteLater)
        return overlay

    def select(self,overlay,a=QPoint(90,120),b=QPoint(800,430)):
        overlay.begin_drag(QPointF(a));overlay.end_drag(QPointF(b));self.app.processEvents()

    def test_mode_picker_is_inside_bottom_panel_before_and_after_selection(self):
        overlay=self.overlay()
        self.assertTrue(overlay.actions.isVisible())
        self.assertGreater(overlay.actions.y(),overlay.height()//2)
        for button in overlay.mode_buttons.values():
            self.assertTrue(overlay.actions.isAncestorOf(button))
        self.select(overlay)
        for button in overlay.mode_buttons.values():
            self.assertTrue(overlay.actions.isAncestorOf(button))
            self.assertTrue(button.isVisible())
        self.assertGreater(overlay.actions.y(),overlay.selection_rect().bottom())

    def test_mode_switching_keeps_selection_and_annotations_and_audio_option(self):
        overlay=self.overlay();self.select(overlay);selection=overlay.selection_rect()
        overlay.canvas.marks=[('rectangle',QPointF(20,20),QPointF(90,90),'','#e34f45')]
        image=overlay.rendered().copy()
        for mode in ('long','video','photo'):
            QTest.mouseClick(overlay.mode_buttons[mode],Qt.MouseButton.LeftButton)
            self.assertEqual(overlay.selection_rect(),selection)
            self.assertEqual(overlay.mode,mode)
            if mode=='video':self.assertTrue(overlay.video_audio_combo.isVisible())
        self.assertEqual(overlay.rendered(),image)

    def test_all_controls_stay_reachable_on_narrow_screens_and_at_edges(self):
        for width in (640,800,948,1280):
            with self.subTest(width=width):
                overlay=self.overlay(width)
                for top,bottom in ((110,350),(440,630)):
                    self.select(overlay,QPoint(30,top),QPoint(width-30,bottom))
                    for mode in ('photo','long','video'):
                        overlay.set_mode(mode)
                        for tool in (('view','mask','text') if mode=='photo' else ('view',)):
                            if mode=='photo':overlay.set_tool(tool)
                            overlay.position_actions();self.app.processEvents()
                            self.assertTrue(overlay.rect().contains(overlay.actions.geometry()))
                            buttons=[*overlay.mode_buttons.values(),overlay.cancel_button,overlay.confirm_button]
                            if mode=='photo':buttons += [*overlay.tool_buttons.values(),overlay.save_button]
                            if mode=='video':buttons += [overlay.video_audio_combo]
                            for button in buttons:
                                point=button.mapTo(overlay.actions,QPoint())
                                self.assertTrue(overlay.actions.rect().contains(QRect(point,button.size())),(width,mode,tool,button.geometry()))
                overlay.close()


if __name__=='__main__':unittest.main()
