from tests.gui_wait import settle_search
import json
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from test_upgrade import Fixture
from document_assistant.archive import recover_pending, undo_batch
from document_assistant.organization import suggest_labels, validate_label_rules
from document_assistant.rules import DEFAULT_RULES
from document_assistant.service import archive_one, scan_files, sha256
from document_assistant.storage import Catalog, CatalogV8


class OrganizationTests(Fixture):
    def test_inbox_selection_edits_and_dismissal_survive_restart(self):
        self.catalog.change_labels([self.item.doc_id], {'course': '自定义课程', 'project': '项目A', 'tags': ''})
        self.catalog.save_selection([(self.item.doc_id, False)])
        new = Catalog(self.library)
        items = new.inbox()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].course, '自定义课程')
        self.assertEqual(items[0].project, '项目A')
        self.assertFalse(items[0].selected)
        self.path.unlink()
        self.assertEqual(len(Catalog(self.library).inbox()), 1)
        new.dismiss_inbox([items[0].doc_id])
        self.assertEqual(Catalog(self.library).inbox(), [])

    def test_manual_empty_and_custom_fields_survive_new_suggestions(self):
        self.catalog.change_labels([self.item.doc_id], {'course': '', 'project': '人工项目', 'tags': ''})
        rules = [{'field': 'project', 'value': '自动项目', 'keywords': ['vlan'], 'source': 'body'}]
        item = scan_files([self.path], DEFAULT_RULES, self.library, organization_rules=rules)[0][0]
        self.assertEqual((item.course, item.project, item.tags), ('', '人工项目', ''))

    def test_path_filename_and_body_suggestions_and_conflicts(self):
        rules = [
            {'field': 'course', 'value': '网络', 'keywords': ['网络'], 'source': 'path'},
            {'field': 'project', 'value': '项目A', 'keywords': ['报告'], 'source': 'filename'},
            {'field': 'tags', 'value': 'VLAN', 'keywords': ['vlan'], 'source': 'body'},
        ]
        values, reason = suggest_labels(Path('网络/实验报告.txt'), 'VLAN', rules)
        self.assertEqual(values, {'course': '网络', 'project': '项目A', 'tags': 'VLAN'})
        self.assertIn('来源目录', reason)
        rules.append({'field': 'course', 'value': '课程B', 'keywords': ['vlan'], 'source': 'body'})
        values, reason = suggest_labels(Path('网络/实验报告.txt'), 'VLAN', rules)
        self.assertNotIn('course', values)
        self.assertIn('多个匹配', reason)
        self.assertEqual(suggest_labels(self.path, self.item.body, [])[0], {'course': '', 'project': '', 'tags': ''})

    def test_invalid_rule_does_not_modify_input(self):
        rules = [{'field': 'project', 'value': '项目', 'keywords': [], 'source': 'body'}]
        before = json.dumps(rules)
        with self.assertRaises(ValueError):
            validate_label_rules(rules)
        self.assertEqual(json.dumps(rules), before)

    def test_link_duplicate_merges_projects_and_alias_without_second_copy(self):
        self.item.project = '项目A'
        self.catalog.save_scan(self.item)
        _, target = archive_one(self.item, self.catalog)
        other = self.root / '别名资料.txt'
        other.write_bytes(self.path.read_bytes())
        second = scan_files([other], DEFAULT_RULES, self.library)[0][0]
        second.project = '项目B, 项目C'
        second.tags = '新标签'
        self.catalog.save_scan(second)
        message, duplicate = archive_one(second, self.catalog, duplicate_policy='link')
        self.assertIn('已关联', message)
        self.assertEqual(target, duplicate)
        self.assertEqual(self.catalog.search_count(), 1)
        for project in ('项目A', '项目B', '项目C'):
            self.assertEqual(self.catalog.search_count(project=project), 1)
        self.assertEqual(self.catalog.search_count('别名', scope='filename'), 1)
        self.assertEqual(self.catalog.search_count(tag='新标签'), 1)
        self.assertEqual(self.catalog.inbox(), [])
        self.assertEqual(len(list((self.library / self.item.category).glob('*.txt'))), 1)
        self.assertEqual(sha256(self.path), sha256(other))
        archive_one(second, self.catalog, duplicate_policy='link')
        self.assertEqual(self.catalog.search_count(), 1)

    def test_skip_choice_does_not_merge_but_completes_inbox(self):
        archive_one(self.item, self.catalog)
        other = self.root / '不同路径.txt'
        other.write_bytes(self.path.read_bytes())
        second = scan_files([other], DEFAULT_RULES, self.library)[0][0]
        second.project = '不合并的项目'
        self.catalog.save_scan(second)
        archive_one(second, self.catalog, duplicate_policy='skip')
        self.assertEqual(self.catalog.search_count(project=second.project), 0)
        self.assertEqual(self.catalog.inbox(), [])

    def test_recovery_preserves_newer_category_and_body(self):
        with patch.object(self.catalog, 'record_archive', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                archive_one(self.item, self.catalog)
        self.path.write_text('研究文献\n新的正文 Docker', encoding='utf-8')
        latest = scan_files([self.path], DEFAULT_RULES, self.library)[0][0]
        self.catalog.change_labels([latest.doc_id], {'category': '研究文献', 'project': '新项目'})
        recover_pending(self.catalog)
        items = Catalog(self.library).inbox()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].category, '研究文献')
        self.assertEqual(items[0].project, '新项目')
        self.assertIn('Docker', items[0].body)
        self.assertEqual(self.catalog.search_count('VLAN'), 1)
        self.assertEqual(self.catalog.search_count('Docker'), 0)
        self.assertEqual(recover_pending(self.catalog), [])

    def test_relocated_interrupted_undo_finishes_and_retains_bytes(self):
        _, target = archive_one(self.item, self.catalog)
        row = self.catalog.search()[0]
        relative = '.documentassistant/undo/test/' + target.name
        self.catalog.prepare_undo(row, relative)
        trash = self.catalog.safe_path(relative)
        trash.parent.mkdir(parents=True)
        target.rename(trash)
        moved = self.root / 'moved'
        self.library.rename(moved)
        new = Catalog(moved)
        self.assertIn('恢复撤销', recover_pending(new)[0])
        self.assertEqual(new.pending_undos(), [])
        self.assertEqual(new.search(), [])
        self.assertEqual(sha256(new.safe_path(relative)), row['sha256'])
        self.assertEqual(sha256(self.path), row['sha256'])
        self.assertEqual(recover_pending(new), [])

    def test_unstarted_undo_is_cancelled_and_changed_labels_still_guarded(self):
        _, target = archive_one(self.item, self.catalog)
        row = self.catalog.search()[0]
        self.catalog.prepare_undo(row, '.documentassistant/undo/not-started.txt')
        self.assertIn('已取消', recover_pending(self.catalog)[0])
        self.assertTrue(target.is_file())
        row = self.catalog.search()[0]
        relative = '.documentassistant/undo/changed.txt'
        self.catalog.prepare_undo(row, relative)
        self.catalog.safe_path(relative).parent.mkdir(parents=True, exist_ok=True)
        target.rename(self.catalog.safe_path(relative))
        self.catalog.change_labels([row['id']], {'project': '后来编辑'}, archives=True)
        self.assertIn('未完成', recover_pending(self.catalog)[0])
        self.assertEqual(len(self.catalog.pending_undos()), 1)
        self.assertEqual(self.catalog.search_count(), 1)

    def test_multiword_phrase_literal_and_normalized_filters(self):
        self.item.body = 'VLAN 的实验步骤涉及 Docker。\n连续短语 VLAN Docker 另有含义。'
        self.item.project = '项目A, 项目B'
        self.item.tags = 'VLAN, Docker'
        self.catalog.save_scan(self.item)
        archive_one(self.item, self.catalog)
        self.assertEqual(self.catalog.search_count('VLAN Docker', project='项目B', tag='Docker'), 1)
        self.assertEqual(self.catalog.search_count('VLAN Docker missing'), 0)
        self.assertEqual(self.catalog.search_count('"VLAN Docker"'), 1)
        self.assertEqual(self.catalog.search_count('"VLAN 的 Docker"'), 0)
        self.assertEqual(self.catalog.search_count('%'), 0)
        self.assertEqual(self.catalog.search_count("' OR 1=1 --"), 0)
        row = self.catalog.search()[0]
        self.catalog.change_labels([row['id']], {'project': '项目C'}, archives=True)
        self.assertEqual(self.catalog.search_count(project='项目B'), 0)
        self.assertEqual(self.catalog.search_count(project='项目C'), 1)

    def test_saved_views_store_conditions_and_follow_new_documents(self):
        filters = {'query': 'VLAN', 'category': '', 'course': '', 'project': '项目A', 'tag': '', 'scope': 'all'}
        self.catalog.save_view('常用筛选', filters)
        self.assertEqual(len(Catalog(self.library).saved_views()), 1)
        self.assertEqual(self.catalog.search_count('VLAN', project='项目A'), 0)
        self.item.project = '项目A'
        self.catalog.save_scan(self.item)
        archive_one(self.item, self.catalog)
        loaded = self.catalog.saved_views()[0]['filters'].copy()
        query = loaded.pop('query')
        self.assertEqual(self.catalog.search_count(query, **loaded), 1)
        filters['project'] = '项目B'
        self.catalog.save_view('常用筛选', filters)
        views = self.catalog.saved_views()
        self.assertEqual(len(views), 1)
        self.assertEqual(views[0]['filters']['project'], '项目B')
        self.catalog.delete_view(views[0]['id'])
        self.assertEqual(self.catalog.saved_views(), [])

    def test_v8_migration_keeps_records_and_backs_up_before_schema_change(self):
        old = CatalogV8(self.root / 'v8')
        item = replace(self.item, doc_id=None, course='旧课程', project='旧项目', tags='标签A,标签B')
        item.doc_id = old.save_scan(item)
        target = old.library / item.category / item.path.name
        target.parent.mkdir()
        target.write_bytes(item.path.read_bytes())
        old.record_archive(item, target, sha256(target))
        new = Catalog(old.library)
        self.assertTrue(new.last_backup.is_file())
        self.assertEqual(new.search_count(project='旧项目', tag='标签B'), 1)
        self.assertEqual(new.document_metadata(item.path)['manual_fields'], 'course,project,tags')
        self.assertEqual(new.inbox(), [])  # Do not revive previously cleared 0.8 scan lists.
        self.assertIsNone(Catalog(old.library).last_backup)


