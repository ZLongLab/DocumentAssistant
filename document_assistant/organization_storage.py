"""Persistent inbox, normalized associations and revision-aware recovery."""
import json
import uuid
from pathlib import Path

from .organization import label_values, query_terms


class OrganizationStorage:
    def _upgrade(self):
        with self.connection() as db:
            meta_exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='library_meta'").fetchone()
            meta = dict(db.execute('SELECT key,value FROM library_meta')) if meta_exists else {}
            if meta.get('schema_version') == '6' and meta.get('root') == str(self.library):
                self.library_id = meta['id']
                self.fts_enabled = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='archive_fts'").fetchone())
                return
        super()._upgrade()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(documents)')}
            for field, definition in {
                'revision': 'INTEGER NOT NULL DEFAULT 0',
                'manual_fields': "TEXT NOT NULL DEFAULT ''",
                'inbox_state': "TEXT NOT NULL DEFAULT 'dismissed'",
                'queue_selected': 'INTEGER NOT NULL DEFAULT 1',
                'content_hash': "TEXT NOT NULL DEFAULT ''",
            }.items():
                if field not in columns:
                    db.execute(f'ALTER TABLE documents ADD COLUMN {field} {definition}')
            if 'manual_fields' not in columns:
                for row in db.execute('SELECT id,course,project,tags FROM documents').fetchall():
                    manual = ','.join(key for key in ('course', 'project', 'tags') if row[key])
                    db.execute('UPDATE documents SET manual_fields=? WHERE id=?', (manual, row['id']))
            if 'label_revision' not in {r['name'] for r in db.execute('PRAGMA table_info(archives)')}:
                db.execute('ALTER TABLE archives ADD COLUMN label_revision INTEGER NOT NULL DEFAULT 0')
            db.execute('''CREATE TABLE IF NOT EXISTS archive_labels (
                archive_id INTEGER NOT NULL REFERENCES archives(id) ON DELETE CASCADE,
                field TEXT NOT NULL CHECK(field IN ('course','project','tags')), value TEXT NOT NULL,
                PRIMARY KEY(archive_id,field,value))''')
            db.execute('CREATE INDEX IF NOT EXISTS archive_labels_value ON archive_labels(field,value,archive_id)')
            db.execute('''CREATE TABLE IF NOT EXISTS archive_sources (
                archive_id INTEGER NOT NULL REFERENCES archives(id) ON DELETE CASCADE,
                document_id INTEGER NOT NULL REFERENCES documents(id),
                source_path TEXT NOT NULL, filename TEXT NOT NULL,
                PRIMARY KEY(archive_id,document_id))''')
            db.execute('CREATE INDEX IF NOT EXISTS inbox_state_index ON documents(inbox_state,id)')
            db.execute('''CREATE TABLE IF NOT EXISTS saved_views (
                id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, filters TEXT NOT NULL)''')
            for row in db.execute('SELECT id,document_id,source_path,filename,course,project,tags FROM archives').fetchall():
                for field in ('course', 'project', 'tags'):
                    self._write_labels(db, row['id'], field, row[field])
                db.execute('INSERT OR IGNORE INTO archive_sources VALUES (?,?,?,?)',
                           (row['id'], row['document_id'], row['source_path'], row['filename']))
            from .library_storage import LibraryStorage
            LibraryStorage.upgrade_library(db)
            if 'extraction_status' not in {r['name'] for r in db.execute('PRAGMA table_info(archives)')}:
                db.execute("ALTER TABLE archives ADD COLUMN extraction_status TEXT NOT NULL DEFAULT ''")
            from .knowledge_storage import KnowledgeStorage
            KnowledgeStorage.upgrade_knowledge(db)
            self.fts_enabled = bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='archive_fts'").fetchone())
            db.execute("UPDATE library_meta SET value='6' WHERE key='schema_version'")

    @staticmethod
    def _write_labels(db, ident, field, text, replace=True):
        if replace:
            db.execute('DELETE FROM archive_labels WHERE archive_id=? AND field=?', (ident, field))
        db.executemany('INSERT OR IGNORE INTO archive_labels VALUES (?,?,?)',
                       [(ident, field, value) for value in label_values(text)])

    @staticmethod
    def _flatten_labels(db, ident):
        values = {field: ', '.join(r[0] for r in db.execute(
            'SELECT value FROM archive_labels WHERE archive_id=? AND field=? ORDER BY rowid', (ident, field)))
            for field in ('course', 'project', 'tags')}
        db.execute('UPDATE archives SET course=?,project=?,tags=?,label_revision=label_revision+1 WHERE id=?',
                   (*values.values(), ident))

    def document_metadata(self, path):
        with self.connection() as db:
            row = db.execute('SELECT revision,manual_fields FROM documents WHERE source_path=?', (str(path),)).fetchone()
            return dict(row) if row else {'revision': 0, 'manual_fields': ''}

    def save_scan(self, item):
        with self.connection() as db:
            db.execute('''INSERT INTO documents
                (source_path,filename,size,mtime_ns,extraction_status,body,suggested_category,category,reason,
                 course,project,tags,revision,manual_fields,inbox_state,queue_selected,content_hash)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1,?,'review',?,?)
                ON CONFLICT(source_path) DO UPDATE SET filename=excluded.filename,size=excluded.size,
                mtime_ns=excluded.mtime_ns,extraction_status=excluded.extraction_status,body=excluded.body,
                suggested_category=excluded.suggested_category,category=excluded.category,reason=excluded.reason,
                course=excluded.course,project=excluded.project,tags=excluded.tags,revision=documents.revision+1,
                manual_fields=excluded.manual_fields,inbox_state='review',queue_selected=excluded.queue_selected,
                content_hash=excluded.content_hash,scanned_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')''',
                (str(item.path), item.path.name, item.size, item.mtime_ns, item.status, item.body, item.suggested,
                 item.category, item.reason, item.course, item.project, item.tags,
                 getattr(item, 'manual_fields', ''), int(getattr(item, 'selected', True)), getattr(item, 'content_hash', '')))
            row = db.execute('SELECT id,revision FROM documents WHERE source_path=?', (str(item.path),)).fetchone()
            item.revision = row['revision']
            db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                       (row['id'], '扫描', item.status + '；' + item.reason))
            ident=row['id']
        item.doc_id=ident
        self.save_document_metadata(item)
        return ident

    def inbox(self):
        from .service import ScanItem
        with self.connection() as db:
            rows = db.execute("SELECT * FROM documents WHERE inbox_state='review' ORDER BY id").fetchall()
        return [ScanItem(Path(r['source_path']), r['size'], r['mtime_ns'], r['body'], r['extraction_status'],
                         r['suggested_category'], r['category'], r['reason'], doc_id=r['id'], course=r['course'],
                         project=r['project'], tags=r['tags'], content_hash=r['content_hash'], revision=r['revision'],
                         manual_fields=r['manual_fields'], selected=bool(r['queue_selected']), display_title=r['display_title'], title_source=r['title_source']) for r in rows]

    def dismiss_inbox(self, ids):
        with self.connection() as db:
            db.executemany("UPDATE documents SET inbox_state='dismissed' WHERE id=?", [(i,) for i in ids if i is not None])

    def save_selection(self, selections):
        with self.connection() as db:
            db.executemany('UPDATE documents SET queue_selected=? WHERE id=?',
                           [(int(selected), ident) for ident, selected in selections if ident is not None])

    @staticmethod
    def _complete_source(db, item):
        # Older journals have no revision: recover the archive without replacing current edits.
        revision = getattr(item, 'revision', 0)
        if revision:
            db.execute("UPDATE documents SET category=?,inbox_state='archived',queue_selected=0 WHERE id=? AND revision=?",
                       (item.category, item.doc_id, revision))

    def record_archive(self, item, target, digest):
        relative = str(target.relative_to(self.library))
        with self.connection() as db:
            self._complete_source(db, item)
            cursor = db.execute('''INSERT INTO archives(document_id,source_path,archive_path,filename,category,sha256,
                relative_path,body_snapshot,course,project,tags,batch_id,extraction_status,display_title,title_source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (item.doc_id, str(item.path), str(target), item.path.name, item.category, digest, relative, item.body,
                 item.course, item.project, item.tags, getattr(item, '_batch_id', ''), item.status, item.display_title, item.title_source))
            ident = cursor.lastrowid
            for field in ('course', 'project', 'tags'):
                self._write_labels(db, ident, field, getattr(item, field))
            self._flatten_labels(db, ident)
            db.execute('INSERT INTO archive_sources VALUES (?,?,?,?)', (ident, item.doc_id, str(item.path), item.path.name))
            db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                       (item.doc_id, '复制归档', json.dumps({'来源': str(item.path), '目标': str(target), '分类': item.category, 'sha256': digest}, ensure_ascii=False)))
            task_id = getattr(item, '_archive_task_id', None)
            if task_id:
                db.execute('DELETE FROM pending_archives WHERE id=?', (task_id,))

    def associate_archive(self, item, archive_id, *, merge=True):
        with self.connection() as db:
            if not db.execute('SELECT 1 FROM archives WHERE id=?', (archive_id,)).fetchone():
                raise ValueError('已有文档记录已变化，请刷新后重试')
            if merge:
                for field in ('course', 'project', 'tags'):
                    self._write_labels(db, archive_id, field, getattr(item, field), replace=False)
                self._flatten_labels(db, archive_id)
                db.execute('INSERT OR IGNORE INTO archive_sources VALUES (?,?,?,?)',
                           (archive_id, item.doc_id, str(item.path), item.path.name))
            self._complete_source(db, item)
            db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                       (item.doc_id, '关联已有文档' if merge else '跳过相同内容', str(archive_id)))

    def existing_archives(self, doc_id, category, digest):
        with self.connection() as db:
            return db.execute('''SELECT * FROM archives WHERE sha256=? AND
                (document_id=? AND category=? OR document_id<>? AND EXISTS(SELECT 1 FROM archive_sources s
                WHERE s.archive_id=archives.id AND s.document_id=?))''', (digest, doc_id, category, doc_id, doc_id)).fetchall()

    def change_category(self, doc_id, category):
        self.change_labels([doc_id], {'category': category})
        self.log(doc_id, '修改分类', category)

    def change_labels(self, ids, updates, *, archives=False):
        from .rules import CATEGORIES
        if not updates or not set(updates) <= {'course', 'project', 'tags', 'category'}:
            raise ValueError('无效标签字段')
        if 'category' in updates and updates['category'] not in self.category_names():
            raise ValueError('无效分类')
        if any(not isinstance(v, str) or len(v) > 300 for v in updates.values()):
            raise ValueError('标签必须为文本，且每项不超过300字')
        table = 'archives' if archives else 'documents'
        with self.connection() as db:
            for ident in ids:
                row = db.execute(f'SELECT * FROM {table} WHERE id=?', (ident,)).fetchone()
                if not row:
                    continue
                db.execute(f'UPDATE {table} SET ' + ','.join(f'{key}=?' for key in updates) + ' WHERE id=?', [*updates.values(), ident])
                if archives:
                    for field in ('course', 'project', 'tags'):
                        if field in updates:
                            self._write_labels(db, ident, field, updates[field])
                    self._flatten_labels(db, ident)
                else:
                    manual = set(row['manual_fields'].split(',')) - {''}
                    manual.update(set(updates) & {'course', 'project', 'tags','category'})
                    db.execute("UPDATE documents SET revision=revision+1,manual_fields=?,inbox_state='review' WHERE id=?", (','.join(sorted(manual)), ident))
                db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                           (row['document_id'] if archives else ident, '修改归档标签' if archives else '修改标签',
                            json.dumps({'记录': ident, '修改': updates}, ensure_ascii=False)))

    def _where(self, query, category, course='', project='', scope='all', tag='', quality='', reading=''):
        fields = ('filename',) if scope == 'filename' else ('filename', 'body_snapshot', 'course', 'project', 'tags', 'display_title','notes')
        clauses, params = [], []
        for term in query_terms(query):
            if scope == 'all' and len(term) >= 3 and self.fts_enabled:
                part = 'id IN (SELECT rowid FROM archive_fts WHERE archive_fts MATCH ?)'
                params.append('"' + term.replace('"', '""') + '"')
            else:
                part = '(' + ' OR '.join(f'instr(lower({f}),lower(?))>0' for f in fields) + ')'
                params.extend([term] * len(fields))
            part += ' OR EXISTS(SELECT 1 FROM archive_sources s WHERE s.archive_id=archives.id AND instr(lower(s.filename),lower(?))>0)'
            params.append(term)
            clauses.append('(' + part + ')')
        if category:
            clauses.append('category=?')
            params.append(category)
        for field, value in (('course', course), ('project', project), ('tags', tag)):
            if value:
                clauses.append('EXISTS(SELECT 1 FROM archive_labels l WHERE l.archive_id=archives.id AND l.field=? AND l.value=?)')
                params.extend([field, value])
        quality_clauses = {
            '': '1', 'complete': "extraction_status LIKE '已提取%' AND instr(extraction_status,'截断')=0",
            'partial': "instr(extraction_status,'截断')>0",
            'none': "extraction_status<>'' AND extraction_status NOT LIKE '已提取%'",
            'unknown': "extraction_status=''"}
        if quality not in quality_clauses:
            raise ValueError('无效的正文范围筛选')
        if quality:
            clauses.append('('+quality_clauses[quality]+')')
        if reading:
            from .document_metadata import READING_STATES
            if reading not in READING_STATES:
                raise ValueError('阅读状态筛选无效')
            clauses.append('reading_state=?')
            params.append(reading)
        return ' AND '.join(clauses) or '1', params

    def search(self, filename='', category='', *, course='', project='', limit=None, offset=0, scope='all', tag='', quality='', sort='newest', reading=''):
        where, params = self._where(filename, category, course, project, scope, tag, quality, reading)
        sql = 'SELECT * FROM archives WHERE ' + where + ' ORDER BY ' + self.search_order(sort)
        if limit is not None:
            sql += ' LIMIT ? OFFSET ?'
            params += [max(1, min(500, int(limit))), max(0, int(offset))]
        with self.connection() as db:
            return db.execute(sql, params).fetchall()

    def search_count(self, query='', category='', *, course='', project='', scope='all', tag='', quality='', sort='newest', reading=''):
        self.search_order(sort)
        where, params = self._where(query, category, course, project, scope, tag, quality, reading)
        with self.connection() as db:
            return db.execute('SELECT COUNT(*) FROM archives WHERE ' + where, params).fetchone()[0]

    @staticmethod
    def search_order(sort):
        orders = {'newest':'created_at DESC,id DESC', 'oldest':'created_at ASC,id ASC',
                  'name':"coalesce(nullif(display_title,''),filename) COLLATE NOCASE ASC,id ASC"}
        if sort not in orders:
            raise ValueError('无效排序方式')
        return orders[sort]

    def search_page_data(self, query, page=0, size=100, cancelled=lambda:False, **filters):
        # One read transaction keeps count and page consistent with concurrent writes.
        where, params = self._where(query, filters.get('category',''), filters.get('course',''),
            filters.get('project',''), filters.get('scope','all'), filters.get('tag',''), filters.get('quality',''),filters.get('reading',''))
        order = self.search_order(filters.get('sort','newest'))
        size = max(1,min(100,int(size)))
        with self.connection() as db:
            db.set_progress_handler(lambda:int(cancelled()),1000)
            db.execute('BEGIN')
            count = db.execute('SELECT COUNT(*) FROM archives WHERE '+where,params).fetchone()[0]
            page = min(max(0,int(page)),max(0,(count-1)//size))
            # SQL only returns a bounded excerpt; full bodies are fetched on preview.
            terms = query_terms(query)
            if terms:
                # SQLite scalar min propagates NULL; use a large sentinel for absent terms.
                positions = ','.join('coalesce(NULLIF(instr(lower(body_snapshot),lower(?)),0),100001)' for _ in terms)
                position = ('min('+positions+')' if len(terms)>1 else positions)
                snippet_sql = 'substr(body_snapshot,max(1,'+position+'-30),180)'
                snippet_params = terms
            else:
                snippet_sql, snippet_params = "''", []
            columns = [r['name'] for r in db.execute('PRAGMA table_info(archives)') if r['name'] != 'body_snapshot']
            sql = 'SELECT '+','.join(columns)+','+snippet_sql+' AS body_snippet FROM archives WHERE '+where+' ORDER BY '+order+' LIMIT ? OFFSET ?'
            rows = [dict(r) for r in db.execute(sql,[*snippet_params,*params,size,page*size])]
        for row in rows:
            row['body_snippet'] = row['body_snippet'].replace('\n',' ').replace('\r',' ')
            if query and not row['body_snippet']:
                from .search_text import body_snippet
                row['body_snippet']=body_snippet(row['notes'],query)
        return count,page,rows

    def archive_by_id(self, ident):
        with self.connection() as db:
            row = db.execute('SELECT * FROM archives WHERE id=?',(ident,)).fetchone()
            return dict(row) if row else None

    def update_extraction(self, ident, body, status, title=None, title_source=''):
        with self.connection() as db:
            db.execute('UPDATE archives SET body_snapshot=?,extraction_status=? WHERE id=?',(body[:100000],status,ident))
            if title is not None:
                db.execute("UPDATE archives SET display_title=?,title_source=? WHERE id=? AND title_source<>'手动设置'",(title,title_source,ident))

    def label_options(self, field):
        if field not in ('course', 'project', 'tags'):
            raise ValueError('无效字段')
        with self.connection() as db:
            values = [r[0] for r in db.execute('SELECT DISTINCT value FROM archive_labels WHERE field=? ORDER BY value', (field,))]
            for row in db.execute(f'SELECT DISTINCT {field} FROM documents'):
                values.extend(label_values(row[0]))
            return sorted(set(values), key=str.casefold)

    @staticmethod
    def _undo_matches(row, metadata):
        # Root relocation changes only archive_path; still verify every reviewed content/label field.
        return all(key in row.keys() and row[key] == value for key, value in metadata.items() if key != 'archive_path')

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
                db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',
                           (row['document_id'], '撤销归档', json.dumps({'归档': dict(row), '保留副本': task['trash_relative']}, ensure_ascii=False)))
                db.execute('DELETE FROM archives WHERE id=?', (row['id'],))
            db.execute('DELETE FROM pending_undo WHERE id=?', (task_id,))

    def cancel_unstarted_undo(self, task_id):
        with self.connection() as db:
            db.execute('DELETE FROM pending_undo WHERE id=?', (task_id,))

    def saved_views(self):
        with self.connection() as db:
            return [{'id': r['id'], 'name': r['name'], 'filters': json.loads(r['filters'])}
                    for r in db.execute('SELECT * FROM saved_views ORDER BY name')]

    def save_view(self, name, filters):
        if not name.strip() or len(name) > 80:
            raise ValueError('视图名称应为 1–80 字')
        if not {'query', 'category', 'course', 'project', 'tag', 'scope'} <= set(filters) <= {'query', 'category', 'course', 'project', 'tag', 'scope', 'sort', 'quality','reading'} or any(not isinstance(v, str) or len(v) > 300 for v in filters.values()):
            raise ValueError('筛选条件无效或过长')
        with self.connection() as db:
            db.execute('INSERT INTO saved_views VALUES (?,?,?) ON CONFLICT(name) DO UPDATE SET filters=excluded.filters',
                       (uuid.uuid4().hex, name.strip(), json.dumps(filters, ensure_ascii=False)))

    def delete_view(self, ident):
        with self.connection() as db:
            db.execute('DELETE FROM saved_views WHERE id=?', (ident,))
