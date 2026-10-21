"""User actions for preview, recycle restoration and whole-library backups."""
from datetime import datetime
import json
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout)

from .library_backup import export_library, restore_library
from .organization import label_values, validate_label_rules
from .pdf_preview import DocumentPreviewDialog
from .recovery import restore_recycled
from .storage_base import archive_file_state


class RecycleDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle('恢复区')
        self.resize(840, 480)
        outer = QVBoxLayout(self)
        note = QLabel('撤销归档的副本保留在这里。恢复后重新加入文档库；同名文件不会覆盖。\n修改过或不存在的副本会保留记录，便于检查。')
        note.setWordWrap(True)
        outer.addWidget(note)
        self.rows = window.catalog.recycle_entries()
        self.table = QTableWidget(len(self.rows), 4)
        self.table.setHorizontalHeaderLabels(['文件名', '课程 / 项目', '撤销时间', '副本状态'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 240)
        self.table.setColumnWidth(2, 150)
        self.table.verticalHeader().setDefaultSectionSize(48)
        for index, entry in enumerate(self.rows):
            metadata = json.loads(entry['metadata'])
            try:
                path = window.catalog.safe_path(entry['trash_relative'])
                state = {'available':'副本存在', 'missing':'副本不存在', 'unknown':'状态无法确认'}[archive_file_state(str(path))]
            except (ValueError, OSError):
                state = '状态无法确认'
            values = (entry['filename'], ' · '.join(metadata.get(f, '') for f in ('course', 'project') if metadata.get(f)), entry['created_at'], state)
            for column, value in enumerate(values):
                self.table.setItem(index, column, QTableWidgetItem(value))
        outer.addWidget(self.table, 1)
        self.empty = QLabel('恢复区目前没有待恢复的文件。')
        self.empty.setVisible(not self.rows)
        outer.addWidget(self.empty)
        actions = QHBoxLayout()
        self.preview_button = QPushButton('预览副本')
        self.folder_button = QPushButton('查看恢复文件夹')
        self.restore_button = QPushButton('恢复选中文件')
        self.restore_button.setObjectName('primary')
        close = QPushButton('关闭')
        for button in (self.preview_button, self.folder_button, self.restore_button, close):
            actions.addWidget(button)
        self.preview_button.clicked.connect(self.preview)
        self.folder_button.clicked.connect(self.open_folder)
        self.restore_button.clicked.connect(self.restore)
        close.clicked.connect(self.accept)
        outer.addLayout(actions)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        if self.rows:
            self.table.selectRow(0)
        self.update_buttons()

    def selected_rows(self):
        return [self.rows[index.row()] for index in self.table.selectionModel().selectedRows()]

    def update_buttons(self):
        selected = bool(self.selected_rows())
        for button in (self.restore_button, self.preview_button, self.folder_button):
            button.setEnabled(selected)

    def preview(self):
        selected = self.selected_rows()
        if not selected:
            return
        entry = selected[0]
        try:
            path = self.window.catalog.safe_path(entry['trash_relative'])
            state = archive_file_state(str(path))
        except (ValueError, OSError):
            state = 'unknown'
        if state != 'available':
            QMessageBox.information(self, '无法预览副本', '保留的副本已不存在，请检查恢复文件夹。' if state == 'missing' else '暂时无法确认副本状态，请检查磁盘连接或访问权限后重试。')
            return
        dialog = DocumentPreviewDialog(path, json.loads(entry['metadata']).get('body_snapshot', ''), self)
        dialog.exec()
        dialog.deleteLater()

    def open_folder(self):
        entry = self.selected_rows()[0]
        self.window.open_path(self.window.catalog.safe_path(entry['trash_relative']).parent)

    def restore(self):
        rows = self.selected_rows()
        if QMessageBox.question(self, '恢复归档', f'恢复选中的 {len(rows)} 个文件？\n同名副本自动编号，原文件保留。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        catalog = self.window.catalog
        self.accept()
        self.window.launch_worker(lambda p, c: restore_recycled(catalog, rows, p, c), self.window.maintenance_finished)


class FolderRuleDialog(QDialog):
    def __init__(self, window, item):
        super().__init__(window)
        self.item = item
        self.setWindowTitle('记住这个文件夹的归类方式')
        self.resize(520, 260)
        outer = QVBoxLayout(self)
        label = QLabel('以后从这个目录或子目录导入时，建议相同的课程或项目：\n' + str(item.path.parent))
        label.setWordWrap(True)
        outer.addWidget(label)
        form = QFormLayout()
        self.field = QComboBox()
        self.field.addItem('课程', 'course')
        self.field.addItem('项目', 'project')
        self.value = QComboBox()
        self.value.setEditable(True)
        self.values = {'course': label_values(item.course), 'project': label_values(item.project)}
        form.addRow('建议字段', self.field)
        form.addRow('建议值', self.value)
        outer.addLayout(form)
        self.field.currentIndexChanged.connect(self.update_values)
        self.update_values()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存为规则')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    def update_values(self):
        self.value.clear()
        self.value.addItems(self.values[self.field.currentData()])
        if not self.value.count():
            self.value.setEditText('')

    def rule(self):
        return {'field': self.field.currentData(), 'value': self.value.currentText().strip(),
                'keywords': [str(self.item.path.parent.resolve())], 'source': 'folder'}

    def validate(self):
        try:
            validate_label_rules([self.rule()])
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, '需要填写建议值', str(exc))


class LibraryActions:
    def preview_archive(self):
        row = self.search_table.currentRow()
        if self.worker or not 0 <= row < len(self.archive_rows):
            return
        record = self.catalog.archive_by_id(self.archive_rows[row]['id'])
        if not record:
            self.refresh_search()
            return
        dialog = DocumentPreviewDialog(record['archive_path'], record['body_snapshot'], self)
        dialog.exec()
        dialog.deleteLater()

    def show_recycle(self):
        if self.catalog and not self.worker:
            RecycleDialog(self).exec()

    def remember_folder_rule(self):
        from .organization_ui import write_json
        row = self.scan_table.currentRow()
        if self.worker or not 0 <= row < len(self.items):
            return
        dialog = FolderRuleDialog(self, self.items[row])
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                rule = dialog.rule()
                path = rule['keywords'][0]
                # Update a previously saved rule for this exact folder and field.
                rules = [r for r in self.organization_rules if not (r['source'] == 'folder' and r['field'] == rule['field'] and r['keywords'] == [path])]
                rules.append(rule)
                rules = validate_label_rules(rules)
                write_json(self.organization_path, rules)
                self.organization_rules = rules
                self.statusBar().showMessage('已记住该目录的建议；后续读取生效，人工确认的字段保留。')
            except (ValueError, OSError) as exc:
                QMessageBox.warning(self, '规则保存失败', str(exc))

    def export_full_backup(self):
        if not self.catalog or self.worker:
            return
        default = f'D:/DocumentAssistant-backup-{datetime.now():%Y%m%d-%H%M%S}.zip'
        path, _ = QFileDialog.getSaveFileName(self, '保存完整文档库备份', default, '文档库备份 (*.zip)')
        if not path:
            return
        if Path(path).suffix.lower() != '.zip':
            path += '.zip'
        catalog = self.catalog
        self.launch_worker(lambda p, c: export_library(catalog, path, p, c), self.backup_finished)

    def backup_finished(self, result):
        self.statusBar().showMessage('完整备份已保存并校验。')
        QMessageBox.information(self, '完整备份完成', f'已保存并校验 {result["file_count"]} 个文件。\n归档：{result["archive_count"]} 个；恢复区：{result["recycle_count"]} 个。\n\n{result["path"]}\n\n包含文档库副本、标签、记录与常用筛选；库外的源文件和全局建议规则不包含在内。')

    def import_full_backup(self):
        if self.worker:
            return
        backup, _ = QFileDialog.getOpenFileName(self, '选择完整文档库备份', 'D:/', '文档库备份 (*.zip)')
        if not backup:
            return
        folder = QFileDialog.getExistingDirectory(self, '选择新的空文件夹恢复', 'D:/')
        if not folder:
            return
        if QMessageBox.question(self, '恢复到新文档库', f'校验备份并恢复到：\n{folder}\n\n目标必须为空，当前文档库保留。恢复成功后切换到新库。',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.launch_worker(lambda p, c: restore_library(backup, folder, p, c), self.library_restored)

    def library_restored(self, result):
        self.items = []
        self.archive_statuses.clear()
        self.populate_scan()
        self.source_edit.clear()
        self.set_library(Path(result['path']))
        self.save_settings()
        self.tabs.setCurrentIndex(0 if self.items else 1)
        QMessageBox.information(self, '文档库已恢复', f'已恢复并校验 {result["archive_count"]} 个归档和 {result["recycle_count"]} 个恢复区条目。\n已切换到：\n{result["path"]}\n\n原文档库保留。')
