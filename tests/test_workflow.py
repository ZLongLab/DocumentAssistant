import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from document_assistant.extractor import extract
from document_assistant.rules import DEFAULT_RULES, classify, validate_rules
from document_assistant.service import archive_batch, archive_one, scan_files, scan_folder, sha256, validate_library, PROJECT_ROOT
from document_assistant.storage import Catalog
from tests.fixtures import make_examples


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary = PROJECT_ROOT.parent / "DocumentAssistant-local" / "tmp"
        temporary.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="workflow-", dir=temporary)
        self.root = Path(self.temp.name)
        self.source = make_examples(self.root / "source")
        self.library = self.root / "library"
        self.catalog = Catalog(self.library)

    def tearDown(self):
        self.temp.cleanup()

    def scan(self):
        return scan_folder(self.source, DEFAULT_RULES, self.library)[0]

    def test_scan_extract_and_classify(self):
        items, warnings = scan_folder(self.source, DEFAULT_RULES, self.library)
        self.assertEqual(len(items), 10)
        self.assertEqual(warnings, [])
        by_name = {item.path.name: item for item in items}
        for name, category in (("实验报告_电路.txt", "实验报告"), ("数据库讲义.docx", "课程资料"),
                               ("研究文献.pdf", "研究文献"), ("个人笔记.txt", "其他"), ("未知.txt", "待整理")):
            self.assertEqual(by_name[name].category, category)
        self.assertIn("索引与事务", by_name["数据库讲义.docx"].body)
        self.assertIn("Abstract", by_name["研究文献.pdf"].body)
        self.assertIn("无可提取正文", by_name["无正文.pdf"].status)
        self.assertIn("无法提取", by_name["损坏.pdf"].status)
        self.assertIn("无法提取", by_name["损坏.docx"].status)
        self.assertTrue(all(item.doc_id for item in items))

    def test_explicit_files_do_not_scan_neighbors_and_skip_unsupported(self):
        report = self.source / "实验报告_电路.txt"
        pdf = self.source / "研究文献.pdf"
        items, warnings = scan_files([report, pdf, report, self.source / "忽略.png",
                                     self.source / "missing.txt", self.source], DEFAULT_RULES, self.library)
        self.assertEqual({item.path for item in items}, {report, pdf})
        self.assertEqual(len(warnings), 3)
        self.assertEqual(items[0].category, "实验报告")
        self.assertEqual(items[1].category, "研究文献")
        self.assertEqual(len(self.catalog.operations()), 2)

    def test_explicit_library_file_is_not_imported(self):
        archived = self.library / "already.txt"
        archived.write_text("keep me", encoding="utf-8")
        items, warnings = scan_files([archived], DEFAULT_RULES, self.library)
        self.assertEqual(items, [])
        self.assertIn("已在文档库", warnings[0])
        self.assertEqual(archived.read_text(encoding="utf-8"), "keep me")

    def test_confirm_copy_collision_search_and_history(self):
        items = self.scan()
        item = next(i for i in items if i.path.name == "未知.txt")
        self.catalog.change_category(item.doc_id, "其他")
        item.category = "其他"
        (self.library / "课程资料").mkdir()
        existing = self.library / "课程资料" / "课程资料.txt"
        existing.write_text("existing file must survive", encoding="utf-8")
        original_hashes = {i.path: sha256(i.path) for i in items}
        results = archive_batch(items, self.library)
        self.assertTrue(all(ok for _, ok, _ in results))
        self.assertEqual(existing.read_text(encoding="utf-8"), "existing file must survive")
        self.assertEqual(len(list((self.library / "课程资料").glob("课程资料*.txt"))), 3)
        self.assertEqual(len(self.catalog.search()), 10)
        self.assertEqual(len(self.catalog.search("课程资料", "课程资料", scope='filename')), 2)
        self.assertEqual(len(self.catalog.search("课程资料", "课程资料")), 3)  # Also matches the DOCX body snapshot.
        self.assertEqual(len(self.catalog.search("%")), 0)
        self.assertEqual(len(self.catalog.search("未知", "其他")), 1)
        for row in self.catalog.search():
            self.assertEqual(sha256(Path(row["archive_path"])), original_hashes[Path(row["source_path"])])
        for path, original_hash in original_hashes.items():
            self.assertEqual(sha256(path), original_hash)
        self.assertIn("修改分类", [r["action"] for r in self.catalog.operations()])
        self.assertEqual(len(Catalog(self.library).search()), 10)

    def test_repeat_archive_and_missing_archive(self):
        item = self.scan()[0]
        _, first = archive_one(item, self.catalog)
        message, repeated = archive_one(item, self.catalog)
        self.assertIn("跳过", message)
        self.assertEqual(first, repeated)
        self.assertEqual(len(self.catalog.search()), 1)
        first.unlink()
        _, restored = archive_one(item, self.catalog)
        self.assertTrue(restored.exists())
        self.assertEqual(len(self.catalog.search()), 2)

    def test_changed_source_is_rejected(self):
        item = self.scan()[0]
        item.path.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "源文件已变化"):
            archive_one(item, self.catalog)
        self.assertEqual(len(self.catalog.search()), 0)

    def test_db_failure_removes_new_copy(self):
        item = self.scan()[0]
        with patch.object(self.catalog, "record_archive", side_effect=OSError("DB unavailable")):
            with self.assertRaisesRegex(OSError, "DB unavailable"):
                archive_one(item, self.catalog)
        self.assertEqual(list((self.library / item.category).iterdir()), [])
        self.assertTrue(item.path.exists())

    def test_batch_failure_does_not_block_other_files(self):
        items = self.scan()[:2]
        items[0].path.unlink()
        results = archive_batch(items, self.library)
        self.assertFalse(results[0][1])
        self.assertTrue(results[1][1])
        self.assertIn("归档失败", [r["action"] for r in self.catalog.operations()])

    def test_library_inside_source_is_excluded(self):
        nested = self.source / "归档库"
        nested.mkdir()
        (nested / "课程.txt").write_text("do not rescan", encoding="utf-8")
        items, _ = scan_folder(self.source, DEFAULT_RULES, nested)
        self.assertEqual(len(items), 10)
        with self.assertRaisesRegex(ValueError, "来源文件夹"):
            scan_folder(nested, DEFAULT_RULES, nested)

    def test_no_code_library_or_invalid_category(self):
        with self.assertRaises(ValueError):
            validate_library(PROJECT_ROOT / "documents")
        with self.assertRaises(ValueError):
            validate_library(PROJECT_ROOT.parent)
        item = self.scan()[0]
        item.category = "../../escape"
        with self.assertRaises(ValueError):
            archive_one(item, self.catalog)

    def test_rule_ties_threshold_english_boundary_and_configuration(self):
        self.assertEqual(classify("实验报告_课程.txt", "", DEFAULT_RULES)[0], "实验报告")
        self.assertEqual(classify("实验报告_研究文献.txt", "", DEFAULT_RULES)[0], "待整理")
        self.assertEqual(classify("random.txt", "doing", DEFAULT_RULES)[0], "待整理")
        self.assertEqual(classify("random.txt", "abstract", DEFAULT_RULES)[0], "待整理")
        rules = json.loads(json.dumps(DEFAULT_RULES))
        rules["keywords"]["课程资料"].append("自定义")
        self.assertEqual(classify("自定义.txt", "", validate_rules(rules))[0], "课程资料")
        rules["filename_weight"] = 0
        with self.assertRaises(ValueError):
            validate_rules(rules)

    def test_extraction_limits_and_password(self):
        from pypdf import PdfWriter
        path = self.source / "加密.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=100, height=100)
        writer.encrypt("secret")
        with path.open("wb") as handle:
            writer.write(handle)
        self.assertIn("密码", extract(path)["status"])
        path = self.source / "large.txt"
        path.write_text("课" * 100_001, encoding="utf-8")
        self.assertEqual(len(extract(path)["text"]), 100_000)
        self.assertIn("截断", extract(path)["status"])


if __name__ == "__main__":
    unittest.main()
