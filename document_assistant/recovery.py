"""Restore only verified recycle files, preserving any existing destination."""
import json
import uuid
from pathlib import Path

from .service import sha256
from .paths import filesystem_path


def restore_recycled(catalog, rows, progress=lambda *_: None, cancelled=lambda: False):
    catalog.backup('before-restore')
    batch_id = uuid.uuid4().hex
    messages = []
    for index, row in enumerate(rows, 1):
        if cancelled():
            break
        progress(index - 1, len(rows), '恢复 ' + row['filename'])
        try:
            trash = catalog.safe_path(row['trash_relative'])
            if not filesystem_path(trash).is_file() or sha256(trash, cancelled) != row['sha256']:
                raise ValueError('恢复副本不存在或已修改，记录和文件均保留')
            metadata = json.loads(row['metadata'])
            original = catalog.safe_path(metadata['relative_path'])
            filesystem_path(original.parent).mkdir(parents=True, exist_ok=True)
            reserved = catalog.reserved_paths()
            for number in range(100_000):
                target = original if not number else original.with_name(f'{original.stem} (恢复 {number}){original.suffix}')
                if filesystem_path(target).exists() or str(target).casefold() in reserved:
                    continue
                task_id = catalog.prepare_restore(row, str(target.relative_to(catalog.library)), batch_id)
                try:
                    if cancelled():
                        catalog.cancel_restore(task_id)
                        raise InterruptedError('已停止恢复，副本保留')
                    filesystem_path(trash).rename(filesystem_path(target))  # Refuses overwrite on Windows.
                except FileExistsError:
                    catalog.cancel_restore(task_id)
                    continue
                catalog.finish_restore(task_id)
                messages.append('已恢复：' + target.name)
                break
            else:
                raise ValueError('无法分配不冲突的恢复文件名')
        except Exception as exc:
            messages.append(row['filename'] + '：恢复未完成：' + str(exc))
        progress(index, len(rows), row['filename'])
    return messages


def recover_restores(catalog, cancelled=lambda: False):
    messages = []
    for task in catalog.pending_restores():
        if cancelled():
            break
        try:
            target = catalog.safe_path(task['target_relative'])
            trash = catalog.safe_path(task['trash_relative'])
            if not filesystem_path(target).exists() and filesystem_path(trash).is_file() and sha256(trash, cancelled) == task['digest']:
                catalog.cancel_restore(task['id'])
                messages.append('恢复尚未移动副本，已取消中断任务，可重新恢复：' + trash.name)
            elif not filesystem_path(trash).exists() and filesystem_path(target).is_file() and sha256(target, cancelled) == task['digest']:
                catalog.finish_restore(task['id'])
                messages.append('恢复归档登记：' + target.name)
            else:
                messages.append('恢复任务状态有变化，所有副本保留待检查：' + target.name)
        except Exception as exc:
            messages.append('恢复登记未完成：' + str(exc))
    return messages
