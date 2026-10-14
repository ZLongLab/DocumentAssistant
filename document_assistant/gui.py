from __future__ import annotations

import json
import os
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QLibraryInfo, QThread, QTimer, QTranslator, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QColor, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QComboBox, QDialog, QDialogButtonBox,
    QFileDialog, QFormLayout, QHeaderView, QLabel, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QHBoxLayout, QFrame, QScrollArea, QWidget,
)

from .rules import CATEGORIES, DEFAULT_RULES, classify, load_rules, save_rules, validate_rules
from .service import EXTENSIONS, PROJECT_ROOT, archive_batch, scan_files, scan_folder, validate_library
from .storage import Catalog, archive_file_state
from .presentation import GLYPH, SUBTEXT, SUCCESS, WARNING, HintTable
from .windows_identity import ICON_PATH, configure_process, tag_window
from . import __version__
from .workflow_ui import WorkflowActions
from .search_ui import SearchActions
from .knowledge_ui import KnowledgeActions
from .document_metadata import attention_rank
from .rules import categories_for
from .presentation import MATCH_TERMS
from .organization import query_terms


def runtime_directory() -> Path:
    return Path(os.environ.get("DOCUMENTASSISTANT_HOME", str(PROJECT_ROOT.parent / "DocumentAssistant-local"))).resolve()


class Worker(QThread):
    progress = Signal(int, int, str)
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, operation, parent):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            result = self.operation(self.progress.emit, self.isInterruptionRequested)
            self.completed.emit(result)
        except Exception as exc:
            self.failed.emit(f"{type(exc).__name__}: {exc}")


class RuleDialog(QDialog):
    def __init__(self, rules, parent):
        super().__init__(parent)
        self.setWindowTitle("配置分类规则")
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(700, min(760, available.height() - 64))
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("每行填写一个关键词。较长的完整词组优先，文件名、标题和正文共同判断。\n零散通用词不单独定类；自动识别论文/实验结构并忽略参考文献列表。\n得分不足或类型冲突时保留待整理；清空某类关键词可停用该类建议。"))
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        scroll.setWidget(content)
        form = QFormLayout(content)
        self.editors = {}
        for category in categories_for(rules)[:-1]:
            editor = QPlainTextEdit()
            editor.setMaximumHeight(80)
            editor.setPlaceholderText("每行一个关键词")
            self.editors[category] = editor
            form.addRow(category, editor)
        self.weights = {}
        for field, label in (("filename_weight", "文件名命中得分"),
                             ("title_weight", "正文标题命中得分"),
                             ("body_weight", "正文命中得分"), ("minimum_score", "最低分类分数"),
                             ("minimum_margin", "前两类最低分差")):
            spin = QSpinBox()
            spin.setRange(1, 100)
            self.weights[field] = spin
            form.addRow(label, spin)
        layout.addWidget(scroll, 1)
        self.populate(rules)
        reset = QPushButton("恢复默认规则")
        reset.clicked.connect(lambda: self.populate(DEFAULT_RULES))
        layout.addWidget(reset)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("保存")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.validate)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def populate(self, rules):
        for category, editor in self.editors.items():
            editor.setPlainText("\n".join(rules["keywords"].get(category,[])))
        for field, spin in self.weights.items():
            spin.setValue(rules[field])

    def validate(self):
        try:
            rules = {field: spin.value() for field, spin in self.weights.items()}
            rules['schema_version'] = DEFAULT_RULES['schema_version']
            rules["keywords"] = {category: [word.strip() for word in editor.toPlainText().splitlines() if word.strip()]
                                 for category, editor in self.editors.items()}
            self.rules = validate_rules(rules)
        except (ValueError, TypeError) as exc:
            QMessageBox.warning(self, "规则格式有误", str(exc))
            return
        self.accept()


def table(headers):
    widget = HintTable(0, len(headers))
    widget.setHorizontalHeaderLabels(headers)
    widget.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    widget.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    widget.setAlternatingRowColors(True)
    widget.verticalHeader().hide()
    widget.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
    widget.horizontalHeader().setStretchLastSection(True)
    widget.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    widget.setWordWrap(False)
    return widget


