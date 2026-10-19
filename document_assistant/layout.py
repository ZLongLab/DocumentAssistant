"""Native card workbench inspired by the user's reference image."""
from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMenu, QPlainTextEdit, QProgressBar, QPushButton,
    QStackedWidget, QVBoxLayout, QWidget,
)
from .cards import CardGrid, DetailPane, ShelfArtwork
from .presentation import TwoLineDelegate, line_icon
from .rules import CATEGORIES
from .theme import get_colors, normalize_theme, switch_theme
from .windows_identity import ICON_PATH
from .library_decoration import ActionMenu, LibraryFlourish, WorkbenchFlourish
from PySide6.QtGui import QIcon


def label(text, name=None):
    item = QLabel(text)
    item.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        item.setObjectName(name)
    return item


def button(text, handler, icon=None, primary=False):
    item = QPushButton(text)
    item.clicked.connect(handler)
    if icon:
        item.setIcon(line_icon(icon, '#ffffff' if primary else '#43504c'))
        item.setIconSize(QSize(20, 20))
    if primary:
        item.setObjectName('primary')
        item.setMinimumWidth(140)
    return item


def frame(name, direction=QVBoxLayout, margins=(0, 0, 0, 0), spacing=0):
    from .theme_starry import GlassFrame
    item = GlassFrame() if name in {'sidebar', 'sidebarFooter', 'list', 'workflowBand', 'actionbar'} else QFrame()
    item.setObjectName(name)
    layout = direction(item)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    return item, layout


class WorkbenchResponsive(QObject):
    def __init__(self,window):
        super().__init__(window)
        self.window=window;self.compact=None;self.restore_details=False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fit)
        window.installEventFilter(self)
        self.timer.start(0)

    def eventFilter(self,watched,event):
        if event.type()==QEvent.Type.Resize:self.timer.start(0)
        return False

    def fit(self):
        compact=self.window.width()<1200
        self.window.import_hint.setVisible(not compact)
        wide = self.window.width() >= 1200
        if hasattr(self.window, 'topbar_art'):
            self.window.topbar_art.setVisible(not getattr(self.window, '_compact_layout', False) and self.window.tabs.currentIndex() == 0 and wide)
        if hasattr(self.window, 'library_art'):
            self.window.library_art.setVisible(not getattr(self.window, '_compact_layout', False) and self.window.tabs.currentIndex() == 1 and wide)
        if compact!=self.compact:
            if compact:
                self.restore_details=not self.window.details_panel.isHidden()
                self.window.details_panel.hide()
            elif self.restore_details:self.window.details_panel.show()
            self.compact=compact


class TableColumns(QObject):
    def __init__(self, table, kind):
        super().__init__(table)
        self.table, self.scheduled = table, False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.fit)
        table.viewport().installEventFilter(self)

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize and not self.scheduled:
            self.scheduled = True
            self.timer.start(0)
        return False

    def fit(self):
        available = max(500, self.table.viewport().width())
        for column, size in enumerate((available - 260, 120, 140)):
            if self.table.columnWidth(column) != size:
                self.table.setColumnWidth(column, size)
        self.scheduled = False


class WorkflowSteps(QWidget):
    def __init__(self):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.badges = []
        self.stage = 0
        for index, title in enumerate(('导入文件', '检查分类', '确认归档')):
            if index:
                row.addWidget(label('—', 'muted'))
            badge = label(str(index + 1))
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setFixedSize(24, 24)
            self.badges.append(badge)
            row.addWidget(badge)
            row.addWidget(label(title, 'muted'))
        row.addStretch()
        self.set_stage(0)

    def set_stage(self, stage):
        self.stage = stage
        colors = get_colors()
        from .theme import CURRENT_THEME
        starry = CURRENT_THEME == 'starry'
        for index, badge in enumerate(self.badges):
            badge.setFixedSize(32 if starry else 24, 32 if starry else 24)
            if index < stage:
                bg = colors['step_done']
                fg = '#ffffff'
            elif index == stage:
                bg = colors['step_active']
                fg = '#ffffff'
            else:
                bg = colors['step_inactive_bg']
                fg = colors['step_inactive_text']
            badge.setStyleSheet(f'background:{bg};color:{fg};border-radius:{16 if starry else 12}px;font-weight:600;')

    def refresh_stage(self):
        self.set_stage(self.stage)


