"""Durable copy journal and recoverable undo; never modify source documents."""
import json
import os
import uuid
from pathlib import Path

from .rules import CATEGORIES
from .service import ScanItem, sha256, validate_library, within
from .paths import filesystem_path


def identity(path):
    info = filesystem_path(path).stat()
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns]


def item_metadata(item):
    return {key: str(item.path) if key == 'path' else getattr(item,key)
            for key in ('path','size','mtime_ns','body','status','suggested','category','reason','doc_id','course','project','tags','revision','display_title','title_source')}


def from_metadata(data):
    payload = {key:value for key,value in data.items() if key in ScanItem.__dataclass_fields__}
    payload['path'] = Path(payload['path'])
    return ScanItem(**payload)


def archive_one(item, catalog, cancelled=lambda: False, duplicate_policy='keep'):
    if item.category not in catalog.category_names():
        raise ValueError('无效分类')
    if duplicate_policy not in ('keep','skip','link'):
        raise ValueError('无效重复处理方式')
    validate_library(catalog.library)
    if within(item.path,catalog.library):
        raise ValueError('不能把文档库中的文件再次归档')
    before = filesystem_path(item.path).stat()
    if (before.st_size,before.st_mtime_ns) != (item.size,item.mtime_ns):
        raise ValueError('源文件已变化，请重新读取后确认')
    digest = sha256(item.path,cancelled)
    if item.content_hash and digest != item.content_hash:
        raise ValueError('源文件内容已变化，请重新读取后确认')
    if item.doc_id is None:
        item.doc_id = catalog.save_scan(item)
    rows = catalog.existing_archives(item.doc_id,item.category,digest)
    for row in rows:
        old = Path(row['archive_path'])
        if filesystem_path(old).is_file() and sha256(old,cancelled) == digest:
            catalog.associate_archive(item,row['id'])
            catalog.log(item.doc_id,'跳过重复归档',str(old))
            return '已归档，跳过重复',old
    if duplicate_policy in ('skip','link'):
        for row in catalog.content_duplicates(digest):
            old = Path(row['archive_path'])
            if filesystem_path(old).is_file() and sha256(old,cancelled) == digest:
                catalog.associate_archive(item,row['id'],merge=duplicate_policy=='link')
                return ('内容相同，已关联已有文档' if duplicate_policy=='link' else '内容相同，已跳过'),old
    folder = catalog.safe_path(item.category)
    filesystem_path(folder).mkdir(parents=True,exist_ok=True)
    reserved = catalog.reserved_paths()
    task_id = uuid.uuid4().hex
    temporary = catalog.safe_path(str(Path('.documentassistant')/'pending'/f'{task_id}.part'))
    filesystem_path(temporary.parent).mkdir(parents=True,exist_ok=True)
    reservation = None
    target = None
    task_active = False
    try:
        for number in range(100_000):
            name = item.path.name if not number else f'{item.path.stem} ({number}){item.path.suffix}'
            candidate = folder/name
            if str(candidate).casefold() in reserved:
                continue
            metadata = item_metadata(item)
            metadata['batch_id'] = getattr(item,'_batch_id',uuid.uuid4().hex)
            catalog.create_task({'id':task_id,'target_relative':str(candidate.relative_to(catalog.library)),
                'temp_relative':str(temporary.relative_to(catalog.library)),'document_id':item.doc_id,'digest':digest,'metadata':metadata})
            task_active = True
            try:
                with filesystem_path(candidate).open('xb'):
                    pass
            except FileExistsError:
                catalog.delete_task(task_id)
                task_active = False
                continue
            target = candidate
            reservation = identity(target)
            catalog.reserve_task(task_id,reservation)
            break
        if target is None:
            raise ValueError('同名文件过多，无法分配新文件名')
        with filesystem_path(temporary).open('xb') as destination, filesystem_path(item.path).open('rb') as original:
            for chunk in iter(lambda: original.read(1024*1024),b''):
                if cancelled():
                    raise InterruptedError('复制已停止，原文件保留')
                destination.write(chunk)
            destination.flush()
            os.fsync(destination.fileno())
        after = filesystem_path(item.path).stat()
        if sha256(temporary,cancelled) != digest or (after.st_size,after.st_mtime_ns) != (before.st_size,before.st_mtime_ns):
            raise ValueError('复制期间源文件变化或校验失败，请重新扫描')
        if identity(target) != reservation:
            raise ValueError('目标文件已被其他程序修改，已保留该文件')
        os.replace(filesystem_path(temporary),filesystem_path(target))  # Only our checked exclusive reservation.
        item._archive_task_id = task_id
        item._batch_id = metadata['batch_id']
        catalog.record_archive(item,target,digest)
        return '归档成功',target
    except Exception:
        # Do not remove a committed archive, or a target changed by another program.
        recorded = any(Path(row['archive_path']) == target for row in catalog.content_duplicates(digest)) if target else False
        safe_target = target and filesystem_path(target).is_file() and (identity(target) == reservation or sha256(target) == digest)
        if safe_target and not recorded:
            filesystem_path(target).unlink()
        if filesystem_path(temporary).exists():
            filesystem_path(temporary).unlink()
        if task_active and (not target or not filesystem_path(target).exists() or recorded):
            catalog.delete_task(task_id)
        raise


