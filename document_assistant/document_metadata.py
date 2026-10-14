"""Local title suggestions, portable category names and review priority."""
import re
import unicodedata
from pathlib import Path

PARSER_VERSION = 'metadata-1'
READING_STATES = ('未读', '阅读中', '已读', '重点参考')


def validate_category(name):
    if not isinstance(name, str) or not name or len(name)>60 or name != name.strip():
        raise ValueError('分类名称应为 1–60 字，且首尾不能是空格')
    if name in ('.','..') or name.endswith('.') or re.search(r'[<>:"/\\|?*\x00-\x1f]',name):
        raise ValueError('分类名称不能包含路径或 Windows 文件名禁用字符')
    base = name.split('.')[0].casefold()
    if base in {'con','prn','aux','nul',*(f'com{i}' for i in range(10)),*(f'lpt{i}' for i in range(10)),'.documentassistant','.git','.venv','__pycache__'} or name.startswith('.'):
        raise ValueError('这个名称是保留目录名，请换一个分类名称')
    return name


def clean_title(text):
    text = re.sub(r'\s+',' ',unicodedata.normalize('NFKC',str(text or ''))).strip()
    if not 5<=len(text)<=250 or re.match(r'^(?:untitled|document\d*|microsoft word|word document|default title|arxiv:|https?://)',text,re.I):
        return ''
    if re.fullmatch(r'[\d\W]+',text):
        return ''
    return text


def title_suggestion(filename, body, metadata=''):
    title=clean_title(metadata)
    if title and title.casefold()!=Path(filename).stem.casefold():
        return title,'文档元信息（可修改）'
    candidates=[]
    for raw in body.splitlines()[:18]:
        line=re.sub(r'\s+',' ',raw).strip()
        if not line:
            continue
        if re.match(r'^(?:abstract|摘要|index terms|keywords|关键词|第[一二三四五六七八九十\d]+章|\d+(?:\.\d+)*[.、 ]|[IVX]+\.|姓名|学号|作者|实验目的|实验步骤)',line,re.I):
            break
        if re.search(r'IEEE TRANSACTIONS|\bVOL\.|\bDOI\b|https?://|arxiv|copyright|©|ISSN|\bworkshop\b|\bconference\b|\bproceedings\b',line,re.I) or re.fullmatch(r'[\d\W]+',line):
            continue
        if re.match(r'^(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d',line,re.I):
            continue
        if len(line)>160 or len(line)<4:
            continue
        if candidates and (re.search(r'[,，;；]|\b(?:university|department|school|author)\b',line,re.I) or re.search(r'\d{4}',line)):
            break
        candidates.append(line)
        if len(candidates)>=3 or re.search(r'[\u3400-\u9fff]',line):
            break
    # Descriptive Chinese filenames are safer than guessing from a chapter/task list.
    if re.search(r'[\u3400-\u9fff]',Path(filename).stem) or len(re.findall(r'[A-Za-z]{3,}',Path(filename).stem))>=3:
        return '', ''
    title=clean_title(' '.join(candidates))
    return (title,'正文开头（建议，可修改）') if title else ('','')


def attention_rank(item):
    if not item.status.startswith('已提取'):
        return 3
    if 'category' in item.manual_fields.split(',') or item.category!=item.suggested and item.category!='待整理':
        return 0
    if item.category=='待整理' or '冲突' in item.reason or '建议把握：不足' in item.reason:
        return 2
    return 1 if '建议把握：一般' in item.reason else 0


def category_rule_match(path, rules):
    matches=[]
    for r in rules:
        if r['source']=='filename' and r['pattern'].casefold() in path.name.casefold():
            matches.append((2,len(r['pattern']),r))
        elif r['source']=='folder' and path.parent.resolve().is_relative_to(Path(r['pattern']).resolve()):
            matches.append((1,len(Path(r['pattern']).parts),r))
    if not matches:
        return None
    rank=max((a,b) for a,b,_ in matches)
    top=[r for a,b,r in matches if (a,b)==rank]
    if len({r['category'] for r in top})>1:
        return {'category':'待整理','reason':'已保存的分类规则冲突，请人工确认'}
    r=top[0]
    return {'category':r['category'],'reason':f"沿用你保存的分类规则：{'文件名包含' if r['source']=='filename' else '目录及子目录'}“{r['pattern']}” → {r['category']}"}


def classification_suggestion(path,body,general_rules,saved_rules):
    from .rules import classify
    remembered=category_rule_match(path,saved_rules)
    return (remembered['category'],remembered['reason']) if remembered else classify(path.name,body,general_rules)


def preview_category_rule(item, proposed, existing, general_rules):
    """Use the same saved-rule precedence and explicit manual choice as scan_files."""
    from .rules import classify
    rule=dict(proposed)
    rule['pattern']=rule['pattern'].strip()
    if rule['source']=='folder':rule['pattern']=str(Path(rule['pattern']).resolve())
    if not category_rule_match(item.path,[rule]):return None
    combined=[r for r in existing if (r['source'],r['pattern']) != (rule['source'],rule['pattern'])]+[rule]
    category,reason=classification_suggestion(item.path,item.body,general_rules,combined)
    if 'category' in item.manual_fields.split(',') or item.category!=item.suggested:
        return item.category,'已人工确认；后续读取内容不变时保留当前分类'
    return category,reason
