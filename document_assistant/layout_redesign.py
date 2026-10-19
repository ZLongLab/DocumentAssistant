"""Redesigned layout based on taste-design: compact, clear, efficient."""
from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPlainTextEdit, QPushButton, QStackedWidget, QTableWidget,
    QVBoxLayout, QWidget,
)
from PySide6.QtGui import QIcon

from .cards import CardGrid, DetailPane
from .presentation import line_icon
from .theme_redesign import get_colors, normalize_theme, switch_theme
from .windows_identity import ICON_PATH


def label(text, name=None):
    """Create a plain text label."""
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        item.setObjectName(name)
    return item


def button(text, handler, icon=None, name=None):
    """Create a button with optional icon."""
    item = QPushButton(text)
    item.clicked.connect(handler)
    if icon:
        item.setIcon(line_icon(icon, '#ffffff' if name in ('primary', 'success', 'addFile') else '#374151'))
        item.setIconSize(QSize(18, 18))
    if name:
        item.setObjectName(name)
    return item


def frame(name, direction=QVBoxLayout, margins=(0, 0, 0, 0), spacing=0):
    """Create a frame with layout."""
    item = QFrame()
    item.setObjectName(name)
    layout = direction(item)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return item, layout


class WorkflowSteps(QWidget):
    """Compact workflow step indicator."""
    def __init__(self):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        self.badges = []
        self.stage = 0

        for index, title in enumerate(('导入', '检查', '归档')):
            if index:
                sep = label('→', 'muted')
                sep.setStyleSheet('color: #cbd5e1;')
                row.addWidget(sep)

            badge = label(str(index + 1), 'stepBadge')
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(20, 20)
            self.badges.append(badge)
            row.addWidget(badge)

            lbl = label(title, 'muted')
            lbl.setStyleSheet('font-size: 12px; color: #64748b;')
            row.addWidget(lbl)

        row.addStretch()
        self.set_stage(0)

    def set_stage(self, stage):
        """Update the active stage."""
        self.stage = stage
        colors = get_colors()

        for index, badge in enumerate(self.badges):
            if index < stage:
                # Done
                bg = colors['success']
                fg = '#ffffff'
            elif index == stage:
                # Active
                bg = colors['accent']
                fg = '#ffffff'
            else:
                # Inactive
                bg = '#e5e7eb'
                fg = '#64748b'

            badge.setStyleSheet(
                f'background: {bg}; color: {fg}; '
                f'border-radius: 10px; font-weight: 600; font-size: 11px;'
            )

    def refresh_stage(self):
        """Re-apply current stage colors after theme change."""
        self.set_stage(self.stage)


class SelectAllCheckBox(QCheckBox):
    """Tri-state checkbox for select all."""
    def nextCheckState(self):
        state = Qt.CheckState.Unchecked if self.checkState() == Qt.CheckState.Checked else Qt.CheckState.Checked
        self.setCheckState(state)


def apply_theme(window, theme_name, *, persist=True):
    """Apply theme to window."""
    theme_name = normalize_theme(theme_name)
    switch_theme(theme_name)
    from .theme_redesign import WORKBENCH_QSS
    window.setStyleSheet(WORKBENCH_QSS)

    # Update dynamic elements
    if hasattr(window, 'steps_label') and window.steps_label:
        window.steps_label.refresh_stage()

    if hasattr(window, 'details_panel') and window.details_panel:
        window.details_panel.refresh_theme()

    colors = get_colors()

    # Update nav icons
    if hasattr(window, 'nav_buttons') and hasattr(window, 'tabs'):
        idx = window.tabs.currentIndex()
        for i, nav in enumerate(window.nav_buttons):
            icon_name = 'import' if i == 0 else 'library'
            icon_color = '#ffffff' if i == idx else colors['sidebar_text']
            nav.setIcon(line_icon(icon_name, icon_color))

    # Update other icons
    if hasattr(window, 'screenshot_button'):
        window.screenshot_button.setIcon(line_icon('capture', '#ffffff'))

    if hasattr(window, 'library_title_icon'):
        window.library_title_icon.setPixmap(
            line_icon('library', colors['accent']).pixmap(24, 24)
        )

    # Save theme preference
    if hasattr(window, 'settings') and isinstance(window.settings, dict):
        window.settings['theme'] = theme_name
        if persist and hasattr(window, 'save_settings'):
            window.save_settings()

    window.statusBar().showMessage(
        f"已切换至 {'暖玫瑰金' if theme_name == 'rose' else '海蓝晶石'} 主题"
    )


