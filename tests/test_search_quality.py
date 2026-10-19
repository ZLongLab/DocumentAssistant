import time
from dataclasses import replace
from unittest.mock import patch
from pathlib import Path

from test_upgrade import Fixture
from tests.gui_wait import settle_search
from document_assistant.archive import index_archives
from document_assistant.extractor import extract
from document_assistant.library_backup import export_library, restore_library
from document_assistant.rules import classify, DEFAULT_RULES
from document_assistant.search_text import match_spans, body_snippet
from document_assistant.search_ui import quality_report
from document_assistant.service import archive_one, scan_files
from document_assistant.storage import Catalog


class SearchQualityTests(Fixture):
    def test_misnamed_docx_and_empty_file_are_explained(self):
        from docx import Document
        p = self.root/'项目计划.doc'
        doc = Document()
        doc.add_paragraph('项目计划：归档与搜索。')
        doc.save(p)
        result = extract(p)
        self.assertIn('项目计划',result['text'])
        self.assertIn('DOC 实为 DOCX',result['status'])
        empty = self.root/'空白.docx'
        empty.touch()
        self.assertEqual(extract(empty)['status'],'无法提取：空文件（0 字节）')

    def test_ieee_small_caps_and_inline_abstract_are_paper_evidence(self):
        body = 'IEEE TRANSACTIONS\nA Novel Framework\nAbstract— A segmentation approach.\nI. I NTRODUCTION\nIII. M ETHOD\nVI. C ONCLUSION\nREFERENCES'
        category, reason = classify('opaque.pdf',body,DEFAULT_RULES)
        self.assertEqual(category,'研究文献')
        self.assertIn('正文结构',reason)
        self.assertEqual(classify('memo.txt','My abstract idea, introduction to methods and conclusion.',DEFAULT_RULES)[0],'待整理')

    def test_quality_uses_archive_snapshot_and_handles_missing_and_unknown(self):
        _, target = archive_one(self.item,self.catalog)
        ident = self.catalog.search()[0]['id']
        # Later source extraction failures do not change historical archive status.
        self.catalog.save_scan(replace(self.item,status='无法提取：新来源失败',body=''))
        self.assertEqual(self.catalog.search(quality='complete')[0]['id'],ident)
        self.assertEqual(quality_report(self.catalog)['counts']['complete'],1)
        self.catalog.update_extraction(ident,'部分正文','已提取（前 10 万字，已截断）')
        self.assertEqual(len(self.catalog.search(quality='partial')),1)
        target.unlink()
        report = quality_report(self.catalog)
        self.assertEqual(report['counts']['missing'],1)
        self.assertEqual(report['counts']['partial'],1)
        with self.catalog.connection() as db:
            db.execute("UPDATE archives SET extraction_status='' WHERE id=?",(ident,))
        self.assertEqual(self.catalog.search_count(quality='unknown'),1)
        self.assertEqual(quality_report(self.catalog)['counts']['unknown'],1)

    def test_old_schema_backup_restores_with_unknown_status_without_inference(self):
        archive_one(self.item,self.catalog)
        with self.catalog.connection() as db:
            db.execute('ALTER TABLE archives DROP COLUMN extraction_status')
            db.execute("UPDATE library_meta SET value='4' WHERE key='schema_version'")
        bundle = self.root/'old-schema.zip'
        export_library(self.catalog,bundle)
        restored = restore_library(bundle,self.root/'restored')
        catalog = Catalog(self.root/'restored')
        self.assertEqual(catalog.search_count(quality='unknown'),1)
        self.assertIn('VLAN',catalog.search()[0]['body_snapshot'])
        self.assertEqual(quality_report(catalog)['counts']['complete'],0)
        self.assertIsNotNone(Catalog(self.library).last_backup)

    def test_reindex_records_failure_if_no_body_and_keeps_existing_body(self):
        archive_one(self.item,self.catalog)
        ident = self.catalog.search()[0]['id']
        with patch('document_assistant.service.extract_isolated',return_value={'text':'','status':'无法提取：暂时失败'}):
            index_archives(self.catalog)
        self.assertIn('VLAN',self.catalog.search()[0]['body_snapshot'])
        self.catalog.update_extraction(ident,'','')
        with patch('document_assistant.service.extract_isolated',return_value={'text':'','status':'无法提取：空白'}):
            index_archives(self.catalog)
        self.assertEqual(self.catalog.search_count(quality='none'),1)
        index_archives(self.catalog)
        self.assertEqual(self.catalog.search_count(quality='complete'),1)

    def test_paged_search_limits_bodies_and_sorts_and_filters(self):
        archive_one(self.item,self.catalog)
        first = self.catalog.search()[0]
        with self.catalog.connection() as db:
            fields = [k for k in first.keys() if k!='id']
            values = dict(first)
            values['filename'] = 'AAA.txt'
            values['archive_path'] = str(self.library/'AAA.txt')
            values['relative_path'] = 'AAA.txt'
            values['created_at'] = '2099-01-01'
            values['body_snapshot'] = '前文。'+('无关内容'*100)+' Docker and VLAN test.'
            db.execute('INSERT INTO archives('+','.join(fields)+') VALUES ('+','.join('?' for _ in fields)+')',[values[k] for k in fields])
        total, page, rows = self.catalog.search_page_data('VLAN',0,1,sort='newest')
        self.assertEqual(total,2)
        self.assertEqual(rows[0]['filename'],'AAA.txt')
        self.assertNotIn('body_snapshot',rows[0])
        self.assertLessEqual(len(rows[0]['body_snippet']),180)
        self.assertIn('VLAN',rows[0]['body_snippet'])
        second = self.catalog.search_page_data('VLAN',1,1)[2][0]
        self.assertNotEqual(rows[0]['id'],second['id'])
        self.assertEqual(self.catalog.search(sort='oldest')[0]['id'],first['id'])
        self.assertEqual(self.catalog.search(sort='name')[0]['filename'],'AAA.txt')
        for filters in ({'sort':'id; DROP TABLE archives'},{'quality':'invalid'}):
            with self.assertRaises(ValueError):
                self.catalog.search(**filters)
        self.assertEqual(match_spans('<VLAN> Docker', ['vlan','Docker']),[(1,5),(7,13)])
        self.assertIn('VLAN',body_snippet('prefix VLAN Docker suffix','VLAN Docker'))


