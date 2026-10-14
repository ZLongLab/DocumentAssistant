"""Offline, explainable label suggestions. Suggestions never replace confirmed fields."""
import copy
import re
from pathlib import Path

DEFAULT_LABEL_RULES = [
    {'field': 'course', 'value': '计算机网络', 'keywords': ['计算机网络', 'computer network', 'mininet', 'vlan', 'ospf'], 'source': 'any'},
    {'field': 'course', 'value': '操作系统', 'keywords': ['操作系统', 'operating system'], 'source': 'any'},
    {'field': 'course', 'value': '计算机组成原理', 'keywords': ['计算机组成原理', '计算机组成'], 'source': 'any'},
    {'field': 'course', 'value': '人工智能', 'keywords': ['人工智能', 'artificial intelligence'], 'source': 'path'},
    {'field': 'tags', 'value': 'VLAN', 'keywords': ['vlan'], 'source': 'any'},
    {'field': 'tags', 'value': 'Docker', 'keywords': ['docker'], 'source': 'any'},
    {'field': 'tags', 'value': 'Mininet', 'keywords': ['mininet'], 'source': 'any'},
]


def label_values(text):
    return list(dict.fromkeys(part.strip() for part in re.split(r'[,，;；\n]+', text) if part.strip()))


def query_terms(query):
    """Unquoted terms mean AND; straight/fullwidth quotes keep a phrase together."""
    query = query.replace('“', '"').replace('”', '"')
    return [a or b for a, b in re.findall(r'"([^"\n]+)"|([^\s"]+)', query)]


def validate_label_rules(rules):
    if not isinstance(rules, list) or len(rules) > 100:
        raise ValueError('最多配置 100 条规则')
    for rule in rules:
        if not isinstance(rule, dict) or set(rule) != {'field', 'value', 'keywords', 'source'}:
            raise ValueError('每条规则需要 field、value、keywords、source')
        if rule['field'] not in ('course', 'project', 'tags') or rule['source'] not in ('path', 'filename', 'body', 'any', 'folder'):
            raise ValueError('字段或匹配来源无效')
        if not isinstance(rule['value'], str) or not rule['value'].strip() or len(rule['value']) > 80:
            raise ValueError('建议值应为 1–80 字，且不能为空')
        keywords = rule['keywords']
        if not isinstance(keywords, list) or not keywords or len(keywords) > 30 or any(
            not isinstance(k, str) or not k.strip() or len(k) > (4000 if rule['source']=='folder' else 100) for k in keywords
        ):
            raise ValueError('每条规则需要 1–30 个非空关键词')
        if rule['source']=='folder' and (len(keywords)!=1 or not Path(keywords[0]).is_absolute()):
            raise ValueError('目录规则需要一个完整目录路径')
    return copy.deepcopy(rules)


def suggest_labels(path, body, rules=None):
    rules = validate_label_rules(DEFAULT_LABEL_RULES if rules is None else rules)
    sources = {'path': str(path.parent), 'filename': path.name, 'body': body[:100_000]}
    names = {'path': '来源目录', 'filename': '文件名', 'body': '正文'}
    hits = {key: {} for key in ('course', 'project', 'tags')}
    ranks = {key: -1 for key in hits}
    for rule in rules:
        if rule['source']=='folder':
            folder = Path(rule['keywords'][0]).resolve()
            if not path.parent.resolve().is_relative_to(folder):
                continue
            rank = len(folder.parts)
            field = rule['field']
            if rank > ranks[field]:
                hits[field].clear()
                ranks[field] = rank
            if rank == ranks[field]:
                hits[field][rule['value'].strip()] = f'来源目录位于“{folder}”'
            continue
        if ranks[rule['field']] >= 0:
            continue
        for source in sources if rule['source'] == 'any' else (rule['source'],):
            text = sources[source].casefold()
            keyword = next((k for k in rule['keywords'] if k.strip().casefold() in text), None)
            if keyword:
                hits[rule['field']].setdefault(rule['value'].strip(), f'{names[source]}包含“{keyword}”')
                break
    values, explanations = {}, []
    for field, found in hits.items():
        if field in ('course', 'project') and len(found) > 1:
            explanations.append(('课程' if field == 'course' else '项目') + '存在多个匹配，请人工选择：' + '、'.join(found))
        else:
            values[field] = ', '.join(found)
            explanations.extend(f'{value}：{evidence}' for value, evidence in found.items())
    return values, '；'.join(explanations)