class OrganizationGuiTests(Fixture):
    def setUp(self):
        super().setUp()
        from PySide6.QtWidgets import QApplication
        from document_assistant.gui import MainWindow
        self.app = QApplication.instance() or QApplication([])
        self.MainWindow = MainWindow
        self.home = self.root / 'home'
        self.window = MainWindow(self.home)
        self.window.set_library(self.library)

    def tearDown(self):
        settle_search(self.window)
        self.window.close()
        self.app.processEvents()
        super().tearDown()

    def test_gui_restarts_with_manual_edits_and_selection(self):
        self.window.apply_bulk_updates({'course': '人工课程', 'project': '项目A'})
        self.window.check_all(False)
        settle_search(self.window)
        self.window.close()
        self.window = self.MainWindow(self.home)
        self.assertEqual(len(self.window.items), 1)
        self.assertEqual(self.window.items[0].course, '人工课程')
        self.assertEqual(self.window.selected_scan_rows(), [])
        self.assertEqual(self.window.tabs.currentIndex(), 0)
        with patch('document_assistant.gui.QMessageBox.question', return_value=16384):
            self.window.clear_imports()
        settle_search(self.window)
        self.window.close()
        self.window = self.MainWindow(self.home)
        self.assertEqual(self.window.items, [])
        self.assertTrue(self.path.exists())

    def test_loose_inbox_without_library_survives_restart_and_transfer(self):
        settle_search(self.window)
        self.window.close()
        home = self.root / 'loose'
        self.window = self.MainWindow(home)
        item = replace(self.item, doc_id=None)
        self.window.import_finished(([item], []))
        self.window.apply_bulk_updates({'project': '临时项目'})
        settle_search(self.window)
        self.window.close()
        self.window = self.MainWindow(home)
        self.assertEqual(len(self.window.items), 1)
        self.assertEqual(self.window.items[0].project, '临时项目')
        self.window.set_library(self.root / 'new-library')
        settle_search(self.window)
        self.window.close()
        self.window = self.MainWindow(home)
        self.assertEqual(len(self.window.items), 1)
        self.assertEqual(self.window.items[0].project, '临时项目')

    def test_filters_saved_view_and_editable_rule_preview(self):
        from document_assistant.organization_ui import SuggestionRuleDialog
        self.window.apply_bulk_updates({'project': '项目A'})
        item = self.window.items[0]
        archive_one(item, self.window.catalog)
        self.window.refresh_filter_options()
        filters = {'query': 'VLAN', 'category': '', 'course': '', 'project': '项目A', 'tag': '', 'scope': 'all'}
        self.window.catalog.save_view('项目视图', filters)
        self.window.refresh_filter_options()
        self.window.saved_view_combo.setCurrentIndex(1)
        settle_search(self.window)
        self.assertEqual(self.window.search_table.rowCount(), 1)
        self.assertEqual(self.window.current_filters()['project'], '项目A')
        self.window.filter_combos['project'].setEditText('不存在的项目')
        self.window.refresh_search()
        settle_search(self.window)
        self.assertEqual(self.window.search_table.rowCount(), 0)
        self.window.clear_filters()
        settle_search(self.window)
        self.assertEqual(self.window.search_table.rowCount(), 1)
        dialog = SuggestionRuleDialog(self.window)
        dialog.preview_rules()
        self.assertIn('VLAN', dialog.preview.toPlainText())
        dialog.close()

    def test_apply_suggestion_preserves_confirmed_field(self):
        self.window.apply_bulk_updates({'project': '人工项目'})
        self.window.organization_rules = [{'field': 'project', 'value': '自动项目', 'keywords': ['VLAN'], 'source': 'body'}]
        self.window.suggest_selected()
        self.assertEqual(self.window.items[0].project, '人工项目')