def toggle_theme(window):
    """Toggle between ocean and rose themes."""
    from .theme_redesign import CURRENT_THEME
    next_theme = 'rose' if CURRENT_THEME == 'ocean' else 'ocean'
    apply_theme(window, next_theme)


def build_window(window):
    """Build the main window UI with redesigned layout."""
    from .gui import table

    # Apply initial theme before building UI
    init_theme = normalize_theme(window.settings.get('theme', 'ocean'))
    switch_theme(init_theme)

    window.setMinimumSize(960, 600)
    available = QApplication.primaryScreen().availableGeometry()
    window.resize(
        min(1440, max(960, available.width() - 48)),
        min(900, max(600, available.height() - 64))
    )

    root = QWidget()
    window.setCentralWidget(root)
    root_layout = QHBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)

    # ═══════════════════════════════════════════════════════════════
    # Sidebar - Compact Design
    # ═══════════════════════════════════════════════════════════════
    sidebar, side = frame('sidebar', margins=(12, 16, 12, 16), spacing=12)
    sidebar.setFixedWidth(200)

    # Brand
    brand = QHBoxLayout()
    brand.setSpacing(8)
    mark = label('', 'brandMark')
    mark.setFixedSize(32, 32)
    mark.setPixmap(QIcon(str(ICON_PATH)).pixmap(32, 32))
    mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
    brand.addWidget(mark)

    brand_text = label('DocumentAssistant', 'brand')
    brand.addWidget(brand_text)
    side.addLayout(brand)

    side.addSpacing(8)

    # Navigation
    window.nav_buttons = []
    group = QButtonGroup(window)

    for index, (text, symbol) in enumerate((('添加 / 整理', 'import'), ('文档库', 'library'))):
        nav = button(text, lambda checked=False, i=index: window.tabs.setCurrentIndex(i), symbol, 'nav')
        nav.setIcon(line_icon(symbol, '#94a3b8'))
        nav.setCheckable(True)
        nav.setMinimumHeight(40)
        group.addButton(nav, index)
        side.addWidget(nav)
        window.nav_buttons.append(nav)

    # Screenshot button
    window.screenshot_button = button(
        '截图 Alt+S',
        window.take_screenshot,
        'capture',
        'captureLaunch'
    )
    window.screenshot_button.setIcon(line_icon('capture', '#ffffff'))
    window.screenshot_button.setMinimumHeight(40)
    window.screenshot_button.setToolTip('框选屏幕截图，支持标注')
    side.addWidget(window.screenshot_button)

    side.addStretch()

    # Footer actions
    colors = get_colors()
    footer_actions = [
        ('设置', window.show_settings, 'settings'),
        ('主题', lambda: toggle_theme(window), 'more'),
        ('更多', lambda: window.show_more_menu(), 'more'),
    ]

    for text, handler, icon in footer_actions:
        btn = button(text, handler, icon, 'footerAction')
        btn.setIcon(line_icon(icon, colors['sidebar_text']))
        btn.setMinimumHeight(36)
        side.addWidget(btn)

    root_layout.addWidget(sidebar)

    # ═══════════════════════════════════════════════════════════════
    # Main Content Area
    # ═══════════════════════════════════════════════════════════════
    main = QWidget()
    main_layout = QVBoxLayout(main)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)

    # Topbar - Compact
    topbar, heading = frame('topbar', QHBoxLayout, (16, 16, 20, 16), 12)

    titles = QVBoxLayout()
    titles.setSpacing(4)

    window.page_title = label('整理你的文档', 'pageTitle')
    window.page_subtitle = label('检查分类建议，确认后复制到文档库', 'subtitle')
    window.page_subtitle.setWordWrap(True)

    titles.addWidget(window.page_title)
    titles.addWidget(window.page_subtitle)

    # Workflow steps
    window.steps_label = WorkflowSteps()
    titles.addWidget(window.steps_label)

    heading.addLayout(titles, 1)

    # Library icon (hidden initially)
    window.library_title_icon = label('', 'libraryTitleIcon')
    window.library_title_icon.setFixedSize(40, 40)
    window.library_title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.library_title_icon.setPixmap(line_icon('library', colors['accent']).pixmap(24, 24))
    window.library_title_icon.setVisible(False)
    heading.addWidget(window.library_title_icon)

    # Topbar actions
    actions = QVBoxLayout()
    actions.setSpacing(6)

    # Library selection
    location = QHBoxLayout()
    location.setSpacing(8)
    window.library_edit = label('尚未选择文档库', 'muted')
    window.library_edit.setStyleSheet('font-size: 12px;')
    window.library_button = button('选择文档库', window.choose_library)
    location.addWidget(window.library_edit)
    location.addWidget(window.library_button)
    actions.addLayout(location)

    heading.addLayout(actions)

    main_layout.addWidget(topbar)

    # ═══════════════════════════════════════════════════════════════
    # Tab Content
    # ═══════════════════════════════════════════════════════════════
    window.tabs = QStackedWidget()

    # --- Review Tab (Add/Organize) ---
    review = QWidget()
    review_layout = QVBoxLayout(review)
    review_layout.setContentsMargins(20, 16, 20, 16)
    review_layout.setSpacing(12)

    body = QHBoxLayout()
    body.setSpacing(12)

    left = QVBoxLayout()
    left.setSpacing(12)

    # Dropzone
    # Hidden source edit for compatibility
    window.source_edit = QLineEdit(root)
    window.source_edit.setReadOnly(True)
    window.source_edit.hide()

    dropzone, drop = frame('dropzone', QHBoxLayout, (12, 12, 12, 12), 8)
    window.file_button = button('+ 添加文件', window.choose_files, 'plus', 'addFile')
    window.source_button = button('扫描文件夹', window.choose_and_scan_folder, 'folder')
    window.scan_button = window.source_button

    drop.addWidget(window.file_button)
    drop.addWidget(window.source_button)

    window.import_hint = label('支持 PDF、DOCX、DOC、TXT\n可拖入文件或一次选择多个', 'muted')
    window.import_hint.setWordWrap(True)
    drop.addWidget(window.import_hint, 1)

    left.addWidget(dropzone)

    # Toolbar
    toolbar = QHBoxLayout()
    toolbar.setSpacing(8)

    window.file_count = label('待整理文件', 'sectionTitle')
    toolbar.addWidget(window.file_count)

    count_badge = label('0', 'muted')
    count_badge.setStyleSheet('font-weight: 600; color: #1a1a1a;')
    window.count_badge = count_badge
    toolbar.addWidget(count_badge)

    toolbar.addStretch()

    window.review_sort = QComboBox()
    window.review_sort.addItem('优先显示待确认文件', 'attention')
    window.review_sort.addItem('保留添加顺序', 'original')
    window.review_sort.setCurrentIndex(0 if window.review_order == 'attention' else 1)
    window.review_sort.currentIndexChanged.connect(window.review_order_changed)
    toolbar.addWidget(window.review_sort)

    window.view_button = button(
        '列表视图' if window.review_mode == 'cards' else '卡片视图',
        window.toggle_review_view
    )
    toolbar.addWidget(window.view_button)

    window.clear_button = button('清空', window.clear_imports)
    toolbar.addWidget(window.clear_button)

    left.addLayout(toolbar)

    # Content stack
    window.scan_table = table(['选择', '文件名', '建议分类', '分类依据', '处理状态'])
    window.scan_table.setParent(review)
    window.scan_table.hide()
    window.scan_table.itemSelectionChanged.connect(window.show_scan_detail)
    window.scan_table.itemChanged.connect(window.scan_item_changed)

    window.review_stack = QStackedWidget()

    # Empty state
    empty, empty_layout = frame('emptyState', margins=(20, 40, 20, 40), spacing=12)
    empty_layout.addStretch()

    empty_icon = label('📄', 'emptyIcon')
    empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    empty_icon.setStyleSheet('font-size: 48px; opacity: 0.3;')
    empty_layout.addWidget(empty_icon)

    empty_title = label('拖入文件，开始整理', 'emptyTitle')
    empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
    empty_layout.addWidget(empty_title)

    empty_text = label(
        '把文档拖到这里，或点击"添加文件"\n导入 → 检查分类 → 确认归档',
        'emptyText'
    )
    empty_text.setWordWrap(True)
    empty_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
    empty_layout.addWidget(empty_text)

    empty_layout.addStretch()

    # Cards view
    window.cards_view = CardGrid(window)

    window.review_stack.addWidget(empty)
    window.review_stack.addWidget(window.cards_view)
    window.review_stack.addWidget(window.scan_table)

    left.addWidget(window.review_stack, 1)
    left.addWidget(window.cards_view.page_controls)

    body.addLayout(left, 1)

    # Detail panel
    window.details_panel = DetailPane(window)
    body.addWidget(window.details_panel)

    review_layout.addLayout(body, 1)

    # Hidden compatibility elements
    window.reason_label = QLabel()
    window.reason_label.setParent(review)
    window.reason_label.hide()

    # Progress bar (hidden by default)
    window.progress_container = QWidget()
    progress_row = QHBoxLayout(window.progress_container)
    progress_row.setContentsMargins(0, 0, 0, 0)
    from PySide6.QtWidgets import QProgressBar
    window.progress = QProgressBar()
    window.progress.setRange(0, 100)
    window.cancel_button = button('停止', window.cancel_work)
    progress_row.addWidget(window.progress, 1)
    progress_row.addWidget(window.cancel_button)
    review_layout.addWidget(window.progress_container)
    window.progress_container.hide()

    # Bottom action bar
    actionbar, bottom = frame('actionbar', QHBoxLayout, (0, 12, 0, 12), 8)

    summary = QVBoxLayout()
    summary.setSpacing(4)

    count = QHBoxLayout()
    count.setSpacing(8)
    window.all_check = SelectAllCheckBox('全选')
    window.all_check.setTristate(True)
    window.all_check.setChecked(True)
    window.all_check.checkStateChanged.connect(
        lambda state: window.check_all(state == Qt.CheckState.Checked)
    )
    count.addWidget(window.all_check)

    window.count_label = label('尚未添加文件')
    count.addWidget(window.count_label, 1)
    summary.addLayout(count)

    window.selection_hint = label('添加文件后，检查分类建议再确认归档', 'muted')
    window.selection_hint.setWordWrap(True)
    summary.addWidget(window.selection_hint)

    bottom.addLayout(summary, 1)

    window.bulk_button = button('批量整理', window.bulk_organize)
    window.reread_button = button('重新读取', window.reread_selected)
    window.details_button = button('详情', window.show_details)
    window.archive_button = button('✓ 确认归档', window.confirm_archive, 'check', 'success')

    bottom.addWidget(window.bulk_button)
    bottom.addWidget(window.reread_button)
    bottom.addWidget(window.details_button)
    bottom.addWidget(window.archive_button)

    review_layout.addWidget(actionbar)

    window.tabs.addWidget(review)

    # Details dialog (for compatibility)
    window.details_dialog = QDialog(window)
    window.details_dialog.setWindowTitle('文件信息')
    window.details_dialog.resize(740, 500)
    details_layout = QVBoxLayout(window.details_dialog)
    window.detail = QPlainTextEdit()
    window.detail.setReadOnly(True)
    details_layout.addWidget(window.detail)
    window.open_source_button = button('打开原文件', window.open_source, 'open')
    details_layout.addWidget(window.open_source_button)

    # History dialog
    window.history_dialog = QDialog(window)
    window.history_dialog.setWindowTitle('操作记录')
    window.history_dialog.resize(900, 520)
    history_layout = QVBoxLayout(window.history_dialog)
    history_layout.addWidget(label('最近 500 条记录', 'muted'))
    window.history_table = table(['时间（UTC）', '操作', '详情'])
    window.history_table.setColumnWidth(0, 200)
    window.history_table.setColumnWidth(1, 130)
    history_layout.addWidget(window.history_table)

    # --- Library Tab (Search) ---
    search = QWidget()
    search_layout = QVBoxLayout(search)
    search_layout.setContentsMargins(20, 16, 20, 16)
    search_layout.setSpacing(12)

    # Search toolbar
    search_toolbar = QHBoxLayout()
    search_toolbar.setSpacing(8)

    window.search_edit = QLineEdit()
    window.search_edit.setPlaceholderText('搜索文件名、正文、课程、项目或标签')
    window.search_edit.addAction(
        line_icon('search', '#64748b'),
        QLineEdit.ActionPosition.LeadingPosition
    )
    window.search_edit.returnPressed.connect(window.refresh_search)
    window.search_edit.textChanged.connect(window.queue_search)
    search_toolbar.addWidget(window.search_edit, 1)

    window.search_category = QComboBox()
    window.search_category.addItems(['全部分类', *window.categories])
    window.search_category.currentIndexChanged.connect(window.reset_search)
    search_toolbar.addWidget(window.search_category)

    window.search_scope = QComboBox()
    window.search_scope.addItems(['全文与标签', '仅文件名'])
    window.search_scope.currentIndexChanged.connect(window.reset_search)
    search_toolbar.addWidget(window.search_scope)

    window.search_button = button('搜索', window.refresh_search)
    search_toolbar.addWidget(window.search_button)

    search_layout.addLayout(search_toolbar)

    # Organization filters
    window.build_organization_filters(search_layout)

    # More filters toggle
    window.more_filters = button('更多筛选', lambda: None)
    window.more_filters.setCheckable(True)
    window.more_filters.toggled.connect(window.advanced_filters.setVisible)
    window.more_filters.toggled.connect(
        lambda expanded: window.more_filters.setText('收起' if expanded else '更多筛选')
    )
    search_toolbar.addWidget(window.more_filters)

    # Results heading
    results_heading = QHBoxLayout()
    results_heading.setSpacing(8)

    results_heading.addWidget(label('已归档文件', 'sectionTitle'))

    window.search_count = label('选择文档库后查找', 'muted')
    window.search_count.setStyleSheet('font-weight: 600; color: #1a1a1a;')
    results_heading.addWidget(window.search_count)

    results_heading.addStretch()

    window.labels_button = button('分类/标签', window.edit_archive_labels)
    window.reading_button = button('阅读/备注', window.edit_reading)
    window.cleanup_button = button('清理失效', window.cleanup_missing_records)

    results_heading.addWidget(window.labels_button)
    results_heading.addWidget(window.reading_button)
    results_heading.addWidget(window.cleanup_button)

    search_layout.addLayout(results_heading)

    # Results table
    search_list, listing = frame('list')
    window.search_table = table(['文件名', '分类', '归档日期'])
    window.search_table.setSelectionMode(
        window.search_table.SelectionMode.ExtendedSelection
    )
    window.search_table.setProperty(
        'emptyText',
        '尚未选择文档库\n点击右上角"选择文档库"查看归档记录'
    )
    from .presentation import TwoLineDelegate, CategoryDelegate
    window.search_table.setItemDelegateForColumn(0, TwoLineDelegate('file', window.search_table))
    window.search_table.setItemDelegateForColumn(1, CategoryDelegate(window.search_table))
    window.search_table.itemDoubleClicked.connect(lambda _: window.open_archive())
    window.search_table.itemSelectionChanged.connect(window.update_archive_selection)

    listing.addWidget(window.search_table)
    search_layout.addWidget(search_list, 1)

    # Pagination
    pages = QHBoxLayout()
    pages.addStretch()
    window.previous_page = button('上一页', lambda: window.change_search_page(-1))
    window.page_label = label('第 1 页', 'muted')
    window.next_page = button('下一页', lambda: window.change_search_page(1))
    pages.addWidget(window.previous_page)
    pages.addWidget(window.page_label)
    pages.addWidget(window.next_page)
    search_layout.addLayout(pages)

    # Search action bar
    search_actionbar, search_bottom = frame('actionbar', QHBoxLayout, (0, 12, 0, 12), 8)

    library_summary = QVBoxLayout()
    library_summary.setSpacing(4)
    window.library_selection = label('选择文件后可直接打开')
    library_summary.addWidget(window.library_selection)
    library_summary.addWidget(label('无需手动查找文件夹', 'muted'))
    search_bottom.addLayout(library_summary, 1)

    window.preview_archive_button = button('预览', window.preview_archive)
    window.open_folder_button = button('所在文件夹', window.open_archive_folder)
    window.open_archive_button = button('打开文件', window.open_archive, 'open', 'primary')

    search_bottom.addWidget(window.preview_archive_button)
    search_bottom.addWidget(window.open_folder_button)
    search_bottom.addWidget(window.open_archive_button)

    search_layout.addWidget(search_actionbar)

    window.tabs.addWidget(search)

    main_layout.addWidget(window.tabs, 1)
    root_layout.addWidget(main, 1)

    # ═══════════════════════════════════════════════════════════════
    # Page Change Handler
    # ═══════════════════════════════════════════════════════════════
    def page_changed(index):
        window.nav_buttons[index].setChecked(True)
        window.page_title.setText('整理你的文档' if index == 0 else '你的文档库')
        window.page_subtitle.setText(
            '检查分类建议，确认后复制到文档库' if index == 0
            else '搜索正文、课程与项目，直接打开已归档文件'
        )
        window.steps_label.setVisible(index == 0)
        window.library_title_icon.setVisible(index == 1)

        colors = get_colors()
        for i, nav in enumerate(window.nav_buttons):
            icon_name = 'import' if i == 0 else 'library'
            icon_color = '#ffffff' if i == index else colors['sidebar_text']
            nav.setIcon(line_icon(icon_name, icon_color))

    window.tabs.currentChanged.connect(page_changed)
    page_changed(0)

    # ═══════════════════════════════════════════════════════════════
    # Status Bar & Window Setup
    # ═══════════════════════════════════════════════════════════════
    window.statusBar().setSizeGripEnabled(False)
    window.statusBar().showMessage('添加文件 → 检查分类 → 确认归档；在文档库搜索并打开')
    window.setWindowIcon(QIcon(str(ICON_PATH)))

    # Apply theme
    apply_theme(window, init_theme, persist=False)

    # Handle list view mode
    if window.review_mode == 'list':
        window.details_panel.hide()
        from PySide6.QtWidgets import QHeaderView
        window.scan_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        window.scan_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed
        )
        window.scan_table.setColumnWidth(0, 44)

    # Create more menu
    window.create_more_menu()


