import copy
import os
import time
from pathlib import Path
from dataclasses import replace
from unittest.mock import patch
from test_upgrade import Fixture
from tests.gui_wait import settle_search
from document_assistant.document_metadata import title_suggestion,validate_category,attention_rank,category_rule_match
from document_assistant.rules import DEFAULT_RULES,classify,validate_rules
from document_assistant.service import scan_files,archive_one,sha256
from document_assistant.storage import Catalog
from document_assistant.library_backup import export_library,restore_library
from document_assistant.archive import undo_batch
from document_assistant.recovery import restore_recycled
from document_assistant.watch_inbox import discover_folders


class PersonalWorkflowTests(Fixture):
    def test_title_skips_conference_header_and_preserves_original(self):
        body='The Ninth International Workshop on Imaging, IMQA2018\nSeptember 27-28, 2018 Kobe, Japan\nFULLY AUTOMATIC SEGMENTATION\nFROM RETRAINED U-NET MODEL\nAlice Wang, Bob Smith\nABSTRACT\nContent.'
        title,source=title_suggestion('1812.09477v1.pdf',body,'Microsoft Word - final.docx')
        self.assertEqual(title,'FULLY AUTOMATIC SEGMENTATION FROM RETRAINED U-NET MODEL')
        self.assertIn('建议',source)
        self.assertEqual(title_suggestion('id.pdf','', 'A Study of Digital Libraries')[0],'A Study of Digital Libraries')
        self.assertEqual(title_suggestion('论文结构.docx','第一章 绪论\n1.1 背景')[0],'')
        self.assertEqual(title_suggestion('Sublingual Recognition Literature Search.docx','An unrelated paragraph','Word Document')[0],'')

    def test_custom_category_rules_and_archive_directory(self):
        rules=copy.deepcopy(DEFAULT_RULES)
        rules['keywords']['毕业论文草稿']=['论文结构']
        self.assertEqual(classify('论文结构_详细.docx','',rules)[0],'毕业论文草稿')
        self.catalog.register_categories(['毕业论文草稿'])
        self.catalog.change_category(self.item.doc_id,'毕业论文草稿')
        self.item.category='毕业论文草稿'
        _,target=archive_one(self.item,self.catalog)
        self.assertEqual(target.parent.name,'毕业论文草稿')
        self.assertEqual(sha256(target),sha256(self.path))
        self.assertIn('毕业论文草稿',Catalog(self.library).category_names())
        for name in ('../逃逸','.documentassistant','CON','CON.txt','bad/name','x.',' trailing','a\\b'):
            with self.assertRaises(ValueError):validate_category(name)
        with self.assertRaises(ValueError):
            bad=copy.deepcopy(rules);bad['keywords']['../bad']=[];validate_rules(bad)

    def test_saved_category_rule_preview_conflict_and_manual_confirmation(self):
        self.catalog.register_categories(['论文草稿'])
        self.catalog.save_category_keywords('论文草稿',['论文结构'])
        self.catalog.save_category_rule('filename','实验报告','论文草稿')
        again=scan_files([self.path],DEFAULT_RULES,self.library)[0][0]
        self.assertEqual(again.category,'论文草稿')
        self.assertIn('保存的分类规则',again.reason)
        self.catalog.change_category(again.doc_id,'个人资料')
        stat=self.path.stat()
        os.utime(self.path,ns=(stat.st_atime_ns,stat.st_mtime_ns+1000000))
        again=scan_files([self.path],DEFAULT_RULES,self.library)[0][0]
        self.assertEqual(again.category,'个人资料')
        self.catalog.save_category_rule('folder',str(self.root),'课程资料')
        self.assertEqual(category_rule_match(self.path,self.catalog.category_rules())['category'],'论文草稿')
        conflicting=[{'source':'filename','pattern':'实验','category':'课程资料'},
                     {'source':'filename','pattern':'报告','category':'个人资料'}]
        self.assertEqual(category_rule_match(self.path,conflicting)['category'],'待整理')
        ident=self.catalog.category_rules()[0]['id']
        self.catalog.delete_category_rule(ident)
        self.assertEqual(len(self.catalog.category_rules()),1)

    def test_cache_uses_hash_and_can_force_refresh(self):
        with patch('document_assistant.service.extract_isolated',side_effect=AssertionError('cache should be used')):
            cached=scan_files([self.path],DEFAULT_RULES,self.library)[0][0]
        self.assertIn('VLAN',cached.body)
        stat=self.path.stat()
        body=self.path.read_text(encoding='utf-8').replace('VLAN','TEST')
        self.path.write_text(body,encoding='utf-8')
        os.utime(self.path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
        self.assertEqual(self.path.stat().st_size,stat.st_size)
        with patch('document_assistant.service.extract_isolated',return_value={'text':'Changed body','status':'已提取'}) as parser:
            changed=scan_files([self.path],DEFAULT_RULES,self.library)[0][0]
        self.assertEqual(parser.call_count,1)
        self.assertEqual(changed.body,'Changed body')
        with patch('document_assistant.service.extract_isolated',return_value={'text':'Forced body','status':'已提取'}) as parser:
            forced=scan_files([self.path],DEFAULT_RULES,self.library,refresh_body=True)[0][0]
        self.assertEqual(parser.call_count,1)
        self.assertEqual(forced.body,'Forced body')

    def test_reading_title_notes_search_backup_and_recycle_round_trip(self):
        self.item.display_title='Network isolation study'
        self.item.title_source='文档元信息'
        archive_one(self.item,self.catalog)
        r=self.catalog.search()[0]
        self.catalog.update_reading([r['id']],'重点参考','可参考的实验指标','My network reference')
        self.assertEqual(self.catalog.search_count('实验指标'),1)
        self.assertEqual(self.catalog.search_count('My network'),1)
        self.assertEqual(self.catalog.search_count('My network',scope='filename'),0)
        self.assertEqual(self.catalog.search_count(reading='重点参考'),1)
        self.catalog.register_categories(['论文草稿'])
        self.catalog.save_category_keywords('论文草稿',['论文结构'])
        self.catalog.save_category_rule('filename','论文结构','论文草稿')
        watch=self.root/'inbox';watch.mkdir();self.catalog.set_watch_folder(watch)
        bundle=self.root/'backup.zip'
        export_library(self.catalog,bundle)
        restore_library(bundle,self.root/'restored')
        restored=Catalog(self.root/'restored')
        self.assertEqual(restored.search()[0]['notes'],'可参考的实验指标')
        self.assertIn('论文草稿',restored.category_names())
        self.assertEqual(restored.category_keywords()['论文草稿'],['论文结构'])
        self.assertEqual(restored.category_rules()[0]['category'],'论文草稿')
        self.assertFalse(restored.watch_folders()[0]['enabled'])
        undo_batch(self.catalog,self.catalog.search())
        recycle=self.catalog.recycle_entries()
        restore_recycled(self.catalog,recycle)
        row=self.catalog.search()[0]
        self.assertEqual(row['display_title'],'My network reference')
        self.assertEqual(row['reading_state'],'重点参考')
        self.assertEqual(row['notes'],'可参考的实验指标')

    def test_priority_ranks_extraction_and_conflicts_without_losing_manual_choice(self):
        normal=replace(self.item,status='已提取',reason='建议把握：较强')
        pending=replace(normal,category='待整理')
        unreadable=replace(normal,status='无法提取：空文件')
        confirmed=replace(pending,category='项目资料',manual_fields='category')
        self.assertGreater(attention_rank(unreadable),attention_rank(pending))
        self.assertEqual(attention_rank(confirmed),0)

    def test_watched_files_wait_for_stability_and_acknowledgment(self):
        folder=self.root/'watch';folder.mkdir()
        p=folder/'新文献.txt';p.write_text('研究文献：正文',encoding='utf-8')
        (folder/'~$锁.docx').write_bytes(b'lock')
        self.catalog.set_watch_folder(folder)
        previous,ready,warnings=discover_folders(self.catalog)
        self.assertEqual(ready,[])
        self.assertEqual(len(previous),1)
        p.write_text('研究文献：新的正文',encoding='utf-8')
        current,ready,_=discover_folders(self.catalog,previous)
        self.assertEqual(ready,[])
        current,ready,_=discover_folders(self.catalog,current)
        self.assertEqual(len(ready),1)
        items=scan_files([p],DEFAULT_RULES,self.library)[0]
        self.catalog.acknowledge_watch(ready,items)
        self.assertEqual(discover_folders(self.catalog,current)[1],[])
        self.catalog.set_watch_folder(folder,False)
        p.write_text('new',encoding='utf-8')
        self.assertEqual(discover_folders(self.catalog)[0],{})
        self.catalog.remove_watch_folder(str(folder.resolve()))
        self.assertEqual(self.catalog.watch_seen(),{})
        with self.assertRaises(ValueError):self.catalog.set_watch_folder(self.library)


class PersonalGuiTests(Fixture):
    def setUp(self):
        super().setUp()
        from PySide6.QtWidgets import QApplication
        from document_assistant.gui import MainWindow
        self.app=QApplication.instance() or QApplication([])
        self.window=MainWindow(self.root/'settings')
        self.window.set_library(self.library)
        settle_search(self.window)

    def wait(self,condition):
        from PySide6.QtTest import QTest
        deadline=time.monotonic()+15
        while not condition():
            self.app.processEvents();QTest.qWait(10)
            if time.monotonic()>deadline:raise AssertionError('GUI operation timed out')
        self.app.processEvents()

    def tearDown(self):
        from PySide6.QtCore import QCoreApplication,QEvent
        self.window.watch_timer.stop()
        self.wait(lambda:self.window.watch_worker is None and self.window.worker is None)
        settle_search(self.window)
        self.window.close();self.window.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        self.app.processEvents()
        super().tearDown()

    def test_custom_category_dialog_card_and_rule_preview(self):
        from document_assistant.knowledge_ui import CategoryDialog,RememberRuleDialog,ReadingDialog
        dialog=CategoryDialog(self.window)
        dialog.name.setText('我的实验')
        dialog.words.setPlainText('自定义报告')
        dialog.save()
        self.assertIn('我的实验',self.window.categories)
        self.window.category_combo(0).setCurrentText('我的实验')
        self.assertEqual(self.window.items[0].category,'我的实验')
        self.assertEqual(self.window.cards_view.cards[0].badge.text(),'我的实验')
        rule=RememberRuleDialog(self.window)
        rule.pattern.setText('实验报告')
        rule.preview_rule()
        self.assertIn('实验报告.txt',rule.preview.toPlainText())
        rule.save()
        self.assertEqual(self.window.catalog.category_rules()[0]['category'],'我的实验')
        archive_one(self.window.items[0],self.window.catalog)
        self.window.refresh_search();settle_search(self.window)
        rows=[self.window.catalog.archive_by_id(self.window.archive_rows[0]['id'])]
        dialog=ReadingDialog(self.window,rows)
        dialog.state.setCurrentText('阅读中')
        dialog.notes.setPlainText('GUI 备注保存')
        dialog.title.setText('自定义显示标题')
        dialog.save();settle_search(self.window)
        self.assertEqual(self.window.search_table.item(0,0).text(),'自定义显示标题')
        self.window.reading_filter.setCurrentText('已读');settle_search(self.window)
        self.assertEqual(self.window.search_total,0)
        self.window.reading_filter.setCurrentText('阅读中');settle_search(self.window)
        self.assertEqual(self.window.search_total,1)

    def test_watch_imports_to_review_once_without_archiving(self):
        folder=self.root/'watch';folder.mkdir()
        path=folder/'研究文献.txt';path.write_text('研究文献：摘要与方法。',encoding='utf-8')
        self.window.catalog.set_watch_folder(folder)
        self.window.poll_watch()
        self.wait(lambda:self.window.watch_worker is None)
        self.assertEqual(len(self.window.items),1)
        self.window.poll_watch()
        self.wait(lambda:self.window.watch_worker is None and self.window.worker is None)
        self.assertEqual(len(self.window.items),2)
        self.assertEqual(self.window.catalog.search_count(),0)
        revision=next(i.revision for i in self.window.items if i.path==path)
        self.window.poll_watch();self.wait(lambda:self.window.watch_worker is None)
        self.assertEqual(next(i.revision for i in self.window.items if i.path==path),revision)
