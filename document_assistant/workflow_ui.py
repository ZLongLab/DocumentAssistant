"""Explicit user actions for organizing, recovery and archive maintenance."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QCheckBox, QComboBox, QCompleter, QDialog, QDialogButtonBox, QFormLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QVBoxLayout
from .rules import CATEGORIES
from .archive import recover_pending, undo_batch, index_archives
from .organization_ui import OrganizationActions
from .library_ui import LibraryActions


class OrganizeDialog(QDialog):
    def __init__(self, parent, archives=False):
        super().__init__(parent)
        self.setWindowTitle('批量分类与标签' if not archives else '编辑归档分类与标签')
        self.resize(500,320)
        layout = QVBoxLayout(self)
        note = QLabel('仅更新勾选的字段；空白表示清空该字段。'+
            ('\n归档分类仅更新检索记录，不移动磁盘副本。' if archives else '\n标签随本次归档保存；已有归档请在文档库编辑。'))
        note.setWordWrap(True)
        layout.addWidget(note)
        form = QFormLayout()
        self.category = QComboBox()
        self.category.addItems(['保持原分类',*parent.categories])
        form.addRow('分类',self.category)
        self.fields = {}
        for key, label in (('course','课程'),('project','项目'),('tags','主题标签')):
            check = QCheckBox('更改'+label)
            edit = QLineEdit()
            edit.setMaxLength(300)
            edit.setPlaceholderText('多个课程、项目或标签用逗号分隔')
            if parent.catalog:
                completer = QCompleter(parent.catalog.label_options(key), edit)
                completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
                edit.setCompleter(completer)
            edit.setEnabled(False)
            check.toggled.connect(edit.setEnabled)
            form.addRow(check,edit)
            self.fields[key] = (check,edit)
        layout.addLayout(form)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def updates(self):
        result = {key:edit.text().strip() for key,(check,edit) in self.fields.items() if check.isChecked()}
        if self.category.currentIndex()>0:
            result['category'] = self.category.currentText()
        return result


class WorkflowActions(OrganizationActions, LibraryActions):
    def selected_scan_rows(self):
        return [row for row in range(len(self.items)) if self.scan_table.item(row,0).checkState()==Qt.CheckState.Checked]

    def toggle_review_view(self):
        self.review_mode = 'list' if self.review_mode=='cards' else 'cards'
        self.view_button.setText('卡片视图' if self.review_mode=='list' else '列表视图')
        if self.review_mode=='list':
            self.details_panel.hide()
            self.scan_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.scan_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
            self.scan_table.setColumnWidth(0,44)
        else:
            self.details_panel.show()
        self.cards_view.rebuild()
        self.review_stack.setCurrentIndex(0 if not self.items else 2 if self.review_mode=='list' else 1)
        self.save_settings()

    def reread_selected(self):
        rows = self.selected_scan_rows()
        if not rows:
            QMessageBox.information(self,'请选择文件','勾选需要重新读取的文件。')
            return
        self.import_files([self.items[row].path for row in rows],force=True)

    def bulk_organize(self):
        if not self.selected_scan_rows():
            QMessageBox.information(self,'请选择文件','勾选需要批量整理的文件。')
            return
        dialog = OrganizeDialog(self)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.apply_bulk_updates(dialog.updates())

    def edit_archive_labels(self):
        if not self.catalog or not self.search_table.selectionModel().selectedRows():
            QMessageBox.information(self,'请选择文件','在文档库列表中选中需要编辑的文件，可用 Ctrl 或 Shift 多选。')
            return
        dialog = OrganizeDialog(self,archives=True)
        if dialog.exec()==QDialog.DialogCode.Accepted:
            self.apply_bulk_updates(dialog.updates(),archives=True)

    def apply_bulk_updates(self,updates,archives=False):
        if not updates:
            return
        try:
            if archives:
                ids = [self.archive_rows[index.row()]['id'] for index in self.search_table.selectionModel().selectedRows()]
                self.catalog.change_labels(ids,updates,archives=True)
                self.archive_statuses.clear()
                for row in range(len(self.items)):
                    self.update_scan_status(row)
                self.refresh_search()
                self.update_selection()
            else:
                rows = self.selected_scan_rows()
                if self.catalog:
                    for row in rows:
                        if self.items[row].doc_id is None:
                            self.items[row].doc_id = self.catalog.save_scan(self.items[row])
                    self.catalog.change_labels([self.items[row].doc_id for row in rows],updates)
                selected = {str(item.path):self.scan_table.item(row,0).checkState()==Qt.CheckState.Checked for row,item in enumerate(self.items)}
                for row in rows:
                    item = self.items[row]
                    for key,value in updates.items():
                        setattr(item,key,value)
                    if self.catalog:
                        self.sync_document_revision(item)
                    else:
                        item.manual_fields = ','.join(sorted(set(item.manual_fields.split(',')) - {''} | (set(updates) & {'course','project','tags','category'})))
                    if 'category' in updates:
                        self.archive_statuses.pop(str(item.path),None)
                self.populate_scan(selected)
            self.save_loose_queue()
            self.refresh_filter_options()
            self.statusBar().showMessage('分类与标签已保存；可按课程、项目或主题搜索。')
        except Exception as exc:
            QMessageBox.warning(self,'保存失败',str(exc))

    def reset_search(self):
        self.search_page = 0
        self.refresh_search()

    def change_search_page(self,delta):
        pages = max(1,(self.search_total+self.page_size-1)//self.page_size)
        self.search_page = max(0,min(pages-1,self.search_page+delta))
        self.refresh_search()

    def backup_library(self):
        if self.catalog and self.worker is None:
            try:
                target = self.catalog.backup()
                QMessageBox.information(self,'数据库已备份',f'元信息、标签和记录已备份到：\n{target}\n\n此备份不包含文档副本。')
            except Exception as exc:
                QMessageBox.warning(self,'备份失败',str(exc))

    def recover_archives(self):
        if not self.catalog or self.worker:
            return
        if QMessageBox.question(self,'恢复未完成归档','检查当前文档库的中断任务，校验后恢复登记。\n不完整副本会保留在隔离目录，原文件保留。',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            return
        catalog = self.catalog
        self.launch_worker(lambda p,c:recover_pending(catalog,p,c),self.maintenance_finished)

    def undo_last_archive(self):
        if not self.catalog or self.worker:
            return
        rows = self.catalog.latest_batch()
        if not rows:
            QMessageBox.information(self,'暂无可撤销批次','可撤销本次升级后创建的归档批次。')
            return
        if QMessageBox.question(self,'撤销最近归档',f'撤销最近一批 {len(rows)} 个归档记录？\n校验未变化的副本会移入文档库的 .documentassistant/undo 恢复区。\n原文件和被修改过的副本保留，数据库先备份。',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            return
        catalog = self.catalog
        self.launch_worker(lambda p,c:undo_batch(catalog,rows,p,c),self.maintenance_finished)

    def rebuild_body_index(self):
        if not self.catalog or self.worker:
            return
        if QMessageBox.question(self,'更新正文索引','读取当前库中的归档副本以更新正文搜索。\n用于旧版本归档记录；文件内容不会修改。\n扫描件仍需 OCR，本版不支持 OCR。',
            QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes:
            return
        catalog = self.catalog
        self.launch_worker(lambda p,c:index_archives(catalog,p,c),self.maintenance_finished)

    def maintenance_finished(self,messages):
        self.archive_statuses.clear()
        for row in range(len(self.items)):
            self.update_scan_status(row)
        self.refresh_search()
        self.refresh_filter_options()
        self.detail.setPlainText('\n'.join(messages))
        self.statusBar().showMessage(f'处理结束，共 {len(messages)} 条结果。')
        QMessageBox.information(self,'处理结果','\n'.join(messages[:25]) or '没有待处理任务。')
