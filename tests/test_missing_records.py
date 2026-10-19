import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from document_assistant.rules import DEFAULT_RULES
from document_assistant.service import PROJECT_ROOT, archive_one, scan_files, sha256
from document_assistant.storage import Catalog


class MissingRecordTests(unittest.TestCase):
    def setUp(self):
        directory = PROJECT_ROOT.parent / 'DocumentAssistant-local/tmp'
        directory.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='cleanup-', dir=directory)
        self.root = Path(self.temp.name)
        self.library = self.root / '库'
        self.catalog = Catalog(self.library)
        paths = [self.root / '实验报告.txt', self.root / '项目计划.txt']
        for path in paths:
            path.write_text('本文件为临时示例。', encoding='utf-8')
        self.items = scan_files(paths, DEFAULT_RULES, self.library)[0]
        self.copies = [archive_one(item, self.catalog)[1] for item in self.items]
        self.source_hashes = {item.path: sha256(item.path) for item in self.items}

    def tearDown(self):
        self.temp.cleanup()

    def test_cleanup_removes_missing_record_only_and_keeps_history(self):
        existing_hash = sha256(self.copies[1])
        self.copies[0].unlink()
        candidates, unknown = self.catalog.missing_archives()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(unknown, 0)
        result = self.catalog.cleanup_missing_archives(candidates)
        self.assertEqual(result['removed'], 1)
        self.assertEqual(len(self.catalog.search()), 1)
        self.assertEqual(sha256(self.copies[1]), existing_hash)
        self.assertTrue(all(sha256(p) == h for p, h in self.source_hashes.items()))
        record = next(r for r in self.catalog.operations() if r['action'] == '清理失效记录')
        self.assertEqual(json.loads(record['detail']), candidates[0])
        self.assertIn('复制归档', [r['action'] for r in self.catalog.operations()])
        # Scan metadata and user edits remain usable after clearing a library entry.
        with self.catalog.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM documents').fetchone()[0], 2)
        message, target = archive_one(self.items[0], self.catalog)
        self.assertEqual(target, self.copies[0])
        self.assertEqual(message, '归档成功')

    def test_restored_file_between_preview_and_confirm_is_kept(self):
        self.copies[0].unlink()
        candidates, _ = self.catalog.missing_archives()
        self.copies[0].write_bytes(self.items[0].path.read_bytes())
        result = self.catalog.cleanup_missing_archives(candidates)
        self.assertEqual(result['removed'], 0)
        self.assertEqual(result['restored'], 1)
        self.assertEqual(len(self.catalog.search()), 2)

    def test_changed_record_between_preview_and_confirm_is_kept(self):
        self.copies[0].unlink()
        candidates, _ = self.catalog.missing_archives()
        with self.catalog.connection() as db:
            db.execute('UPDATE archives SET category=? WHERE id=?', ('其他', candidates[0]['id']))
        result = self.catalog.cleanup_missing_archives(candidates)
        self.assertEqual(result['removed'], 0)
        self.assertEqual(result['skipped'], 1)

    def test_permission_error_is_not_proof_of_deletion(self):
        original_stat = Path.stat
        blocked = self.copies[0]

        def checked_stat(path, *args, **kwargs):
            if path == blocked:
                raise PermissionError('temporary access error')
            return original_stat(path, *args, **kwargs)

        with patch.object(Path, 'stat', checked_stat):
            candidates, unknown = self.catalog.missing_archives()
            self.assertEqual(candidates, [])
            self.assertEqual(unknown, 1)
            result = self.catalog.cleanup_missing_archives([dict(self.catalog.search()[1])])
            self.assertEqual(result['removed'], 0)
        self.assertTrue(blocked.is_file())

    def test_unavailable_library_does_not_clean_records(self):
        self.copies[0].unlink()
        candidates, _ = self.catalog.missing_archives()
        moved = self.root / '暂时不可用的库'
        assert self.library.is_relative_to(self.root) and moved.is_relative_to(self.root)
        self.library.rename(moved)
        with self.assertRaisesRegex(OSError, '文档库目录不可访问'):
            self.catalog.cleanup_missing_archives(candidates)
        self.assertEqual(len(Catalog(moved).search()), 2)

    def test_audit_write_failure_rolls_back_all_removals(self):
        for path in self.copies:
            path.unlink()
        candidates, _ = self.catalog.missing_archives()
        failure_doc = candidates[-1]['document_id']
        with self.catalog.connection() as db:
            db.execute(f'''CREATE TRIGGER fail_cleanup BEFORE INSERT ON operations
                WHEN NEW.action='清理失效记录' AND NEW.document_id={failure_doc}
                BEGIN SELECT RAISE(ABORT, 'audit unavailable'); END''')
        with self.assertRaises(sqlite3.IntegrityError):
            self.catalog.cleanup_missing_archives(candidates)
        self.assertEqual(len(self.catalog.search()), 2)
        self.assertNotIn('清理失效记录', [r['action'] for r in self.catalog.operations()])


if __name__ == '__main__':
    unittest.main()
