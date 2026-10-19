from tests.gui_wait import settle_search
import os
import sqlite3
import tempfile
import time
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from document_assistant.service import PROJECT_ROOT, archive_one, archive_batch, scan_files, sha256
from document_assistant.rules import DEFAULT_RULES
from document_assistant.storage import Catalog
from document_assistant.storage_base import Catalog as LegacyCatalog
from document_assistant.archive import recover_pending, undo_batch, index_archives
from document_assistant.paths import sqlite_filename


class Fixture(unittest.TestCase):
    def setUp(self):
        root=Path(os.environ.get('DOCUMENTASSISTANT_TEST_TMP', str(PROJECT_ROOT.parent/'DocumentAssistant-local/tmp')))
        root.mkdir(parents=True,exist_ok=True)
        self.temp_parent=root.resolve()
        self.temp=tempfile.TemporaryDirectory(prefix='upgrade-',dir=root)
        self.root=Path(self.temp.name)
        self.path=self.root/'实验报告.txt'
        self.path.write_text('实验目的：配置VLAN。\n实验步骤：隔离网络。\n实验结果：测试成功。',encoding='utf-8')
        self.library=self.root/'library'
        self.catalog=Catalog(self.library)
        self.item=scan_files([self.path],DEFAULT_RULES,self.library)[0][0]

    def tearDown(self):
        if self.root.resolve()==self.temp_parent or not self.root.resolve().is_relative_to(self.temp_parent) or not self.root.name.startswith('upgrade-'):
            raise RuntimeError('Refusing to clean an unexpected fixture directory')
        self.temp.name=sqlite_filename(self.root)
        self.temp.cleanup()