def apply_theme(window, theme_name, *, persist=True):
    theme_name = normalize_theme(theme_name)
    switch_theme(theme_name)
    from .theme import WORKBENCH_QSS
    colors = get_colors()
    if getattr(window, '_compact_layout', False):
        from .theme_minimal import build_minimal_qss
        from .theme_starry import STARRY_QSS
        window.setStyleSheet(WORKBENCH_QSS + build_minimal_qss(colors) + (STARRY_QSS if theme_name == 'starry' else ''))
    else:
        window.setStyleSheet(WORKBENCH_QSS)

    if hasattr(window, 'theme_toggle'):
        if theme_name == 'starry':
            window.theme_toggle.setText('主题：星空毛玻璃')
            window.theme_toggle.setToolTip('蓝黑星空与背景磨砂玻璃；点击切换其他主题')
        elif theme_name == 'ocean':
            window.theme_toggle.setText('主题：海蓝晶石')
            window.theme_toggle.setToolTip('当前为海蓝晶石。点击切换为暖玫瑰金。')
        else:
            window.theme_toggle.setText('主题：暖玫瑰金')
            window.theme_toggle.setToolTip('当前为暖玫瑰金。点击切换为海蓝晶石。')
        window.theme_toggle.setIcon(line_icon('more', colors['footer_text']))

    if hasattr(window, 'shelf') and window.shelf:
        window.shelf.update()
    if hasattr(window, 'library_art') and window.library_art:
        window.library_art.update()
    if hasattr(window, 'topbar_art') and window.topbar_art:
        window.topbar_art.update()

    if hasattr(window, 'steps_label') and window.steps_label:
        window.steps_label.refresh_stage()

    if hasattr(window, 'details_panel') and window.details_panel:
        window.details_panel.refresh_theme()

    if hasattr(window, 'nav_buttons') and hasattr(window, 'tabs'):
        idx = window.tabs.currentIndex()
        for i, nav in enumerate(window.nav_buttons):
            nav.setIcon(line_icon('import' if i == 0 else 'library', '#ffffff' if i == idx else colors['nav_text']))
    if hasattr(window, 'screenshot_button'):
        window.screenshot_button.setIcon(line_icon('capture', '#ffffff'))
    for attribute, symbol in (('source_button', 'folder'), ('library_button', 'folder'),
                              ('open_folder_button', 'folder'), ('open_source_button', 'open')):
        if hasattr(window, attribute):
            getattr(window, attribute).setIcon(line_icon(symbol, colors['muted']))
    if hasattr(window, 'library_edit') and window.library_edit.actions():
        window.library_edit.actions()[0].setIcon(line_icon('folder', colors['muted']))
    if hasattr(window, 'search_edit') and window.search_edit.actions():
        window.search_edit.actions()[0].setIcon(line_icon('search', colors['muted']))
    if hasattr(window, 'library_title_icon'):
        window.library_title_icon.setPixmap(line_icon('library', colors['primary_bg']).pixmap(28, 28))
    if hasattr(window, 'more_button'):
        window.more_button.setIcon(line_icon('more', colors['footer_text']))
    if hasattr(window, 'settings_button'):
        window.settings_button.setIcon(line_icon('settings', colors['footer_text']))
    if hasattr(window, 'topbar_frame'):
        window.topbar_frame.style().unpolish(window.topbar_frame)
        window.topbar_frame.style().polish(window.topbar_frame)
    if hasattr(window.centralWidget(), 'set_theme'):
        window.centralWidget().set_theme(theme_name, colors['page_bg'])
    if hasattr(window, 'window_chrome'):
        window.window_chrome.set_theme(theme_name)

    if hasattr(window, 'settings') and isinstance(window.settings, dict):
        window.settings['theme'] = theme_name
        if getattr(window, '_compact_layout', False):
            window.settings['design_revision'] = 'starry-v1'
        if persist and hasattr(window, 'save_settings'):
            window.save_settings()


