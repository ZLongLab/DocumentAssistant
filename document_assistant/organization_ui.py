"""Inbox persistence and editable local organization rules and saved filters."""
import json
from dataclasses import asdict
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QComboBox, QCompleter, QDialog, QDialogButtonBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout)
from .organization import DEFAULT_LABEL_RULES, label_values, suggest_labels, validate_label_rules


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(path)


class SuggestionRuleDialog(QDialog):
    FIELDS = {'课程': 'course', '项目': 'project', '标签': 'tags'}
    SOURCES = {'任意来源': 'any', '来源目录': 'path', '文件名': 'filename', '正文': 'body', '目录及子目录': 'folder'}

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle('课程 / 项目建议规则')
        self.resize(760, 520)
        outer = QVBoxLayout(self)
        note = QLabel('关键词用逗号分隔，命中任意关键词即给出建议。课程或项目同时命中多个值时会提示冲突。\n建议可以修改；不会覆盖已人工确认的字段。保存后对后续读取生效。')
        note.setWordWrap(True)
        outer.addWidget(note)
        self.table = QTableWidget(0, 4)
        self.table.verticalHeader().setDefaultSectionSize(44)
        self.table.setHorizontalHeaderLabels(['建议字段', '建议值', '关键词', '匹配来源'])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setColumnWidth(0, 100)
        self.table.setColumnWidth(1, 170)
        self.table.setColumnWidth(2, 260)
        outer.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for title, callback in (('添加规则', lambda: self.add_rule()), ('删除选中规则', self.remove_rule), ('试运行当前规则', self.preview_rules)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            actions.addWidget(button)
        outer.addLayout(actions)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setMaximumHeight(130)
        self.preview.setPlaceholderText('试运行仅显示建议，不修改文件或已有标签。')
        outer.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存规则')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.rules = parent.organization_rules
        for rule in self.rules:
            self.add_rule(rule)

    def add_rule(self, rule=None):
        rule = rule if isinstance(rule, dict) else {'field': 'project', 'value': '', 'keywords': [], 'source': 'path'}
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, mapping, key in ((0, self.FIELDS, 'field'), (3, self.SOURCES, 'source')):
            combo = QComboBox()
            for name, value in mapping.items():
                combo.addItem(name, value)
            combo.setCurrentIndex(combo.findData(rule[key]))
            self.table.setCellWidget(row, column, combo)
        self.table.setItem(row, 1, QTableWidgetItem(rule['value']))
        self.table.setItem(row, 2, QTableWidgetItem(', '.join(rule['keywords'])))
        self.table.setCurrentCell(row, 1)

    def remove_rule(self):
        if self.table.currentRow() >= 0:
            self.table.removeRow(self.table.currentRow())

    def read_rules(self):
        return validate_label_rules([{'field': self.table.cellWidget(row, 0).currentData(),
            'value': self.table.item(row, 1).text().strip(), 'keywords': [self.table.item(row,2).text().strip()] if self.table.cellWidget(row,3).currentData()=='folder' else label_values(self.table.item(row, 2).text()),
            'source': self.table.cellWidget(row, 3).currentData()} for row in range(self.table.rowCount())])

    def preview_rules(self):
        try:
            rules = self.read_rules()
            items = self.parent().items[:10]
            lines = []
            for item in items:
                values, evidence = suggest_labels(item.path, item.body, rules)
                lines.append(item.path.name + '\n' + ' · '.join(v for v in values.values() if v) + '\n' + (evidence or '没有规则命中'))
            self.preview.setPlainText('\n\n'.join(lines) or '先导入示例文件，再试运行（最多显示 10 个）。')
        except ValueError as exc:
            self.preview.setPlainText(str(exc))

    def save(self):
        try:
            self.rules = self.read_rules()
            self.accept()
        except ValueError as exc:
            QMessageBox.warning(self, '规则需要修改', str(exc))


class OrganizationActions:
    def load_organization(self):
        self.organization_path = self.home / 'organization-rules.json'
        try:
            self.organization_rules = validate_label_rules(json.loads(self.organization_path.read_text(encoding='utf-8'))
                if self.organization_path.exists() else DEFAULT_LABEL_RULES)
        except Exception as exc:
            self.organization_rules = validate_label_rules(DEFAULT_LABEL_RULES)
            self.startup_errors.append('课程/项目规则读取失败，使用默认规则：' + str(exc))

    def load_loose_queue(self):
        from .service import ScanItem
        path = self.home / 'pending-inbox.json'
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(payload, list):
                raise ValueError('待整理列表格式无效')
            result = []
            for data in payload:
                data['path'] = Path(data['path'])
                data['doc_id'] = None
                result.append(ScanItem(**data))
            return result
        except Exception as exc:
            self.startup_errors.append('待整理列表读取失败，已保留原记录：' + str(exc))
            self.loose_queue_invalid = True
            return []

    def save_loose_queue(self):
        if getattr(self, 'loose_queue_invalid', False):
            return
        payload = []
        if not self.catalog:
            for item in self.items:
                data = asdict(item)
                data['path'] = str(item.path)
                payload.append(data)
        write_json(self.home / 'pending-inbox.json', payload)

    def persist_review_selection(self):
        selections = []
        for row, item in enumerate(self.items):
            cell = self.scan_table.item(row, 0)
            if cell is None:
                continue
            item.selected = cell.checkState() == Qt.CheckState.Checked
            selections.append((item.doc_id, item.selected))
        if self.catalog:
            self.catalog.save_selection(selections)
        else:
            self.save_loose_queue()

    def sync_document_revision(self, item):
        if self.catalog:
            metadata = self.catalog.document_metadata(item.path)
            item.revision = metadata['revision']
            item.manual_fields = metadata['manual_fields']

    def edit_organization_rules(self):
        if self.worker:
            return
        dialog = SuggestionRuleDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                write_json(self.organization_path, dialog.rules)
                self.organization_rules = dialog.rules
                self.statusBar().showMessage('建议规则已保存；重新读取文件后生效，也可应用到勾选文件。')
            except OSError as exc:
                QMessageBox.warning(self, '规则保存失败', str(exc))

    def suggest_selected(self):
        if self.worker:
            return
        selected = {str(item.path): item.selected for item in self.items}
        for row in self.selected_scan_rows():
            item = self.items[row]
            values, evidence = suggest_labels(item.path, item.body, self.organization_rules)
            for key, value in values.items():
                if key not in item.manual_fields.split(','):
                    setattr(item, key, value)
            if evidence:
                item.reason = item.reason.split('；课程/项目/标签建议：')[0] + '；课程/项目/标签建议：' + evidence
            if self.catalog:
                item.doc_id = self.catalog.save_scan(item)
            self.archive_statuses.pop(str(item.path), None)
        self.populate_scan(selected)
        self.save_loose_queue()
        self.refresh_filter_options()
        self.statusBar().showMessage('已更新勾选文件的建议；人工确认的课程、项目、标签保留。')

    def build_organization_filters(self, search_layout):
        from PySide6.QtWidgets import QWidget
        self.advanced_filters=QWidget()
        outer_layout=search_layout
        search_layout=QVBoxLayout(self.advanced_filters)
        search_layout.setContentsMargins(0,0,0,0)
        row = QHBoxLayout()
        self.filter_combos = {}
        for key, title in (('course', '全部课程'), ('project', '全部项目'), ('tag', '全部标签')):
            combo = QComboBox()
            combo.setEditable(True)
            combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
            combo.addItem(title, '')
            combo.setMinimumWidth(110)
            combo.setMaximumWidth(175)
            combo.setAccessibleName(title)
            combo.currentTextChanged.connect(self.queue_search)
            self.filter_combos[key] = combo
            row.addWidget(combo, 1)
        clear = QPushButton('重置筛选')
        clear.setMaximumWidth(110)
        clear.clicked.connect(self.clear_filters)
        row.addWidget(clear)
        row.addStretch(1)
        search_layout.addLayout(row)
        search_tools = QHBoxLayout()
        self.quality_filter = QComboBox()
        for title, key in (('全部正文范围',''),('正文已提取','complete'),('正文被截断','partial'),('无法提取正文','none'),('旧记录待检查','unknown')):
            self.quality_filter.addItem(title,key)
        self.quality_filter.currentIndexChanged.connect(self.reset_search)
        self.reading_filter=QComboBox()
        self.reading_filter.addItem('全部阅读状态','')
        from .document_metadata import READING_STATES
        for state in READING_STATES:self.reading_filter.addItem(state,state)
        self.reading_filter.currentIndexChanged.connect(self.reset_search)
        self.search_sort = QComboBox()
        for title, key in (('最新归档在前','newest'),('最早归档在前','oldest'),('按文件名排序','name')):
            self.search_sort.addItem(title,key)
        self.search_sort.currentIndexChanged.connect(self.reset_search)
        self.quality_button = QPushButton('检查文档质量')
        self.quality_button.clicked.connect(self.show_quality)
        search_tools.addWidget(self.quality_filter)
        search_tools.addWidget(self.search_sort)
        search_tools.addWidget(self.reading_filter)
        search_tools.addStretch()
        search_tools.addWidget(self.quality_button)
        search_layout.addLayout(search_tools)
        views = QHBoxLayout()
        views.addWidget(QLabel('常用筛选'))
        self.saved_view_combo = QComboBox()
        self.saved_view_combo.addItem('选择已保存视图', None)
        self.saved_view_combo.currentIndexChanged.connect(self.apply_saved_view)
        views.addWidget(self.saved_view_combo, 1)
        for title, callback in (('保存当前筛选', self.save_current_view), ('删除视图', self.delete_current_view)):
            button = QPushButton(title)
            button.clicked.connect(callback)
            views.addWidget(button)
        search_layout.addLayout(views)
        outer_layout.addWidget(self.advanced_filters)
        self.advanced_filters.hide()
        from .filter_chips import FilterChips
        self.filter_chips=FilterChips(self)
        outer_layout.addWidget(self.filter_chips)

    def current_filters(self):
        return {'query': self.search_edit.text().strip(),
                'category': '' if self.search_category.currentIndex() == 0 else self.search_category.currentText(),
                'scope': 'filename' if self.search_scope.currentIndex() == 1 else 'all',
                'quality': self.quality_filter.currentData(), 'sort': self.search_sort.currentData(), 'reading':self.reading_filter.currentData(),
                **{key: '' if combo.currentIndex() == 0 and combo.currentText() == combo.itemText(0) else combo.currentText().strip()
                   for key, combo in self.filter_combos.items()}}

    def refresh_filter_options(self):
        for key, combo in self.filter_combos.items():
            value = self.current_filters()[key]
            title = combo.itemText(0)
            blocked = combo.blockSignals(True)
            combo.clear()
            combo.addItem(title, '')
            if self.catalog:
                combo.addItems(self.catalog.label_options('tags' if key == 'tag' else key))
            if value:
                combo.setEditText(value)
            combo.blockSignals(blocked)
        blocked = self.saved_view_combo.blockSignals(True)
        old = self.saved_view_combo.currentData()
        self.saved_view_combo.clear()
        self.saved_view_combo.addItem('选择已保存视图', None)
        if self.catalog:
            for view in self.catalog.saved_views():
                self.saved_view_combo.addItem(view['name'], view['id'])
        self.saved_view_combo.setCurrentIndex(max(0, self.saved_view_combo.findData(old)))
        self.saved_view_combo.blockSignals(blocked)

    def clear_filters(self):
        for combo in self.filter_combos.values():
            combo.setCurrentIndex(0)
        self.search_category.setCurrentIndex(0)
        self.search_scope.setCurrentIndex(0)
        self.quality_filter.setCurrentIndex(0)
        self.search_sort.setCurrentIndex(0)
        self.reading_filter.setCurrentIndex(0)
        self.search_edit.clear()
        self.saved_view_combo.setCurrentIndex(0)
        self.reset_search()

    def save_current_view(self):
        if not self.catalog or self.worker:
            return
        name, accepted = QInputDialog.getText(self, '保存常用筛选', '名称，例如“本学期网络实验”：')
        if not accepted:
            return
        try:
            if any(v['name'] == name.strip() for v in self.catalog.saved_views()):
                if QMessageBox.question(self, '更新已有视图', '已有同名视图，要更新其筛选条件吗？') != QMessageBox.StandardButton.Yes:
                    return
            self.catalog.save_view(name, self.current_filters())
            self.refresh_filter_options()
            self.statusBar().showMessage('已保存筛选条件；以后新增的匹配资料会自动显示。')
        except ValueError as exc:
            QMessageBox.warning(self, '无法保存', str(exc))

    def apply_saved_view(self):
        ident = self.saved_view_combo.currentData()
        if not self.catalog or not ident:
            return
        view = next((v for v in self.catalog.saved_views() if v['id'] == ident), None)
        if not view:
            return
        filters = view['filters']
        widgets = [self.search_edit, self.search_category, self.search_scope, self.search_sort, self.quality_filter, self.reading_filter, *self.filter_combos.values()]
        states = [w.blockSignals(True) for w in widgets]
        try:
            self.search_edit.setText(filters['query'])
            self.search_category.setCurrentIndex(max(0, self.search_category.findText(filters['category'])))
            self.search_scope.setCurrentIndex(int(filters['scope'] == 'filename'))
            self.search_sort.setCurrentIndex(max(0,self.search_sort.findData(filters.get('sort','newest'))))
            self.quality_filter.setCurrentIndex(max(0,self.quality_filter.findData(filters.get('quality',''))))
            self.reading_filter.setCurrentIndex(max(0,self.reading_filter.findData(filters.get('reading',''))))
            for key, combo in self.filter_combos.items():
                combo.setCurrentIndex(0)
                if filters[key]:
                    combo.setEditText(filters[key])
        finally:
            for widget, state in zip(widgets, states):
                widget.blockSignals(state)
        self.filter_chips.schedule()
        self.reset_search()

    def delete_current_view(self):
        ident = self.saved_view_combo.currentData()
        if self.catalog and ident and not self.worker:
            if QMessageBox.question(self, '删除常用筛选', '删除这个视图？文档不会删除。') == QMessageBox.StandardButton.Yes:
                self.catalog.delete_view(ident)
                self.refresh_filter_options()