class StorageUpgradeTests(Fixture):
    def test_relocation_rebinds_paths_and_keeps_records(self):
        _,target=archive_one(self.item,self.catalog)
        relative=target.relative_to(self.library)
        moved=self.root/'moved'
        self.library.rename(moved)
        new=Catalog(moved)
        rows=new.search('VLAN')
        self.assertEqual(len(rows),1)
        self.assertEqual(Path(rows[0]['archive_path']),moved/relative)
        self.assertTrue(Path(rows[0]['archive_path']).is_file())
        self.assertEqual(new.missing_archives(),([],0))
        self.assertIsNotNone(new.last_backup)

    def test_moved_legacy_library_is_backed_up_and_reindexed(self):
        legacy=LegacyCatalog(self.root/'legacy')
        item=replace(self.item,doc_id=None)
        item.doc_id=legacy.save_scan(item)
        target=legacy.library/item.category/item.path.name
        target.parent.mkdir()
        target.write_bytes(item.path.read_bytes())
        legacy.record_archive(item,target,sha256(target))
        moved=self.root/'moved-legacy'
        for attempt in range(10):
            try:
                legacy.library.rename(moved)
                break
            except PermissionError:
                if attempt==9:
                    raise
                time.sleep(.1)  # OneDrive/AV may temporarily hold a newly written fixture.
        current=Catalog(moved)
        self.assertEqual(current.search('VLAN'),[])
        self.assertTrue(current.last_backup.is_file())
        with sqlite3.connect(current.last_backup) as backup:
            self.assertNotIn('relative_path',{r[1] for r in backup.execute('PRAGMA table_info(archives)')})
        backup.close()
        self.assertEqual(current.missing_archives(),([],0))
        index_archives(current)
        self.assertEqual(len(current.search('VLAN')),1)

    def test_fulltext_snapshot_survives_later_source_scan(self):
        archive_one(self.item,self.catalog)
        self.path.write_text('实验报告\n实验目的：OSPF。\n实验步骤：重新配置。',encoding='utf-8')
        scan_files([self.path],DEFAULT_RULES,self.library)
        self.assertEqual(len(self.catalog.search('VLAN')),1)
        self.assertEqual(len(self.catalog.search('OSPF')),0)
        self.assertEqual(len(self.catalog.search('VLAN',scope='filename')),0)
        self.assertEqual(len(self.catalog.search('隔离')),1)
        self.assertEqual(len(self.catalog.search('%')),0)

    def test_labels_persist_and_update_fulltext_index(self):
        self.item.course='计算机网络'
        self.item.project='课程项目'
        self.item.tags='VLAN,交换机'
        self.catalog.save_scan(self.item)
        archive_one(self.item,self.catalog)
        for query in ('计算机网络','课程项目','交换机'):
            self.assertEqual(len(self.catalog.search(query)),1)
        row=self.catalog.search()[0]
        self.catalog.change_labels([row['id']],{'tags':'OSPF'},archives=True)
        self.assertEqual(len(self.catalog.search('交换机')),0)
        self.assertEqual(len(self.catalog.search('OSPF')),1)
        self.assertEqual(scan_files([self.path],DEFAULT_RULES,self.library)[0][0].course,'计算机网络')

    def test_pagination_has_no_overlap_and_correct_total(self):
        _,target=archive_one(self.item,self.catalog)
        with self.catalog.connection() as db:
            for index in range(5):
                db.execute('''INSERT INTO archives(document_id,source_path,archive_path,filename,category,sha256,relative_path)
                    VALUES(?,?,?,?,?,?,?)''',(self.item.doc_id,str(self.path),str(target)+str(index),f'分页{index}.txt',self.item.category,'unused',str(target.relative_to(self.library))+str(index)))
        self.assertEqual(self.catalog.search_count(),6)
        first=self.catalog.search(limit=2)
        second=self.catalog.search(limit=2,offset=2)
        self.assertEqual(len(first),2)
        self.assertFalse({r['id'] for r in first}&{r['id'] for r in second})

    def test_duplicate_policy_is_user_choice(self):
        archive_one(self.item,self.catalog)
        other=self.root/'另一份实验报告.txt'
        other.write_bytes(self.path.read_bytes())
        item=scan_files([other],DEFAULT_RULES,self.library)[0][0]
        message,_=archive_one(item,self.catalog,duplicate_policy='skip')
        self.assertIn('内容相同',message)
        self.assertEqual(len(self.catalog.search()),1)
        archive_one(item,self.catalog,duplicate_policy='keep')
        self.assertEqual(len(self.catalog.search()),2)
        self.assertEqual(sha256(other),sha256(self.path))

    def test_interrupted_copy_recovers_without_second_file(self):
        with patch.object(self.catalog,'record_archive',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                archive_one(self.item,self.catalog)
        self.assertEqual(len(self.catalog.pending_tasks()),1)
        self.assertEqual(len(self.catalog.search()),0)
        self.assertIn('恢复归档',recover_pending(self.catalog)[0])
        self.assertEqual(len(self.catalog.search()),1)
        self.assertEqual(len(self.catalog.pending_tasks()),0)
        _,target=archive_one(self.item,self.catalog)
        self.assertNotIn('(1)',target.name)
        self.assertEqual(len(list((self.library/self.item.category).glob('*.txt'))),1)

    def test_cancel_copy_preserves_source_and_cleans_reservation(self):
        def cancelled():
            return any((self.library/'.documentassistant/pending').glob('*.part'))
        original=sha256(self.path)
        with self.assertRaises(InterruptedError):
            archive_one(self.item,self.catalog,cancelled)
        self.assertEqual(sha256(self.path),original)
        self.assertEqual(self.catalog.search(),[])
        self.assertEqual(self.catalog.pending_tasks(),[])
        self.assertEqual(list((self.library/self.item.category).glob('*.txt')),[])

    def test_recovery_preserves_modified_target(self):
        with patch.object(self.catalog,'record_archive',side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                archive_one(self.item,self.catalog)
        task=self.catalog.pending_tasks()[0]
        target=self.catalog.safe_path(task['target_relative'])
        target.write_text('用户后来修改的内容',encoding='utf-8')
        recover_pending(self.catalog)
        self.assertEqual(target.read_text(encoding='utf-8'),'用户后来修改的内容')
        self.assertEqual(len(self.catalog.pending_tasks()),1)
        self.assertEqual(len(self.catalog.search()),0)

    def test_undo_is_recoverable_and_preserves_source(self):
        archive_batch([self.item],self.library)
        rows=self.catalog.latest_batch()
        target=Path(rows[0]['archive_path'])
        digest=sha256(self.path)
        self.assertIn('已撤销',undo_batch(self.catalog,rows)[0])
        self.assertEqual(self.catalog.search(),[])
        self.assertFalse(target.exists())
        recovered=list((self.library/'.documentassistant/undo').rglob('*.txt'))
        self.assertEqual(len(recovered),1)
        self.assertEqual(sha256(recovered[0]),digest)
        self.assertEqual(sha256(self.path),digest)
        self.assertTrue(list((self.library/'.documentassistant/backups').glob('*.sqlite3')))

    def test_undo_preserves_modified_archive(self):
        archive_batch([self.item],self.library)
        rows=self.catalog.latest_batch()
        target=Path(rows[0]['archive_path'])
        target.write_text('保留新的修改',encoding='utf-8')
        undo_batch(self.catalog,rows)
        self.assertEqual(target.read_text(encoding='utf-8'),'保留新的修改')
        self.assertEqual(len(self.catalog.search()),1)


class GuiUpgradeTests(Fixture):
    def setUp(self):
        super().setUp()
        from PySide6.QtWidgets import QApplication
        from document_assistant.gui import MainWindow
        self.app=QApplication.instance() or QApplication([])
        self.window=MainWindow(self.root/'settings')
        self.window.set_library(self.library)
        self.window.items=[self.item]
        self.window.populate_scan()

    def tearDown(self):
        settle_search(self.window)
        self.window.close()
        self.app.processEvents()
        super().tearDown()

    def test_switch_library_resets_archive_state(self):
        _,target=archive_one(self.item,self.catalog)
        self.window.archive_finished([(self.item,True,'归档成功：'+str(target))])
        self.window.set_library(self.root/'library_b')
        self.assertEqual(self.window.archive_statuses,{})
        self.assertNotEqual(self.window.scan_table.item(0,4).text(),'已归档')
        self.assertEqual(self.window.catalog.search(),[])

    def test_changed_file_reimport_refreshes_existing_item(self):
        old=self.item.size
        self.path.write_text('实验报告\n实验目的：新的正文。\n实验步骤：再次测试。\n更多内容。',encoding='utf-8')
        captured=[]
        with patch.object(self.window,'launch_worker',side_effect=lambda operation,callback:captured.append((operation,callback))):
            self.window.import_files([self.path])
        self.assertEqual(len(captured),1)
        operation,callback=captured[0]
        callback(operation(lambda *_:None,lambda:False))
        self.assertEqual(len(self.window.items),1)
        self.assertNotEqual(self.window.items[0].size,old)
        self.assertIn('新的正文',self.window.items[0].body)

    def test_bulk_selection_refreshes_only_once(self):
        self.window.items=[replace(self.item,path=self.root/f'实验报告{i}.txt',doc_id=None) for i in range(30)]
        self.window.populate_scan()
        with patch.object(self.window.cards_view,'sync',wraps=self.window.cards_view.sync) as sync:
            self.window.check_all(False)
            self.assertEqual(sync.call_count,1)
        self.assertEqual(self.window.selected_scan_rows(),[])
        self.assertEqual(self.window.all_check.checkState(),self.window.scan_table.item(0,0).checkState())

    def test_bulk_labels_and_list_view(self):
        self.window.apply_bulk_updates({'course':'计算机网络','project':'课程项目','tags':'VLAN','category':'课程资料'})
        self.assertEqual(self.window.items[0].course,'计算机网络')
        self.assertEqual(self.window.items[0].category,'课程资料')
        self.assertEqual(self.window.cards_view.cards[0].badge.text(),'课程资料')
        self.window.toggle_review_view()
        self.assertEqual(self.window.review_stack.currentIndex(),2)
        self.assertEqual(self.window.cards_view.cards,[])
        self.assertFalse(self.window.details_panel.isVisible())
        self.window.toggle_review_view()
        self.assertEqual(len(self.window.cards_view.cards),1)

    def test_gui_fulltext_and_filename_scope(self):
        archive_one(self.item,self.catalog)
        self.window.search_edit.setText('VLAN')
        self.window.refresh_search()
        settle_search(self.window)
        self.assertEqual(self.window.search_table.rowCount(),1)
        self.window.search_scope.setCurrentIndex(1)
        settle_search(self.window)
        self.assertEqual(self.window.search_table.rowCount(),0)
