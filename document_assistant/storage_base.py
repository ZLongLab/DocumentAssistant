from __future__ import annotations

import json
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from .paths import filesystem_path


def archive_file_state(path: str) -> str:
    """Only proven absence is eligible for cleanup; access errors stay untouched."""
    try:
        info = filesystem_path(path).stat()
        return 'available' if stat.S_ISREG(info.st_mode) else 'unknown'
    except FileNotFoundError:
        return 'missing'
    except (OSError, ValueError):
        return 'unknown'


class Catalog:
    def __init__(self, library: Path):
        self.library = library.resolve()
        directory = self.library / ".documentassistant"
        filesystem_path(directory).mkdir(parents=True, exist_ok=True)
        self.path = directory / "catalog.sqlite3"
        with self.connection() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    id INTEGER PRIMARY KEY, source_path TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                    extraction_status TEXT NOT NULL, body TEXT NOT NULL,
                    suggested_category TEXT NOT NULL, category TEXT NOT NULL, reason TEXT NOT NULL,
                    scanned_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS archives (
                    id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL REFERENCES documents(id),
                    source_path TEXT NOT NULL, archive_path TEXT NOT NULL UNIQUE,
                    filename TEXT NOT NULL, category TEXT NOT NULL, sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id INTEGER PRIMARY KEY, document_id INTEGER REFERENCES documents(id),
                    action TEXT NOT NULL, detail TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))
                );
                CREATE INDEX IF NOT EXISTS archives_category ON archives(category);
            """)

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def previous_manual_category(self, path: Path, size: int, mtime_ns: int):
        with self.connection() as db:
            row = db.execute('''SELECT category FROM documents WHERE source_path=? AND size=? AND mtime_ns=?
                AND category<>suggested_category''', (str(path.resolve()), size, mtime_ns)).fetchone()
            return row['category'] if row else None

    def save_scan(self, item) -> int:
        with self.connection() as db:
            db.execute("""INSERT INTO documents
                (source_path,filename,size,mtime_ns,extraction_status,body,suggested_category,category,reason)
                VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(source_path) DO UPDATE SET
                filename=excluded.filename,size=excluded.size,mtime_ns=excluded.mtime_ns,
                extraction_status=excluded.extraction_status,body=excluded.body,
                suggested_category=excluded.suggested_category,category=excluded.category,
                reason=excluded.reason,scanned_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')""",
                (str(item.path), item.path.name, item.size, item.mtime_ns, item.status,
                 item.body, item.suggested, item.category, item.reason))
            doc_id = db.execute("SELECT id FROM documents WHERE source_path=?", (str(item.path),)).fetchone()[0]
            db.execute("INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)",
                       (doc_id, "扫描", item.status + "；" + item.reason))
            return doc_id

    def change_category(self, doc_id: int, category: str):
        with self.connection() as db:
            old = db.execute("SELECT category FROM documents WHERE id=?", (doc_id,)).fetchone()[0]
            db.execute("UPDATE documents SET category=? WHERE id=?", (category, doc_id))
            db.execute("INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)",
                       (doc_id, "修改分类", f"{old} → {category}"))

    def log(self, doc_id: int | None, action: str, detail: str):
        with self.connection() as db:
            db.execute("INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)", (doc_id, action, detail))

    def existing_archives(self, doc_id: int, category: str, digest: str):
        with self.connection() as db:
            return db.execute("SELECT archive_path FROM archives WHERE document_id=? AND category=? AND sha256=?",
                              (doc_id, category, digest)).fetchall()

    def reserved_paths(self):
        with self.connection() as db:
            return {row[0].casefold() for row in db.execute("SELECT archive_path FROM archives")}

    def record_archive(self, item, target: Path, digest: str):
        with self.connection() as db:
            db.execute("UPDATE documents SET category=? WHERE id=?", (item.category, item.doc_id))
            db.execute("""INSERT INTO archives(document_id,source_path,archive_path,filename,category,sha256)
                VALUES (?,?,?,?,?,?)""", (item.doc_id, str(item.path), str(target), item.path.name, item.category, digest))
            db.execute("INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)",
                       (item.doc_id, "复制归档", json.dumps({"来源": str(item.path), "目标": str(target),
                        "分类": item.category, "sha256": digest}, ensure_ascii=False)))

    def search(self, filename: str = "", category: str = ""):
        # instr treats %, _ as literal characters rather than SQL wildcards.
        with self.connection() as db:
            return db.execute("""SELECT * FROM archives WHERE instr(lower(filename),lower(?))>0
                AND (?='' OR category=?) ORDER BY id DESC""", (filename, category, category)).fetchall()

    def operations(self):
        with self.connection() as db:
            return db.execute("SELECT * FROM operations ORDER BY id DESC LIMIT 500").fetchall()

    def _check_library_access(self):
        try:
            if not stat.S_ISDIR(self.library.stat().st_mode):
                raise OSError('Not a directory')
        except OSError as exc:
            raise OSError('文档库目录不可访问，未清理记录。请检查库位置或磁盘连接。') from exc

    def missing_archives(self):
        self._check_library_access()
        missing, unknown = [], 0
        for row in self.search():
            state = archive_file_state(row['archive_path'])
            if state == 'missing':
                missing.append(dict(row))
            elif state == 'unknown':
                unknown += 1
        self._check_library_access()
        return missing, unknown

    def cleanup_missing_archives(self, candidates):
        """Remove only reviewed, unchanged, still-missing archive rows; never file data."""
        self._check_library_access()
        removed, restored, skipped = [], 0, 0
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for candidate in candidates:
                row = db.execute('SELECT * FROM archives WHERE id=?', (candidate['id'],)).fetchone()
                if row is None or dict(row) != dict(candidate):
                    skipped += 1
                    continue
                state = archive_file_state(row['archive_path'])
                if state != 'missing':
                    restored += state == 'available'
                    skipped += state == 'unknown'
                    continue
                db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                           (row['document_id'], '清理失效记录', json.dumps(dict(row), ensure_ascii=False)))
                db.execute('DELETE FROM archives WHERE id=?', (row['id'],))
                removed.append(dict(row))
            self._check_library_access()
        return {'removed': len(removed), 'restored': restored, 'skipped': skipped, 'records': removed}
