"""Regression for native DPR versus rounded Windows screen geometry."""
import unittest
from PySide6.QtCore import QRect,QRectF,QSize
from PySide6.QtGui import QColor,QImage
from document_assistant.capture_pixels import crop_selection,pixel_scale,selection_pixels


class PixelAlignmentTests(unittest.TestCase):
    def test_150_percent_screen_keeps_native_origin_and_pixel_extent(self):
        image=QImage(2560,1600,QImage.Format.Format_RGB32)
        image.fill(QColor('#223344'));image.setDevicePixelRatio(1.5)
        image.setPixelColor(228,303,QColor('#d94e35'))
        logical=QSize(1707,1067)
        selection=QRectF(152,202,503,233)
        self.assertEqual(pixel_scale(image,logical),(1.5,1.5))
        self.assertEqual(selection_pixels(image,selection,logical),QRect(228,303,755,350))
        crop=crop_selection(image,selection,logical)
        self.assertEqual(crop.pixelColor(0,0),QColor('#d94e35'))
        self.assertEqual(crop.size(),QSize(755,350))
        self.assertEqual(crop.devicePixelRatio(),1)

    def test_rounding_tolerance_tracks_dpr_and_does_not_hide_real_resizing(self):
        image=QImage(2560,1600,QImage.Format.Format_RGB32)
        image.setDevicePixelRatio(2.5)
        self.assertEqual(pixel_scale(image,QSize(1024,640)),(2.5,2.5))
        image=QImage(401,301,QImage.Format.Format_RGB32)
        self.assertEqual(pixel_scale(image,QSize(400,300)),(401/400,301/300))


if __name__=='__main__':unittest.main()