class MainWindow(KnowledgeActions, SearchActions, WorkflowActions, QMainWindow):
    def __init__(self, home: Path | None = None):
        super().__init__()
        self.setWindowTitle(f"DocumentAssistant · 卡片工作台 · {__version__}")
        self.home = home or runtime_directory()
        self.home.mkdir(parents=True, exist_ok=True)
        self.rules_path = self.home / "rules.json"
        self.settings_path = self.home / "settings.json"
        self.startup_errors = []
        try:
            if not self.rules_path.exists():
                save_rules(self.rules_path, DEFAULT_RULES)
            self.rules = load_rules(self.rules_path)
        except Exception as exc:
            self.rules = DEFAULT_RULES
            self.startup_errors.append(f"规则读取失败，暂用默认规则：{exc}")
        try:
            self.settings = json.loads(self.settings_path.read_text(encoding="utf-8")) if self.settings_path.exists() else {}
            if not isinstance(self.settings, dict):
                raise ValueError("设置必须是对象")
        except Exception as exc:
            self.settings = {}
            self.startup_errors.append(f"设置读取失败：{exc}")
        self.capture_controller=None
        self.init_knowledge()
        self.load_organization()
        self.items = self.load_loose_queue()
        self.archive_statuses = {}
        self.worker = None
        self.catalog = None
        self.archive_rows = []
        self.search_page = 0
        self.search_total = 0
        self.search_worker = None
        self.pending_search = None
        self.search_generation = 0
        self.closing = False
        self.page_size = 100
        self.review_mode = self.settings.get('view','cards')
        if self.review_mode not in ('cards','list'):
            self.review_mode = 'cards'
        self.search_timer = QTimer(self)
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(200)
        self.search_timer.timeout.connect(self.refresh_search)
        self.setAcceptDrops(True)
        self.build_ui()
        self.populate_scan({str(item.path):item.selected for item in self.items})
        self.restore_paths()
        self.update_controls()
        if self.startup_errors:
            self.detail.setPlainText("\n".join(self.startup_errors))
            self.statusBar().showMessage("配置有问题，请点击文件详情查看")
            self.details_button.setEnabled(True)

    def build_ui(self):
        from .layout import build_window
        build_window(self)

    def restore_paths(self):
        source = self.settings.get("source", "")
        library = self.settings.get("library", "")
        if isinstance(source, str) and source and Path(source).is_dir():
            self.source_edit.setText(source)
        if isinstance(library, str) and library and Path(library).is_dir():
            try:
                self.set_library(Path(library))
                self.tabs.setCurrentIndex(0 if self.items else 1)
            except Exception as exc:
                self.startup_errors.append(f"文档库读取失败：{exc}")

    def save_settings(self):
        data = {
            "source": self.source_edit.text(),
            "library": self.library_edit.text(),
            "view": self.review_mode,
            "review_order": self.review_order,
            "theme": self.settings.get("theme", "ocean"),
        }
        try:
            temporary = self.settings_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.settings_path)
            self.persist_review_selection()
            self.save_loose_queue()
        except OSError as exc:
            self.statusBar().showMessage(f"设置保存失败：{exc}")

    def toggle_theme(self):
        from .layout import toggle_theme
        toggle_theme(self)

    def choose_source(self):
        selected = QFileDialog.getExistingDirectory(self, "选择待整理文件夹", self.source_edit.text() or "D:/")
        if selected:
            if self.catalog and Path(selected).resolve().is_relative_to(self.catalog.library):
                QMessageBox.warning(self, "来源文件夹无效", "请选择文档库之外的来源文件夹")
                return False
            self.source_edit.setText(selected)
            self.save_settings()
            self.update_controls()
            return True
        return False

    def choose_and_scan_folder(self):
        if self.worker is None and self.choose_source():
            self.start_scan()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "添加要整理的文件", self.source_edit.text() or "D:/",
                                               "文档 (*.pdf *.PDF *.docx *.DOCX *.doc *.DOC *.txt *.TXT)")
        if paths:
            self.import_files(paths)

    def dragEnterEvent(self, event):
        if self.worker is None and event.possibleActions() & Qt.DropAction.CopyAction and event.mimeData().hasUrls() and any(
            url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in EXTENSIONS
            for url in event.mimeData().urls()
        ):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dropEvent(self, event):
        if self.worker is not None or not event.possibleActions() & Qt.DropAction.CopyAction or not event.mimeData().hasUrls():
            event.ignore()
            return
        paths = [Path(url.toLocalFile()) for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self.import_files(paths)
        else:
            event.ignore()

    def import_files(self, paths, force=False):
        if self.worker is not None:
            return
        known = {str(item.path).casefold():item for item in self.items}
        fresh, seen = [], set()
        for path in paths:
            key = str(Path(path).resolve()).casefold()
            changed = False
            if key in known:
                try:
                    info = Path(path).stat()
                    changed = (info.st_size,info.st_mtime_ns)!=(known[key].size,known[key].mtime_ns)
                except OSError:
                    changed = True
            if key not in seen and (key not in known or changed or force):
                fresh.append(Path(path))
                seen.add(key)
        self.tabs.setCurrentIndex(0)
        if not fresh:
            self.statusBar().showMessage("这些文件已在列表中，无需重复添加。")
            return
        library = self.catalog.library if self.catalog else None
        rules = json.loads(json.dumps(self.rules))
        organization_rules = json.loads(json.dumps(self.organization_rules))
        self.launch_worker(lambda p, c: scan_files(fresh, rules, library, p, c, organization_rules, refresh_body=force), self.import_finished)

    def import_finished(self, result):
        incoming, warnings = result
        if self.watch_import and self.catalog:
            self.catalog.acknowledge_watch(self.watch_import,incoming)
            self.watch_import=[]
        selected = {str(item.path): self.scan_table.item(row, 0).checkState() == Qt.CheckState.Checked
                    for row, item in enumerate(self.items)}
        positions = {str(item.path).casefold():row for row,item in enumerate(self.items)}
        for item in incoming:
            key = str(item.path).casefold()
            if key in positions:
                row = positions[key]
                if not self.catalog:
                    for field in ('course','project','tags'):
                        if field in self.items[row].manual_fields.split(','):
                            setattr(item,field,getattr(self.items[row],field))
                    item.manual_fields = self.items[row].manual_fields
                self.items[row] = item
                self.archive_statuses.pop(str(item.path),None)
            else:
                positions[key] = len(self.items)
                self.items.append(item)
        self.populate_scan(selected)
        self.save_loose_queue()
        self.refresh_filter_options()
        self.import_hint.setText(f"已添加 {len(self.items)} 个文件，可继续拖入")
        self.statusBar().showMessage(f"已读取 {len(incoming)} 个文件。检查分类后，点击确认归档。")
        if warnings:
            QMessageBox.warning(self, "添加提示", "\n".join(warnings[:30]))
        if self.catalog:
            self.refresh_history()

    def clear_imports(self):
        if self.worker is not None:
            return
        if self.items and QMessageBox.question(self, "清空待整理列表", "清空当前列表？原文件和已归档文件都会保留。") != QMessageBox.StandardButton.Yes:
            return
        if self.catalog:
            self.catalog.dismiss_inbox([item.doc_id for item in self.items])
        self.items = []
        self.archive_statuses.clear()
        self.populate_scan()
        self.save_loose_queue()
        self.import_hint.setText("拖入 PDF、DOCX、DOC、TXT，或点击添加文件")
        self.update_controls()

    def set_library(self, path):
        validate_library(path)
        if self.source_edit.text() and Path(self.source_edit.text()).resolve().is_relative_to(path.resolve()):
            raise ValueError("来源文件夹不能是文档库或文档库的子文件夹")
        new_catalog = Catalog(path)
        if any(item.path.resolve().is_relative_to(new_catalog.library) for item in self.items):
            raise ValueError('待整理文件位于这个文档库内，请先清空列表或选择其他文档库')
        saved_ids = [(item, new_catalog.save_scan(item)) for item in self.items] if not self.catalog or self.catalog.library != new_catalog.library else []
        for item, doc_id in saved_ids:
            item.doc_id = doc_id
        self.catalog = new_catalog
        self.refresh_categories()
        self.reset_watch()
        known = {str(item.path).casefold() for item in self.items}
        self.items.extend(item for item in new_catalog.inbox() if str(item.path).casefold() not in known)
        self.archive_statuses.clear()
        self.populate_scan({str(item.path):item.selected for item in self.items})
        self.search_page = 0
        self.library_edit.setText(str(path.resolve()))
        self.library_edit.setToolTip(str(path.resolve()))
        self.library_button.setText("切换")
        self.clear_filters()
        self.refresh_filter_options()
        self.save_loose_queue()
        self.refresh_search()
        self.update_selection()
        if new_catalog.pending_tasks() or new_catalog.pending_undos() or new_catalog.pending_restores():
            self.statusBar().showMessage('发现未完成任务，可在“更多操作 → 恢复未完成归档”中检查。')

    def choose_library(self):
        selected = QFileDialog.getExistingDirectory(self, "选择文档库（文件将按分类复制到这里）", self.library_edit.text() or "D:/")
        if selected:
            try:
                self.set_library(Path(selected))
                self.save_settings()
                self.update_controls()
            except Exception as exc:
                QMessageBox.warning(self, "文档库不可用", str(exc))

    def update_controls(self):
        busy = self.worker is not None
        for widget in (self.source_button, self.file_button, self.library_button, self.rule_button, self.all_check,
                       self.scan_table, self.search_button, self.search_category):
            widget.setEnabled(not busy)
        self.scan_button.setEnabled(not busy)
        self.reclassify_button.setEnabled(not busy and bool(self.items))
        self.clear_action.setEnabled(not busy and bool(self.items))
        self.more_button.setEnabled(not busy)
        self.settings_button.setEnabled(not busy)
        self.cards_view.setEnabled(not busy)
        self.review_sort.setEnabled(not busy)
        self.reading_button.setEnabled(not busy and bool(self.archive_rows))
        self.reading_filter.setEnabled(not busy)
        self.remember_category_action.setEnabled(not busy and self.catalog is not None)
        self.category_rules_action.setEnabled(not busy and self.catalog is not None)
        self.watch_action.setEnabled(not busy and self.catalog is not None)
        self.details_panel.show_item(self.scan_table.currentRow())
        self.clear_button.setEnabled(not busy and bool(self.items))
        self.bulk_button.setEnabled(not busy and bool(self.items))
        self.reread_button.setEnabled(not busy and bool(self.items))
        self.view_button.setEnabled(not busy)
        self.labels_button.setEnabled(not busy and bool(self.archive_rows))
        self.recycle_action.setEnabled(not busy and self.catalog is not None)
        self.full_backup_action.setEnabled(not busy and self.catalog is not None)
        self.restore_backup_action.setEnabled(not busy)
        self.previous_page.setEnabled(not busy and self.search_page>0)
        self.next_page.setEnabled(not busy and (self.search_page+1)*self.page_size<self.search_total)
        for navigation in self.nav_buttons:
            navigation.setEnabled(not busy)
        self.search_edit.setEnabled(not busy)
        self.search_scope.setEnabled(not busy)
        self.search_sort.setEnabled(not busy)
        self.quality_filter.setEnabled(not busy)
        self.quality_button.setEnabled(not busy and self.catalog is not None)
        for combo in (*self.filter_combos.values(), self.saved_view_combo):
            combo.setEnabled(not busy and self.catalog is not None)
        self.details_button.setEnabled(not busy and bool(self.items))
        self.all_check.setVisible(bool(self.items))
        self.progress.setVisible(busy)
        self.progress_container.setVisible(busy)
        self.cancel_button.setVisible(busy)
        self.cancel_button.setEnabled(busy)
        self.update_selection()
        self.update_archive_selection()

    def update_selection(self, sync_cards=True):
        selected = sum(1 for row in range(self.scan_table.rowCount())
                       if self.scan_table.item(row, 0) is not None
                       and self.scan_table.item(row, 0).checkState() == Qt.CheckState.Checked)
        self.archive_button.setEnabled(self.worker is None and selected > 0 and self.catalog is not None)
        blocked = self.all_check.blockSignals(True)
        self.all_check.setCheckState(Qt.CheckState.Checked if not self.items or selected==len(self.items) else
                                    Qt.CheckState.Unchecked if not selected else Qt.CheckState.PartiallyChecked)
        self.all_check.blockSignals(blocked)
        if self.items:
            pending = sum(self.items[row].category == "待整理" for row in range(len(self.items))
                          if self.scan_table.item(row, 0).checkState() == Qt.CheckState.Checked)
            suffix = f" · {pending} 个待整理" if pending else ""
            self.count_label.setText(f"已选择 {selected} 个文件（共 {len(self.items)} 个）{suffix}")
            self.file_count.setText(f"{len(self.items)} 个文件 · {sum(attention_rank(i)>0 for i in self.items)} 个需检查")
            self.selection_hint.setText("请先选择右上角的文档库，才能确认归档。" if not self.catalog else
                                        "至少勾选一个文件，才能确认归档。" if not selected else
                                        "归档会复制文件，原文件保留；同名文件自动编号。")
        else:
            self.count_label.setText("尚未添加文件")
            self.file_count.setText("尚未添加文件")
            self.selection_hint.setText("添加文件后，检查分类建议再确认归档。")
        if sync_cards:
            self.cards_view.sync()
        archived = bool(self.items) and all(self.archive_statuses.get(str(item.path), (False, ''))[0]
                                            for item in self.items)
        self.steps_label.set_stage(2 if archived else 1 if self.items else 0)

    def launch_worker(self, operation, callback):
        if self.worker is not None:
            return
        self.worker = Worker(operation, self)
        self.worker.progress.connect(self.on_progress)
        self.worker.completed.connect(callback)
        self.worker.failed.connect(self.on_failure)
        self.worker.finished.connect(self.worker_finished)
        self.update_controls()
        self.worker.start()

    def worker_finished(self):
        self.worker.deleteLater()
        self.worker = None
        if self.progress.maximum() == 0:
            self.progress.setRange(0, 100)
        self.progress.setValue(self.progress.maximum())
        self.progress.setFormat("处理结束")
        self.update_controls()

    def on_progress(self, current, total, message):
        self.progress.setRange(0, total)
        self.progress.setValue(current)
        self.progress.setFormat(f"{current}/{total}" if total else "正在发现文件…")
        self.statusBar().showMessage(message)

    def on_failure(self, message):
        self.watch_import=[]
        self.statusBar().showMessage("处理失败")
        if not (self.capture_controller and self.capture_controller.exiting):
            QMessageBox.critical(self, "处理失败", message)

    def cancel_work(self):
        if self.worker:
            self.worker.requestInterruption()
            self.cancel_button.setEnabled(False)
            self.statusBar().showMessage("正在停止：保留已完成结果。正文解析最多等待 25 秒；哈希与复制可在分块间停止。")

    def start_scan(self):
        if not self.source_edit.text():
            return
        source = Path(self.source_edit.text())
        library = self.catalog.library if self.catalog else None
        rules = json.loads(json.dumps(self.rules))
        self.tabs.setCurrentIndex(0)
        organization_rules = json.loads(json.dumps(self.organization_rules))
        self.launch_worker(lambda p, c: scan_folder(source, rules, library, p, c, organization_rules), self.scan_finished)

    def scan_finished(self, result):
        self.import_finished(result)

    def populate_scan(self, selected_states=None):
        self.scan_table.blockSignals(True)
        if self.review_order=='attention':
            self.items.sort(key=lambda i:-attention_rank(i))
        self.scan_table.setRowCount(len(self.items))
        for row, item in enumerate(self.items):
            check = QTableWidgetItem()
            check.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            checked = selected_states.get(str(item.path), True) if selected_states is not None else self.all_check.isChecked()
            item.selected = checked
            check.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
            self.scan_table.setItem(row, 0, check)
            filename = QTableWidgetItem(item.display_title or item.path.name)
            filename.setToolTip(str(item.path))
            filename.setData(GLYPH, item.path.suffix[1:].upper())
            size = f"{item.size / 1024:.1f} KB" if item.size >= 1024 else f"{item.size} 字节"
            filename.setData(SUBTEXT, f"{item.path.name} · {size}" if item.display_title else f"{size} · 双击打开原文件")
            self.scan_table.setItem(row, 1, filename)
            evidence, separator, score = item.reason.partition("。得分：")
            reason = QTableWidgetItem(evidence)
            reason.setToolTip(item.reason)
            reason.setData(SUBTEXT, f"得分：{score}" if separator else f"建议：{item.suggested}")
            self.scan_table.setItem(row, 3, reason)
            self.scan_table.setItem(row, 4, QTableWidgetItem())
            self.update_scan_status(row)
            self.scan_table.removeCellWidget(row, 2)
            self.scan_table.setItem(row, 2, QTableWidgetItem(item.category))
        self.scan_table.blockSignals(False)
        self.cards_view.rebuild()
        self.review_stack.setCurrentIndex(0 if not self.items else 2 if self.review_mode=='list' else 1)
        self.detail.clear()
        self.reason_label.clear()
        self.reason_label.hide()
        self.details_panel.show_item(-1)
        if self.items:
            self.scan_table.selectRow(0)
            self.show_scan_detail()
        self.update_selection()
        self.persist_review_selection()

    def category_combo(self, row):
        holder = self.scan_table.cellWidget(row, 2)
        if holder:
            return holder.findChild(QComboBox)
        item = self.items[row]
        combo = QComboBox()
        combo.addItems(self.categories)
        combo.setCurrentText(item.category)
        combo.currentTextChanged.connect(lambda value,index=row:self.category_changed(index,value))
        combo.setToolTip(f"建议：{item.suggested}\n{item.reason}")
        combo.setAccessibleName(f"{item.path.name} 的分类")
        holder = QFrame()
        holder.setObjectName('categoryCell')
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(8,0,8,0)
        layout.addWidget(combo)
        self.scan_table.setCellWidget(row,2,holder)
        return combo

    def update_scan_status(self, row):
        item = self.items[row]
        cell = self.scan_table.item(row, 4)
        cell.setForeground(QColor("#202733" if item.status.startswith("已提取") else WARNING))
        cell.setText("已读取正文" if item.status.startswith("已提取") else "无法提取正文")
        cell.setToolTip(item.status)
        subtitle = "已手动修改分类" if item.category != item.suggested else (
            "待确认分类" if item.category == "待整理" else "待确认归档")
        if str(item.path) in self.archive_statuses:
            ok, message = self.archive_statuses[str(item.path)]
            cell.setText(('已有相同内容' if '内容相同' in message else '已归档') if ok else "归档失败 · 请检查")
            cell.setToolTip(f"{item.status}\n{message}")
            cell.setForeground(QColor(SUCCESS if ok else WARNING))
            subtitle = "原文件保留" if ok else "请查看详情"
        cell.setData(SUBTEXT, subtitle)

    def check_all(self, checked):
        blocked = self.scan_table.blockSignals(True)
        try:
            for row in range(self.scan_table.rowCount()):
                self.scan_table.item(row, 0).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        finally:
            self.scan_table.blockSignals(blocked)
        self.update_selection()
        self.persist_review_selection()

    def scan_item_changed(self, cell):
        if cell.column() == 0:
            self.persist_review_selection()
        self.update_selection(sync_cards=False)
        self.cards_view.sync(cell.row())

    def category_changed(self, row, category):
        item = self.items[row]
        old = item.category
        try:
            if self.catalog and item.doc_id:
                self.catalog.change_category(item.doc_id, category)
                self.sync_document_revision(item)
            item.category = category
            self.scan_table.item(row,2).setText(category)
            self.archive_statuses.pop(str(item.path),None)
            self.update_scan_status(row)
            self.update_selection()
            self.show_scan_detail()
            self.refresh_history()
            self.save_loose_queue()
        except Exception as exc:
            combo = self.category_combo(row)
            combo.blockSignals(True)
            combo.setCurrentText(old)
            combo.blockSignals(False)
            QMessageBox.warning(self, "分类保存失败", str(exc))

    def show_scan_detail(self):
        row = self.scan_table.currentRow()
        self.details_panel.show_item(row)
        self.cards_view.sync()
        if 0 <= row < len(self.items):
            item = self.items[row]
            reason = item.reason if len(item.reason) <= 180 else item.reason[:180] + "…（完整依据见文件详情）"
            if item.category != item.suggested:
                reason += f"；你已改为{item.category}"
            self.reason_label.setText("分类依据：" + reason)
            self.reason_label.setToolTip(item.reason)
            self.detail.setPlainText(f"原路径：{item.path}\n大小：{item.size:,} 字节\n正文：{item.status}\n"
                f"建议：{item.suggested}　确认分类：{item.category}\n依据：{item.reason}\n\n正文预览（最多 6000 字）：\n"
                + (item.body[:6000] or "[无可提取正文，分类仅参考文件名；请人工检查原文件]"))

    def show_details(self):
        if self.items:
            self.details_panel.show()
            self.show_scan_detail()
            self.details_panel.preview.setFocus()
            return
        self.details_dialog.show()
        self.details_dialog.raise_()
        self.details_dialog.activateWindow()

    def show_history(self):
        try:
            self.refresh_history()
            self.history_dialog.show()
            self.history_dialog.raise_()
        except Exception as exc:
            QMessageBox.warning(self, "记录读取失败", str(exc))

    def show_help(self):
        QMessageBox.information(self, "如何使用", "存资料：\n1. 选择一次文档库，例如 D:\\DocumentLibrary。\n2. 把桌面文件拖进窗口，或点击添加文件。\n3. 检查分类，点击确认归档。\n\n取资料：\n进入“文档库”，输入文件名，双击结果即可打开。\n留空显示全部归档文件，最新存入的排在前面。\n\n要整理整个文件夹，可点击扫描文件夹。\n原文件会保留。规则和操作记录在“更多操作”里。\n\n截图：\n默认按 Alt+S 或点侧栏“框选截图”，框选后可拖动边缘调整，按 Enter 进入编辑；编辑后按 Enter 仅复制。选择工具可移动、删除标注，Ctrl+Y 重做；小字保存入口写入桌面。\n保存位置和快捷键在“设置 → 截图设置”修改。\n关闭主窗口后在托盘运行，托盘菜单可退出程序。侧栏“设置”可开关开机自启动，开启后登录 Windows 时驻留托盘。")

    def edit_rules(self):
        dialog = RuleDialog(self.rules, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            try:
                self.install_category_rules(dialog.rules)
                self.statusBar().showMessage("规则已保存，下次扫描生效；可点击重新建议分类应用到当前列表。")
            except Exception as exc:
                QMessageBox.warning(self, "规则保存失败", str(exc))

    def reclassify(self):
        answer = QMessageBox.question(self, "重新建议分类", "会使用当前规则重新计算，并重置当前列表里的人工分类。继续？")
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            self.archive_statuses.clear()
            from .document_metadata import classification_suggestion
            saved_rules=self.catalog.category_rules() if self.catalog else []
            selections={str(item.path):item.selected for item in self.items}
            for item in self.items:
                item.suggested,item.reason=classification_suggestion(item.path,item.body,self.rules,saved_rules)
                item.category=item.suggested
                item.manual_fields=','.join(field for field in item.manual_fields.split(',') if field and field!='category')
                if not item.body:item.reason+='；正文不可用，请人工确认。'+item.status
                if self.catalog:
                    item.doc_id = self.catalog.save_scan(item)
            self.populate_scan(selections)
            self.save_loose_queue()
            self.refresh_history()
        except Exception as exc:
            QMessageBox.warning(self, "重新分类失败", str(exc))

    def confirm_archive(self):
        selected = [item for row, item in enumerate(self.items)
                    if self.scan_table.item(row, 0).checkState() == Qt.CheckState.Checked]
        if not selected:
            QMessageBox.information(self, "没有选中文件", "请勾选需要归档的文件")
            return
        counts = {category: sum(i.category == category for i in selected) for category in self.categories}
        summary = "\n".join(f"{c}：{n} 个" for c, n in counts.items() if n)
        message = f"将复制 {len(selected)} 个文件到：\n{self.catalog.library}\n\n{summary}\n\n原文件保留。同名文件自动编号，重复归档将跳过。"
        if counts["待整理"]:
            message += "\n其中待整理文件也会复制到“待整理”文件夹。"
        if QMessageBox.question(self, "确认复制归档", message,
                               QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                               QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        duplicate_policy = 'keep'
        seen = set()
        duplicates = 0
        for item in selected:
            digest = item.content_hash
            if digest and (digest in seen or any(row['document_id']!=item.doc_id for row in self.catalog.content_duplicates(digest))):
                duplicates += 1
            if digest:
                seen.add(digest)
        if duplicates:
            choice = QMessageBox(self)
            choice.setWindowTitle('发现相同内容')
            choice.setText(f'有 {duplicates} 个文件内容相同。请选择处理方式：\n关联已有文档会合并课程、项目和标签，并保留来源关联。')
            link = choice.addButton('关联已有文档', QMessageBox.ButtonRole.AcceptRole)
            keep = choice.addButton('保留独立副本', QMessageBox.ButtonRole.ActionRole)
            skip = choice.addButton('仅跳过', QMessageBox.ButtonRole.ActionRole)
            choice.addButton('取消', QMessageBox.ButtonRole.RejectRole)
            choice.setDefaultButton(link)
            choice.exec()
            selected_button = choice.clickedButton()
            if selected_button not in (link, keep, skip):
                return
            duplicate_policy = 'link' if selected_button == link else 'keep' if selected_button == keep else 'skip'
        self.begin_archive(selected,duplicate_policy)

    def begin_archive(self, selected, duplicate_policy='keep'):
        library = self.catalog.library
        self.launch_worker(lambda p, c: archive_batch(selected, library, p, c, duplicate_policy), self.archive_finished)

    def archive_finished(self, results):
        for item, ok, message in results:
            self.archive_statuses[str(item.path)] = (ok, message)
            if ok:
                row = self.items.index(item)
                self.scan_table.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
            self.scan_table.item(self.items.index(item), 1).setToolTip(f"{item.path}\n{message}")
            self.update_scan_status(self.items.index(item))
        successful = sum(ok for _, ok, _ in results)
        if successful:
            self.clear_filters()
            self.tabs.setCurrentIndex(1)
        self.refresh_filter_options()
        self.refresh_search()
        self.statusBar().showMessage(f"已处理 {len(results)} 个：成功 / 重复跳过 {successful} 个，失败 {len(results) - successful} 个。")
        self.detail.setPlainText("\n".join(message for _, _, message in results))
        self.reason_label.setText(f"归档完成：{successful} 个成功，{len(results) - successful} 个失败。在“文档库”中双击文件即可打开。")
        if successful < len(results):
            QMessageBox.warning(self, "部分文件归档失败", "\n".join(message for _, ok, message in results if not ok)[:3000])

    def queue_search(self):
        # A change invalidates old results immediately, before debounce expires.
        self.search_generation += 1
        self.pending_search = None
        if self.search_worker:
            self.search_worker.requestInterruption()
        self.archive_rows = []
        self.search_table.setRowCount(0)
        self.search_table.setProperty('emptyText', '正在搜索…')
        self.update_archive_selection()
        self.search_page = 0
        self.search_timer.start()

    def update_archive_selection(self):
        row = self.search_table.currentRow()
        valid = 0 <= row < len(self.archive_rows)
        available = valid and self.archive_rows[row].get('_file_state') == 'available'
        self.open_archive_button.setEnabled(bool(available) and self.worker is None)
        self.preview_archive_button.setEnabled(bool(available) and self.worker is None)
        self.open_folder_button.setEnabled(valid and self.worker is None)
        self.cleanup_button.setEnabled(self.catalog is not None and self.worker is None)
        self.open_archive_button.setToolTip("打开选中的归档副本" if available else "请选择存在的归档文件")
        self.library_selection.setText(f"已选：{self.archive_rows[row]['filename']}" if valid else "选择一个文件")
        self.library_selection.setToolTip(self.archive_rows[row]["archive_path"] if valid else "")

    def cleanup_missing_records(self):
        if self.worker is not None or self.catalog is None:
            return
        try:
            candidates, unknown = self.catalog.missing_archives()
            if not candidates:
                message = '未发现归档副本已不存在的记录，无需清理。'
                if unknown:
                    message += f'\n有 {unknown} 条记录暂时无法确认文件状态，已保留。'
                QMessageBox.information(self, '清理失效记录', message)
                self.refresh_search()
                return
            names = '\n'.join('• ' + row['filename'][:100] for row in candidates[:10])
            if len(candidates) > 10:
                names += f'\n……另有 {len(candidates) - 10} 条'
            message = (f'当前文档库中发现 {len(candidates)} 条归档副本已不存在的记录。\n'
                       '范围为整个当前文档库，不受搜索或分类筛选限制。\n\n' + names +
                       '\n\n确认后从文档库列表中移除这些条目。\n原文件、其他现有文件和操作日志都会保留。')
            if unknown:
                message += f'\n另有 {unknown} 条状态无法确认，保留不处理。'
            answer = QMessageBox.question(self, '确认清理失效记录', message,
                                          QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                          QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            result = self.catalog.cleanup_missing_archives(candidates)
            for record in result['records']:
                status = self.archive_statuses.get(record['source_path'])
                if status and status[1].endswith(record['archive_path']):
                    self.archive_statuses.pop(record['source_path'], None)
                    for row, item in enumerate(self.items):
                        if str(item.path) == record['source_path']:
                            self.update_scan_status(row)
            self.refresh_search()
            self.show_scan_detail()
            self.update_controls()
            summary = f'已清理 {result["removed"]} 条失效记录；文件和操作日志保留。'
            if result['restored'] or result['skipped']:
                summary += f' 重新出现或状态变化的 {result["restored"] + result["skipped"]} 条记录已保留。'
            self.statusBar().showMessage(summary)
            QMessageBox.information(self, '清理完成', summary)
        except Exception as exc:
            QMessageBox.warning(self, '未能清理记录', str(exc))

    def apply_search_result(self, payload):
        filters = payload['filters']
        query, category = filters['query'], filters['category']
        self.search_total, self.search_page = payload['total'], payload['page']
        pages = max(1,(self.search_total+self.page_size-1)//self.page_size)
        self.archive_rows = payload['rows']
        filtered = bool(query or category or any(filters[key] for key in ('course','project','tag','quality','reading')))
        self.search_table.setProperty("emptyText", "没有找到匹配的文件\n试试更短的关键词，或重置分类、课程等筛选。\n扫描件与空文件无法搜正文；截断文件只能搜前 10 万字。" if filtered else
                                      "文档库还没有归档记录\n在“添加 / 整理”中确认归档后，文件会出现在这里。")
        self.search_table.setRowCount(len(self.archive_rows))
        for row, result in enumerate(self.archive_rows):
            state = result['_file_state']
            available = state == 'available'
            for column, field in enumerate(("filename", "category", "created_at")):
                cell = QTableWidgetItem(result[field][:10] if field == "created_at" else result[field])
                if column == 0 and not available:
                    cell.setText(cell.text() + ("（文件不存在）" if state == 'missing' else '（状态无法确认）'))
                    cell.setForeground(QColor(WARNING))
                if column == 0:
                    if result["display_title"]:
                        cell.setText(result["display_title"]+("（文件不存在）" if state=="missing" else ""))
                    cell.setData(GLYPH, Path(result["filename"]).suffix[1:].upper())
                    labels = ' · '.join(value for value in (result['course'],result['project'],result['tags']) if value)
                    snippet = result['body_snippet']
                    cell.setData(MATCH_TERMS, query_terms(query))
                    cell.setData(SUBTEXT, '归档副本不存在' if state=='missing' else '归档副本状态无法确认' if state=='unknown' else ' · '.join(v for v in (result['filename'] if result['display_title'] else '',result['reading_state'],snippet or result['notes'][:90] or labels) if v))
                cell.setToolTip(f"原路径：{result['source_path']}\n归档路径：{result['archive_path']}\n时间（UTC）：{result['created_at']}"
                                + f"\n课程：{result['course']}\n项目：{result['project']}\n标签：{result['tags']}"
                               + f"\n显示标题：{result['display_title']}\n标题来源：{result['title_source']}\n阅读状态：{result['reading_state']}\n备注：{result['notes'][:300]}"
                               + f"\n正文范围：{result['extraction_status'] or '旧记录未保存，请更新正文索引'}"
                               + ("" if available else "\n归档副本可能已被移动或删除"))
                self.search_table.setItem(row, column, cell)
        prefix = "找到" if filtered else "已归档"
        self.search_count.setText(f"{prefix} {self.search_total} 个文件 · {self.search_sort.currentText()}")
        self.page_label.setText(f'第 {self.search_page+1} / {pages} 页 · 每页 {self.page_size} 个')
        self.previous_page.setEnabled(self.worker is None and self.search_page>0)
        self.next_page.setEnabled(self.worker is None and self.search_page+1<pages)
        if self.archive_rows:
            self.search_table.selectRow(0)
        self.update_archive_selection()
        if self.history_dialog.isVisible():
            self.refresh_history()

    def refresh_history(self):
        if not self.catalog:
            return
        records = self.catalog.operations()
        self.history_table.setRowCount(len(records))
        for row, record in enumerate(records):
            for column, field in enumerate(("created_at", "action", "detail")):
                cell = QTableWidgetItem(record[field])
                cell.setToolTip(record[field])
                self.history_table.setItem(row, column, cell)

    def open_path(self, path: Path):
        if not path.exists():
            QMessageBox.warning(self, "文件不存在", f"文件可能已被移动或删除：\n{path}")
            return False
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.resolve()))):
            QMessageBox.warning(self, "无法打开", "Windows 未能打开该路径，请检查默认应用关联。")
            return False
        return True

    def open_source(self):
        row = self.scan_table.currentRow()
        if 0 <= row < len(self.items):
            return self.open_path(self.items[row].path)

    def open_archive(self):
        row = self.search_table.currentRow()
        if 0 <= row < len(self.archive_rows):
            return self.open_path(Path(self.archive_rows[row]["archive_path"]))

    def open_archive_folder(self):
        row = self.search_table.currentRow()
        if 0 <= row < len(self.archive_rows):
            return self.open_path(Path(self.archive_rows[row]["archive_path"]).parent)

    def ensure_capture(self):
        if self.capture_controller is None:
            from .screen_capture import CaptureController
            self.capture_controller=CaptureController(self)
        return self.capture_controller

    def take_screenshot(self):self.ensure_capture().begin()

    def screenshot_settings(self):self.ensure_capture().show_settings()

    def show_settings(self):
        from .settings_dialog import SettingsDialog
        SettingsDialog(self).exec()

    def closeEvent(self, event):
        capture=self.capture_controller
        if capture and capture.tray and not capture.exiting:
            self.save_settings()
            self.hide()
            capture.notify('已在托盘运行','截图快捷键 '+capture.settings['hotkey']+'；托盘菜单可退出程序')
            event.ignore()
            return
        if self.worker:
            self.cancel_work()
            self.statusBar().showMessage("正在处理当前文件，请处理结束后关闭窗口。")
            event.ignore()
            return
        self.search_timer.stop()
        self.watch_timer.stop()
        self.closing = True
        self.pending_search = None
        if self.search_worker:
            self.search_worker.requestInterruption()
            event.ignore()
            return
        if self.watch_worker:
            self.watch_worker.requestInterruption()
            event.ignore()
            return
        self.save_settings()
        self.details_panel.pdf.shutdown()
        if capture:
            capture.shutdown()
            QTimer.singleShot(0,QApplication.instance().quit)
        event.accept()


def configure_app(app):
    configure_process()
    app.setApplicationName("DocumentAssistant")
    app.setWindowIcon(QIcon(str(ICON_PATH)))
    app.setStyle("Fusion")
    translator = QTranslator(app)
    if translator.load("qtbase_zh_CN", QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)):
        app.installTranslator(translator)
    app._chinese_translator = translator


def main(start_in_tray=False):
    configure_process()
    app = QApplication([])
    configure_app(app)
    from .app_instance import AppInstance
    instance=None
    try:
        instance=AppInstance(runtime_directory(),app)
        if not instance.start(activate=not start_in_tray):return 0
        window = MainWindow()
    except Exception as exc:
        if instance:instance.shutdown()
        QMessageBox.critical(None, "启动失败", f"无法初始化 DocumentAssistant：\n{exc}\n请检查运行目录的写权限。")
        return 1
    tag_window(int(window.winId()))
    if not start_in_tray:window.show()
    window.ensure_capture()
    if start_in_tray and not window.capture_controller.tray:window.show()
    instance.activated.connect(window.capture_controller.show_main)
    result = app.exec()
    instance.shutdown()
    if window.capture_controller:window.capture_controller.shutdown()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    return result
