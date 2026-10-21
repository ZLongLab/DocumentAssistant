"""Verified ZIP library backups and restoration to a new, empty library."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import uuid
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

from . import __version__
from .service import sha256, validate_library, within
from .paths import comparison_path, filesystem_path, sqlite_filename

DATABASE = '.documentassistant/catalog.sqlite3'


def portable_relative(name):
    if not isinstance(name, str) or not name or '\\' in name:
        raise ValueError('备份包含非法路径')
    path = PurePosixPath(name)
    if path.is_absolute() or name != path.as_posix() or any(p in ('', '.', '..') for p in path.parts):
        raise ValueError('备份包含非法相对路径')
    for part in path.parts:
        if any(ch in part for ch in '<>:"|?*') or part.rstrip(' .') != part or any(ord(ch) < 32 for ch in part):
            raise ValueError('备份包含 Windows 不支持的文件名')
        if re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])', part.split('.')[0], re.I):
            raise ValueError('备份包含保留设备名称')
    return path


def inventory(library):
    library = comparison_path(library)
    result, visited = {}, set()
    def inaccessible(error):
        raise error
    # Descendants may be long even when the library root is short.
    for root, dirs, files in os.walk(sqlite_filename(library), followlinks=False, onerror=inaccessible):
        folder = comparison_path(root)
        stat = filesystem_path(folder).stat()
        identity = (stat.st_dev, stat.st_ino)
        if identity in visited or not within(folder,library):
            raise ValueError('文档库包含循环链接或指向库外的目录')
        visited.add(identity)
        for name in list(dirs):
            path = folder / name
            relative = path.relative_to(library).as_posix()
            if relative.casefold() == '.documentassistant/backups':
                dirs.remove(name)
            elif filesystem_path(path).is_symlink() or not within(path,library):
                raise ValueError('文档库包含目录链接，请先移出链接')
        for name in files:
            path = folder / name
            relative = path.relative_to(library).as_posix()
            if relative.casefold() in (DATABASE, DATABASE + '-wal', DATABASE + '-shm', DATABASE + '-journal'):
                continue
            first = relative.split('/')[0]
            if first.casefold()=='.documentassistant':
                relative = '.documentassistant' + relative[len(first):]
            portable_relative(relative)
            if filesystem_path(path).is_symlink() or not within(path,library) or not filesystem_path(path).is_file():
                raise ValueError('文档库包含不支持的文件链接')
            stat = filesystem_path(path).stat()
            result[relative] = (path, stat.st_size, stat.st_mtime_ns)
    return result


def check_snapshot(path, files):
    with closing(sqlite3.connect(sqlite_filename(path))) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA query_only=ON')
        if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('备份数据库校验失败')
        version = db.execute("SELECT value FROM library_meta WHERE key='schema_version'").fetchone()
        if not version or version[0] not in ('4','5','6'):
            raise ValueError('备份数据库版本不受支持')
        for table in ('pending_archives', 'pending_undo', 'pending_restores'):
            if db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0]:
                raise ValueError('文档库有未完成任务，请先检查恢复任务后再备份')
        archives = db.execute('SELECT relative_path FROM archives').fetchall()
        entries = db.execute("SELECT trash_relative FROM recycle_entries WHERE status='available'").fetchall()
        available = {name.casefold() for name in files}
        for relative in [r[0] for r in archives] + [r[0] for r in entries]:
            portable_relative(relative.replace('\\', '/'))
            if relative.replace('\\', '/').casefold() not in available:
                raise ValueError('记录引用的副本不存在，无法创建完整备份：' + relative)
        return len(archives), len(entries)


def export_library(catalog, destination, progress=lambda *_: None, cancelled=lambda: False):
    destination = filesystem_path(destination)
    if within(destination,catalog.library):
        raise ValueError('请把备份保存到当前文档库之外')
    if destination.exists() or destination.is_symlink():
        raise FileExistsError('备份文件已存在，请使用新的文件名')
    destination.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.documentassistant-backup-', dir=destination.parent)).resolve()
    temporary = stage / 'bundle.zip'
    try:
        files = inventory(catalog.library)
        if len({name.casefold() for name in files})!=len(files):
            raise ValueError('文档库文件名存在大小写冲突，无法生成可恢复的备份')
        snapshot = stage / 'catalog.sqlite3'
        with catalog.connection() as source, closing(sqlite3.connect(sqlite_filename(snapshot))) as copied:
            version = source.execute('PRAGMA data_version').fetchone()[0]
            source.backup(copied)
            archived, recycled = check_snapshot(snapshot, files)
            manifest = {'format': 1, 'app_version': __version__, 'library_id': catalog.library_id,
                        'archive_count': archived, 'recycle_count': recycled, 'files': {}}
            files[DATABASE] = (snapshot, snapshot.stat().st_size, snapshot.stat().st_mtime_ns)
            with zipfile.ZipFile(filesystem_path(temporary), 'x', compression=zipfile.ZIP_DEFLATED, allowZip64=True) as bundle:
                for index, (relative, (path, size, modified)) in enumerate(sorted(files.items()), 1):
                    if cancelled():
                        raise InterruptedError('备份已停止，原库保留')
                    progress(index - 1, len(files), '备份 ' + Path(relative).name)
                    digest = hashlib.sha256()
                    count = 0
                    with filesystem_path(path).open('rb') as stream, bundle.open('library/' + relative, 'w', force_zip64=True) as target:
                        for block in iter(lambda: stream.read(1024 * 1024), b''):
                            if cancelled():
                                raise InterruptedError('备份已停止，原库保留')
                            digest.update(block)
                            count += len(block)
                            target.write(block)
                    after = filesystem_path(path).stat()
                    if count != size or (after.st_size, after.st_mtime_ns) != (size, modified):
                        raise ValueError('备份期间文件发生变化，请重新备份：' + relative)
                    manifest['files'][relative] = {'size': count, 'sha256': digest.hexdigest()}
                    progress(index, len(files), '备份 ' + Path(relative).name)
                bundle.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))
            if source.execute('PRAGMA data_version').fetchone()[0] != version:
                raise ValueError('备份期间文档库记录发生变化，请重新备份')
            current = inventory(catalog.library)
            original = {key: value[1:] for key, value in files.items() if key != DATABASE}
            if {key: value[1:] for key, value in current.items()} != original:
                raise ValueError('备份期间文档库文件列表发生变化，请重新备份')
        with zipfile.ZipFile(filesystem_path(temporary)) as bundle:
            for relative, expected in manifest['files'].items():
                if cancelled():
                    raise InterruptedError('备份已停止，原库保留')
                digest = hashlib.sha256()
                with bundle.open('library/' + relative) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        if cancelled():
                            raise InterruptedError('备份已停止，原库保留')
                        digest.update(block)
                if digest.hexdigest() != expected['sha256']:
                    raise ValueError('备份包内容校验失败')
        # Publish without replacing an existing file, including a concurrent creator.
        if os.name == 'nt':
            filesystem_path(temporary).rename(filesystem_path(destination))
        else:
            os.link(temporary, destination)
        return {'path': str(destination), 'archive_count': archived, 'recycle_count': recycled,
                'file_count': len(files), 'verified': True}
    finally:
        if stage.parent == destination.parent.resolve() and stage.name.startswith('.documentassistant-backup-'):
            shutil.rmtree(sqlite_filename(stage))


def restore_library(backup, destination, progress=lambda *_: None, cancelled=lambda: False):
    from .storage import Catalog
    backup, destination = filesystem_path(backup), filesystem_path(destination)
    validate_library(destination)
    if destination.is_symlink() or (destination.exists() and (not destination.is_dir() or any(destination.iterdir()))):
        raise ValueError('请使用新的空文件夹恢复，不覆盖现有文档库')
    destination.parent.mkdir(parents=True, exist_ok=True)
    original_stat = destination.stat() if destination.exists() else None
    stage = Path(tempfile.mkdtemp(prefix='.documentassistant-restore-', dir=destination.parent)).resolve()
    published = False
    try:
        with zipfile.ZipFile(backup) as bundle:
            info = bundle.getinfo('manifest.json')
            if info.file_size > 32 * 1024 * 1024:
                raise ValueError('备份清单过大')
            manifest = json.loads(bundle.read(info))
            if not isinstance(manifest, dict) or manifest.get('format') != 1 or not isinstance(manifest.get('files'), dict):
                raise ValueError('不是受支持的文档库完整备份')
            files = manifest['files']
            if len(files) > 100_000 or DATABASE not in files:
                raise ValueError('备份文件数量或数据库无效')
            expected_names = {'manifest.json'}
            total = 0
            for relative, expected in files.items():
                portable_relative(relative)
                if not isinstance(expected, dict) or type(expected.get('size')) is not int or expected['size'] < 0 or not re.fullmatch('[0-9a-f]{64}', expected.get('sha256', '')):
                    raise ValueError('备份文件清单无效')
                total += expected['size']
                expected_names.add('library/' + relative)
            actual_names = [info.filename for info in bundle.infolist()]
            if len(set(name.casefold() for name in actual_names)) != len(actual_names) or set(actual_names) != expected_names:
                raise ValueError('备份包含重复路径或清单以外的内容')
            if len(set(name.casefold() for name in expected_names)) != len(expected_names):
                raise ValueError('备份包含 Windows 路径冲突')
            if shutil.disk_usage(stage).free < total + 10 * 1024 * 1024:
                raise ValueError('目标磁盘空间不足')
            for index, (relative, expected) in enumerate(sorted(files.items()), 1):
                if cancelled():
                    raise InterruptedError('恢复已停止，原文档库保留')
                entry = bundle.getinfo('library/' + relative)
                mode = (entry.external_attr >> 16) & 0o170000
                if entry.is_dir() or mode == 0o120000 or entry.file_size != expected['size']:
                    raise ValueError('备份文件类型或大小与清单不符')
                target = stage.joinpath(*PurePosixPath(relative).parts)
                if not target.resolve().is_relative_to(stage):
                    raise ValueError('备份路径指向恢复目录外')
                filesystem_path(target.parent).mkdir(parents=True, exist_ok=True)
                digest, count = hashlib.sha256(), 0
                progress(index - 1, len(files), '恢复 ' + Path(relative).name)
                with bundle.open(entry) as stream, filesystem_path(target).open('xb') as copied:
                    for block in iter(lambda: stream.read(1024 * 1024), b''):
                        if cancelled():
                            raise InterruptedError('恢复已停止，原文档库保留')
                        count += len(block)
                        if count > expected['size']:
                            raise ValueError('备份解压大小与清单不符')
                        digest.update(block)
                        copied.write(block)
                if count != expected['size'] or digest.hexdigest() != expected['sha256']:
                    raise ValueError('备份校验失败：' + relative)
                progress(index, len(files), '恢复 ' + Path(relative).name)
        archived, recycled = check_snapshot(stage / DATABASE, files)
        staged_catalog = Catalog(stage)
        if staged_catalog.library_id != manifest.get('library_id'):
            raise ValueError('备份文档库身份不符')
        if cancelled():
            raise InterruptedError('恢复已停止，原文档库保留')
        if destination.exists():
            current = destination.stat()
            if original_stat is None or (current.st_dev, current.st_ino, current.st_mtime_ns) != (original_stat.st_dev, original_stat.st_ino, original_stat.st_mtime_ns) or any(destination.iterdir()) or destination.is_symlink():
                raise ValueError('目标文件夹在恢复期间发生变化，未覆盖')
            destination.rmdir()  # Remove only the reviewed empty placeholder, never recursively.
        elif original_stat is not None:
            raise ValueError('目标文件夹在恢复期间被移走，未发布')
        if not destination.resolve().is_relative_to(destination.parent.resolve()) or stage.parent != destination.parent.resolve():
            raise ValueError('恢复目标路径检查失败')
        for attempt in range(20):
            try:
                stage.rename(destination)
                break
            except PermissionError:
                if attempt==19 or destination.exists() or not stage.is_dir():
                    raise
                time.sleep(0.1)  # OneDrive/AV can briefly hold newly created database files.
        published = True
        restored_catalog = Catalog(destination)
        with restored_catalog.connection() as db:
            db.execute('UPDATE watch_folders SET enabled=0')
        return {'path': str(destination), 'archive_count': archived, 'recycle_count': recycled,
                'file_count': len(files), 'verified': True}
    finally:
        if not published and stage.parent == destination.parent.resolve() and stage.name.startswith('.documentassistant-restore-'):
            shutil.rmtree(sqlite_filename(stage))
            if original_stat is not None and not destination.exists():
                destination.mkdir()
