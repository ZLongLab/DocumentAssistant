"""Native editing for custom categories, explicit rules, reading notes and inboxes."""
import copy
from pathlib import Path
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QFormLayout,QLabel,QLineEdit,
    QPlainTextEdit,QComboBox,QDialogButtonBox,QPushButton,QCheckBox,QTableWidget,QTableWidgetItem,
    QMessageBox,QFileDialog,QAbstractItemView,QApplication)
from .document_metadata import READING_STATES,validate_category,category_rule_match,attention_rank
from .rules import CATEGORIES,categories_for,save_rules
from .watch_inbox import WatchWorker, DiscoveryCursor


def note(text):
    label=QLabel(text)
    label.setWordWrap(True)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class CategoryDialog(QDialog):
    def __init__(self,window):
        super().__init__(window)
        self.window=window
        self.setWindowTitle('自定义分类')
        self.resize(520,380)
        layout=QVBoxLayout(self)
        layout.addWidget(note('新增分类会成为新归档文件的目录名。关键词命中后给出建议，仍需确认归档。\n已有副本可修改检索分类，其所在目录保留。'))
        form=QFormLayout()
        self.name=QLineEdit()
        self.name.setPlaceholderText('例如：毕业论文草稿、比赛资料')
        self.words=QPlainTextEdit()
        self.words.setPlaceholderText('每行一个关键词，例如：论文结构、论文草稿')
        form.addRow('新分类名称',self.name)
        form.addRow('匹配关键词',self.words)
        layout.addLayout(form)
        layout.addWidget(note('已有分类：'+'、'.join(window.categories)))
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            name=validate_category(self.name.text())
            if name.casefold() in {c.casefold() for c in self.window.categories}:
                raise ValueError('这个分类已存在；修改关键词请进入分类规则')
            rules=copy.deepcopy(self.window.rules)
            rules['keywords'][name]=[s.strip() for s in self.words.toPlainText().splitlines() if s.strip()]
            self.window.install_category_rules(rules)
            self.accept()
        except Exception as exc:
            QMessageBox.warning(self,'分类需要修改',str(exc))


class RememberRuleDialog(QDialog):
    def __init__(self,window):
        super().__init__(window)
        self.window=window
        self.setWindowTitle('记住分类方式')
        self.resize(660,440)
        layout=QVBoxLayout(self)
        layout.addWidget(note('明确保存一条规则，让后续导入沿用你的分类。预览只展示影响范围。\n当前已人工确认的分类保留；同级规则冲突时提示人工选择。'))
        form=QFormLayout()
        self.source=QComboBox()
        self.source.addItem('文件名包含','filename')
        self.source.addItem('目录及子目录','folder')
        self.pattern=QLineEdit()
        self.category=QComboBox()
        self.category.addItems([c for c in window.categories if c!='待整理'])
        row=window.scan_table.currentRow()
        self.item=window.items[row] if 0<=row<len(window.items) else None
        if self.item:
            self.pattern.setText(self.item.path.stem[:100])
            self.category.setCurrentText(self.item.category)
        self.source.currentIndexChanged.connect(self.source_changed)
        for title,widget in (('匹配条件',self.source),('关键词 / 完整目录',self.pattern),('建议分类',self.category)):
            form.addRow(title,widget)
        layout.addLayout(form)
        self.preview=QPlainTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview,1)
        preview_button=QPushButton('预览会影响哪些文件')
        preview_button.clicked.connect(self.preview_rule)
        layout.addWidget(preview_button)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.preview_rule()

    def source_changed(self):
        if self.item:
            self.pattern.setText(str(self.item.path.parent) if self.source.currentData()=='folder' else self.item.path.stem[:100])
        self.preview.clear()

    def preview_rule(self):
        rule={'source':self.source.currentData(),'pattern':self.pattern.text().strip(),'category':self.category.currentText()}
        if not rule['pattern']:
            self.preview.setPlainText('请填写匹配条件。')
            return
        if rule['source']=='folder' and not Path(rule['pattern']).is_absolute():
            self.preview.setPlainText('目录规则需要完整路径。')
            return
        from .document_metadata import preview_category_rule
        existing=self.window.catalog.category_rules()
        lines=[]
        for item in self.window.items:
            result=preview_category_rule(item,rule,existing,self.window.rules)
            if result:
                category,reason=result
                lines.append(f'{item.path.name}：{item.category} → {category}\n  {reason}')
        self.preview.setPlainText('\n'.join(lines) or '当前待整理列表没有匹配项；规则保存后对后续导入生效。')

    def save(self):
        try:
            self.window.catalog.save_category_rule(self.source.currentData(),self.pattern.text(),self.category.currentText())
            self.window.statusBar().showMessage('分类方式已保存，对后续导入生效；可在“已保存分类方式”中删除。')
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self,'规则需要修改',str(exc))


