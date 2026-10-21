"""Bounded discovery in explicitly selected folders; stable files enter review only."""
import os
from pathlib import Path
from PySide6.QtCore import QThread, Signal
from .paths import comparison_path, filesystem_path, sqlite_filename


def validate_watch_folder(path, library):
    from .service import PROJECT_ROOT, within, directory_link
    path=Path(path)
    if directory_link(path) or not filesystem_path(path).is_dir():
        raise ValueError('请选择存在的普通文件夹')
    path=comparison_path(path)
    if within(path,library) or within(path,PROJECT_ROOT) or within(PROJECT_ROOT,path):
        raise ValueError('收件箱不能位于文档库或代码目录中，也不能包含代码目录')
    return path


class DiscoveryCursor:
    """Continue bounded traversal between polls; rotate folders within each batch."""
    def __init__(self):
        self.folders = None
        self.streams = []
        self.observed = {}
        self.position = 0
        self.checked = 0
        self.complete = True


def _paths(root, library, warnings, cancelled):
    from .service import within, PROJECT_ROOT, directory_link
    # Descendants can exceed MAX_PATH even when the selected root is short.
    for base, dirs, files in os.walk(sqlite_filename(root), followlinks=False, onerror=lambda exc:warnings.append(str(exc))):
        if cancelled(): return
        dirs[:] = [d for d in dirs if d not in {'.git','.venv','__pycache__','.documentassistant'}
            and not directory_link(Path(base)/d) and not within(Path(base)/d,library) and not within(Path(base)/d,PROJECT_ROOT)]
        # Empty directories also consume the traversal budget.
        yield None
        for name in files:
            if cancelled(): return
            yield Path(base)/name


def discover_folders(catalog, previous=None, cancelled=lambda:False, cursor=None, budget=20000):
    from .service import EXTENSIONS
    previous=previous or {}
    cursor=cursor or DiscoveryCursor()
    folders=tuple(r['path'] for r in catalog.watch_folders(active=True))
    warnings=[]
    if cursor.complete or cursor.folders != folders:
        cursor.folders=folders
        cursor.streams=[]
        cursor.observed={}
        cursor.checked=0
        cursor.position=0
        cursor.complete=False
        for folder in folders:
            try:
                root=validate_watch_folder(Path(folder),catalog.library)
                # Keep error messages on the cursor for generators resumed in another poll.
                errors=[]
                cursor.streams.append((folder,iter(_paths(root,catalog.library,errors,lambda:False)),errors))
            except ValueError as exc:
                warnings.append(folder+'：'+str(exc))
    seen=catalog.watch_seen()
    ready=[]
    examined=0
    while cursor.streams and examined<budget:
        if cancelled(): return dict(previous),[],warnings
        cursor.position %= len(cursor.streams)
        folder,stream,errors=cursor.streams[cursor.position]
        # Each folder receives a slice; later folders cannot starve behind a large one.
        for _ in range(min(1000,budget-examined)):
            if cancelled(): return dict(previous),[],warnings
            try: path=next(stream)
            except StopIteration:
                cursor.streams.pop(cursor.position)
                break
            examined+=1
            cursor.checked+=1
            if path is None: continue
            if path.suffix.lower() not in EXTENSIONS or path.name.startswith('~$') or path.is_symlink():continue
            try:
                physical=filesystem_path(path)
                stat=physical.stat()
                if not physical.is_file():continue
            except OSError:continue
            key=(folder,str(comparison_path(path)))
            signature=(stat.st_size,stat.st_mtime_ns)
            if seen.get(key)==signature:continue
            cursor.observed[key]=signature
            if previous.get(key)==signature:ready.append((folder,key[1],signature))
        else:
            cursor.position+=1
        if errors:
            warnings.extend(errors);errors.clear()
    cursor.complete=not cursor.streams
    if not cursor.complete:
        warnings.append(f'收件箱分批检查中：本轮已检查 {cursor.checked} 个文件或目录，下次从当前位置继续')
        return {**previous,**cursor.observed},ready,warnings
    return dict(cursor.observed),ready,warnings


class WatchWorker(QThread):
    completed=Signal(object)

    def __init__(self,catalog,previous,generation,parent,cursor=None):
        super().__init__(parent)
        self.catalog,self.previous,self.generation=catalog,previous,generation
        self.cursor=cursor

    def run(self):
        try:
            observed,ready,warnings=discover_folders(self.catalog,self.previous,self.isInterruptionRequested,self.cursor)
            if not self.isInterruptionRequested():
                self.completed.emit({'library':self.catalog.library_id,'generation':self.generation,
                    'observed':observed,'ready':ready,'warnings':warnings})
        except Exception as exc:
            if not self.isInterruptionRequested():self.completed.emit({'error':str(exc),'generation':self.generation})