class AsyncSearchTests(Fixture):
    def setUp(self):
        super().setUp()
        from PySide6.QtWidgets import QApplication
        from document_assistant.gui import MainWindow
        self.app = QApplication.instance() or QApplication([])
        self.window = MainWindow(self.root/'home')
        self.window.set_library(self.library)
        settle_search(self.window)

    def tearDown(self):
        settle_search(self.window)
        self.window.close()
        self.app.processEvents()
        super().tearDown()

    def test_slow_old_result_never_replaces_new_query_and_ui_stays_responsive(self):
        from PySide6.QtCore import QTimer
        from PySide6.QtTest import QTest
        archive_one(self.item,self.catalog)
        original = self.window.catalog.search_page_data
        started = []
        def slow(query,*args,**kwargs):
            started.append(query)
            time.sleep(0.16)
            return original(query,*args,**kwargs)
        beats=[]
        timer=QTimer()
        timer.timeout.connect(lambda:beats.append(1))
        timer.start(10)
        with patch.object(self.window.catalog,'search_page_data',side_effect=slow):
            self.window.search_edit.setText('VLAN')
            self.window.refresh_search()
            QTest.qWait(30)
            self.window.search_edit.setText('not-present')
            self.window.refresh_search()
            settle_search(self.window)
        timer.stop()
        self.assertGreater(len(beats),5)
        self.assertEqual(self.window.search_table.rowCount(),0)
        self.assertEqual(self.window.search_total,0)
        self.assertEqual(started[-1],'not-present')

    def test_library_switch_discards_old_results(self):
        from PySide6.QtTest import QTest
        archive_one(self.item,self.catalog)
        old = self.window.catalog
        original = old.search_page_data
        def slow(*args,**kwargs):
            time.sleep(0.12)
            return original(*args,**kwargs)
        with patch.object(old,'search_page_data',side_effect=slow):
            self.window.refresh_search()
            QTest.qWait(20)
            self.window.set_library(self.root/'other-library')
            settle_search(self.window)
        self.assertEqual(self.window.search_total,0)
        self.assertEqual(self.window.archive_rows,[])

    def test_cards_are_bounded_and_page_indices_preserve_edits_and_selection(self):
        self.window.items=[replace(self.item,path=self.root/f'file-{n}.txt',doc_id=None) for n in range(1000)]
        self.window.populate_scan()
        self.assertEqual(len(self.window.cards_view.cards),60)
        self.assertEqual(self.window.scan_table.rowCount(),1000)
        self.assertIsNone(self.window.scan_table.cellWidget(500,2))
        self.window.cards_view.change_page(1)
        card=self.window.cards_view.cards[0]
        self.assertEqual(card.row,60)
        card.check.setChecked(False)
        card.combo.setCurrentText('课程资料')
        self.assertFalse(self.window.items[60].selected)
        self.assertEqual(self.window.items[60].category,'课程资料')
        self.assertEqual(self.window.items[0].category,self.item.category)
        self.window.cards_view.change_page(-1)
        self.assertEqual(self.window.cards_view.cards[0].row,0)
        self.assertFalse(self.window.items[60].selected)
