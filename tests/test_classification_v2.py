import copy
import tempfile
import unittest
from pathlib import Path

from document_assistant.extractor import extract
from document_assistant.rules import DEFAULT_RULES, LEGACY_KEYWORDS, classify, load_rules, save_rules, validate_rules
from document_assistant.service import PROJECT_ROOT, archive_batch, scan_files, sha256
from document_assistant.storage import Catalog
from tests.legacy_fixtures import make_doc


class ClassificationV2Tests(unittest.TestCase):
    def test_project_and_personal_filenames(self):
        cases = {
            'phase1-experiment-plan-v1-1.pdf': '项目资料',
            '舌下血管分割项目_逐项改进计划.doc': '项目资料',
            '分工.docx': '项目资料', '考核测试.docx': '课程资料',
            '示例姓名_项目组简历 (1).docx': '个人资料', '课程实验记录.docx': '实验报告',
            'CURRICULUM_VITAE.doc': '个人资料', '文献综述.pdf': '研究文献',
            '课程实验指导.pdf': '课程资料',
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(classify(name, '', DEFAULT_RULES)[0], expected)

    def test_generic_name_needs_real_evidence(self):
        self.assertEqual(classify('方案.docx', '', DEFAULT_RULES)[0], '待整理')
        self.assertEqual(classify('方案.docx', '项目实施方案\n任务分配与进度计划。', DEFAULT_RULES)[0], '项目资料')
        self.assertEqual(classify('附件.pdf', '个人简历\n教育经历与求职意向。', DEFAULT_RULES)[0], '个人资料')

    def test_references_do_not_turn_report_into_paper(self):
        category, reason = classify('VLAN实验报告.docx', '实验目的：验证网络。\n实验步骤与实验结果。\n摘要 abstract doi 参考文献 references journal', DEFAULT_RULES)
        self.assertEqual(category, '实验报告')
        self.assertIn('明确文件名优先', reason)

    def test_actual_type_conflict_stays_pending(self):
        self.assertEqual(classify('个人简历.doc', '项目实施方案\n项目计划与任务分配。', DEFAULT_RULES)[0], '待整理')
        self.assertEqual(classify('实验报告_研究文献.pdf', '', DEFAULT_RULES)[0], '待整理')

    def test_normalization_weak_evidence_and_threshold(self):
        self.assertEqual(classify('ＰＲＯＪＥＣＴ＿ＰＬＡＮ.doc', '', DEFAULT_RULES)[0], '项目资料')
        for body in ('abstract', 'doing', '12345'):
            self.assertEqual(classify('未知.txt', body, DEFAULT_RULES)[0], '待整理')
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['minimum_score'] = 100
        self.assertEqual(classify('简历.doc', '', rules)[0], '待整理')

    def test_old_config_upgrade_preserves_custom_lists_and_weights(self):
        old = {'filename_weight': 7, 'body_weight': 2, 'minimum_score': 3, 'keywords': copy.deepcopy(LEGACY_KEYWORDS)}
        old['keywords']['课程资料'].append('自定义教材术语')
        before = copy.deepcopy(old)
        upgraded = validate_rules(old)
        self.assertEqual(old, before)
        self.assertEqual(upgraded['keywords']['课程资料'], old['keywords']['课程资料'])
        self.assertEqual(upgraded['filename_weight'], 7)
        self.assertIn('项目资料', upgraded['keywords'])
        self.assertIn('实验记录', upgraded['keywords']['实验报告'])
        upgraded['keywords']['个人资料'] = []
        self.assertEqual(validate_rules(upgraded)['keywords']['个人资料'], [])


class LegacyDocTests(unittest.TestCase):
    def setUp(self):
        root = PROJECT_ROOT.parent / 'DocumentAssistant-local' / 'tmp'
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='doc-v2-', dir=root)
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_unicode_and_compressed_multiple_pieces(self):
        path = make_doc(self.root / '示例.doc', ('项目实施方案\r中文正文与😀。\r', b'experiment plan\r'))
        result = extract(path)
        self.assertTrue(result['status'].startswith('已提取'), result)
        self.assertIn('中文正文与😀', result['text'])
        self.assertIn('experiment plan', result['text'])

    def test_zero_table_and_limit(self):
        from document_assistant.legacy_doc import extract_doc
        path = make_doc(self.root / '零号表.doc', ('项目计划\r正文内容。\r',), table_one=False)
        self.assertIn('项目计划', extract(path)['text'])
        text, limited = extract_doc(path, limit=4)
        self.assertEqual(text, '项目计划')
        self.assertTrue(limited)

    def test_password_corruption_and_filename_fallback(self):
        encrypted = make_doc(self.root / '实验计划.doc', encrypted=True)
        self.assertIn('密码', extract(encrypted)['status'])
        broken = self.root / '坏文件.doc'
        broken.write_bytes(b'not a word file')
        items, warnings = scan_files([encrypted, broken], DEFAULT_RULES)
        self.assertEqual(warnings, [])
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0].category, '项目资料')
        self.assertIn('正文不可用', items[0].reason)
        self.assertIn('无法提取', items[1].status)

    def test_doc_copy_and_new_category_search(self):
        path = make_doc(self.root / '来源' / '改进计划.doc')
        digest = sha256(path)
        library = self.root / '库'
        items, warnings = scan_files([path], DEFAULT_RULES, library)
        self.assertEqual(warnings, [])
        self.assertTrue(items[0].body)
        self.assertEqual(items[0].category, '项目资料')
        self.assertEqual(Catalog(library).search(), [])
        result = archive_batch(items, library)
        self.assertTrue(result[0][1], result)
        rows = Catalog(library).search('改进计划', '项目资料')
        self.assertEqual(len(rows), 1)
        self.assertEqual(sha256(Path(rows[0]['archive_path'])), digest)
        self.assertEqual(sha256(path), digest)

    def test_rule_roundtrip(self):
        path = self.root / 'rules.json'
        save_rules(path, DEFAULT_RULES)
        self.assertEqual(load_rules(path), DEFAULT_RULES)

    def test_manual_choice_survives_rescan_until_file_changes(self):
        path = make_doc(self.root / '任务分配.doc')
        library = self.root / '库'
        item = scan_files([path], DEFAULT_RULES, library)[0][0]
        Catalog(library).change_category(item.doc_id, '个人资料')
        repeated = scan_files([path], DEFAULT_RULES, library)[0][0]
        self.assertEqual(repeated.suggested, '项目资料')
        self.assertEqual(repeated.category, '个人资料')
        self.assertIn('沿用你此前确认', repeated.reason)
        make_doc(path, ('项目计划\r文件内容已经改变，需要重新检查。\r',))
        changed = scan_files([path], DEFAULT_RULES, library)[0][0]
        self.assertEqual(changed.category, '项目资料')


if __name__ == '__main__':
    unittest.main()
