"""Recoverable recycle entries and durable restore transactions."""
import json
import uuid
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .organization import label_values
from .paths import filesystem_path, sqlite_filename


class LibraryStorage:
    def __init__(self, library):
        super().__init__(filesystem_path(library))

    @contextmanager
    def connection(self):
        db = sqlite3.connect(sqlite_filename(self.path), timeout=15)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def upgrade_library(db):
        db.execute('''CREATE TABLE IF NOT EXISTS recycle_entries (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, trash_relative TEXT NOT NULL UNIQUE,
            sha256 TEXT NOT NULL, metadata TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'available',
            restored_archive_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
        db.execute('''CREATE TABLE IF NOT EXISTS pending_restores (
            id TEXT PRIMARY KEY, recycle_id TEXT NOT NULL REFERENCES recycle_entries(id),
            target_relative TEXT NOT NULL, trash_relative TEXT NOT NULL,
            digest TEXT NOT NULL, metadata TEXT NOT NULL)''')
        for row in db.execute("SELECT id,detail FROM operations WHERE action='撤销归档'").fetchall():
            try:
                data = json.loads(row['detail'])
                metadata, relative = data['归档'], data['保留副本']
                ident = data.get('恢复区条目', 'legacy-' + str(row['id']))
                db.execute('INSERT OR IGNORE INTO recycle_entries(id,filename,trash_relative,sha256,metadata) VALUES (?,?,?,?,?)',
                           (ident, metadata['filename'], relative, metadata['sha256'], json.dumps(metadata, ensure_ascii=False)))
            except (KeyError, TypeError, json.JSONDecodeError):
                continue

    def prepare_undo(self, row, trash_relative):
        task_id = uuid.uuid4().hex
        with self.connection() as db:
            current = db.execute('SELECT * FROM archives WHERE id=?', (row['id'],)).fetchone()
            if current is None or dict(current) != dict(row):
                raise ValueError('归档记录已变化，请刷新后重试')
            metadata = dict(row)
            metadata['_labels'] = [dict(r) for r in db.execute('SELECT field,value FROM archive_labels WHERE archive_id=?', (row['id'],))]
            metadata['_sources'] = [dict(r) for r in db.execute('SELECT document_id,source_path,filename FROM archive_sources WHERE archive_id=?', (row['id'],))]
            db.execute('INSERT INTO pending_undo VALUES (?,?,?,?,?)',
                       (task_id, row['id'], row['relative_path'], trash_relative, json.dumps(metadata, ensure_ascii=False)))
        return task_id

    @staticmethod
    def _undo_matches(row, metadata):
        return all(key in row.keys() and row[key] == value for key, value in metadata.items()
                   if key not in ('archive_path', '_labels', '_sources'))

    def finish_undo(self, task_id):
        with self.connection() as db:
            task = db.execute('SELECT * FROM pending_undo WHERE id=?', (task_id,)).fetchone()
            if not task:
                return
            row = db.execute('SELECT * FROM archives WHERE id=?', (task['archive_id'],)).fetchone()
            metadata = json.loads(task['metadata'])
            if row and not self._undo_matches(row, metadata):
                raise ValueError('归档内容或标签已变化，撤销记录保留待恢复')
            if row:
                db.execute('INSERT INTO recycle_entries(id,filename,trash_relative,sha256,metadata) VALUES (?,?,?,?,?)',
                           (task_id, row['filename'], task['trash_relative'], row['sha256'], task['metadata']))
                db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                           (row['document_id'], '撤销归档', json.dumps({'归档': metadata,
                            '保留副本': task['trash_relative'], '恢复区条目': task_id}, ensure_ascii=False)))
                db.execute('DELETE FROM archives WHERE id=?', (row['id'],))
            db.execute('DELETE FROM pending_undo WHERE id=?', (task_id,))

    def recycle_entries(self):
        with self.connection() as db:
            return db.execute("SELECT * FROM recycle_entries WHERE status='available' ORDER BY created_at DESC,id").fetchall()

    def prepare_restore(self, row, relative, batch_id):
        task_id = uuid.uuid4().hex
        with self.connection() as db:
            current = db.execute('SELECT * FROM recycle_entries WHERE id=?', (row['id'],)).fetchone()
            if current is None or dict(current) != dict(row) or current['status'] != 'available':
                raise ValueError('恢复区记录已变化，请刷新后重试')
            if db.execute('SELECT 1 FROM pending_restores WHERE recycle_id=?', (row['id'],)).fetchone():
                raise ValueError('已有未完成的恢复任务，请先恢复中断任务')
            metadata = json.loads(row['metadata'])
            metadata['_restore_batch'] = batch_id
            db.execute('INSERT INTO pending_restores VALUES (?,?,?,?,?,?)',
                       (task_id, row['id'], relative, row['trash_relative'], row['sha256'], json.dumps(metadata, ensure_ascii=False)))
        return task_id

    def finish_restore(self, task_id):
        with self.connection() as db:
            task = db.execute('SELECT * FROM pending_restores WHERE id=?', (task_id,)).fetchone()
            if not task:
                return
            entry = db.execute('SELECT * FROM recycle_entries WHERE id=?', (task['recycle_id'],)).fetchone()
            if entry['status'] == 'restored':
                db.execute('DELETE FROM pending_restores WHERE id=?', (task_id,))
                return
            metadata = json.loads(task['metadata'])
            target = self.safe_path(task['target_relative'])
            fields = [r['name'] for r in db.execute('PRAGMA table_info(archives)') if r['name'] != 'id' and r['name'] in metadata]
            values = {key: metadata[key] for key in fields}
            values.update(archive_path=str(target), relative_path=task['target_relative'], batch_id=metadata['_restore_batch'])
            cursor = db.execute('INSERT INTO archives(' + ','.join(values) + ') VALUES (' + ','.join('?' for _ in values) + ')', list(values.values()))
            ident = cursor.lastrowid
            labels = metadata.get('_labels')
            if labels is None:
                labels = [{'field': field, 'value': value} for field in ('course', 'project', 'tags') for value in label_values(metadata.get(field, ''))]
            db.executemany('INSERT OR IGNORE INTO archive_labels VALUES (?,?,?)', [(ident, r['field'], r['value']) for r in labels])
            sources = metadata.get('_sources') or [{'document_id': metadata['document_id'], 'source_path': metadata['source_path'], 'filename': metadata['filename']}]
            db.executemany('INSERT INTO archive_sources VALUES (?,?,?,?)', [(ident, r['document_id'], r['source_path'], r['filename']) for r in sources])
            self._flatten_labels(db, ident)
            db.execute("UPDATE recycle_entries SET status='restored',restored_archive_id=? WHERE id=?", (ident, entry['id']))
            db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                       (metadata['document_id'], '恢复归档', json.dumps({'恢复区条目': entry['id'], '目标': str(target)}, ensure_ascii=False)))
            db.execute('DELETE FROM pending_restores WHERE id=?', (task_id,))

    def pending_restores(self):
        with self.connection() as db:
            return db.execute('SELECT * FROM pending_restores').fetchall()

    def cancel_restore(self, task_id):
        with self.connection() as db:
            db.execute('DELETE FROM pending_restores WHERE id=?', (task_id,))
