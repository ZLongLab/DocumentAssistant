"""Versioned archive snapshots, portable library paths and durable task records."""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .storage_base import Catalog as BaseCatalog, archive_file_state
from .paths import sqlite_filename, filesystem_path


class CatalogV8(BaseCatalog):
    def __init__(self, library: Path):
        self.library = library.resolve()
        self.directory = self.library / '.documentassistant'
        self.path = self.directory / 'catalog.sqlite3'
        self.last_backup = None
        needs_backup = False
        if filesystem_path(self.path).exists():
            with self.connection() as db:
                columns = {r['name'] for r in db.execute('PRAGMA table_info(archives)')}
                needs_backup = 'relative_path' not in columns
                if not needs_backup:
                    old = db.execute("SELECT value FROM library_meta WHERE key='root'").fetchone()
                    version = db.execute("SELECT value FROM library_meta WHERE key='schema_version'").fetchone()
                    needs_backup = bool(old and old[0] != str(self.library)) or not version or version[0] != '6'
            if needs_backup:
                self.last_backup = self.backup('before-upgrade-or-relocation')
        super().__init__(library)
        self._upgrade()

    def safe_path(self, relative: str) -> Path:
        part = Path(relative)
        if not relative or part.is_absolute() or '..' in part.parts:
            raise ValueError('非法文档库相对路径')
        target = self.library / part
        if not target.resolve().is_relative_to(self.library):
            raise ValueError('路径或链接指向文档库外部')
        return target

    def backup(self, label='manual') -> Path:
        folder = self.directory / 'backups'
        filesystem_path(folder).mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        target = folder / f'catalog-{stamp}-{label}-{uuid.uuid4().hex[:8]}.sqlite3'
        with self.connection() as source, closing(sqlite3.connect(sqlite_filename(target))) as destination:
            source.backup(destination)
        return filesystem_path(target)

    def _upgrade(self):
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            for table, fields in (
                ('documents', {'course': "TEXT NOT NULL DEFAULT ''", 'project': "TEXT NOT NULL DEFAULT ''", 'tags': "TEXT NOT NULL DEFAULT ''"}),
                ('archives', {'relative_path': "TEXT NOT NULL DEFAULT ''", 'body_snapshot': "TEXT NOT NULL DEFAULT ''",
                              'course': "TEXT NOT NULL DEFAULT ''", 'project': "TEXT NOT NULL DEFAULT ''", 'tags': "TEXT NOT NULL DEFAULT ''",
                              'batch_id': "TEXT NOT NULL DEFAULT ''"}),
            ):
                columns = {r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
                for name, definition in fields.items():
                    if name not in columns:
                        db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
            db.execute('CREATE TABLE IF NOT EXISTS library_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('''CREATE TABLE IF NOT EXISTS pending_archives (
                id TEXT PRIMARY KEY, target_relative TEXT NOT NULL, temp_relative TEXT NOT NULL,
                document_id INTEGER NOT NULL, digest TEXT NOT NULL, metadata TEXT NOT NULL,
                reservation TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            db.execute('''CREATE TABLE IF NOT EXISTS pending_undo (
                id TEXT PRIMARY KEY, archive_id INTEGER NOT NULL, target_relative TEXT NOT NULL,
                trash_relative TEXT NOT NULL, metadata TEXT NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS archives_hash ON archives(sha256)')
            db.execute('CREATE INDEX IF NOT EXISTS archives_document_hash ON archives(document_id,category,sha256)')
            db.execute('CREATE INDEX IF NOT EXISTS archives_batch ON archives(batch_id)')
            old_root = db.execute("SELECT value FROM library_meta WHERE key='root'").fetchone()
            for row in db.execute('SELECT id,archive_path,category,relative_path FROM archives').fetchall():
                relative = row['relative_path']
                if not relative:
                    old = Path(row['archive_path'])
                    if old_root:
                        try:
                            relative = str(old.relative_to(Path(old_root[0])))
                        except ValueError:
                            pass
                    # Legacy versions always archived to exactly category/filename.
                    if not relative and old.parent.name == row['category']:
                        relative = str(Path(row['category']) / old.name)
                if relative:
                    target = self.safe_path(relative)
                    if str(target) != row['archive_path'] or relative != row['relative_path']:
                        db.execute('UPDATE archives SET relative_path=?, archive_path=? WHERE id=?', (relative, str(target), row['id']))
            for key, value in (('root', str(self.library)), ('schema_version', '2')):
                db.execute('INSERT INTO library_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, value))
            db.execute("INSERT OR IGNORE INTO library_meta VALUES ('id',?)", (uuid.uuid4().hex,))
            exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='archive_fts'").fetchone()
            self.fts_enabled = bool(exists)
            if not exists:
                try:
                    db.execute("CREATE VIRTUAL TABLE archive_fts USING fts5(filename,body_snapshot,course,project,tags, content='archives',content_rowid='id',tokenize='trigram')")
                    db.execute("""CREATE TRIGGER archive_fts_insert AFTER INSERT ON archives BEGIN
                        INSERT INTO archive_fts(rowid,filename,body_snapshot,course,project,tags)
                        VALUES(new.id,new.filename,new.body_snapshot,new.course,new.project,new.tags); END""")
                    db.execute("""CREATE TRIGGER archive_fts_delete AFTER DELETE ON archives BEGIN
                        INSERT INTO archive_fts(archive_fts,rowid,filename,body_snapshot,course,project,tags)
                        VALUES('delete',old.id,old.filename,old.body_snapshot,old.course,old.project,old.tags); END""")
                    db.execute("""CREATE TRIGGER archive_fts_update AFTER UPDATE ON archives BEGIN
                        INSERT INTO archive_fts(archive_fts,rowid,filename,body_snapshot,course,project,tags)
                        VALUES('delete',old.id,old.filename,old.body_snapshot,old.course,old.project,old.tags);
                        INSERT INTO archive_fts(rowid,filename,body_snapshot,course,project,tags)
                        VALUES(new.id,new.filename,new.body_snapshot,new.course,new.project,new.tags); END""")
                    db.execute("INSERT INTO archive_fts(archive_fts) VALUES ('rebuild')")
                    self.fts_enabled = True
                except sqlite3.OperationalError as exc:
                    if 'no such' not in str(exc).lower() and 'tokenizer' not in str(exc).lower():
                        raise
            self.library_id = db.execute("SELECT value FROM library_meta WHERE key='id'").fetchone()[0]

    def previous_labels(self, path):
        with self.connection() as db:
            row = db.execute('SELECT course,project,tags FROM documents WHERE source_path=?', (str(path),)).fetchone()
            return dict(row) if row else {}

    def save_scan(self, item):
        with self.connection() as db:
            db.execute('''INSERT INTO documents
                (source_path,filename,size,mtime_ns,extraction_status,body,suggested_category,category,reason,course,project,tags)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_path) DO UPDATE SET
                filename=excluded.filename,size=excluded.size,mtime_ns=excluded.mtime_ns,
                extraction_status=excluded.extraction_status,body=excluded.body,
                suggested_category=excluded.suggested_category,category=excluded.category,reason=excluded.reason,
                course=excluded.course,project=excluded.project,tags=excluded.tags,
                scanned_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''',
                (str(item.path),item.path.name,item.size,item.mtime_ns,item.status,item.body,item.suggested,item.category,item.reason,
                 getattr(item,'course',''),getattr(item,'project',''),getattr(item,'tags','')))
            doc_id = db.execute('SELECT id FROM documents WHERE source_path=?',(str(item.path),)).fetchone()[0]
            db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',(doc_id,'扫描',item.status+'；'+item.reason))
            return doc_id

    def record_archive(self, item, target, digest):
        relative = str(target.relative_to(self.library))
        with self.connection() as db:
            db.execute('UPDATE documents SET category=? WHERE id=?',(item.category,item.doc_id))
            db.execute('''INSERT INTO archives(document_id,source_path,archive_path,filename,category,sha256,
                relative_path,body_snapshot,course,project,tags,batch_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (item.doc_id,str(item.path),str(target),item.path.name,item.category,digest,relative,item.body,
                 getattr(item,'course',''),getattr(item,'project',''),getattr(item,'tags',''),getattr(item,'_batch_id','')))
            db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                (item.doc_id,'复制归档',json.dumps({'来源':str(item.path),'目标':str(target),'分类':item.category,'sha256':digest},ensure_ascii=False)))
            task_id = getattr(item,'_archive_task_id',None)
            if task_id:
                db.execute('DELETE FROM pending_archives WHERE id=?',(task_id,))

    def content_duplicates(self, digest):
        with self.connection() as db:
            return db.execute('SELECT * FROM archives WHERE sha256=? ORDER BY id DESC',(digest,)).fetchall()

    def _where(self, query, category, course='', project='', scope='all'):
        fields = ('filename',) if scope=='filename' else ('filename','body_snapshot','course','project','tags')
        if scope=='all' and query and len(query) >= 3 and self.fts_enabled:
            text = 'id IN (SELECT rowid FROM archive_fts WHERE archive_fts MATCH ?)'
            params = ['"'+query.replace('"','""')+'"']
        else:
            text = '('+' OR '.join(f'instr(lower({f}),lower(?))>0' for f in fields)+')'
            params = [query]*len(fields)
        for field, value in (('category',category),('course',course),('project',project)):
            if value:
                text += f' AND {field}=?'
                params.append(value)
        return text, params

    def search(self, filename='', category='', *, course='', project='', limit=None, offset=0, scope='all'):
        where, params = self._where(filename,category,course,project,scope)
        sql = 'SELECT * FROM archives WHERE '+where+' ORDER BY id DESC'
        if limit is not None:
            sql += ' LIMIT ? OFFSET ?'
            params += [max(1,min(500,int(limit))),max(0,int(offset))]
        with self.connection() as db:
            return db.execute(sql,params).fetchall()

    def search_count(self, query='', category='', *, course='', project='', scope='all'):
        where, params = self._where(query,category,course,project,scope)
        with self.connection() as db:
            return db.execute('SELECT count(*) FROM archives WHERE '+where,params).fetchone()[0]

    def change_labels(self, ids, updates, *, archives=False):
        allowed = {'course','project','tags','category'}
        if not updates or not set(updates) <= allowed:
            raise ValueError('无效标签字段')
        from .rules import CATEGORIES
        if 'category' in updates and updates['category'] not in CATEGORIES:
            raise ValueError('无效分类')
        if any(not isinstance(v,str) or len(v)>300 for v in updates.values()):
            raise ValueError('标签必须为文本，且每项不超过300字')
        table = 'archives' if archives else 'documents'
        with self.connection() as db:
            for ident in ids:
                row = db.execute(f'SELECT * FROM {table} WHERE id=?',(ident,)).fetchone()
                if not row:
                    continue
                db.execute(f'UPDATE {table} SET '+','.join(f'{key}=?' for key in updates)+' WHERE id=?',[*updates.values(),ident])
                db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                    (row['document_id'] if archives else ident,'修改归档标签' if archives else '修改标签',
                     json.dumps({'记录':ident,'修改':updates},ensure_ascii=False)))

    def update_body(self, archive_id, body):
        with self.connection() as db:
            db.execute('UPDATE archives SET body_snapshot=? WHERE id=?',(body[:100_000],archive_id))

    def create_task(self, task):
        with self.connection() as db:
            db.execute('INSERT INTO pending_archives(id,target_relative,temp_relative,document_id,digest,metadata) VALUES (?,?,?,?,?,?)',
                (task['id'],task['target_relative'],task['temp_relative'],task['document_id'],task['digest'],json.dumps(task['metadata'],ensure_ascii=False)))

    def reserve_task(self, task_id, identity):
        with self.connection() as db:
            db.execute('UPDATE pending_archives SET reservation=? WHERE id=?',(json.dumps(identity),task_id))

    def delete_task(self, task_id):
        with self.connection() as db:
            db.execute('DELETE FROM pending_archives WHERE id=?',(task_id,))

    def pending_tasks(self):
        with self.connection() as db:
            return db.execute('SELECT * FROM pending_archives ORDER BY created_at').fetchall()

    def latest_batch(self):
        with self.connection() as db:
            row = db.execute("SELECT batch_id FROM archives WHERE batch_id<>'' ORDER BY id DESC LIMIT 1").fetchone()
            return db.execute('SELECT * FROM archives WHERE batch_id=? ORDER BY id DESC',(row[0],)).fetchall() if row else []

    def prepare_undo(self, row, trash_relative):
        task_id = uuid.uuid4().hex
        with self.connection() as db:
            current = db.execute('SELECT * FROM archives WHERE id=?',(row['id'],)).fetchone()
            if current is None or dict(current)!=dict(row):
                raise ValueError('归档记录已变化，请刷新后重试')
            db.execute('INSERT INTO pending_undo VALUES (?,?,?,?,?)',
                (task_id,row['id'],row['relative_path'],trash_relative,json.dumps(dict(row),ensure_ascii=False)))
        return task_id

    def finish_undo(self, task_id):
        with self.connection() as db:
            task = db.execute('SELECT * FROM pending_undo WHERE id=?',(task_id,)).fetchone()
            if not task:
                return
            row = db.execute('SELECT * FROM archives WHERE id=?',(task['archive_id'],)).fetchone()
            metadata = json.loads(task['metadata'])
            if row and dict(row) != metadata:
                raise ValueError('归档记录已变化，撤销记录保留待恢复')
            if row:
                db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                    (row['document_id'],'撤销归档',json.dumps({'归档':dict(row),'保留副本':task['trash_relative']},ensure_ascii=False)))
                db.execute('DELETE FROM archives WHERE id=?',(row['id'],))
            db.execute('DELETE FROM pending_undo WHERE id=?',(task_id,))

    def pending_undos(self):
        with self.connection() as db:
            return db.execute('SELECT * FROM pending_undo').fetchall()

    def missing_archives(self):
        missing, unknown = super().missing_archives()
        # An unrecognized legacy layout must be repaired, never blindly cleared.
        safe = [row for row in missing if row['relative_path']]
        return safe, unknown + len(missing) - len(safe)


from .organization_storage import OrganizationStorage
from .library_storage import LibraryStorage


from .knowledge_storage import KnowledgeStorage


class Catalog(KnowledgeStorage, LibraryStorage, OrganizationStorage, CatalogV8):
    """Current catalog; prior schemas migrate with a backup."""
