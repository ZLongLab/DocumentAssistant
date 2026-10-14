from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .rules import CATEGORIES, classify, categories_for
from .document_metadata import title_suggestion, category_rule_match, classification_suggestion
from .storage import Catalog
from .paths import comparison_path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {".pdf", ".docx", ".doc", ".txt"}


@dataclass
class ScanItem:
    path: Path
    size: int
    mtime_ns: int
    body: str
    status: str
    suggested: str
    category: str
    reason: str
    doc_id: int | None = None
    course: str = ''
    project: str = ''
    tags: str = ''
    content_hash: str = ''
    revision: int = 0
    manual_fields: str = ''
    selected: bool = True
    display_title: str = ''
    title_source: str = ''


def within(path: Path, parent: Path) -> bool:
    return comparison_path(path).is_relative_to(comparison_path(parent))


def validate_library(path: Path):
    if within(path, PROJECT_ROOT) or within(PROJECT_ROOT, path):
        raise ValueError("文档库必须放在代码目录之外，例如 D:\\DocumentLibrary")
    if path.exists() and not path.is_dir():
        raise ValueError("文档库路径不是文件夹")


def extract_isolated(path: Path) -> dict:
    try:
        result = subprocess.run([sys.executable, "-m", "document_assistant.extractor", str(path)],
                                cwd=PROJECT_ROOT, capture_output=True, text=True, encoding="utf-8",
                                timeout=25, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            return {"text": "", "status": "无法提取：解析进程异常退出"}
        return json.loads(result.stdout)
    except subprocess.TimeoutExpired:
        return {"text": "", "status": "未提取：超过 25 秒，已跳过正文"}
    except Exception as exc:
        return {"text": "", "status": f"无法提取：{str(exc)[:180]}"}


def scan_folder(source: Path, rules: dict, library: Path | None = None,
                progress=lambda *_: None, cancelled=lambda: False, organization_rules=None):
    source = source.resolve()
    if not source.is_dir():
        raise ValueError("来源文件夹不存在")
    if library and within(source, library):
        raise ValueError("来源文件夹不能是文档库或文档库的子文件夹")
    paths, warnings = [], []
    def on_error(error):
        warnings.append(f"目录无法访问：{error.filename}：{error.strerror}")
    for root, dirs, files in os.walk(source, followlinks=False, onerror=on_error):
        if cancelled():
            return [], ["扫描已取消"]
        dirs[:] = [d for d in dirs if d not in {".git", ".venv", "__pycache__", ".documentassistant"}
                   and not (Path(root) / d).is_symlink()
                   and not (library and within(Path(root) / d, library))]
        for name in files:
            path = Path(root) / name
            if path.suffix.lower() in EXTENSIONS and not name.startswith("~$") and not path.is_symlink():
                paths.append(path)
        progress(0, 0, f"正在发现文件：已找到 {len(paths)} 个")
    return _scan_paths(sorted(paths), rules, library, progress, cancelled, warnings, organization_rules)


def scan_files(paths, rules: dict, library: Path | None = None,
               progress=lambda *_: None, cancelled=lambda: False, organization_rules=None, refresh_body=False):
    """Read only explicitly supplied files; never scan their containing directories."""
    accepted, seen, warnings = [], set(), []
    for supplied in paths:
        path = Path(supplied).absolute()
        if path.is_symlink():
            warnings.append(f"已跳过链接：{path.name}")
            continue
        path = path.resolve()
        key = str(path).casefold()
        if key in seen:
            continue
        seen.add(key)
        if not path.is_file():
            warnings.append(f"已跳过：{path.name} 不是可访问的文件；文件夹请使用“扫描文件夹”")
        elif path.suffix.lower() not in EXTENSIONS or path.name.startswith("~$"):
            warnings.append(f"已跳过不支持的文件：{path.name}（支持 PDF、DOCX、DOC、TXT）")
        elif library and within(path, library):
            warnings.append(f"已在文档库内，无需再次添加：{path.name}")
        else:
            accepted.append(path)
    return _scan_paths(accepted, rules, library, progress, cancelled, warnings, organization_rules, refresh_body)


def _scan_paths(paths, rules, library, progress, cancelled, warnings, organization_rules=None, refresh_body=False):
    catalog = Catalog(library) if library else None
    if catalog:
        import copy
        rules=copy.deepcopy(rules)
        rules['keywords'].update(catalog.category_keywords())
        catalog.register_categories(categories_for(rules))
        definitions=catalog.category_keywords()
        for name in rules['keywords']:
            if name not in CATEGORIES and name not in definitions:
                catalog.save_category_keywords(name,rules['keywords'][name])
    saved_rules = catalog.category_rules() if catalog else []
    items = []
    for index, path in enumerate(paths, 1):
        if cancelled():
            warnings.append("扫描已取消，已完成的结果保留")
            break
        progress(index - 1, len(paths), f"提取 {path.name}")
        try:
            before = path.stat()
            digest_before = sha256(path,cancelled)
            cached = catalog.cached_extraction(path,digest_before) if catalog and not refresh_body else None
            extracted = {'text':cached['body'],'status':cached['extraction_status'],'display_title':cached['display_title'],'title_source':cached['title_source']} if cached else extract_isolated(path)
            digest_after = sha256(path,cancelled)
            after = path.stat()
            if digest_before != digest_after or (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                extracted = {"text": "", "status": "文件在扫描时发生变化，请重新扫描"}
            category, reason = classification_suggestion(path,extracted["text"],rules,saved_rules)
            if not extracted['text']:
                reason += f'；正文不可用，仅依据文件名，请人工确认。{extracted["status"]}'
            item = ScanItem(path.resolve(), before.st_size, before.st_mtime_ns,
                            extracted["text"], extracted["status"], category, category, reason)
            item.content_hash = digest_after
            item.display_title, item.title_source = (extracted.get('display_title',''), extracted.get('title_source','')) if 'display_title' in extracted else title_suggestion(path.name,item.body)
            from .organization import suggest_labels
            suggestions, evidence = suggest_labels(item.path, item.body, organization_rules)
            for key, value in suggestions.items():
                setattr(item, key, value)
            if evidence:
                item.reason += '；课程/项目/标签建议：' + evidence
            if catalog:
                item.manual_fields = catalog.document_metadata(item.path)['manual_fields']
                for key, value in catalog.previous_labels(item.path).items():
                    if key in item.manual_fields.split(','):
                        setattr(item, key, value)
                previous = catalog.confirmed_category(item.path,item.content_hash)
                if previous in catalog.category_names():
                    item.category = previous
                    item.reason += f'；沿用你此前确认的分类：{previous}（同一路径、内容哈希未变化）。'
                item.doc_id = catalog.save_scan(item)
            items.append(item)
        except OSError as exc:
            warnings.append(f"文件无法访问：{path}：{exc}")
        progress(index, len(paths), path.name)
    return items, warnings


def sha256(path: Path, cancelled=lambda: False) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            if cancelled():
                raise InterruptedError('已停止当前文件处理')
            digest.update(chunk)
    return digest.hexdigest()


def archive_one(item: ScanItem, catalog: Catalog, cancelled=lambda: False, duplicate_policy='keep'):
    from .archive import archive_one as durable_archive
    return durable_archive(item, catalog, cancelled, duplicate_policy)


def archive_batch(items, library, progress=lambda *_: None, cancelled=lambda: False, duplicate_policy='keep'):
    import uuid
    validate_library(library)
    catalog = Catalog(library)
    results = []
    batch_id = uuid.uuid4().hex
    for index, item in enumerate(items, 1):
        if cancelled():
            break
        progress(index - 1, len(items), f"复制 {item.path.name}")
        try:
            item._batch_id = batch_id
            message, path = archive_one(item, catalog, cancelled, duplicate_policy)
            results.append((item, True, f"{message}：{path}"))
        except Exception as exc:
            message = f"归档失败：{item.path.name}：{exc}"
            try:
                catalog.log(item.doc_id, "归档失败", message)
            except Exception as log_exc:
                message += f"；操作记录写入失败：{log_exc}"
            results.append((item, False, message))
        progress(index, len(items), item.path.name)
    return results