def recover_pending(catalog, progress=lambda *_:None, cancelled=lambda:False):
    tasks = catalog.pending_tasks()
    messages = []
    for index, task in enumerate(tasks,1):
        if cancelled():
            break
        progress(index-1,len(tasks),'检查未完成归档')
        try:
            target = catalog.safe_path(task['target_relative'])
            temporary = catalog.safe_path(task['temp_relative'])
            metadata = json.loads(task['metadata'])
            digest = task['digest']
            already = any(Path(r['archive_path']) == target for r in catalog.content_duplicates(digest))
            if already:
                catalog.delete_task(task['id'])
                messages.append('已登记，清理任务：'+target.name)
                continue
            ready = filesystem_path(target).is_file() and sha256(target,cancelled) == digest
            reserved = json.loads(task['reservation'] or 'null')
            if not ready and filesystem_path(temporary).is_file() and sha256(temporary,cancelled) == digest:
                if not filesystem_path(target).exists():
                    # Rename is exclusive on Windows; never replace somebody else's file.
                    filesystem_path(temporary).rename(filesystem_path(target))
                elif reserved and identity(target) == reserved:
                    os.replace(filesystem_path(temporary),filesystem_path(target))
                else:
                    raise ValueError('目标已被修改，保留临时副本待检查')
                ready = True
            if ready:
                item = from_metadata(metadata)
                item._archive_task_id = task['id']
                item._batch_id = metadata.get('batch_id','')
                catalog.record_archive(item,target,digest)
                messages.append('恢复归档：'+target.name)
            else:
                # Keep incomplete bytes for inspection, remove only our untouched empty reservation.
                if reserved and filesystem_path(target).exists() and identity(target) == reserved:
                    filesystem_path(target).unlink()
                if not filesystem_path(target).exists():
                    catalog.delete_task(task['id'])
                    messages.append('未完成副本已隔离，原文件保留，可重新导入：'+target.name)
                else:
                    messages.append('目标状态有变化，保留任务待检查：'+target.name)
        except Exception as exc:
            messages.append(f'恢复未完成：{exc}')
        progress(index,len(tasks),'检查未完成归档')
    for task in catalog.pending_undos():
        if cancelled():
            break
        try:
            target = catalog.safe_path(task['target_relative'])
            trash = catalog.safe_path(task['trash_relative'])
            row = json.loads(task['metadata'])
            if not filesystem_path(target).exists() and filesystem_path(trash).is_file() and sha256(trash,cancelled) == row['sha256']:
                catalog.finish_undo(task['id'])
                messages.append('恢复撤销记录：'+row['filename'])
            elif not filesystem_path(trash).exists() and filesystem_path(target).is_file() and sha256(target,cancelled) == row['sha256']:
                catalog.cancel_unstarted_undo(task['id'])
                messages.append('撤销尚未移动副本，已取消中断任务：'+row['filename'])
            else:
                messages.append('撤销任务需检查，所有副本保留：'+row['filename'])
        except Exception as exc:
            messages.append('撤销恢复未完成：'+str(exc))
    from .recovery import recover_restores
    messages.extend(recover_restores(catalog, cancelled))
    return messages


def undo_batch(catalog, rows, progress=lambda *_:None, cancelled=lambda:False):
    catalog.backup('before-undo')
    messages = []
    for index, row in enumerate(rows,1):
        if cancelled():
            break
        progress(index-1,len(rows),'撤销 '+row['filename'])
        try:
            target = catalog.safe_path(row['relative_path'])
            if not filesystem_path(target).is_file() or sha256(target,cancelled) != row['sha256']:
                messages.append('已变化或不存在，保留记录：'+row['filename'])
                continue
            relative = str(Path('.documentassistant')/'undo'/uuid.uuid4().hex/target.name)
            trash = catalog.safe_path(relative)
            filesystem_path(trash.parent).mkdir(parents=True,exist_ok=True)
            task_id = catalog.prepare_undo(row,relative)
            filesystem_path(target).rename(filesystem_path(trash))
            catalog.finish_undo(task_id)
            messages.append('已撤销，副本保留在恢复区：'+row['filename'])
        except Exception as exc:
            messages.append('撤销未完成：'+str(exc))
        progress(index,len(rows),row['filename'])
    return messages


def index_archives(catalog, progress=lambda *_:None, cancelled=lambda:False):
    from .service import extract_isolated
    rows = catalog.search()
    messages = []
    for index, row in enumerate(rows,1):
        if cancelled():
            break
        progress(index-1,len(rows),'索引 '+row['filename'])
        path = Path(row['archive_path'])
        try:
            if not filesystem_path(path).is_file() or sha256(path,cancelled) != row['sha256']:
                messages.append('文件已变化或不存在，保留原索引：'+row['filename'])
                continue
            extracted = extract_isolated(path)
            if sha256(path,cancelled) != row['sha256']:
                messages.append('读取时文件变化，保留原索引：'+row['filename'])
                continue
            if extracted['text']:
                catalog.update_extraction(row['id'],extracted['text'],extracted['status'],extracted.get('display_title'),extracted.get('title_source',''))
                messages.append('已索引：'+row['filename'])
            else:
                if not row['body_snapshot']:
                    catalog.update_extraction(row['id'],'',extracted['status'])
                messages.append(extracted['status']+'：'+row['filename'])
        except Exception as exc:
            messages.append('索引失败：'+str(exc))
        progress(index,len(rows),row['filename'])
    return messages
