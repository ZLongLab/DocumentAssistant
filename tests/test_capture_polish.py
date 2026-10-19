import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QColor
from PySide6.QtWidgets import QApplication
from test_upgrade import Fixture
from document_assistant.screen_capture import AnnotationCanvas, CaptureEditor, CaptureController
from document_assistant.gui import MainWindow
from tests.gui_wait import settle_search

class CapturePolishTests(Fixture):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def test_zoom_and_pan_preserve_source_and_annotation_coordinates(self):
        image=QImage(3840,2160,QImage.Format.Format_ARGB32);image.fill(QColor('blue'))
        canvas=AnnotationCanvas(image);canvas.resize(800,450)
        canvas.marks=[('rectangle',QPointF(100,100),QPointF(300,300),'','#e34f45')]
        original=canvas.rendered().copy()
        before=canvas.scale();canvas.set_zoom(1.)
        self.assertLess(before,1);self.assertEqual(canvas.image_rect().width(),3840)
        canvas.pan=QPointF(200,100);canvas.clamp_pan()
        rect=canvas.image_rect();point=QPointF(rect.x()+250,rect.y()+200)
        self.assertEqual(canvas.image_point(point),QPointF(250,200))
        self.assertEqual(canvas.rendered(),original);self.assertEqual(canvas.image,image)
        canvas.set_zoom();self.assertEqual(canvas.pan,QPointF());self.assertEqual(canvas.rendered(),original)

    def test_copy_failure_can_retry_without_duplicate_and_save_after_edit(self):
        image=QImage(300,200,QImage.Format.Format_ARGB32);image.fill(QColor('blue'))
        controller=SimpleNamespace(settings={'directory':str(self.root/'captures')},last_saved=None,notify=lambda *a:None)
        editor=CaptureEditor(image,controller)
        with patch('document_assistant.screen_capture.copy_image',side_effect=OSError('clipboard busy')):
            editor.save();first=controller.last_saved
            self.assertTrue(first.is_file());self.assertTrue(editor.save_button.isEnabled())
            editor.save();self.assertEqual(len(list(first.parent.glob('*.png'))),1)
            editor.canvas.marks.append(('rectangle',QPointF(10,10),QPointF(80,80),'','#e34f45'))
            editor.canvas.changed.emit();editor.save()
            self.assertNotEqual(controller.last_saved,first)
            self.assertEqual(len(list(first.parent.glob('*.png'))),2)
            self.assertNotEqual(QImage(str(first)),QImage(str(controller.last_saved)))
        editor.reject()

    def test_hotkey_finish_restores_target_without_activating_workbench(self):
        calls=[]
        window=SimpleNamespace(setAttribute=lambda *a:calls.append(a),show=lambda:calls.append('show'))
        controller=SimpleNamespace(editor=None,capturing=True,restore_main=True,exiting=False,from_hotkey=True,
            previous_foreground=123,window=window,show_main=lambda:calls.append('activate-main'),
            long_capture=None,long_stop=None)
        with patch('document_assistant.screen_capture.restore_foreground') as restore:
            CaptureController.finished(controller);self.app.processEvents()
            restore.assert_called_once_with(123)
        self.assertNotIn('activate-main',calls)
        self.assertIn((Qt.WidgetAttribute.WA_ShowWithoutActivating,True),calls)

    def test_small_workbench_collapses_details_and_hotkey_status_is_honest(self):
        # This regression covers the classic responsive detail pane. The compact
        # workbench intentionally keeps the pane collapsed until explicitly opened.
        with patch.dict(os.environ,{'DOCUMENTASSISTANT_LAYOUT':'classic'}):
            window=MainWindow(self.root/'settings')
        window.show();settle_search(window)
        window.resize(960,640);self.app.processEvents();self.app.processEvents()
        self.assertTrue(window.details_panel.isHidden());self.assertTrue(window.import_hint.isHidden())
        window.resize(1400,850);self.app.processEvents();self.app.processEvents()
        self.assertFalse(window.details_panel.isHidden());self.assertFalse(window.import_hint.isHidden())
        controller=CaptureController(window,activate=False)
        self.assertIn('未启用',window.screenshot_button.text())
        controller.shutdown();window.close();self.app.processEvents()

if __name__=='__main__':unittest.main()
