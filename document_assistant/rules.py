from __future__ import annotations

import copy
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path
from .document_metadata import validate_category

CATEGORIES = ('实验报告', '研究文献', '课程资料', '项目资料', '个人资料', '其他', '待整理')
LEGACY_KEYWORDS = {
    '实验报告': ['实验报告', '实验目的', '实验步骤', '实验结果', 'lab report'],
    '研究文献': ['论文', '文献', '摘要', '参考文献', 'abstract', 'doi', 'references'],
    '课程资料': ['课件', '课程', '讲义', '教材', '复习', 'lecture', 'syllabus'],
    '其他': ['说明书', '个人笔记', '备忘录', '使用指南'],
}
DEFAULT_RULES = {
    'schema_version': 2, 'filename_weight': 3, 'title_weight': 3, 'body_weight': 1,
    'minimum_score': 2, 'minimum_margin': 2,
    'keywords': {
        '实验报告': [*LEGACY_KEYWORDS['实验报告'], '实验记录', '实验总结', '实验分析', '实验结论', '实习报告', '课程实验报告', '实验数据', 'laboratory report'],
        '研究文献': [*LEGACY_KEYWORDS['研究文献'], '研究文献', '研究论文', '学位论文', '毕业论文', '文献综述', '期刊', '学报', 'research paper', 'literature review', 'journal', 'arxiv'],
        '课程资料': [*LEGACY_KEYWORDS['课程资料'], '课程资料', '学习资料', '教学大纲', '课堂笔记', '课程笔记', '实验指导', '实验教程', '习题', '试卷', '考试', '考核', '测验', '作业', 'lecture notes', 'course notes', 'textbook', 'exam', 'quiz'],
        '项目资料': ['项目', '项目计划', '项目方案', '实施方案', '研究计划', '实验计划', '改进计划', '进度计划', '开发计划', '项目分工', '分工', '任务分配', '任务书', '工作安排', '会议纪要', '需求文档', '需求分析', '设计方案', '技术路线', '开题报告', 'project plan', 'experiment plan', 'research proposal', 'work plan', 'project', 'proposal', 'roadmap'],
        '个人资料': ['简历', '个人简介', '自我介绍', '个人陈述', '求职', '报名表', '申请表', '证书', '成绩单', 'resume', 'curriculum vitae', 'personal statement', 'transcript'],
        '其他': LEGACY_KEYWORDS['其他'][:],
    },
}
V2_KEYWORDS = copy.deepcopy(DEFAULT_RULES['keywords'])
DEFAULT_RULES['schema_version'] = 3
# Specific compound types suppress their contained, broader type words across categories.
DEFAULT_RULES['keywords']['项目资料'] += ['毕业论文任务书', '论文任务书', '毕业论文开题报告',
    '论文开题报告', '文献阅读计划', '论文写作计划', '项目申请表', '项目申报书']
DEFAULT_RULES['keywords']['课程资料'] += ['实验报告评分标准', '实验报告写作指导',
    '实验报告模板', '课程设计指导', '课程设计任务书', '实验指导书', 'lab manual']
# Structural headings/topic words are supporting evidence, not specific document types.
WEAK_SIGNALS = {'摘要', '参考文献', 'abstract', 'references', 'doi', '课程', '项目', 'project',
                '实验目的', '实验步骤', '实验结果', '实验分析', '实验结论', '实验数据'}


