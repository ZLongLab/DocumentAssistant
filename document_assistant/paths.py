"""Windows extended paths for SQLite, which otherwise fails on long filenames."""
import os
from pathlib import Path


def sqlite_filename(path):
    name = str(Path(path).resolve())
    if os.name == 'nt' and not name.startswith('\\\\?\\'):
        return '\\\\?\\UNC\\' + name[2:] if name.startswith('\\\\') else '\\\\?\\' + name
    return name


def filesystem_path(path):
    resolved = Path(path).resolve()
    return Path(sqlite_filename(resolved)) if os.name=='nt' and len(str(resolved))>=220 else resolved


def comparison_path(path):
    name = str(Path(path).resolve())
    if name.startswith('\\\\?\\UNC\\'):
        name = '\\\\' + name[8:]
    elif name.startswith('\\\\?\\'):
        name = name[4:]
    return Path(name)