def create_more_menu_method(self):
    """Create the more menu for the sidebar."""
    from PySide6.QtWidgets import QMenu

    self.more_menu = QMenu(self)

    # Store references for update_controls
    self.rule_button = self.more_menu.addAction('分类规则', self.edit_rules)
    self.more_menu.addAction('自定义分类', self.manage_categories)
    self.more_menu.addSeparator()
    self.more_menu.addAction('课程/项目规则', self.edit_organization_rules)
    self.remember_category_action = self.more_menu.addAction('记住分类方式', self.remember_category)
    self.category_rules_action = self.more_menu.addAction('已保存分类方式', self.manage_category_rules)
    self.watch_action = self.more_menu.addAction('文件夹收件箱', self.manage_watch_folders)
    self.more_menu.addSeparator()
    self.reclassify_button = self.more_menu.addAction('重新建议分类', self.reclassify)
    self.clear_action = self.more_menu.addAction('清空待整理列表', self.clear_imports)
    self.more_menu.addSeparator()
    self.history_action = self.more_menu.addAction('操作记录', self.show_history)
    self.recycle_action = self.more_menu.addAction('恢复区', self.show_recycle)
    self.full_backup_action = self.more_menu.addAction('完整备份', self.export_full_backup)
    self.restore_backup_action = self.more_menu.addAction('从备份恢复', self.import_full_backup)
