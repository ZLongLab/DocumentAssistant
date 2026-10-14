"""Library-owned custom categories, metadata, saved choices and watched inboxes."""
import uuid
import sqlite3
import json
from pathlib import Path
from .document_metadata import PARSER_VERSION, READING_STATES, validate_category
from .rules import CATEGORIES


class KnowledgeStorage:
    @staticmethod
    def upgrade_knowledge(db):
        for table, fields in (
            ('documents', {'display_title':"TEXT NOT NULL DEFAULT ''",'title_source':"TEXT NOT NULL DEFAULT ''",'parser_version':"TEXT NOT NULL DEFAULT ''"}),
            ('archives', {'display_title':"TEXT NOT NULL DEFAULT ''",'title_source':"TEXT NOT NULL DEFAULT ''",'reading_state':"TEXT NOT NULL DEFAULT '未读'",'notes':"TEXT NOT NULL DEFAULT ''"}),
        ):
            columns={r['name'] for r in db.execute(f'PRAGMA table_info({table})')}
            for name, definition in fields.items():
                if name not in columns:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {definition}')
        db.execute('CREATE TABLE IF NOT EXISTS category_names(name TEXT PRIMARY KEY COLLATE NOCASE)')
        db.executemany('INSERT OR IGNORE INTO category_names VALUES (?)',[(c,) for c in CATEGORIES])
        db.execute('CREATE TABLE IF NOT EXISTS category_definitions(name TEXT PRIMARY KEY REFERENCES category_names(name),keywords TEXT NOT NULL)')
        for row in db.execute('SELECT category FROM archives UNION SELECT category FROM documents'):
            db.execute('INSERT OR IGNORE INTO category_names VALUES (?)',(validate_category(row[0]),))
        db.execute('''CREATE TABLE IF NOT EXISTS category_rules(id TEXT PRIMARY KEY,
            source TEXT NOT NULL CHECK(source IN ('filename','folder')),pattern TEXT NOT NULL,
            category TEXT NOT NULL REFERENCES category_names(name),UNIQUE(source,pattern))''')
        db.execute('CREATE TABLE IF NOT EXISTS watch_folders(path TEXT PRIMARY KEY,enabled INTEGER NOT NULL DEFAULT 1)')
        db.execute('''CREATE TABLE IF NOT EXISTS watch_seen(folder TEXT NOT NULL REFERENCES watch_folders(path) ON DELETE CASCADE,
            source_path TEXT NOT NULL,size INTEGER NOT NULL,mtime_ns INTEGER NOT NULL,PRIMARY KEY(folder,source_path))''')
        # Rebuild FTS in the same migration transaction so titles and notes are searchable.
        for name in ('archive_fts_insert','archive_fts_delete','archive_fts_update'):
            db.execute(f'DROP TRIGGER IF EXISTS {name}')
        db.execute('DROP TABLE IF EXISTS archive_fts')
        try:
            fields='filename,body_snapshot,course,project,tags,display_title,notes'
            db.execute(f"CREATE VIRTUAL TABLE archive_fts USING fts5({fields},content='archives',content_rowid='id',tokenize='trigram')")
            db.execute(f'CREATE TRIGGER archive_fts_insert AFTER INSERT ON archives BEGIN INSERT INTO archive_fts(rowid,{fields}) VALUES(new.id,'+','.join('new.'+f for f in fields.split(','))+'); END')
            db.execute(f"CREATE TRIGGER archive_fts_delete AFTER DELETE ON archives BEGIN INSERT INTO archive_fts(archive_fts,rowid,{fields}) VALUES('delete',old.id,"+','.join('old.'+f for f in fields.split(','))+'); END')
            db.execute(f"CREATE TRIGGER archive_fts_update AFTER UPDATE ON archives BEGIN INSERT INTO archive_fts(archive_fts,rowid,{fields}) VALUES('delete',old.id,"+','.join('old.'+f for f in fields.split(','))+f'); INSERT INTO archive_fts(rowid,{fields}) VALUES(new.id,'+','.join('new.'+f for f in fields.split(','))+'); END')
            db.execute("INSERT INTO archive_fts(archive_fts) VALUES('rebuild')")
        except sqlite3.OperationalError as exc:
            if 'no such module' not in str(exc):
                raise

    def category_names(self):
        with self.connection() as db:
            names=[r[0] for r in db.execute('SELECT name FROM category_names ORDER BY rowid')]
        return [*CATEGORIES[:-1],*(n for n in names if n not in CATEGORIES),'待整理']

    def register_categories(self, names):
        names=list(dict.fromkeys(validate_category(n) for n in names))
        if len({n.casefold() for n in names})!=len(names):
            raise ValueError('分类名称不能仅大小写不同')
        with self.connection() as db:
            old={r[0].casefold():r[0] for r in db.execute('SELECT name FROM category_names')}
            if len(set(old)|{n.casefold() for n in names})>50:
                raise ValueError('最多建立 50 个分类')
            if any(n.casefold() in old and old[n.casefold()]!=n for n in names):
                raise ValueError('分类名称与已有分类仅大小写不同')
            db.executemany('INSERT OR IGNORE INTO category_names VALUES (?)',[(n,) for n in names])

    def cached_extraction(self, path, digest):
        with self.connection() as db:
            row=db.execute('SELECT body,extraction_status,display_title,title_source,content_hash FROM documents WHERE source_path=? AND content_hash=? AND parser_version=?',
                (str(path),digest,PARSER_VERSION)).fetchone()
        return dict(row) if row and row['extraction_status'].startswith('已提取') else None

    def confirmed_category(self,path,digest):
        with self.connection() as db:
            row=db.execute("SELECT category FROM documents WHERE source_path=? AND content_hash=? AND (category<>suggested_category OR instr(','||manual_fields||',',',category,')>0)",(str(path),digest)).fetchone()
            return row[0] if row else None

    def save_document_metadata(self, item):
        with self.connection() as db:
            db.execute('UPDATE documents SET display_title=?,title_source=?,parser_version=? WHERE id=?',
                (item.display_title,item.title_source,PARSER_VERSION,item.doc_id))

    def category_rules(self):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM category_rules ORDER BY rowid')]

    def category_keywords(self):
        with self.connection() as db:
            return {r['name']:json.loads(r['keywords']) for r in db.execute('SELECT * FROM category_definitions')}

    def save_category_keywords(self,name,words):
        if name in CATEGORIES or name not in self.category_names() or not isinstance(words,list) or len(words)>500 or any(not isinstance(w,str) or not w.strip() or len(w)>100 for w in words):
            raise ValueError('自定义分类关键词无效')
        with self.connection() as db:
            db.execute('INSERT INTO category_definitions VALUES (?,?) ON CONFLICT(name) DO UPDATE SET keywords=excluded.keywords',(name,json.dumps(words,ensure_ascii=False)))

    def save_category_rule(self, source, pattern, category):
        if category not in self.category_names() or category=='待整理':
            raise ValueError('请选择有效的目标分类')
        if source not in ('filename','folder') or not isinstance(pattern,str) or not pattern.strip() or len(pattern)>4000:
            raise ValueError('规则条件无效')
        pattern=pattern.strip()
        if source=='folder':
            if not Path(pattern).is_absolute():
                raise ValueError('目录规则需要完整路径')
            pattern=str(Path(pattern).resolve())
        elif len(pattern)>100:
            raise ValueError('文件名关键词最多 100 字')
        with self.connection() as db:
            db.execute('INSERT INTO category_rules VALUES (?,?,?,?) ON CONFLICT(source,pattern) DO UPDATE SET category=excluded.category',
                (uuid.uuid4().hex,source,pattern,category))

    def delete_category_rule(self, ident):
        with self.connection() as db:
            db.execute('DELETE FROM category_rules WHERE id=?',(ident,))

    def update_reading(self, ids, state, notes=None, title=None):
        if state not in READING_STATES or notes is not None and (not isinstance(notes,str) or len(notes)>10000) or title is not None and (not isinstance(title,str) or len(title)>250):
            raise ValueError('阅读状态、备注或标题无效')
        with self.connection() as db:
            for ident in ids:
                row=db.execute('SELECT document_id FROM archives WHERE id=?',(ident,)).fetchone()
                if not row:
                    raise ValueError('归档记录已变化，请刷新')
                values={'reading_state':state}
                if notes is not None:values['notes']=notes
                if title is not None:values.update(display_title=title.strip(),title_source='手动设置')
                db.execute('UPDATE archives SET '+','.join(k+'=?' for k in values)+' WHERE id=?',[*values.values(),ident])
                db.execute('INSERT INTO operations(document_id,action,detail) VALUES (?,?,?)',(row[0],'更新阅读信息',str(ident)))

    def watch_folders(self, active=False):
        with self.connection() as db:
            return [dict(r) for r in db.execute('SELECT * FROM watch_folders'+(' WHERE enabled=1' if active else '')+' ORDER BY path')]

    def set_watch_folder(self, path, enabled=True):
        from .watch_inbox import validate_watch_folder
        path=validate_watch_folder(path,self.library)
        with self.connection() as db:
            db.execute('INSERT INTO watch_folders VALUES (?,?) ON CONFLICT(path) DO UPDATE SET enabled=excluded.enabled',(str(path),int(enabled)))

    def remove_watch_folder(self, path):
        with self.connection() as db:
            db.execute('DELETE FROM watch_folders WHERE path=?',(str(path),))

    def watch_seen(self):
        with self.connection() as db:
            return {(r['folder'],r['source_path']):(r['size'],r['mtime_ns']) for r in db.execute('SELECT * FROM watch_seen')}

    def acknowledge_watch(self, observations, items):
        completed={str(i.path):(i.size,i.mtime_ns) for i in items}
        with self.connection() as db:
            for folder,path,signature in observations:
                if completed.get(path)==tuple(signature) and db.execute('SELECT 1 FROM watch_folders WHERE path=? AND enabled=1',(folder,)).fetchone():
                    db.execute('INSERT INTO watch_seen VALUES (?,?,?,?) ON CONFLICT(folder,source_path) DO UPDATE SET size=excluded.size,mtime_ns=excluded.mtime_ns',
                        (folder,path,*signature))