class CategoryRulesDialog(QDialog):
    def __init__(self,window):
        super().__init__(window)
        self.window=window
        self.setWindowTitle('已保存分类方式')
        self.resize(720,380)
        layout=QVBoxLayout(self)
        layout.addWidget(note('删除规则只停止后续建议，已有分类和文件保留。'))
        self.table=QTableWidget(0,3)
        self.table.setHorizontalHeaderLabels(['匹配来源','条件','目标分类'])
        self.table.setColumnWidth(0,120)
        self.table.setColumnWidth(1,400)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table,1)
        row=QHBoxLayout()
        add=QPushButton('新增分类方式')
        delete=QPushButton('删除选中规则')
        close=QPushButton('关闭')
        for b in (add,delete,close):row.addWidget(b)
        add.clicked.connect(self.add)
        delete.clicked.connect(self.remove)
        close.clicked.connect(self.accept)
        layout.addLayout(row)
        self.reload()

    def reload(self):
        self.rows=self.window.catalog.category_rules()
        self.table.setRowCount(len(self.rows))
        for i,r in enumerate(self.rows):
            for col,value in enumerate(('文件名包含' if r['source']=='filename' else '目录及子目录',r['pattern'],r['category'])):
                cell=QTableWidgetItem(value);cell.setToolTip(value);self.table.setItem(i,col,cell)

    def add(self):
        RememberRuleDialog(self.window).exec()
        self.reload()

    def remove(self):
        row=self.table.currentRow()
        if row>=0:
            self.window.catalog.delete_category_rule(self.rows[row]['id'])
            self.reload()


class ReadingDialog(QDialog):
    def __init__(self,window,rows):
        super().__init__(window)
        self.window,self.rows=window,rows
        self.setWindowTitle('阅读状态与备注')
        self.resize(600,420)
        layout=QVBoxLayout(self)
        layout.addWidget(note(f'已选择 {len(rows)} 份归档文档。标题只改变界面显示，原文件名仍可搜索。'))
        form=QFormLayout()
        self.state=QComboBox()
        if len(rows)>1:self.state.addItem('保持各自阅读状态','')
        for state in READING_STATES:self.state.addItem(state,state)
        if len(rows)==1:self.state.setCurrentText(rows[0]['reading_state'])
        form.addRow('阅读状态',self.state)
        self.title=QLineEdit(rows[0]['display_title'])
        self.title.setMaxLength(250)
        if len(rows)==1:
            form.addRow('显示标题',self.title)
            form.addRow('标题来源',note(rows[0]['title_source'] or '文件名；可手动设置标题'))
            form.addRow('原文件名',note(rows[0]['filename']))
            if rows[0]['title_source'].startswith('文档元信息'):
                form.addRow('',note('文档元信息可能沿用旧标题，请结合原文件名核对。'))
            reset=QPushButton('恢复为文件名显示')
            reset.clicked.connect(lambda:self.title.clear())
            form.addRow('',reset)
        self.change_notes=QCheckBox('修改备注（留空表示清空）')
        self.change_notes.setChecked(len(rows)==1)
        self.notes=QPlainTextEdit(rows[0]['notes'] if len(rows)==1 else '')
        self.notes.setPlaceholderText('例如：这篇论文的指标定义可用于实验设计。最多 1 万字。')
        self.notes.setEnabled(self.change_notes.isChecked())
        self.change_notes.toggled.connect(self.notes.setEnabled)
        layout.addLayout(form)
        layout.addWidget(self.change_notes)
        layout.addWidget(self.notes,1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def save(self):
        try:
            state=self.state.currentData()
            notes=self.notes.toPlainText() if self.change_notes.isChecked() else None
            title=self.title.text() if len(self.rows)==1 and self.title.text()!=self.rows[0]['display_title'] else None
            if state:
                self.window.catalog.update_reading([r['id'] for r in self.rows],state,notes,title)
            else:
                for r in self.rows:self.window.catalog.update_reading([r['id']],r['reading_state'],notes)
            self.window.refresh_search()
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self,'阅读信息未保存',str(exc))


