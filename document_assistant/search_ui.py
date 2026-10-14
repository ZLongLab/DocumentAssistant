"""Background library queries and an explicit local extraction quality report."""
from PySide6.QtCore import QThread, Signal, QTimer, Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QAbstractItemView
from .storage import archive_file_state


class SearchWorker(QThread):
    completed = Signal(object)

    def __init__(self, catalog, request, parent):
        super().__init__(parent)
        self.catalog, self.request = catalog, request

    def run(self):
        generation, filters, page, size = self.request
        try:
            query = filters['query']
            options = {k:v for k,v in filters.items() if k != 'query'}
            total, page, rows = self.catalog.search_page_data(query, page, size, self.isInterruptionRequested, **options)
            for row in rows:
                if self.isInterruptionRequested():
                    return
                row['_file_state'] = archive_file_state(row['archive_path'])
            self.completed.emit({'generation': generation, 'total': total, 'page': page, 'rows': rows,
                                 'filters': filters, 'library': self.catalog.library_id})
        except Exception as exc:
            if not self.isInterruptionRequested():
                self.completed.emit({'generation': generation, 'error': str(exc)})


def quality_report(catalog, progress=lambda *_:None, cancelled=lambda:False):
    with catalog.connection() as db:
        rows = [dict(r) for r in db.execute('SELECT id,filename,archive_path,extraction_status,length(body_snapshot) AS characters FROM archives ORDER BY id DESC')]
    counts = dict(complete=0, partial=0, none=0, unknown=0, missing=0, inaccessible=0)
    issues = []
    for n, row in enumerate(rows, 1):
        if cancelled():
            return None
        state = archive_file_state(row['archive_path'])
        status = row['extraction_status']
        quality = 'unknown' if not status else 'partial' if '截断' in status else 'complete' if status.startswith('已提取') else 'none'
        counts[quality] += 1
        if state != 'available':
            counts['missing' if state == 'missing' else 'inaccessible'] += 1
        if quality != 'complete' or state != 'available':
            issues.append({**row, 'quality': quality, 'file_state': state})
        progress(n, len(rows), '检查 '+row['filename'])
    return {'total':len(rows), 'counts':counts, 'issues':issues}


class QualityDialog(QDialog):
    def __init__(self, window, report):
        super().__init__(window)
        self.setWindowTitle('文档质量检查')
        self.resize(820, 440)
        layout = QVBoxLayout(self)
        c = report['counts']
        summary = QLabel(f"共 {report['total']} 份归档 · 正文已提取 {c['complete']} · 正文被截断 {c['partial']} · 无可搜索正文 {c['none']} · 旧记录待检查 {c['unknown']}\n"
                         f"副本不存在 {c['missing']} · 副本状态无法确认 {c['inaccessible']}。以下显示需要检查的文件。")
        summary.setWordWrap(True)
        layout.addWidget(summary)
        table = QTableWidget(len(report['issues']), 3)
        table.setHorizontalHeaderLabels(['文件名', '正文搜索范围', '归档副本'])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setColumnWidth(0, 320)
        table.setColumnWidth(1, 300)
        table.horizontalHeader().setStretchLastSection(True)
        for n, row in enumerate(report['issues']):
            values = (row['filename'], row['extraction_status'] or '旧记录未保存提取状态；可更新正文索引',
                      {'available':'存在', 'missing':'不存在', 'unknown':'无法确认'}[row['file_state']])
            for col, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setToolTip(value)
                table.setItem(n, col, item)
        layout.addWidget(table, 1)
        note = QLabel('未提取正文仍可按文件名与标签搜索。截断文件只搜索前 10 万字；旧记录不推断完整性。\n更新正文索引会读取归档副本；扫描图片仍需 OCR。检查结果不会移动或删除文件。')
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        reindex = buttons.addButton('更新正文索引', QDialogButtonBox.ButtonRole.ActionRole)
        reindex.clicked.connect(lambda: (self.accept(), QTimer.singleShot(0, window.rebuild_body_index)))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class SearchActions:
    def show_quality(self):
        if self.catalog and not self.worker:
            catalog = self.catalog
            self.launch_worker(lambda p,c:quality_report(catalog,p,c), self.quality_finished)

    def quality_finished(self, report):
        if report is None:
            self.statusBar().showMessage('质量检查已取消，文件保留。')
            return
        self.last_quality_report = report
        self.statusBar().showMessage('文档质量检查完成。')
        self._quality_dialog = QualityDialog(self, report)
        # Nonmodal delivery lets the worker finish before a user asks to reindex.
        self._quality_dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._quality_dialog.show()

    def refresh_search(self):
        self.search_timer.stop()
        self.search_generation += 1
        self.pending_search = None
        self.archive_rows = []
        self.search_table.setRowCount(0)
        if not self.catalog:
            self.search_table.setProperty('emptyText', '尚未选择文档库\n点击右上角“选择文档库”，即可查看已有归档记录。')
            self.update_archive_selection()
            return
        self.search_table.setProperty('emptyText', '正在搜索…')
        self.search_count.setText('正在查找文档…')
        self.pending_search = (self.search_generation, self.current_filters(), self.search_page, self.page_size)
        if self.search_worker:
            self.search_worker.requestInterruption()
        else:
            self.start_search()
        self.update_archive_selection()

    def start_search(self):
        if self.closing or not self.pending_search:
            return
        request, self.pending_search = self.pending_search, None
        self.search_worker = SearchWorker(self.catalog, request, self)
        self.search_worker.completed.connect(self.search_completed)
        self.search_worker.finished.connect(self.search_finished)
        self.search_worker.start()

    def search_completed(self, result):
        if self.closing or result['generation'] != self.search_generation:
            return
        if 'error' in result:
            self.search_table.setProperty('emptyText', '搜索未完成，请重试。')
            self.search_count.setText('搜索失败')
            self.statusBar().showMessage('搜索失败：'+result['error'])
            return
        if not self.catalog or result['library'] != self.catalog.library_id:
            return
        self.apply_search_result(result)

    def search_finished(self):
        worker, self.search_worker = self.search_worker, None
        if worker:
            worker.deleteLater()
        if self.closing:
            QTimer.singleShot(0, self.close)
        elif self.pending_search:
            self.start_search()
        else:
            self.update_controls()
