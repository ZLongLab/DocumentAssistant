import os,unittest
from pathlib import Path
from unittest.mock import patch
from dataclasses import replace
from test_upgrade import Fixture
from document_assistant.archive import archive_one,undo_batch
from document_assistant.service import scan_folder,scan_files,sha256
from document_assistant.rules import DEFAULT_RULES
from document_assistant.paths import filesystem_path
from document_assistant.library_backup import export_library,restore_library
from document_assistant.recovery import restore_recycled
from document_assistant.storage import Catalog
from document_assistant.storage_base import archive_file_state
from tests.gui_wait import settle_search


class ReviewRegressions(Fixture):
    def test_archive_rejects_changed_bytes_even_when_size_and_time_preserved(self):
        before=self.path.stat();self.path.write_bytes(self.path.read_bytes().replace(b'VLAN',b'OSPF'))
        os.utime(self.path,ns=(before.st_atime_ns,before.st_mtime_ns))
        self.assertEqual(self.path.stat().st_size,self.item.size)
        with self.assertRaisesRegex(ValueError,'变化'):
            archive_one(self.item,self.catalog)
        self.assertEqual(self.catalog.search_count(),0)
        self.assertEqual(self.catalog.pending_tasks(),[])

    @unittest.skipUnless(os.name=='nt','Windows junction test')
    def test_scan_skips_directory_junctions_and_cycles(self):
        import _winapi
        source=self.root/'scan';source.mkdir();inside=source/'inside.txt';inside.write_text('示例课程资料',encoding='utf-8')
        outside=self.root/'outside';outside.mkdir();(outside/'not-selected.txt').write_text('不应读取',encoding='utf-8')
        _winapi.CreateJunction(str(outside),str(source/'linked-folder'))
        _winapi.CreateJunction(str(source),str(source/'loop'))
        visits=[]
        # Bound the old implementation so its cycle is reproduced without
        # hanging the suite or reading any data outside this temporary fixture.
        def progress(*args):visits.append(args)
        items,warnings=scan_folder(source,DEFAULT_RULES,progress=progress,cancelled=lambda:len(visits)>8)
        self.assertEqual([item.path for item in items],[inside.resolve()])
        self.assertLessEqual(len(visits),8)

    def test_long_filename_roundtrip_archive_backup_undo_and_restore(self):
        source=self.root/'source';source.mkdir()
        path=source/('课程实验报告'+'x'*180+'.txt')
        filesystem_path(path).write_text('VLAN 实验目的：验证隔离。实验结果：成功。',encoding='utf-8')
        items,warnings=scan_files([path],DEFAULT_RULES,self.library)
        self.assertEqual(len(items),1,warnings)
        item=items[0];self.assertIn('VLAN',item.body,item.status)
        _,target=archive_one(item,self.catalog)
        self.assertEqual(archive_file_state(str(target)),'available')
        self.assertEqual(sha256(target),sha256(path))
        backup=self.root/'roundtrip.zip';export_library(self.catalog,backup)
        restored_path=self.root/'restored';restore_library(backup,restored_path)
        restored=Catalog(restored_path)
        self.assertEqual(restored.search_count(),1)
        self.assertEqual(sha256(Path(restored.search()[0]['archive_path'])),sha256(path))
        messages=undo_batch(self.catalog,self.catalog.latest_batch())
        self.assertTrue(any('已撤销' in m for m in messages),messages)
        messages=restore_recycled(self.catalog,self.catalog.recycle_entries())
        self.assertTrue(any('已恢复' in m for m in messages),messages)
        self.assertEqual(sha256(Path(self.catalog.search()[0]['archive_path'])),sha256(path))

    def test_scan_short_root_with_deep_nested_document(self):
        source=self.root/'deep-source';deep=source/('a'*70)/('b'*70)/('c'*70)
        filesystem_path(deep).mkdir(parents=True)
        path=deep/'实验报告.txt';filesystem_path(path).write_text('实验目的 VLAN；实验结果：成功',encoding='utf-8')
        items,warnings=scan_folder(source,DEFAULT_RULES)
        self.assertEqual([item.path for item in items],[path],warnings)
        self.assertIn('VLAN',items[0].body,items[0].status)

    def test_backup_short_library_with_deep_nested_file(self):
        relative=Path('a'*70)/('b'*70)/('c'*70)/'示例资料.txt'
        path=self.library/relative
        filesystem_path(path.parent).mkdir(parents=True)
        filesystem_path(path).write_text('示例资料，备份应完整保留',encoding='utf-8')
        backup=self.root/'deep-backup.zip';export_library(self.catalog,backup)
        destination=self.root/'deep-restored';restore_library(backup,destination)
        self.assertEqual(sha256(destination/relative),sha256(path))


class ReviewGuiRegressions(Fixture):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])

    def window(self):
        from document_assistant.gui import MainWindow
        window=MainWindow(self.root/'home')
        self.addCleanup(lambda:(settle_search(window),window.close()))
        return window

    def test_ctrl_f_opens_library_search_and_selects_query(self):
        from PySide6.QtCore import Qt
        from PySide6.QtTest import QTest
        window=self.window();window.show();window.activateWindow();self.app.processEvents()
        window.search_edit.setText('待替换关键词');window.tabs.setCurrentIndex(0)
        QTest.keyClick(window,Qt.Key.Key_F,Qt.KeyboardModifier.ControlModifier);self.app.processEvents()
        self.assertEqual(window.tabs.currentIndex(),1)
        self.assertTrue(window.search_edit.hasFocus())
        self.assertEqual(window.search_edit.selectedText(),'待替换关键词')

    def test_library_containing_a_pending_file_is_rejected_with_long_path(self):
        from document_assistant.service import ScanItem
        library=self.root/('a'*70)/('b'*70)/('c'*70)
        filesystem_path(library).mkdir(parents=True)
        path=library/'pending.txt';filesystem_path(path).write_text('示例课程资料',encoding='utf-8')
        info=filesystem_path(path).stat();window=self.window()
        window.items=[ScanItem(path,info.st_size,info.st_mtime_ns,'示例课程资料','已提取','课程资料','课程资料','示例')]
        with self.assertRaisesRegex(ValueError,'文档库内'):
            window.set_library(library)
        window.items=[]

    def test_open_long_file_dispatches_normal_windows_file_url(self):
        from document_assistant import gui
        path=self.root/('课程实验报告'+'x'*180+'.txt')
        filesystem_path(path).write_text('示例',encoding='utf-8');window=self.window()
        with patch.object(gui.QDesktopServices,'openUrl',return_value=True) as opened:
            self.assertTrue(window.open_path(path))
        self.assertEqual(Path(opened.call_args.args[0].toLocalFile()),path)


if __name__=='__main__':unittest.main()