def validate_rules(rules: dict) -> dict:
    """Upgrade unchanged stock lists; never overwrite edited or explicitly empty lists."""
    if not isinstance(rules, dict):
        raise ValueError('规则必须是 JSON 对象')
    result = copy.deepcopy(rules)
    version = result.get('schema_version', 1)
    if type(version) is not int or version not in (1, 2, 3):
        raise ValueError('不支持的规则版本，请使用 1、2 或 3')
    legacy = version == 1
    for field in ('title_weight', 'minimum_margin'):
        result.setdefault(field, DEFAULT_RULES[field])
    for field in ('filename_weight', 'title_weight', 'body_weight', 'minimum_score', 'minimum_margin'):
        if type(result.get(field)) is not int or not 1 <= result[field] <= 100:
            raise ValueError(f'{field} 必须是 1–100 的整数')
    keywords = result.get('keywords')
    if not isinstance(keywords, dict) or not set(LEGACY_KEYWORDS) <= set(keywords) or len(keywords)>49 or '待整理' in keywords:
        raise ValueError('关键词需要保留既有分类，且最多 49 个可匹配分类')
    for name in keywords:
        validate_category(name)
    if len({name.casefold() for name in keywords})!=len(keywords):
        raise ValueError('分类名称不能仅大小写不同')
    for category in CATEGORIES[:-1]:
        if category not in keywords:
            keywords[category] = DEFAULT_RULES['keywords'][category][:]
        elif legacy and category in LEGACY_KEYWORDS and keywords[category] == LEGACY_KEYWORDS[category]:
            keywords[category] = DEFAULT_RULES['keywords'][category][:]
        elif version < 3 and keywords[category] == V2_KEYWORDS[category]:
            keywords[category] = DEFAULT_RULES['keywords'][category][:]
        words = keywords[category]
        if not isinstance(words, list) or len(words) > 500:
            raise ValueError(f'{category} 的关键词必须是列表，最多 500 项')
        if any(not isinstance(w, str) or not normalize(w) or len(w) > 100 for w in words):
            raise ValueError('关键词必须是非空文本，最多 100 字')
    for category, words in keywords.items():
        if not isinstance(words,list) or len(words)>500 or any(not isinstance(w,str) or not normalize(w) or len(w)>100 for w in words):
            raise ValueError('每类关键词应为最多 500 个非空文本，每词最多 100 字')
    result['schema_version'] = 3
    return result


def categories_for(rules):
    names=validate_rules(rules)['keywords']
    return [*CATEGORIES[:-1],*(n for n in names if n not in CATEGORIES),'待整理']


def load_rules(path: Path) -> dict:
    return validate_rules(json.loads(path.read_text(encoding='utf-8')))


