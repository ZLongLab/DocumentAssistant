import os, unittest
from pathlib import Path
from unittest.mock import patch
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox
from test_upgrade import Fixture
from tests.gui_wait import settle_search
from document_assistant.paths import filesystem_path
from document_assistant.watch_inbox import DiscoveryCursor, discover_folders, validate_watch_folder
from document_assistant.archive import archive_one, undo_batch
from document_assistant.service import scan_files
from document_assistant.rules import DEFAULT_RULES


class WatchRegressions(Fixture):
    @unittest.skipUnless(os.name=='nt','Windows directory junction')
    def test_nested_links_never_enter_watch_queue(self):
        import _winapi
        folder=self.root/'watch';folder.mkdir()
        document=folder/'inside.txt';document.write_text('示例课程资料',encoding='utf-8')
        outside=self.root/'outside';outside.mkdir();(outside/'not-selected.txt').write_text('示例',encoding='utf-8')
        _winapi.CreateJunction(str(outside),str(folder/'outside-link'))
        _winapi.CreateJunction(str(folder),str(folder/'loop'))
        self.catalog.set_watch_folder(folder)
        cursor=DiscoveryCursor()
        previous,ready,warnings=discover_folders(self.catalog,cursor=cursor,budget=40)
        self.assertTrue(cursor.complete,warnings)
        self.assertEqual(set(previous),{(str(folder),str(document))})
        _,ready,_=discover_folders(self.catalog,previous,cursor=cursor,budget=40)
        self.assertEqual([Path(path) for _,path,_ in ready],[document])

    @unittest.skipUnless(os.name=='nt','Windows directory junction')
    def test_junction_cannot_be_registered_as_watch_root(self):
        import _winapi
        folder=self.root/'watch';folder.mkdir();link=self.root/'junction'
        _winapi.CreateJunction(str(folder),str(link))
        with self.assertRaisesRegex(ValueError,'普通文件夹'):
            validate_watch_folder(link,self.library)

    def test_deep_watch_document_becomes_ready_with_readable_path(self):
        folder=self.root/'watch';deep=folder/('a'*70)/('b'*70)/('c'*70)
        filesystem_path(deep).mkdir(parents=True)
        path=deep/'示例课程资料.txt';filesystem_path(path).write_text('课程示例',encoding='utf-8')
        self.catalog.set_watch_folder(folder)
        previous,ready,warnings=discover_folders(self.catalog)
        self.assertEqual(ready,[])
        self.assertEqual(set(previous),{(str(folder),str(path))},warnings)
        _,ready,warnings=discover_folders(self.catalog,previous)
        self.assertEqual([Path(name) for _,name,_ in ready],[path],warnings)
        self.assertEqual(validate_watch_folder(deep,self.library),deep)


class FollowupGuiRegressions(Fixture):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def window(self):
        from document_assistant.gui import MainWindow
        window=MainWindow(self.root/'home')
        self.addCleanup(lambda:(settle_search(window),window.close()))
        return window

    def test_f5_refreshes_external_deletion_without_changing_filter(self):
        _,target=archive_one(self.item,self.catalog)
        window=self.window();window.set_library(self.library);window.tabs.setCurrentIndex(1)
        window.search_edit.setText('VLAN');settle_search(window)
        self.assertEqual(window.archive_rows[0]['_file_state'],'available')
        target.unlink()
        window.show();window.activateWindow();self.app.processEvents()
        QTest.keyClick(window.search_edit,Qt.Key.Key_F5);settle_search(window)
        self.assertEqual(window.search_edit.text(),'VLAN')
        self.assertEqual(window.archive_rows[0]['_file_state'],'missing')
        self.assertEqual(window.catalog.search_count(),1)

    def test_f5_does_not_switch_import_page(self):
        window=self.window();window.show();window.activateWindow();self.app.processEvents()
        window.tabs.setCurrentIndex(0)
        QTest.keyClick(window,Qt.Key.Key_F5);self.app.processEvents()
        self.assertEqual(window.tabs.currentIndex(),0)
        self.assertIsNone(window.worker)

    def test_recycle_long_existing_file_is_available(self):
        from document_assistant.library_ui import RecycleDialog
        path=self.root/('实验报告'+'x'*180+'.txt')
        filesystem_path(path).write_text('VLAN 实验目的；实验结果：成功',encoding='utf-8')
        item=scan_files([path],DEFAULT_RULES,self.library)[0][0]
        archive_one(item,self.catalog);undo_batch(self.catalog,self.catalog.latest_batch())
        window=self.window();window.set_library(self.library)
        dialog=RecycleDialog(window);self.addCleanup(dialog.close)
        self.assertEqual(dialog.table.item(0,3).text(),'副本存在')

    def test_recycle_unknown_state_does_not_claim_missing_or_preview(self):
        from document_assistant import library_ui
        archive_one(self.item,self.catalog);undo_batch(self.catalog,self.catalog.latest_batch())
        window=self.window();window.set_library(self.library)
        with patch.object(library_ui,'archive_file_state',return_value='unknown'):
            dialog=library_ui.RecycleDialog(window);self.addCleanup(dialog.close)
            self.assertEqual(dialog.table.item(0,3).text(),'状态无法确认')
            with patch.object(QMessageBox,'information') as message, patch.object(library_ui,'DocumentPreviewDialog') as preview:
                dialog.preview()
            message.assert_called_once();preview.assert_not_called()

    def test_pdf_long_path_preview_renders_without_holding_original(self):
        import io, time
        from pypdf import PdfWriter
        from PySide6.QtPdf import QPdfDocument
        from document_assistant.pdf_preview import PdfPreview
        path=self.root/('示例文献'+'x'*180+'.pdf')
        writer=PdfWriter();writer.add_blank_page(width=200,height=300)
        buffer=io.BytesIO();writer.write(buffer)
        filesystem_path(path).write_bytes(buffer.getvalue())
        preview=PdfPreview();self.addCleanup(preview.close)
        preview.load_path(path)
        deadline=time.monotonic()+3
        while preview.document.status()==QPdfDocument.Status.Loading and time.monotonic()<deadline:
            self.app.processEvents();QTest.qWait(10)
        self.assertEqual(preview.document.status(),QPdfDocument.Status.Ready,preview.message.text())
        filesystem_path(path).unlink()
        self.assertEqual(preview.document.pageCount(),1)