class WatchFolderDialog(QDialog):
    def __init__(self,window):
        super().__init__(window)
        self.window=window
        self.setWindowTitle('文件夹收件箱')
        self.resize(760,390)
        layout=QVBoxLayout(self)
        layout.addWidget(note('应用运行时每 10 秒检查指定目录及子目录。新增和变化文件两次检查稳定后进入待整理列表，由你确认归档。\n添加目录后也会检查现有文档；关闭应用时暂停，重新启动后继续。'))
        self.table=QTableWidget(0,2)
        self.table.setHorizontalHeaderLabels(['收件箱目录','监听状态'])
        self.table.setColumnWidth(0,570)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table,1)
        row=QHBoxLayout()
        for title,callback in (('添加文件夹',self.add),('暂停 / 启用',self.toggle),('移除监听',self.remove),('关闭',self.accept)):
            b=QPushButton(title);b.clicked.connect(callback);row.addWidget(b)
        layout.addLayout(row)
        self.reload()

    def reload(self):
        self.rows=self.window.catalog.watch_folders()
        self.table.setRowCount(len(self.rows))
        for i,r in enumerate(self.rows):
            self.table.setItem(i,0,QTableWidgetItem(r['path']))
            self.table.setItem(i,1,QTableWidgetItem('运行中' if r['enabled'] else '已暂停'))

    def add(self):
        path=QFileDialog.getExistingDirectory(self,'选择文档收件箱','D:/')
        if path:
            try:
                self.window.catalog.set_watch_folder(Path(path))
                self.window.reset_watch()
                self.reload()
            except ValueError as exc:QMessageBox.warning(self,'目录不可用',str(exc))

    def toggle(self):
        n=self.table.currentRow()
        if n>=0:
            r=self.rows[n]
            self.window.catalog.set_watch_folder(Path(r['path']),not r['enabled'])
            self.window.reset_watch();self.reload()

    def remove(self):
        n=self.table.currentRow()
        if n>=0:
            self.window.catalog.remove_watch_folder(self.rows[n]['path'])
            self.window.reset_watch();self.reload()


