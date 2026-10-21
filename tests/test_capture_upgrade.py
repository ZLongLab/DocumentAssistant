import json
import math
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from test_upgrade import Fixture
from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from document_assistant.capture_hotkey import parse_hotkey
from document_assistant.document_metadata import preview_category_rule
from document_assistant.rules import DEFAULT_RULES
from document_assistant.watch_inbox import DiscoveryCursor, discover_folders
from document_assistant.paths import comparison_path
from document_assistant.screen_capture import (AnnotationCanvas, CaptureController,
    CaptureEditor, copy_image, crop_selection, render_annotations, save_png)
from document_assistant.gui import MainWindow
from tests.gui_wait import settle_search


class ManagementFixTests(Fixture):
    def test_rule_preview_reports_existing_specific_rule_and_conflict(self):
        proposed={'source':'folder','pattern':str(self.root),'category':'课程资料'}
        specific={'source':'filename','pattern':'实验报告','category':'实验报告'}
        category,reason=preview_category_rule(self.item,proposed,[specific],DEFAULT_RULES)
        self.assertEqual(category,'实验报告')
        conflicting={'source':'filename','pattern':'验报告','category':'研究文献'}
        proposed={'source':'filename','pattern':'实验报','category':'课程资料'}
        self.assertEqual(preview_category_rule(self.item,proposed,[conflicting],DEFAULT_RULES)[0],'待整理')
        self.item.manual_fields='category'
        self.assertEqual(preview_category_rule(self.item,proposed,[conflicting],DEFAULT_RULES)[0],self.item.category)

    def test_preview_replaces_identical_rule_instead_of_creating_conflict(self):
        old={'source':'filename','pattern':'实验','category':'课程资料'}
        new={**old,'category':'项目资料'}
        self.assertEqual(preview_category_rule(self.item,new,[old],DEFAULT_RULES)[0],'项目资料')

    def test_large_watch_continues_and_rotates_folders(self):
        a=self.root/'watch-a';b=self.root/'watch-b';a.mkdir();b.mkdir()
        first=a/'first.txt';later=a/'later.txt';second=b/'second.txt'
        for p in (first,later,second):p.write_text('Stable synthetic text',encoding='utf-8')
        self.catalog.set_watch_folder(a);self.catalog.set_watch_folder(b)
        cursor=DiscoveryCursor();previous={};found=set();cycles=0
        def walk(root,**kwargs):
            if comparison_path(root)==a:
                yield str(a),[],['first.txt']+[f'{i}.bin' for i in range(24000)]+['later.txt']
            else:yield str(b),[],['second.txt']
        with patch('document_assistant.watch_inbox.os.walk',side_effect=walk):
            for _ in range(22):
                previous,ready,warnings=discover_folders(self.catalog,previous,cursor=cursor,budget=3000)
                found.update(Path(p).name for _,p,_ in ready)
                if cursor.complete:cycles+=1
            self.assertIn((str(b.resolve()),str(second.resolve())),previous)
            self.assertIn('later.txt',found)
            self.assertIn('second.txt',found)
            self.assertGreaterEqual(cycles,1)