def save_rules(path: Path, rules: dict) -> None:
    rules = validate_rules(rules)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(rules, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


def normalize(text: str) -> str:
    text = unicodedata.normalize('NFKC', text).casefold()
    text = re.sub('[\u200b\u200c\u200d\ufeff\u00ad]', '', text)
    text = re.sub(r'(?<=[\u3400-\u9fff])\s+(?=[\u3400-\u9fff])', '', text)
    return re.sub(r'[\s_\-‐‑‒–—]+', ' ', text).strip()


def has_keyword(text: str, keyword: str) -> bool:
    text, keyword = normalize(text), normalize(keyword)
    return contains(text, keyword)


def contains(text: str, keyword: str) -> bool:
    return bool(keyword and keyword_pattern(keyword).search(text))


@lru_cache(maxsize=4096)
def keyword_pattern(keyword: str):
    # Apply ASCII boundaries to each edge, including mixed Chinese/English keywords.
    left = r'(?<![a-z0-9])' if keyword[:1].isascii() and keyword[:1].isalnum() else ''
    right = r'(?![a-z0-9])' if keyword[-1:].isascii() and keyword[-1:].isalnum() else ''
    return re.compile(left + re.escape(keyword) + right)


def matches(text, words):
    hits = []
    for word in sorted(set(normalize(w) for w in words), key=lambda w: (-len(w), w)):
        if contains(text, word) and not any(word in longer for longer in hits):
            hits.append(word)
    return hits


def field_matches(text: str, keywords: dict) -> dict:
    """Longest phrase wins at an overlapping position, also across categories.

    Independent occurrences survive; equal phrases configured in two categories
    remain ambiguous. Repetition never increases a keyword's score.
    """
    owners = {}
    for category, words in keywords.items():
        for word in words:
            owners.setdefault(normalize(word), set()).add(category)
    found = {c: [] for c in keywords}
    occupied = bytearray(len(text))
    for word in sorted(owners, key=lambda w: (-len(w), w)):
        accepted = False
        for match in keyword_pattern(word).finditer(text):
            start, end = match.span()
            if not any(occupied[start:end]):
                occupied[start:end] = b'\1' * (end - start)
                accepted = True
        if accepted:
            for category in owners[word]:
                found[category].append(word)
    return found


def heading(line: str) -> str:
    line = unicodedata.normalize('NFKC', line).strip()
    # PDF small capitals can become "I. I NTRODUCTION" in extracted text.
    if re.match(r'^[IVXLCDM]+\s*\.\s*', line):
        line = re.sub(r'^[IVXLCDM]+\s*\.\s*', '', line)
        line = re.sub(r'^([A-Z])\s+([A-Z]{2,})', r'\1\2', line)
    line = line.casefold()
    line = re.sub(r'^(?:\d+(?:\.\d+)*[.、)\s]+|[一二三四五六七八九十]+[、.)]\s*)', '', line)
    return normalize(line)


def document_sections(body: str, keywords: dict):
    lines = body[:100_000].splitlines()
    reference_start = next((i for i, line in enumerate(lines)
                            if re.fullmatch(r'(?:参考文献|references|bibliography)\s*[:：]?', heading(line))), None)
    if reference_start is not None:
        lines = lines[:reference_start]
    title, title_rows = '', set()
    for i, line in enumerate(lines[:12]):
        candidate = heading(line)
        if not candidate or candidate.isdecimal() or re.fullmatch(r'(?:第\s*)?\d+\s*页|page\s+\d+(?:\s+of\s+\d+)?', candidate):
            continue
        if re.fullmatch(r'\d{4}(?:年|[./ -])\s*\d{1,2}(?:月|[./ -])\s*\d{1,2}日?', candidate):
            continue
        if re.match(r'^(?:姓名|学号|作者|日期|学校|学院|专业)\s*[:：]', candidate):
            continue
        if len(candidate) < 40 and re.fullmatch(r'.+(?:大学|学院|university)', candidate):
            continue
        # A section heading is not the document's title. Do not hunt deeper for keywords.
        if re.match(r'^(?:摘要|abstract|实验目的|实验步骤|实验结果)(?:\s*[:：.]|$)', candidate):
            break
        if 2 <= len(candidate) <= 160:
            title, title_rows = candidate, {i}
            # Recover a phrase wrapped over two short English title lines.
            if i + 1 < len(lines) and re.search(r'[a-z]$', candidate):
                following = heading(lines[i + 1])
                joined = candidate + ' ' + following
                if following and len(joined) <= 160:
                    words = {normalize(w) for group in keywords.values() for w in group}
                    if any(contains(joined, w) and not contains(candidate, w) and not contains(following, w) for w in words):
                        title, title_rows = joined, {i, i + 1}
        break
    text = normalize('\n'.join(line for i, line in enumerate(lines) if i not in title_rows))
    return title, text, lines, reference_start is not None


def structure_evidence(lines, keywords):
    """Require complementary, line-anchored sections, not a bag of topic words."""
    headings = [heading(line) for line in lines]
    def has(pattern):
        return any(re.fullmatch(pattern + r'(?:\s*[:：. -].*)?', line) for line in headings)
    evidence = {c: [] for c in keywords}
    configured = {c: {normalize(w) for w in words} for c, words in keywords.items()}
    academic = [('摘要', r'摘要|abstract'), ('引言', r'引言|绪论|introduction'),
                ('方法', r'方法|材料与方法|研究方法|methods?|materials and methods|methodology'),
                ('结果/结论', r'结果|结论|结果与讨论|results|conclusions?|results and discussion')]
    paper = [label for label, pattern in academic if has('(?:' + pattern + ')')]
    if len(configured['研究文献'] & {'摘要', 'abstract', '参考文献', 'references', 'doi'}) >= 2:
        if '摘要' in paper and len(paper) >= 3:
            evidence['研究文献'] = paper
    lab = [('实验目的', r'实验目的'), ('实验步骤', r'实验步骤|实验过程'), ('实验结果', r'实验结果|实验结论')]
    report = [label for label, pattern in lab if has('(?:' + pattern + ')')]
    if len(configured['实验报告'] & {'实验目的', '实验步骤', '实验结果', '实验结论'}) >= 2 and len(report) >= 2:
        evidence['实验报告'] = report
    return evidence


def classify(filename: str, body: str, rules: dict) -> tuple[str, str]:
    rules = validate_rules(rules)
    keywords = rules['keywords']
    title, text, lines, excluded_references = document_sections(body, keywords)
    files = field_matches(normalize(Path(filename).stem), keywords)
    titles = field_matches(title, keywords)
    bodies = field_matches(text, keywords)
    structures = structure_evidence(lines, keywords)
    scores, eligible = {}, set()
    file_types, title_types = [], []
    for category in keywords:
        specific_file = [w for w in files[category] if w not in WEAK_SIGNALS]
        titles[category] = [w for w in titles[category] if w not in WEAK_SIGNALS]
        # A title hit cannot count again as body evidence, even when repeated later.
        bodies[category] = [w for w in bodies[category] if w not in titles[category]]
        strong_body = [w for w in bodies[category] if w not in WEAK_SIGNALS]
        if specific_file:
            file_types.append(category)
        if titles[category]:
            title_types.append(category)
        if specific_file or titles[category] or len(strong_body) >= 2 or structures[category]:
            eligible.add(category)
        scores[category] = (sum(rules['filename_weight'] + (2 if w not in WEAK_SIGNALS else 0) for w in files[category][:3])
                            + min(2, len(titles[category])) * rules['title_weight']
                            + min(6, len(bodies[category])) * rules['body_weight']
                            + (4 * rules['body_weight'] if structures[category] else 0))
    ranked = sorted(scores, key=lambda c: scores[c], reverse=True)
    summary = '；'.join(f'{c} {scores[c]}分' for c in ranked if scores[c]) or '未命中'
    suffix = '；已忽略参考文献列表中的关键词' if excluded_references else ''
    def pending(message):
        return '待整理', f'建议把握：不足。{message}。得分：{summary}{suffix}'
    if len(file_types) > 1 or len(title_types) > 1:
        return pending('出现多个明确文档类型，分类冲突，请人工确认')
    if file_types and title_types and file_types != title_types:
        return pending(f'文件名指向{file_types[0]}，正文标题指向{title_types[0]}，请人工确认')
    priority = ''
    if file_types:
        winner = file_types[0]
        priority = '明确文件名优先；'
    elif title_types:
        winner = title_types[0]
        priority = '正文标题类型优先；'
    else:
        candidates = [c for c in ranked if c in eligible]
        if not candidates:
            return pending('信息不足，只有零散或通用词，缺少明确类型或互相支持的正文结构')
        winner = candidates[0]
        runner = max((scores[c] for c in candidates[1:]), default=0)
        if scores[winner] - runner < rules['minimum_margin']:
            return pending(f'分类冲突，前两类有效证据差距不足 {rules["minimum_margin"]} 分，请人工确认')
    if scores[winner] < rules['minimum_score']:
        return pending(f'未达到最低分 {rules["minimum_score"]}')
    evidence = ([f'文件名命中“{w}”' for w in files[winner][:3]]
                + [f'正文标题命中“{w}”' for w in titles[winner][:2]]
                + [f'正文命中“{w}”' for w in bodies[winner][:4]])
    if structures[winner]:
        evidence.append('正文结构相互支持：' + '、'.join(structures[winner]))
    strength = '较强' if (file_types and title_types) or structures[winner] else '一般'
    return winner, f'建议把握：{strength}（规则证据，非概率）。{priority}' + '；'.join(evidence) + f'。得分：{summary}{suffix}'