class KnowledgeActions:
    def init_knowledge(self):
        self.categories=categories_for(self.rules)
        self.review_order=self.settings.get('review_order','attention')
        self.watch_worker=None
        self.watch_generation=0
        self.watch_observed={}
        self.watch_cursor=DiscoveryCursor()
        self.watch_ready=[]
        self.watch_import=[]
        self.watch_timer=QTimer(self)
        self.watch_timer.setInterval(10000)
        self.watch_timer.timeout.connect(self.poll_watch)

    def install_category_rules(self,rules):
        from .rules import validate_rules
        rules=validate_rules(rules)
        names=categories_for(rules)
        # Validate and durably save global rules before enabling the new UI choices.
        if self.catalog:
            self.catalog.register_categories(names)
            for name in names:
                if name not in CATEGORIES:self.catalog.save_category_keywords(name,rules['keywords'][name])
        save_rules(self.rules_path,rules)
        self.rules=rules
        self.refresh_categories()

    def refresh_categories(self):
        names=categories_for(self.rules)
        if self.catalog:
            self.catalog.register_categories(names)
            names=self.catalog.category_names()
            definitions=self.catalog.category_keywords()
            for name in names:
                if name not in CATEGORIES:
                    if name in definitions:self.rules['keywords'][name]=definitions[name]
                    else:self.catalog.save_category_keywords(name,self.rules['keywords'].get(name,[]))
        self.categories=names
        for c in names:
            if c!='待整理':self.rules['keywords'].setdefault(c,[])
        if hasattr(self,'search_category'):
            old=self.search_category.currentText()
            blocked=self.search_category.blockSignals(True)
            self.search_category.clear();self.search_category.addItems(['全部分类',*names])
            self.search_category.setCurrentIndex(max(0,self.search_category.findText(old)))
            self.search_category.blockSignals(blocked)
            self.details_panel.combo.blockSignals(True)
            self.details_panel.combo.clear();self.details_panel.combo.addItems(names)
            self.details_panel.combo.blockSignals(False)
            self.populate_scan({str(i.path):i.selected for i in self.items})

    def manage_categories(self):
        if not self.worker:CategoryDialog(self).exec()

    def remember_category(self):
        if self.catalog and not self.worker:RememberRuleDialog(self).exec()

    def manage_category_rules(self):
        if self.catalog and not self.worker:CategoryRulesDialog(self).exec()

    def edit_reading(self):
        if not self.catalog or self.worker:return
        rows=[self.catalog.archive_by_id(self.archive_rows[i.row()]['id']) for i in self.search_table.selectionModel().selectedRows()]
        if rows and all(rows):ReadingDialog(self,rows).exec()

    def review_order_changed(self):
        self.review_order=self.review_sort.currentData()
        self.cards_view.page=0
        self.populate_scan({str(i.path):i.selected for i in self.items})
        self.save_settings()

    def manage_watch_folders(self):
        if self.catalog and not self.worker:WatchFolderDialog(self).exec()

    def reset_watch(self):
        self.watch_generation+=1
        self.watch_ready=[]
        self.watch_observed={}
        self.watch_cursor=DiscoveryCursor()
        if self.watch_worker:self.watch_worker.requestInterruption()
        if self.catalog and self.catalog.watch_folders(active=True):
            self.watch_timer.start()
            QTimer.singleShot(0,self.poll_watch)
        else:self.watch_timer.stop()

    def poll_watch(self):
        if self.closing or self.worker or self.watch_worker or not self.catalog or QApplication.activeModalWidget():return
        if not self.catalog.watch_folders(active=True):return
        self.watch_worker=WatchWorker(self.catalog,self.watch_observed,self.watch_generation,self,self.watch_cursor)
        self.watch_worker.completed.connect(self.watch_completed)
        self.watch_worker.finished.connect(self.watch_finished)
        self.watch_worker.start()

    def watch_completed(self,result):
        if self.closing or result['generation']!=self.watch_generation:return
        if 'error' in result:
            self.statusBar().showMessage('收件箱检查失败：'+result['error']);return
        if not self.catalog or result['library']!=self.catalog.library_id:return
        self.watch_observed=result['observed']
        self.watch_ready=result['ready']
        if result['warnings']:self.statusBar().showMessage(result['warnings'][0])

    def watch_finished(self):
        worker,self.watch_worker=self.watch_worker,None
        if worker:worker.deleteLater()
        if self.closing:
            QTimer.singleShot(0,self.close)
            return
        if self.watch_ready and self.catalog and not self.worker and not QApplication.activeModalWidget():
            ready,self.watch_ready=self.watch_ready,[]
            enabled={r['path'] for r in self.catalog.watch_folders(active=True)}
            ready=[r for r in ready if r[0] in enabled]
            known={str(i.path):i for i in self.items}
            existing=[known[path] for _,path,signature in ready if path in known and (known[path].size,known[path].mtime_ns)==signature]
            self.catalog.acknowledge_watch(ready,existing)
            fresh=[r for r in ready if r[1] not in known or (known[r[1]].size,known[r[1]].mtime_ns)!=r[2]]
            if fresh:
                self.watch_import=fresh
                self.import_files(list(dict.fromkeys(Path(r[1]) for r in fresh)))
