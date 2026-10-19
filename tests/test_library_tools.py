import hashlib
import json
import sqlite3
import zipfile
from pathlib import Path
from unittest.mock import patch

from test_upgrade import Fixture
from document_assistant.archive import recover_pending, undo_batch
from document_assistant.library_backup import export_library, restore_library
from document_assistant.organization import DEFAULT_LABEL_RULES, suggest_labels
from document_assistant.recovery import restore_recycled
from document_assistant.service import archive_one, scan_files, sha256
from document_assistant.rules import DEFAULT_RULES
from document_assistant.storage import Catalog


class LibraryToolsTests(Fixture):
    def archive_and_undo(self):
        self.item.project = '项目A, 项目B'
        self.catalog.save_scan(self.item)
        _, target = archive_one(self.item, self.catalog)
        rows = self.catalog.search()
        undo_batch(self.catalog, rows)
        return target, self.catalog.recycle_entries()[0]

    def test_restore_keeps_labels_aliases_and_search_and_is_repeatable(self):
        self.item.project = '项目A'
        self.catalog.save_scan(self.item)
        archive_one(self.item, self.catalog)
        other = self.root / '别名文件.txt'
        other.write_bytes(self.path.read_bytes())
        item = scan_files([other], DEFAULT_RULES, self.library)[0][0]
        item.project = '项目B'
        self.catalog.save_scan(item)
        archive_one(item, self.catalog, duplicate_policy='link')
        undo_batch(self.catalog, self.catalog.search())
        entry = self.catalog.recycle_entries()[0]
        self.assertIn('已恢复', restore_recycled(self.catalog, [entry])[0])
        self.assertEqual(self.catalog.recycle_entries(), [])
        self.assertEqual(self.catalog.search_count(project='项目B'), 1)
        self.assertEqual(self.catalog.search_count('别名', scope='filename'), 1)
        self.assertEqual(self.catalog.search_count('VLAN'), 1)
        self.assertIn('未完成', restore_recycled(self.catalog, [entry])[0])
        self.assertEqual(self.catalog.search_count(), 1)
        self.assertEqual(sha256(self.path), sha256(other))

    def test_restore_does_not_overwrite_existing_file(self):
        target, entry = self.archive_and_undo()
        target.write_text('后来创建的文件', encoding='utf-8')
        self.assertIn('已恢复', restore_recycled(self.catalog, [entry])[0])
        self.assertEqual(target.read_text(encoding='utf-8'), '后来创建的文件')
        restored = self.catalog.search()[0]
        self.assertIn('恢复 1', restored['filename'] if '恢复 1' in restored['filename'] else Path(restored['archive_path']).name)
        self.assertEqual(sha256(Path(restored['archive_path'])), sha256(self.path))

    def test_modified_recycle_file_is_retained(self):
        _, entry = self.archive_and_undo()
        trash = self.catalog.safe_path(entry['trash_relative'])
        trash.write_text('人工修改', encoding='utf-8')
        self.assertIn('已修改', restore_recycled(self.catalog, [entry])[0])
        self.assertEqual(trash.read_text(encoding='utf-8'), '人工修改')
        self.assertEqual(len(self.catalog.recycle_entries()), 1)
        self.assertEqual(self.catalog.search_count(), 0)

    def test_restore_journal_recovers_after_relocation(self):
        _, entry = self.archive_and_undo()
        with patch.object(self.catalog, 'finish_restore', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                restore_recycled(self.catalog, [entry])
        self.assertEqual(len(self.catalog.pending_restores()), 1)
        moved = self.root / 'moved'
        self.library.rename(moved)
        new = Catalog(moved)
        self.assertTrue(any('恢复归档登记' in m for m in recover_pending(new)))
        self.assertEqual(new.pending_restores(), [])
        self.assertEqual(new.recycle_entries(), [])
        self.assertEqual(new.search_count(project='项目B'), 1)
        self.assertEqual(recover_pending(new), [])

    def test_cancelled_restore_keeps_recycle_and_modified_target_task(self):
        target, entry = self.archive_and_undo()
        restore_recycled(self.catalog, [entry], cancelled=lambda: True)
        self.assertEqual(len(self.catalog.recycle_entries()), 1)
        self.assertFalse(target.exists())
        with patch.object(self.catalog, 'finish_restore', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                restore_recycled(self.catalog, [entry])
        target.write_text('新的目标内容', encoding='utf-8')
        messages = recover_pending(self.catalog)
        self.assertTrue(any('待检查' in m for m in messages))
        self.assertEqual(len(self.catalog.pending_restores()), 1)
        self.assertEqual(target.read_text(encoding='utf-8'), '新的目标内容')

    def test_legacy_undo_log_is_visible_and_can_restore(self):
        _, entry = self.archive_and_undo()
        with self.catalog.connection() as db:
            row = db.execute("SELECT id,detail FROM operations WHERE action='撤销归档'").fetchone()
            data = json.loads(row['detail'])
            data.pop('恢复区条目')
            data['归档'].pop('_labels')
            data['归档'].pop('_sources')
            db.execute('UPDATE operations SET detail=? WHERE id=?', (json.dumps(data), row['id']))
            db.execute('DELETE FROM recycle_entries')
            db.execute("UPDATE library_meta SET value='3' WHERE key='schema_version'")
        new = Catalog(self.library)
        self.assertTrue(new.last_backup.is_file())
        rows = new.recycle_entries()
        self.assertEqual(len(rows), 1)
        restore_recycled(new, rows)
        self.assertEqual(new.search_count(project='项目B'), 1)
        moved = self.root / 'moved-legacy'
        self.library.rename(moved)
        self.assertEqual(Catalog(moved).recycle_entries(), [])

    def test_full_backup_restore_preserves_inbox_views_recycle_and_unknown_files(self):
        _, entry = self.archive_and_undo()
        second = self.root / '新资料.txt'
        second.write_text('项目资料：Docker VLAN', encoding='utf-8')
        item = scan_files([second], DEFAULT_RULES, self.library)[0][0]
        item.project = '完整备份项目'
        self.catalog.save_scan(item)
        archive_one(item, self.catalog)
        stored = Path(self.catalog.search()[0]['archive_path'])
        stored.rename(stored.with_suffix('.TXT'))
        scan_files([self.path], DEFAULT_RULES, self.library)
        self.catalog.save_view('课程资料', {'query': 'Docker', 'category': '', 'course': '', 'project': '', 'tag': '', 'scope': 'all'})
        extra = self.library / '附加笔记.md'
        extra.write_text('库内附加文件也应备份', encoding='utf-8')
        output = self.root / '完整备份.zip'
        result = export_library(self.catalog, output)
        self.assertTrue(result['verified'])
        self.assertEqual(result['archive_count'], 1)
        self.assertEqual(result['recycle_count'], 1)
        with zipfile.ZipFile(output) as bundle:
            self.assertFalse(any('/backups/' in n for n in bundle.namelist()))
        target = self.root / 'restored'
        target.mkdir()
        restored = restore_library(output, target)
        self.assertTrue(restored['verified'])
        new = Catalog(target)
        self.assertEqual(new.library_id, self.catalog.library_id)
        self.assertEqual(new.search_count(project='完整备份项目'), 1)
        self.assertEqual(len(new.inbox()), 1)
        self.assertEqual(len(new.saved_views()), 1)
        self.assertEqual(len(new.recycle_entries()), 1)
        self.assertEqual((target / extra.name).read_bytes(), extra.read_bytes())
        for row in new.search():
            self.assertTrue(Path(row['archive_path']).is_relative_to(target))
            self.assertEqual(sha256(Path(row['archive_path'])), row['sha256'])
        restore_recycled(new, new.recycle_entries())
        self.assertEqual(new.search_count(project='项目B'), 1)
        self.assertEqual(len(self.catalog.recycle_entries()), 1)

    def test_export_rejects_missing_file_tasks_inside_library_and_existing_backup(self):
        _, target = archive_one(self.item, self.catalog)
        with self.assertRaises(ValueError):
            export_library(self.catalog, self.library / 'recursive.zip')
        output = self.root / 'backup.zip'
        output.write_bytes(b'preserve me')
        with self.assertRaises(FileExistsError):
            export_library(self.catalog, output)
        self.assertEqual(output.read_bytes(), b'preserve me')
        target.unlink()
        with self.assertRaises(ValueError):
            export_library(self.catalog, self.root / 'missing.zip')
        self.assertFalse((self.root / 'missing.zip').exists())

    def test_export_and_import_cancellation_leave_original_and_target_untouched(self):
        archive_one(self.item, self.catalog)
        cancelled_output = self.root / 'cancelled.zip'
        with self.assertRaises(InterruptedError):
            export_library(self.catalog, cancelled_output, cancelled=lambda: True)
        self.assertFalse(cancelled_output.exists())
        output = self.root / 'valid.zip'
        export_library(self.catalog, output)
        target = self.root / 'empty'
        target.mkdir()
        with self.assertRaises(InterruptedError):
            restore_library(output, target, cancelled=lambda: True)
        self.assertEqual(list(target.iterdir()), [])
        self.assertEqual(self.catalog.search_count(), 1)

    def test_export_aborts_if_file_changes_during_copy(self):
        _, target = archive_one(self.item, self.catalog)
        changed = False
        def change_file(current, total, message):
            nonlocal changed
            if not changed and message.endswith(target.name):
                changed = True
                target.write_text('发生变化的新内容', encoding='utf-8')
        output = self.root / 'changed.zip'
        with self.assertRaises(ValueError):
            export_library(self.catalog, output, progress=change_file)
        self.assertFalse(output.exists())
        self.assertEqual(target.read_text(encoding='utf-8'), '发生变化的新内容')

    def test_export_aborts_if_metadata_changes_and_pending_tasks_exist(self):
        archive_one(self.item, self.catalog)
        edited = False
        def edit_metadata(*_):
            nonlocal edited
            if not edited:
                edited = True
                self.catalog.change_labels([self.catalog.search()[0]['id']], {'project': '编辑期间变化'}, archives=True)
        output = self.root / 'changed-metadata.zip'
        with self.assertRaises(ValueError):
            export_library(self.catalog, output, progress=edit_metadata)
        self.assertFalse(output.exists())
        new_source = self.root / '新文件.txt'
        new_source.write_text('实验报告：未完成归档', encoding='utf-8')
        item = scan_files([new_source], DEFAULT_RULES, self.library)[0][0]
        with patch.object(self.catalog, 'record_archive', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                archive_one(item, self.catalog)
        with self.assertRaises(ValueError):
            export_library(self.catalog, self.root / 'pending.zip')
        self.assertEqual(len(self.catalog.pending_tasks()), 1)

    def test_restore_rejects_nonempty_destination_tampering_traversal_and_extra_members(self):
        archive_one(self.item, self.catalog)
        original = self.root / 'valid.zip'
        export_library(self.catalog, original)
        existing = self.root / 'occupied'
        existing.mkdir()
        (existing / 'keep.txt').write_text('preserve', encoding='utf-8')
        with self.assertRaises(ValueError):
            restore_library(original, existing)
        self.assertEqual((existing / 'keep.txt').read_text(), 'preserve')
        for kind in ('tamper', 'traversal', 'extra', 'case_collision'):
            bad = self.root / (kind + '.zip')
            with zipfile.ZipFile(original) as source, zipfile.ZipFile(bad, 'x') as target:
                manifest = json.loads(source.read('manifest.json'))
                names = [name for name in source.namelist() if name != 'manifest.json']
                if kind == 'traversal':
                    manifest['files']['../escape.txt'] = {'size': 4, 'sha256': hashlib.sha256(b'evil').hexdigest()}
                    target.writestr('library/../escape.txt', b'evil')
                for name in names:
                    data = source.read(name)
                    if kind == 'tamper' and name.endswith('.txt'):
                        data = b'x' * len(data)
                    target.writestr(name, data)
                if kind == 'extra':
                    target.writestr('outside.txt', b'extra')
                if kind == 'case_collision':
                    target.writestr('MANIFEST.JSON', b'{}')
                target.writestr('manifest.json', json.dumps(manifest))
            destination = self.root / (kind + '-destination')
            with self.assertRaises(ValueError):
                restore_library(bad, destination)
            self.assertFalse(destination.exists())
        self.assertFalse((self.root / 'escape.txt').exists())

    def test_folder_rule_matches_subdirectories_not_similar_names_and_is_specific(self):
        folder = self.root / '课程'
        rules = [*DEFAULT_LABEL_RULES,
            {'field': 'course', 'value': '人工目录课程', 'keywords': [str(folder)], 'source': 'folder'},
            {'field': 'course', 'value': '子目录课程', 'keywords': [str(folder / '子目录')], 'source': 'folder'}]
        self.assertEqual(suggest_labels(folder / 'file.txt', 'VLAN', rules)[0]['course'], '人工目录课程')
        self.assertEqual(suggest_labels(folder / '子目录' / 'file.txt', 'VLAN', rules)[0]['course'], '子目录课程')
        self.assertEqual(suggest_labels(self.root / '课程备份' / 'file.txt', 'VLAN', rules)[0]['course'], '计算机网络')

    def test_long_windows_library_paths_backup_and_restore(self):
        from dataclasses import replace
        library = self.root / ('long-' + 'a'*70) / ('nested-' + 'b'*70)
        catalog = Catalog(library)
        item = replace(self.item, doc_id=None)
        item.doc_id = catalog.save_scan(item)
        archive_one(item, catalog)
        self.assertGreater(len(str(catalog.path)), 240)
        self.assertTrue(catalog.backup('long-path').is_file())
        output = self.root / 'long-path.zip'
        export_library(catalog, output)
        target = self.root / 'restored-long'
        restore_library(output, target)
        self.assertEqual(Catalog(target).search_count('VLAN'), 1)

    def test_transient_directory_lock_is_retried_without_overwriting(self):
        archive_one(self.item, self.catalog)
        output = self.root / 'retry.zip'
        export_library(self.catalog, output)
        original_rename = Path.rename
        attempts = 0
        def temporarily_locked(path, target):
            nonlocal attempts
            if path.name.startswith('.documentassistant-restore-'):
                attempts += 1
                if attempts == 1:
                    raise PermissionError('simulated OneDrive lock')
            return original_rename(path, target)
        target = self.root / 'retried'
        with patch.object(Path, 'rename', temporarily_locked):
            restore_library(output, target)
        self.assertEqual(attempts, 2)
        self.assertEqual(Catalog(target).search_count(), 1)


class PdfPreviewTests(Fixture):
    def setUp(self):
        super().setUp()
        from PySide6.QtWidgets import QApplication
        self.app = QApplication.instance() or QApplication([])

    def test_pdf_render_navigation_zoom_and_source_not_held_open(self):
        from pypdf import PdfReader, PdfWriter
        from PySide6.QtCore import QSize
        from PySide6.QtPdf import QPdfDocument
        from document_assistant.pdf_preview import PdfPreview
        from tests.fixtures import write_pdf
        first = self.root / 'page.pdf'
        write_pdf(first, 'Original PDF page text')
        reader = PdfReader(first)
        writer = PdfWriter()
        writer.add_page(reader.pages[0])
        writer.add_blank_page(width=595, height=842)
        path = self.root / 'two-pages.pdf'
        with path.open('wb') as stream:
            writer.write(stream)
        widget = PdfPreview()
        widget.load_path(path)
        self.app.processEvents()
        self.assertEqual(widget.document.status(), QPdfDocument.Status.Ready)
        self.assertEqual(widget.document.pageCount(), 2)
        self.assertFalse(widget.document.render(0, QSize(400, 550)).isNull())
        widget.page.setValue(2)
        self.assertEqual(widget.view.pageNavigator().currentPage(), 1)
        widget.zoom.setCurrentIndex(3)
        self.assertEqual(widget.view.zoomFactor(), 1.5)
        moved = path.with_name('moved.pdf')
        path.rename(moved)
        self.assertTrue(moved.is_file())
        widget.load_path(None)
        widget.close()
        self.dispose(widget)

    def test_password_missing_corrupt_and_too_large_pdf_states(self):
        from pypdf import PdfWriter
        from PySide6.QtPdf import QPdfDocument
        from document_assistant.pdf_preview import PdfPreview
        widget = PdfPreview()
        path = self.root / 'protected.pdf'
        writer = PdfWriter()
        writer.add_blank_page(width=595, height=842)
        writer.encrypt('password')
        with path.open('wb') as stream:
            writer.write(stream)
        widget.load_path(path)
        self.assertEqual(widget.document.error(), QPdfDocument.Error.IncorrectPassword)
        widget.load_path(path, password='password')
        self.assertEqual(widget.document.status(), QPdfDocument.Status.Ready)
        bad = self.root / 'bad.pdf'
        bad.write_bytes(b'not a PDF')
        widget.load_path(bad)
        self.assertNotEqual(widget.document.status(), QPdfDocument.Status.Ready)
        widget.load_path(self.root / 'missing.pdf')
        self.assertIn('无法预览', widget.message.text())
        with patch.object(widget, 'LIMIT', 3):
            widget.load_path(path)
            self.assertIn('超过', widget.message.text())
        widget.load_path(None)
        widget.close()
        self.dispose(widget)

    def dispose(self, widget):
        from PySide6.QtCore import QCoreApplication, QEvent
        widget.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
