"""Generated regressions for the failure patterns from private replay evidence."""
import unittest
import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QImage,QPainter,QLinearGradient
from PySide6.QtWidgets import QApplication
from document_assistant.long_stitch import VerticalStitcher
from tests.test_long_capture import make_page


class BrowserRepaintTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.page=make_page()

    def chat_frame(self,offset):
        image=self.page.copy(0,offset,900,700);p=QPainter(image)
        fade=QLinearGradient(0,615,0,690);fade.setColorAt(0,QColor(255,255,255,0));fade.setColorAt(1,QColor(255,255,255,255))
        p.fillRect(0,615,900,85,fade)
        p.setPen(QColor('#d7d7d7'));p.setBrush(QColor('#fafafa'));p.drawRoundedRect(0,680,899,40,12,12)
        p.end();return image

    def test_fixed_footer_fade_does_not_break_small_upward_scroll(self):
        stitcher=VerticalStitcher(self.chat_frame(400))
        result=stitcher.append(self.chat_frame(378))
        self.assertEqual((result.status,result.added),('prepended',22))

    def test_independent_hover_rows_do_not_break_valid_overlap(self):
        first=self.page.copy(0,0,900,700);frame=self.page.copy(0,60,900,700)
        p=QPainter(frame)
        p.fillRect(30,140,560,24,QColor('#eeeeee'))
        p.fillRect(200,530,400,24,QColor('#d8e6f4'));p.end()
        stitcher=VerticalStitcher(first)
        self.assertEqual(stitcher.append(frame).added,60)

    def test_one_line_snaps_to_adjacent_raster_row_during_real_scroll(self):
        first=self.page.copy(0,300,900,600);frame=self.page.copy(0,70,900,600)
        original=frame.copy();p=QPainter(frame)
        # A single text line is rounded differently by the browser compositor.
        p.drawImage(0,82,original.copy(0,83,900,20));p.end()
        stitcher=VerticalStitcher(first)
        self.assertEqual(stitcher.append(frame).added,230)
        self.assertEqual(stitcher.position,-230)

    def photo(self):
        y,x=np.indices((1800,760),dtype=np.float32)
        rgba=np.empty((1800,760,4),dtype=np.uint8)
        for channel in range(3):
            values=115+55*np.sin(x/(23+channel*3)+y/47)+45*np.sin(x/83-y/(19+channel*7))
            rgba[:,:,channel]=np.clip(values,10,235).astype(np.uint8)
        rgba[:,:,3]=255
        return QImage(rgba.data,760,1800,rgba.strides[0],QImage.Format.Format_RGBA8888).copy()

    def test_slight_photo_raster_change_and_hover_toolbar(self):
        page=self.photo();first=page.copy(0,400,760,600)
        frame=page.copy(0,430,760,600).convertToFormat(QImage.Format.Format_RGBA8888)
        data=np.frombuffer(frame.bits(),np.uint8).reshape(600,frame.bytesPerLine())[:,:760*4].reshape(600,760,4)
        noise=np.ones((600,760,1),dtype=np.int16);noise[:,::13]=10
        data[:,:,:3]=np.clip(data[:,:,:3].astype(np.int16)+noise,0,255).astype(np.uint8)
        p=QPainter(frame);p.fillRect(30,500,320,24,QColor('#eeeeee'));p.end()
        stitcher=VerticalStitcher(first)
        self.assertEqual(stitcher.append(frame).added,30)
        output=stitcher.image()
        self.assertEqual(output.copy(0,0,760,600),first.convertToFormat(QImage.Format.Format_RGB32))
        self.assertEqual(output.copy(0,600,760,30),frame.copy(0,570,760,30).convertToFormat(QImage.Format.Format_RGB32))

    def test_dense_photo_replacement_cannot_match_by_general_shape(self):
        page=self.photo();first=page.copy(0,400,760,600)
        other=page.copy(0,430,760,600).mirrored(True,False)
        self.assertEqual(VerticalStitcher(first).append(other).status,'no_overlap')

    def test_two_large_replacements_are_not_small_overlays(self):
        first=self.page.copy(0,0,900,700);frame=self.page.copy(0,60,900,700)
        p=QPainter(frame);p.fillRect(0,150,900,90,QColor('#abcdef'));p.fillRect(0,400,900,90,QColor('#abcdef'));p.end()
        stitcher=VerticalStitcher(first)
        self.assertEqual(stitcher.append(frame).status,'no_overlap')
        self.assertEqual(stitcher.image(),first)

    def test_same_fixed_header_cannot_link_unrelated_bodies(self):
        first=self.page.copy(0,0,900,700);other=make_page(seed=981).copy(0,0,900,700)
        p=QPainter(other);p.drawImage(0,0,first.copy(0,0,900,80));p.end()
        self.assertEqual(VerticalStitcher(first).append(other).status,'no_overlap')


if __name__=='__main__':unittest.main()
