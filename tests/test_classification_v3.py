import copy
import unittest

from document_assistant.rules import (DEFAULT_RULES, V2_KEYWORDS, classify,
    field_matches, has_keyword, normalize, validate_rules)
from tests.classification_cases import CASES


class ClassificationV3Tests(unittest.TestCase):
    def test_labelled_synthetic_regressions(self):
        for label, name, body, expected in CASES:
            with self.subTest(case=label):
                actual, reason = classify(name, body, DEFAULT_RULES)
                self.assertEqual(actual, expected, reason)

    def test_stock_v2_upgrade_preserves_custom_and_disabled_categories(self):
        old = copy.deepcopy(DEFAULT_RULES)
        old['schema_version'] = 2
        old['keywords'] = copy.deepcopy(V2_KEYWORDS)
        old['keywords']['个人资料'] = []
        old['keywords']['课程资料'].append('我的课堂材料')
        old['filename_weight'] = 8
        before = copy.deepcopy(old)
        new = validate_rules(old)
        self.assertEqual(old, before)
        self.assertEqual(new['schema_version'], 3)
        self.assertEqual(new['filename_weight'], 8)
        self.assertEqual(new['keywords']['个人资料'], [])
        self.assertEqual(new['keywords']['课程资料'], old['keywords']['课程资料'])
        self.assertIn('论文任务书', new['keywords']['项目资料'])
        self.assertEqual(validate_rules(new), new)

    def test_current_config_never_readds_removed_stock_words(self):
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['keywords'] = copy.deepcopy(V2_KEYWORDS)
        self.assertEqual(validate_rules(rules), rules)

    def test_disabled_categories_disable_structural_fallback(self):
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['keywords']['研究文献'] = []
        body = 'A new method\nAbstract\nA method.\nIntroduction\nPrior work.\nMethods\nProcess.\nResults\nDone.'
        self.assertEqual(classify('paper.pdf', body, rules)[0], '待整理')
        rules['keywords']['实验报告'] = []
        self.assertEqual(classify('实验报告.docx', '实验目的：测试\n实验步骤：运行\n实验结果：通过', rules)[0], '待整理')

    def test_custom_phrase_is_literal_and_equal_phrase_conflicts(self):
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['keywords']['课程资料'] += ['C++练习', '自定义材料']
        rules['keywords']['项目资料'] += ['自定义材料']
        self.assertEqual(classify('C++练习.txt', '', rules)[0], '课程资料')
        self.assertEqual(classify('自定义材料.txt', '', rules)[0], '待整理')
        self.assertFalse(has_keyword('macrolecture', 'lecture'))
        self.assertFalse(has_keyword('scriptC++练习', 'C++练习'))
        self.assertFalse(has_keyword('doing', 'doi'))

    def test_cross_category_nested_and_independent_occurrences(self):
        found = field_matches(normalize('毕业论文任务书'), DEFAULT_RULES['keywords'])
        self.assertEqual(found['研究文献'], [])
        self.assertEqual(found['项目资料'], ['毕业论文任务书'])
        found = field_matches(normalize('毕业论文任务书；另附研究论文'), DEFAULT_RULES['keywords'])
        self.assertIn('研究论文', found['研究文献'])
        self.assertEqual(classify('毕业论文任务书_研究论文.docx', '', DEFAULT_RULES)[0], '待整理')

    def test_repetition_and_title_double_count_do_not_inflate_evidence(self):
        once = classify('附件.docx', '个人简历\n普通内容', DEFAULT_RULES)
        repeated = classify('附件.docx', '个人简历\n' * 500, DEFAULT_RULES)
        self.assertEqual(once, repeated)
        self.assertNotIn('正文命中', once[1])
        body = '普通记录\n请提交简历。\n'
        self.assertEqual(classify('附件.docx', body * 500, DEFAULT_RULES)[0], '待整理')

    def test_reference_tail_does_not_affect_category_or_score(self):
        body = '匿名标题\n实验目的：验证\n实验步骤：执行\n实验结果：完成'
        before = classify('附件.txt', body, DEFAULT_RULES)
        after = classify('附件.txt', body + '\n参考文献\n研究论文 journal 个人简历 项目计划', DEFAULT_RULES)
        self.assertEqual(after[0], before[0])
        self.assertEqual(after[1].split('；已忽略')[0], before[1])
        self.assertIn('已忽略参考文献', after[1])

    def test_body_limit_applies_to_title_and_structure_too(self):
        body = ('普通内容' * 25000) + '\n个人简历\nAbstract\nIntroduction\nMethods'
        self.assertEqual(classify('附件.txt', body, DEFAULT_RULES)[0], '待整理')

    def test_thresholds_and_competing_structures(self):
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['minimum_score'] = 100
        self.assertEqual(classify('附件.txt', '个人简历', rules)[0], '待整理')
        body = '附件内容\n实验目的：验证\n实验步骤：执行\nAbstract\nIntroduction\nMethods'
        self.assertEqual(classify('附件.txt', body, DEFAULT_RULES)[0], '待整理')
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['minimum_margin'] = 100
        self.assertEqual(classify('附件.txt', '附件内容\n实验目的：验证\n实验步骤：执行', rules)[0], '待整理')

    def test_invalid_rules_fail_without_mutating_inputs(self):
        for version in (True, 4, '3'):
            rules = copy.deepcopy(DEFAULT_RULES)
            rules['schema_version'] = version
            with self.assertRaises(ValueError):
                validate_rules(rules)
        rules = copy.deepcopy(DEFAULT_RULES)
        rules['keywords']['其他'] = ['\u200b']
        with self.assertRaises(ValueError):
            validate_rules(rules)


if __name__ == '__main__':
    unittest.main()
