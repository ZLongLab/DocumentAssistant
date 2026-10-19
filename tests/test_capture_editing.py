import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QPoint,QPointF,QRect,Qt
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox
from PySide6.QtTest import QTest
from test_upgrade import Fixture
from document_assistant.screen_capture import AnnotationCanvas,SelectionOverlay
from document_assistant.gui import MainWindow
from document_assistant.service import scan_files
from document_assistant.rules import DEFAULT_RULES
from tests.gui_wait import settle_search

class CaptureEditingTests(Fixture):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_move_style_delete_and_redo_keep_export_and_source_correct(self):
        image=QImage(600,400,QImage.Format.Format_ARGB32);image.fill(QColor('white'))
        canvas=AnnotationCanvas(image);canvas.resize(700,500);canvas.show();self.app.processEvents()
        canvas.tool='rectangle';canvas.append_mark(canvas.new_mark(QPointF(50,50),QPointF(150,100)))
        before=canvas.rendered().copy();canvas.tool='select'
        rect=canvas.image_rect();a=QPoint(int(rect.x()+100),int(rect.y()+75));b=a+QPoint(40,30)
        QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(canvas,b);QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=b)
        self.assertEqual(canvas.marks[0][1],QPointF(90,80));moved=canvas.rendered().copy()
        self.assertNotEqual(moved,before);self.assertEqual(canvas.image,image)
        canvas.apply_style(color='#377fde',width=8);styled=canvas.rendered().copy();self.assertNotEqual(styled,moved)
        canvas.undo();self.assertEqual(canvas.rendered(),moved);canvas.redo();self.assertEqual(canvas.rendered(),styled)
        canvas.selected_index=0;canvas.delete_selected();self.assertEqual(canvas.rendered(),image)
        canvas.undo();self.assertEqual(canvas.rendered(),styled);canvas.close()
    def test_mosaic_is_opaque_localized_and_reversible(self):
        image=QImage(120,100,QImage.Format.Format_ARGB32)
        for y in range(image.height()):
            for x in range(image.width()):image.setPixelColor(x,y,QColor('white' if (x+y)%2 else 'black'))
        canvas=AnnotationCanvas(image);canvas.tool='mask';canvas.stroke=[QPointF(20,50),QPointF(90,50)]
        canvas.append_mark(canvas.new_mark(canvas.stroke[0],canvas.stroke[-1]))
        result=canvas.rendered();self.assertNotEqual(result.pixelColor(50,50),image.pixelColor(50,50))
        self.assertEqual(result.pixelColor(50,50),result.pixelColor(51,50))
        self.assertEqual(result.pixelColor(5,5),image.pixelColor(5,5));self.assertEqual(result.pixelColor(50,50).alpha(),255)
        canvas.undo();self.assertEqual(canvas.rendered(),image);canvas.redo();self.assertEqual(canvas.rendered(),result)
    def test_selected_text_can_be_edited_without_highlight_in_export(self):
        image=QImage(500,200,QImage.Format.Format_ARGB32);image.fill(QColor('white'))
        canvas=AnnotationCanvas(image);canvas.tool='text';canvas.append_mark(canvas.new_mark(QPointF(20,20),QPointF(20,20),'before'))
        before=canvas.rendered().copy();canvas.selected_index=0
        self.assertEqual(canvas.rendered(),before)
        with patch.object(QInputDialog,'getText',return_value=('after',True)):canvas.edit_text()
        self.assertEqual(canvas.marks[0][3],'after');self.assertNotEqual(canvas.rendered(),before)
        canvas.undo();self.assertEqual(canvas.rendered(),before)
    def test_selection_resize_move_and_confirm_native_pixels(self):
        image=QImage(1200,900,QImage.Format.Format_ARGB32);image.fill(QColor('blue'))
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,800,600))
        overlay=SelectionOverlay(screen,image);overlay.show();self.app.processEvents();results=[];overlay.selected.connect(results.append)
        def drag(a,b):
            QTest.mousePress(overlay,Qt.MouseButton.LeftButton,pos=a);QTest.mouseMove(overlay,b);QTest.mouseRelease(overlay,Qt.MouseButton.LeftButton,pos=b)
        drag(QPoint(300,200),QPoint(50,50));self.assertFalse(results)
        drag(QPoint(300,125),QPoint(350,125));self.assertEqual(overlay.selection_rect().width(),300)
        drag(QPoint(180,100),QPoint(200,120));self.assertEqual(overlay.selection_rect().topLeft(),QPointF(70,70))
        QTest.keyClick(overlay,Qt.Key.Key_Return);self.assertEqual(results[0].width(),450);self.assertEqual(results[0].height(),225);overlay.close()
    def test_reclassify_applies_saved_rules_and_clears_only_manual_category(self):
        window=MainWindow(self.root/'settings');window.set_library(self.library);window.items=[self.item]
        self.catalog.save_category_rule('filename',self.path.stem,'项目资料')
        window.items[0].manual_fields='category,course';window.items[0].course='keep';window.populate_scan()
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes):window.reclassify()
        self.assertEqual(window.items[0].category,'项目资料');self.assertEqual(window.items[0].manual_fields,'course')
        fresh=scan_files([self.path],DEFAULT_RULES,self.library)[0][0];self.assertEqual(fresh.suggested,'项目资料')
        settle_search(window);window.close()
    def test_filter_chip_removes_only_selected_condition(self):
        window=MainWindow(self.root/'settings');window.show();self.app.processEvents()
        self.assertTrue(window.advanced_filters.isHidden())
        window.search_category.setCurrentText('其他');window.reading_filter.setCurrentIndex(1);self.app.processEvents()
        self.assertEqual(window.filter_chips.flow.count(),2)
        chip=window.filter_chips.flow.itemAt(0).widget();QTest.mouseClick(chip,Qt.MouseButton.LeftButton);self.app.processEvents()
        self.assertEqual(window.search_category.currentIndex(),0);self.assertEqual(window.reading_filter.currentIndex(),1)
        self.assertEqual(window.filter_chips.flow.count(),1);settle_search(window);window.close()
    def test_pdf_card_loads_actual_page_and_bad_pdf_has_readable_fallback(self):
        from document_assistant.cards import DocumentArtwork
        from tests.fixtures import make_examples
        source=make_examples(self.root/'examples')
        path=source/'研究文献.pdf';info=path.stat()
        item=SimpleNamespace(path=path,size=info.st_size,mtime_ns=info.st_mtime_ns,body='Readable fallback',category='研究文献')
        artwork=DocumentArtwork(item);artwork.resize(280,104);artwork.show()
        for _ in range(20):self.app.processEvents();QTest.qWait(10)
        self.assertIsNotNone(artwork.preview);self.assertFalse(artwork.preview.isNull());artwork.close();artwork.deleteLater()
        path=source/'损坏.pdf';info=path.stat();item.path=path;item.size=info.st_size;item.mtime_ns=info.st_mtime_ns
        fallback=DocumentArtwork(item);fallback.show()
        for _ in range(10):self.app.processEvents();QTest.qWait(10)
        self.assertIsNone(fallback.preview);self.assertFalse(fallback.grab().isNull());fallback.close();fallback.deleteLater()

if __name__=='__main__':unittest.main()