def toggle_theme(window):
    from .theme import CURRENT_THEME
    themes = ('starry', 'ocean', 'rose')
    next_theme = themes[(themes.index(CURRENT_THEME) + 1) % len(themes)]
    apply_theme(window, next_theme)
    theme_title = {'starry': '星空毛玻璃', 'ocean': '海蓝晶石', 'rose': '暖玫瑰金'}[next_theme]
    window.statusBar().showMessage(f'已切换至{theme_title}主题')


class SelectAllCheckBox(QCheckBox):
    def nextCheckState(self):
        self.setCheckState(Qt.CheckState.Unchecked if self.checkState()==Qt.CheckState.Checked else Qt.CheckState.Checked)


def build_window(window, *, compact=False):
    # Keep all action/widget contracts in one builder; variants change presentation only.
    window._compact_layout = compact
    if compact:
        from .cards_minimal import CardGrid, MinimalDetailPane as DetailPane
    else:
        from .cards import CardGrid, DetailPane
    from .gui import table
    # Establish the saved palette before constructing theme-aware child widgets.
    init_theme = normalize_theme(window.settings.get('theme', 'ocean'))
    if compact and window.settings.get('design_revision') != 'starry-v1':
        init_theme = 'starry'
    switch_theme(init_theme)
    window.setMinimumSize(960, 580)
    available = QApplication.primaryScreen().availableGeometry()
    window.resize(min(1540, max(960, available.width() - 48)),
                  min(960, max(580, available.height() - 64)))
    from .theme_starry import StarfieldBackground
    root = StarfieldBackground()
    window.setCentralWidget(root)
    root_layout = QHBoxLayout(root)
    root_layout.setContentsMargins(0, 0, 0, 0)
    root_layout.setSpacing(0)
    sidebar, side = frame('sidebar', margins=(14, 24, 14, 18), spacing=18)
    sidebar.setFixedWidth(200 if compact else 220)
    brand = QHBoxLayout()
    mark = label('', 'brandMark')
    mark.setFixedSize(36, 42)
    mark.setPixmap(QIcon(str(ICON_PATH)).pixmap(36, 36))
    mark.setStyleSheet('background: transparent; border: 0;')
    mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
    brand.addWidget(mark)
    brand_text = QVBoxLayout()
    brand_text.addWidget(label('DocumentAssistant', 'brand'))
    brand_text.addWidget(label('本地文档管理', 'sidebarNote'))
    brand.addLayout(brand_text)
    side.addLayout(brand)
    side.addSpacing(4 if compact else 12)
    window.nav_buttons = []
    group = QButtonGroup(window)
    for index, (text, symbol) in enumerate((('添加 / 整理', 'import'), ('文档库', 'library'))):
        nav = button(text, lambda checked=False, i=index: window.tabs.setCurrentIndex(i), symbol)
        nav.setObjectName('nav')
        nav.setIcon(line_icon(symbol,'#e2eee7'))
        nav.setCheckable(True)
        nav.setMinimumHeight(44 if compact else 54)
        group.addButton(nav, index)
        side.addWidget(nav)
        window.nav_buttons.append(nav)
    window.screenshot_button=button('框选截图  Alt+S',window.take_screenshot,'capture')
    window.screenshot_button.setObjectName('captureLaunch')
    window.screenshot_button.setIcon(line_icon('capture','#ffffff'))
    window.screenshot_button.setMinimumHeight(52)
    window.screenshot_button.setToolTip('框选屏幕，标注后保存或复制；快捷键可在截图设置中修改')
    side.addWidget(window.screenshot_button)
    window.shelf = ShelfArtwork()
    side.addWidget(window.shelf, 1)
    if compact:
        window.shelf.hide()
        side.addStretch(1)
    footer,footer_layout=frame('sidebarFooter',margins=(8,10,8,8),spacing=7)
    footer_layout.addWidget(label('当前文档库','footerCaption'))
    location=QHBoxLayout();location.setContentsMargins(8,0,8,4);location.setSpacing(8)
    folder_icon=label('');folder_icon.setPixmap(line_icon('folder','#cbded2').pixmap(18,18));location.addWidget(folder_icon)
    from .path_label import LibraryPathLabel
    window.sidebar_path=LibraryPathLabel('尚未选择文档库')
    location.addWidget(window.sidebar_path,1);footer_layout.addLayout(location)
    separator=QFrame();separator.setObjectName('footerSeparator');separator.setFixedHeight(1);footer_layout.addWidget(separator)
    window.theme_toggle = button('主题：海蓝晶石', lambda: toggle_theme(window), 'more')
    window.theme_toggle.setObjectName('footerAction')
    window.theme_toggle.setMinimumHeight(38)
    window.theme_toggle.setToolTip('点击切换海蓝晶石与暖玫瑰金主题')
    footer_layout.addWidget(window.theme_toggle)
    window.more_button = button('更多操作', lambda: window.more_menu.popup(
        window.more_button.mapToGlobal(QPoint(0, -window.more_menu.sizeHint().height()))), 'more')
    window.more_button.setObjectName('footerAction');window.more_button.setMinimumHeight(38)
    window.more_button.setIcon(line_icon('more','#dcebe1'))
    window.more_menu = ActionMenu(parent=window)
    menu = window.more_menu
    menu_theme = ActionMenu('视觉主题', window.more_menu)
    window.more_menu.addMenu(menu_theme).setIcon(line_icon('more', '#2563eb'))
    menu_theme.addAction('星空毛玻璃', lambda: apply_theme(window, 'starry'))
    menu_theme.addAction('海蓝晶石', lambda: apply_theme(window, 'ocean'))
    menu_theme.addAction('暖玫瑰金', lambda: apply_theme(window, 'rose'))
    menu.addSeparator()
    menu=ActionMenu('截图',window.more_menu);window.more_menu.addMenu(menu).setIcon(line_icon('capture','#198466'))
    menu.addAction('框选截图',window.take_screenshot)
    menu.addAction('截图设置',window.screenshot_settings)
    menu.addSeparator()
    menu=ActionMenu('分类与整理',window.more_menu);window.more_menu.addMenu(menu).setIcon(line_icon('folder','#d47b43'))
    window.rule_button = menu.addAction('分类规则', window.edit_rules)
    menu.addAction('自定义分类',window.manage_categories)
    window.remember_category_action=menu.addAction('记住分类方式',window.remember_category)
    window.category_rules_action=menu.addAction('已保存分类方式',window.manage_category_rules)
    window.watch_action=menu.addAction('文件夹收件箱',window.manage_watch_folders)
    menu.addAction('课程 / 项目建议规则', window.edit_organization_rules)
    menu.addAction('应用课程 / 项目建议', window.suggest_selected)
    window.reclassify_button = menu.addAction('重新建议分类', window.reclassify)
    window.clear_action = menu.addAction('清空待整理列表', window.clear_imports)
    menu.addSeparator()
    menu=ActionMenu('记录与帮助',window.more_menu);window.more_menu.addMenu(menu).setIcon(line_icon('info','#78619c'))
    window.history_action = menu.addAction('操作记录', window.show_history)
    menu.addAction('如何使用', window.show_help)
    menu.addSeparator()
    menu=ActionMenu('备份与恢复',window.more_menu);window.more_menu.addMenu(menu).setIcon(line_icon('copy','#4a83aa'))
    menu.addAction('更新正文索引', window.rebuild_body_index)
    menu.addAction('恢复未完成归档', window.recover_archives)
    menu.addAction('撤销最近归档', window.undo_last_archive)
    menu.addAction('备份文档库数据库', window.backup_library)
    menu.addSeparator()
    window.recycle_action = menu.addAction('恢复区', window.show_recycle)
    window.full_backup_action = menu.addAction('完整备份文档库', window.export_full_backup)
    window.restore_backup_action = menu.addAction('从完整备份恢复', window.import_full_backup)
    footer_layout.addWidget(window.more_button)
    settings = button('设置',window.show_settings,'settings')
    settings.setObjectName('footerAction');settings.setMinimumHeight(38);settings.setIcon(line_icon('settings','#dcebe1'))
    window.settings_button = settings
    footer_layout.addWidget(settings);side.addWidget(footer)
    root_layout.addWidget(sidebar)
    main = QWidget()
    main_layout = QVBoxLayout(main)
    main_layout.setContentsMargins(0, 0, 0, 0)
    main_layout.setSpacing(0)
    topbar, heading = frame('topbar', QHBoxLayout, (22, 14, 22, 12) if compact else (26, 22, 22, 18), 16)
    window.topbar_frame=topbar
    titles = QVBoxLayout()
    titles.setSpacing(5)
    window.page_title = label('整理你的文档', 'pageTitle')
    window.page_subtitle = label('检查分类建议，确认后复制到文档库', 'subtitle')
    window.page_subtitle.setWordWrap(True)
    title_row=QHBoxLayout();title_row.setSpacing(12)
    window.library_title_icon=label('','libraryTitleIcon');window.library_title_icon.setFixedSize(44,44)
    window.library_title_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
    window.library_title_icon.setPixmap(line_icon('library','#24634b').pixmap(28,28))
    title_row.addWidget(window.library_title_icon);title_row.addWidget(window.page_title,1);titles.addLayout(title_row)
    titles.addWidget(window.page_subtitle)
    window.steps_label = WorkflowSteps()
    titles.addWidget(window.steps_label)
    if compact:
        window.library_title_icon.hide()
        window.steps_label.hide()
    heading.addLayout(titles, 1)
    window.topbar_art = WorkbenchFlourish()
    heading.addWidget(window.topbar_art)
    window.library_art=LibraryFlourish()
    heading.addWidget(window.library_art)
    location = QVBoxLayout()
    location.setSpacing(5)
    location.addWidget(label('文档库位置', 'muted'))
    location_row = QHBoxLayout()
    window.library_edit = QLineEdit()
    window.library_edit.setReadOnly(True)
    window.library_edit.setObjectName('libraryPath')
    window.library_edit.setPlaceholderText('尚未选择文档库')
    window.library_edit.setFixedWidth(210)
    window.library_edit.addAction(line_icon('folder', '#164b3c'), QLineEdit.ActionPosition.LeadingPosition)
    window.library_edit.textChanged.connect(lambda text: (
        window.sidebar_path.setText(text or '尚未选择文档库'), window.sidebar_path.setToolTip(text)))
    window.library_button = button('选择文档库', window.choose_library)
    location_row.addWidget(window.library_edit)
    location_row.addWidget(window.library_button)
    location.addLayout(location_row)
    heading.addLayout(location)
    main_layout.addWidget(topbar)
    if compact:
        titles.removeWidget(window.steps_label)
        band, band_layout = frame('workflowBand', QHBoxLayout, (20, 14, 20, 14), 10)
        band_layout.addWidget(window.steps_label)
        window.steps_label.show()
        window.workflow_band = band
        main_layout.addWidget(band)
    window.tabs = QStackedWidget()
    review = QWidget()
    review_layout = QVBoxLayout(review)
    review_layout.setContentsMargins(20, 0, 20, 0)
    review_layout.setSpacing(12)
    body = QHBoxLayout()
    body.setSpacing(12)
    left = QVBoxLayout()
    left.setSpacing(12)
    window.source_edit = QLineEdit(root)
    window.source_edit.setReadOnly(True)
    window.source_edit.hide()
    dropzone, drop = frame('dropzone', QHBoxLayout, (14, 12, 14, 12), 10)
    window.file_button = button('添加文件', window.choose_files, 'plus', True)
    window.file_button.setObjectName('addFile')
    window.source_button = button('扫描文件夹', window.choose_and_scan_folder, 'folder')
    window.scan_button = window.source_button
    drop.addWidget(window.file_button)
    drop.addWidget(window.source_button)
    window.import_hint = label('拖入 PDF、DOCX、DOC、TXT\n可一次添加多个文件', 'muted')
    window.import_hint.setWordWrap(True)
    window.file_button.setToolTip('添加 PDF、DOCX、DOC、TXT，可选择多个文件')
    window.source_button.setToolTip('扫描文件夹内的文档')
    drop.addWidget(window.import_hint, 1)
    left.addWidget(dropzone)
    section = QHBoxLayout()
    section.addWidget(label('待整理文件', 'sectionTitle'))
    window.file_count = label('尚未添加文件', 'muted')
    section.addWidget(window.file_count)
    section.addStretch()
    window.view_button = button('卡片视图' if window.review_mode=='list' else '列表视图',window.toggle_review_view)
    section.addWidget(window.view_button)
    window.clear_button = button('清空列表', window.clear_imports)
    section.addWidget(window.clear_button)
    left.addLayout(section)
    # Hidden table retains the controller's selection/category state. Cards are the visible view.
    window.scan_table = table(['选择', '文件名', '建议分类', '分类依据', '处理状态'])
    window.scan_table.setParent(review)
    window.scan_table.hide()
    window.scan_table.itemSelectionChanged.connect(window.show_scan_detail)
    window.scan_table.itemChanged.connect(window.scan_item_changed)
    window.scan_table.cellClicked.connect(lambda row,col:window.category_combo(row).showPopup() if col==2 and window.worker is None else None)
    for column,size in enumerate((60,250,160,280,180)):
        window.scan_table.setColumnWidth(column,size)
    window.review_stack = QStackedWidget()
    empty, empty_layout = frame('emptyState', margins=(20, 24, 20, 24), spacing=10)
    empty_layout.addStretch()
    for text, name in (('拖入文件，开始整理', 'emptyTitle'),
                       ('把桌面或文件夹里的文档拖到这里\n也可以点击上方“添加文件”或“扫描文件夹”', 'muted'),
                       ('导入 → 检查与修改分类 → 确认复制归档', 'steps')):
        item = label(text, name)
        item.setWordWrap(True)
        item.setAlignment(Qt.AlignmentFlag.AlignCenter)
        empty_layout.addWidget(item)
    empty_layout.addStretch()
    window.cards_view = CardGrid(window)
    window.review_sort=QComboBox()
    window.review_sort.addItem('优先检查不确定文件','attention')
    window.review_sort.addItem('保留当前顺序','original')
    window.review_sort.setCurrentIndex(0 if window.review_order=='attention' else 1)
    window.review_sort.currentIndexChanged.connect(window.review_order_changed)
    window.review_sort.setToolTip('将无正文、分类冲突和较弱建议优先显示')
    left.addWidget(window.review_sort)
    window.review_stack.addWidget(empty)
    window.review_stack.addWidget(window.cards_view)
    window.review_stack.addWidget(window.scan_table)
    left.addWidget(window.review_stack, 1)
    left.addWidget(window.cards_view.page_controls)
    body.addLayout(left, 1)
    window.details_panel = DetailPane(window)
    if compact:
        window.details_panel.hide()
    body.addWidget(window.details_panel)
    window.workbench_responsive=WorkbenchResponsive(window)
    review_layout.addLayout(body, 1)
    window.reason_label = label('')
    window.reason_label.setParent(review)
    window.reason_label.hide()
    window.progress_container = QWidget()
    progress_row = QHBoxLayout(window.progress_container)
    progress_row.setContentsMargins(0, 0, 0, 0)
    window.progress = QProgressBar()
    window.progress.setRange(0, 100)
    window.cancel_button = button('停止', window.cancel_work)
    progress_row.addWidget(window.progress, 1)
    progress_row.addWidget(window.cancel_button)
    review_layout.addWidget(window.progress_container)
    actionbar, bottom = frame('actionbar', QHBoxLayout, (0, 12, 0, 12), 12)
    summary = QVBoxLayout()
    count = QHBoxLayout()
    window.all_check = SelectAllCheckBox('全选')
    window.all_check.setTristate(True)
    window.all_check.setChecked(True)
    window.all_check.checkStateChanged.connect(lambda state:window.check_all(state==Qt.CheckState.Checked))
    count.addWidget(window.all_check)
    window.count_label = label('尚未添加文件')
    count.addWidget(window.count_label, 1)
    summary.addLayout(count)
    window.selection_hint = label('添加文件后，检查分类建议再确认归档。', 'muted')
    window.selection_hint.setWordWrap(True)
    summary.addWidget(window.selection_hint)
    bottom.addLayout(summary, 1)
    window.bulk_button = button('批量整理',window.bulk_organize)
    window.reread_button = button('重新读取',window.reread_selected)
    bottom.addWidget(window.bulk_button)
    bottom.addWidget(window.reread_button)
    window.details_button = button('文件详情', window.show_details)
    window.archive_button = button('确认归档', window.confirm_archive, 'check', True)
    bottom.addWidget(window.details_button)
    bottom.addWidget(window.archive_button)
    review_layout.addWidget(actionbar)
    window.tabs.addWidget(review)
    window.details_dialog = QDialog(window)
    window.details_dialog.setWindowTitle('文件信息与启动提示')
    window.details_dialog.resize(740, 500)
    details_layout = QVBoxLayout(window.details_dialog)
    window.detail = QPlainTextEdit()
    window.detail.setReadOnly(True)
    details_layout.addWidget(window.detail)
    window.open_source_button = button('打开原文件', window.open_source, 'open')
    details_layout.addWidget(window.open_source_button)

    search = QWidget()
    search_layout = QVBoxLayout(search)
    search_layout.setContentsMargins(20, 0, 20, 0)
    search_layout.setSpacing(12)
    toolbar = QHBoxLayout()
    window.search_edit = QLineEdit()
    window.search_edit.setPlaceholderText('搜索文件名、正文、课程、项目或标签')
    window.search_edit.addAction(line_icon('search', '#164b3c'), QLineEdit.ActionPosition.LeadingPosition)
    window.search_edit.returnPressed.connect(window.refresh_search)
    window.search_edit.textChanged.connect(window.queue_search)
    window.search_category = QComboBox()
    window.search_category.addItems(['全部分类', *window.categories])
    window.search_category.currentIndexChanged.connect(window.reset_search)
    window.search_button = button('搜索', window.refresh_search)
    toolbar.addWidget(window.search_edit, 1)
    toolbar.addWidget(window.search_category)
    window.search_scope = QComboBox()
    window.search_scope.addItems(['全文与标签','仅文件名'])
    window.search_scope.currentIndexChanged.connect(window.reset_search)
    toolbar.addWidget(window.search_scope)
    toolbar.addWidget(window.search_button)
    search_layout.addLayout(toolbar)
    window.build_organization_filters(search_layout)
    window.more_filters=button('更多筛选',lambda:None)
    window.more_filters.setCheckable(True)
    window.more_filters.toggled.connect(window.advanced_filters.setVisible)
    window.more_filters.toggled.connect(lambda expanded:window.more_filters.setText('收起筛选' if expanded else '更多筛选'))
    toolbar.addWidget(window.more_filters)
    search_heading = QHBoxLayout()
    search_heading.addWidget(label('已归档文件', 'sectionTitle'))
    window.search_count = label('选择文档库后即可查找', 'muted')
    search_heading.addWidget(window.search_count)
    search_heading.addStretch()
    window.labels_button = button('分类 / 标签',window.edit_archive_labels)
    search_heading.addWidget(window.labels_button)
    window.reading_button=button('阅读 / 备注',window.edit_reading)
    search_heading.addWidget(window.reading_button)
    window.library_maintenance_menu = ActionMenu('文档库维护', window)
    window.cleanup_button = window.library_maintenance_menu.addAction('清理失效记录', window.cleanup_missing_records)
    window.cleanup_button.setToolTip('检查整个当前文档库，确认后移除归档副本已不存在的记录；操作日志保留')
    window.library_maintenance_button = button('维护', lambda: None)
    window.library_maintenance_button.setMenu(window.library_maintenance_menu)
    search_heading.addWidget(window.library_maintenance_button)
    search_layout.addLayout(search_heading)
    search_list, listing = frame('list', margins=(8, 8, 8, 8))
    window.search_table = table(['文件名', '分类', '归档日期'])
    window.search_table.setObjectName('libraryTable')
    window.search_table.setSelectionMode(window.search_table.SelectionMode.ExtendedSelection)
    window.search_table.setProperty('emptyText', '尚未选择文档库\n点击右上角“选择文档库”，即可查看已有归档记录。')
    window.search_table.horizontalHeader().setStretchLastSection(False)
    window.search_table.setShowGrid(False)
    window.search_table.verticalHeader().setDefaultSectionSize(60)
    window.search_table.setItemDelegateForColumn(0, TwoLineDelegate('file', window.search_table))
    from .presentation import CategoryDelegate
    window.search_table.setItemDelegateForColumn(1,CategoryDelegate(window.search_table))
    window.search_columns = TableColumns(window.search_table, 'library')
    window.search_table.itemDoubleClicked.connect(lambda _: window.open_archive())
    window.search_table.itemSelectionChanged.connect(window.update_archive_selection)
    listing.addWidget(window.search_table)
    search_layout.addWidget(search_list, 1)
    pages = QHBoxLayout()
    pages.addStretch()
    window.previous_page = button('上一页',lambda:window.change_search_page(-1))
    window.page_label = label('第 1 页','muted')
    window.next_page = button('下一页',lambda:window.change_search_page(1))
    pages.addWidget(window.previous_page)
    pages.addWidget(window.page_label)
    pages.addWidget(window.next_page)
    window.previous_page.hide()
    window.next_page.hide()
    window.page_label.setText('共 0 项')
    search_layout.addLayout(pages)
    search_actionbar, search_bottom = frame('actionbar', QHBoxLayout, (0, 14, 0, 14), 12)
    library_summary = QVBoxLayout()
    from .presentation import ElidingLabel
    window.library_selection = ElidingLabel('选择一个文件')
    library_summary.addWidget(window.library_selection)
    window.library_selection_hint = label('选中文件后可预览或打开，支持 Ctrl / Shift 多选。', 'muted')
    window.library_selection_hint.setWordWrap(True)
    library_summary.addWidget(window.library_selection_hint)
    search_bottom.addLayout(library_summary, 1)
    window.open_folder_button = button('所在文件夹', window.open_archive_folder)
    window.open_archive_button = button('打开文件', window.open_archive, 'open', True)
    window.preview_archive_button = button('预览', window.preview_archive)
    search_bottom.addWidget(window.preview_archive_button)
    search_bottom.addWidget(window.open_folder_button)
    search_bottom.addWidget(window.open_archive_button)
    search_layout.addWidget(search_actionbar)
    window.tabs.addWidget(search)
    main_layout.addWidget(window.tabs, 1)
    root_layout.addWidget(main, 1)

    def page_changed(index):
        window.centralWidget().set_page(index)
        window.screenshot_button.setProperty('secondary', index == 1)
        window.screenshot_button.style().unpolish(window.screenshot_button)
        window.screenshot_button.style().polish(window.screenshot_button)
        wide = window.width() >= 1200
        window.library_title_icon.setVisible(index == 1 and not compact)
        if hasattr(window, 'topbar_art'):
            window.topbar_art.setVisible(index == 0 and wide and not compact)
        if hasattr(window, 'library_art'):
            window.library_art.setVisible(index == 1 and wide and not compact)
        window.topbar_frame.setProperty('library', index == 1)
        window.topbar_frame.style().unpolish(window.topbar_frame)
        window.topbar_frame.style().polish(window.topbar_frame)
        window.nav_buttons[index].setChecked(True)
        window.page_title.setText('整理你的文档' if index == 0 else '你的文档库')
        window.page_subtitle.setText('检查分类建议，确认后复制到文档库' if index == 0
                                     else '搜索正文、课程与项目，直接打开已归档文件')
        window.steps_label.setVisible(index == 0)
        if compact:
            window.workflow_band.setVisible(index == 0)
        from .theme import get_colors
        c = get_colors()
        for i, nav in enumerate(window.nav_buttons):
            nav.setIcon(line_icon('import' if i == 0 else 'library', '#ffffff' if i == index else c['nav_text']))
    window.tabs.currentChanged.connect(page_changed)
    page_changed(0)
    window.history_dialog = QDialog(window)
    window.history_dialog.setWindowTitle('操作记录')
    window.history_dialog.resize(900, 520)
    history_layout = QVBoxLayout(window.history_dialog)
    history_layout.addWidget(label('最近 500 条记录', 'muted'))
    window.history_table = table(['时间（UTC）', '操作', '详情'])
    window.history_table.setColumnWidth(0, 200)
    window.history_table.setColumnWidth(1, 130)
    history_layout.addWidget(window.history_table)
    window.statusBar().setSizeGripEnabled(False)
    window.statusBar().showMessage('拖入文件 → 检查分类 → 确认复制归档；在文档库搜索并打开。')
    window.setWindowIcon(QIcon(str(ICON_PATH)))
    # Paths and the pending document list are restored after build_window returns.
    apply_theme(window, init_theme, persist=False)
    if window.review_mode=='list':
        window.details_panel.hide()
        from PySide6.QtWidgets import QHeaderView
        window.scan_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        window.scan_table.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Fixed)
        window.scan_table.setColumnWidth(0,44)