class CaptureTests(Fixture):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        super().setUp()
        self.image=QImage(300,200,QImage.Format.Format_ARGB32);self.image.fill(QColor('#225c7d'))

    def test_native_pixel_crop_handles_reverse_and_scaled_selection(self):
        for ratio in (1,1.25,1.5,2):
            image=QImage(int(400*ratio),int(300*ratio),QImage.Format.Format_ARGB32);image.fill(QColor('blue'))
            cropped=crop_selection(image,QRectF(QPointF(220,160),QPointF(20,10)),QSize(400,300))
            self.assertEqual(cropped.size(),QSize(math.ceil(220*ratio)-math.floor(20*ratio),math.ceil(160*ratio)-math.floor(10*ratio)))
            self.assertEqual(cropped.devicePixelRatio(),1)
        with self.assertRaises(ValueError):crop_selection(self.image,QRectF(0,0,1,1),QSize(300,200))

    def test_png_collision_does_not_overwrite_and_clipboard_is_image(self):
        when=datetime(2026,10,13,21,0,0)
        first=save_png(self.image,self.root/'captures',when)
        before=first.read_bytes()
        second=save_png(self.image,self.root/'captures',when)
        self.assertNotEqual(first,second);self.assertEqual(first.read_bytes(),before)
        self.assertEqual(QImage(str(second)).size(),self.image.size())
        copy_image(self.image);self.assertEqual(self.app.clipboard().image().size(),self.image.size())

    def test_annotations_undo_and_source_image_preserved(self):
        source=self.image.copy()
        marks=[('rectangle',QPointF(20,20),QPointF(80,80),'','#e34f45'),
               ('arrow',QPointF(100,30),QPointF(160,100),'','#377fde'),
               ('text',QPointF(20,120),QPointF(20,120),'TEST','#24825c')]
        rendered=render_annotations(self.image,marks)
        self.assertNotEqual(rendered,source);self.assertEqual(self.image,source)
        canvas=AnnotationCanvas(self.image);canvas.marks=list(marks);canvas.undo()
        self.assertEqual(len(canvas.marks),2)
        canvas.resize(600,400);canvas.show();self.app.processEvents()
        canvas.tool='rectangle'
        QTest.mousePress(canvas,Qt.MouseButton.LeftButton,pos=QPoint(170,120))
        QTest.mouseMove(canvas,QPoint(210,160));QTest.mouseRelease(canvas,Qt.MouseButton.LeftButton,pos=QPoint(210,160))
        self.assertEqual(len(canvas.marks),3);canvas.close()

    def test_invalid_hotkeys_are_rejected(self):
        self.assertEqual(parse_hotkey('alt+ctrl+s')[0],'Ctrl+Alt+S')
        self.assertEqual(parse_hotkey('alt+s')[0],'Alt+S')
        self.assertEqual(parse_hotkey('Alt+S')[1:] ,(0x4001,ord('S')))
        for invalid in ('S','Shift+S','Ctrl+Ctrl+S','Ctrl+Alt+Enter','Ctrl+F25','Ctrl+Alt+'):
            with self.assertRaises(ValueError):parse_hotkey(invalid)

    def test_copy_only_creates_no_file_and_failed_save_keeps_editor(self):
        window=MainWindow(self.root/'settings');settle_search(window)
        controller=CaptureController(window,activate=False)
        controller.settings['directory']=str(self.root/'captures')
        editor=CaptureEditor(self.image,controller)
        editor.copy()
        self.assertFalse((self.root/'captures').exists())
        bad=self.root/'not-directory';bad.write_text('do not replace',encoding='utf-8')
        controller.settings['directory']=str(bad)
        editor=CaptureEditor(self.image,controller)
        editor.save()
        self.assertIn('保存失败',editor.message.text());self.assertEqual(bad.read_text(encoding='utf-8'),'do not replace')
        editor.close();controller.shutdown();window.close();self.app.processEvents()

    def test_settings_write_failure_rolls_back_prepared_hotkey(self):
        window=MainWindow(self.root/'settings');settle_search(window)
        controller=CaptureController(window,activate=False)
        with patch.object(controller.hotkey,'prepare',return_value=(42,'Ctrl+Alt+S')) as prepare, \
             patch.object(controller.hotkey,'rollback') as rollback, \
             patch.object(Path,'write_text',side_effect=OSError('full')):
            with self.assertRaises(OSError):controller.configure('Ctrl+Alt+S',str(self.root/'captures'))
            rollback.assert_called_once_with((42,'Ctrl+Alt+S'))
        self.assertIsNone(controller.hotkey.ident)
        controller.shutdown();window.close();self.app.processEvents()
