"""Dual-theme QSS: Ocean Blue Crystal / Warm Rose Gold; implemented with native Qt QSS."""
from pathlib import Path

# ---------------------------------------------------------------------------
# Asset paths (resolved once)
# ---------------------------------------------------------------------------
_CHEVRON_SVG = Path(__file__).with_name('chevron-down.svg').as_posix()
_CHECK_SVG = Path(__file__).with_name('check-white.svg').as_posix()

# ---------------------------------------------------------------------------
# Semantic colour tokens for each theme
# ---------------------------------------------------------------------------
THEME_COLORS: dict[str, dict[str, str]] = {
    'ocean': {
        'sidebar':              '#0c2d48',
        'sidebar_hover':        '#112e47',
        'sidebar_footer':       '#112e47',
        'sidebar_footer_border':'#1a4a6e',
        'sidebar_separator':    '#1a4a6e',
        'footer_text':          '#8bb8d8',
        'footer_hover':         '#1a3a5a',
        'nav_active':           '#2563eb',
        'nav_text':             '#8bb8d8',
        'nav_active_text':      '#ffffff',
        'accent':               '#2563eb',
        'accent_hover':         '#1d4ed8',
        'accent_light':         '#dbeafe',
        'capture_start':        '#087eae',
        'capture_end':          '#087f8c',
        'text':                 '#0c2d48',
        'muted':                '#526f8a',
        'page_bg':              '#f0f6fc',
        'card_bg':              '#ffffff',
        'card_border':          '#c7ddf0',
        'card_active_border':   '#2563eb',
        'card_active_bg':       '#f8fbff',
        'border':               '#c7ddf0',
        'input_focus':          '#2563eb',
        'primary_bg':           '#0c2d48',
        'primary_hover':        '#1a4a6e',
        'addfile_bg':           '#2563eb',
        'addfile_hover':        '#1d4ed8',
        'disabled_bg':          '#e0e8f0',
        'disabled_text':        '#8aabb8',
        'check_bg':             '#2563eb',
        'selection_bg':         '#dbeafe',
        'header_bg':            '#e8f1fc',
        'topbar_gradient_start':'#e0eefa',
        'topbar_gradient_mid':  '#f0f6fc',
        'topbar_gradient_end':  '#dbeafe',
        'library_icon_bg':      '#dbeafe',
        'library_icon_border':  '#c7ddf0',
        'chip_bg':              '#e0eefa',
        'chip_border':          '#c7ddf0',
        'chip_text':            '#2563eb',
        'scrollbar':            '#93b8d8',
        'statusbar_bg':         '#f0f6fc',
        'statusbar_text':       '#526f8a',
        'brand_mark_bg':        '#e0eefa',
        'sidebar_note':         '#8bb8d8',
        'menu_bg':              '#ffffff',
        'menu_border':          '#c7ddf0',
        'menu_selected':        '#eff6ff',
        'tooltip_border':       '#93b8d8',
        # Shelf / flourish artwork
        'shelf_book_1':         '#2563eb',
        'shelf_book_2':         '#0ea5e9',
        'shelf_book_3':         '#0c2d48',
        'shelf_book_4':         '#93b8d8',
        'shelf_book_5':         '#06b6d4',
        'shelf_leaf':           '#38bdf8',
        'shelf_shelf':          '#c7ddf0',
        'flourish_circle':      '#dbeafe',
        'flourish_doc':         '#2563eb',
        'flourish_dot_1':       '#0ea5e9',
        'flourish_dot_2':       '#93b8d8',
        # Step badges
        'step_active':          '#2563eb',
        'step_done':            '#087e9b',
        'step_inactive_bg':     '#e0e8f0',
        'step_inactive_text':   '#52647a',
        # Reason box
        'reason_bg':            '#e0eefa',
        'reason_text':          '#0c2d48',
    },
    'rose': {
        'sidebar':              '#3d1a2a',
        'sidebar_hover':        '#4a2232',
        'sidebar_footer':       '#4a2232',
        'sidebar_footer_border':'#6a3848',
        'sidebar_separator':    '#6a3848',
        'footer_text':          '#c09098',
        'footer_hover':         '#5a3040',
        'nav_active':           '#bf3651',
        'nav_text':             '#c09098',
        'nav_active_text':      '#ffffff',
        'accent':               '#bf3651',
        'accent_hover':         '#c03050',
        'accent_light':         '#fce0e8',
        'capture_start':        '#b04e63',
        'capture_end':          '#a9485a',
        'text':                 '#3d1a2a',
        'muted':                '#825a69',
        'page_bg':              '#fdf6f8',
        'card_bg':              '#ffffff',
        'card_border':          '#f0c8d0',
        'card_active_border':   '#d44860',
        'card_active_bg':       '#fff8fa',
        'border':               '#f0c8d0',
        'input_focus':          '#d44860',
        'primary_bg':           '#3d1a2a',
        'primary_hover':        '#5a2e42',
        'addfile_bg':           '#bf3651',
        'addfile_hover':        '#c03050',
        'disabled_bg':          '#f0e0e4',
        'disabled_text':        '#b8909c',
        'check_bg':             '#d44860',
        'selection_bg':         '#fce0e8',
        'header_bg':            '#fce8ef',
        'topbar_gradient_start':'#fce8ef',
        'topbar_gradient_mid':  '#fdf6f8',
        'topbar_gradient_end':  '#f8e0e8',
        'library_icon_bg':      '#fce0e8',
        'library_icon_border':  '#f0c8d0',
        'chip_bg':              '#fce0e8',
        'chip_border':          '#f0c8d0',
        'chip_text':            '#b02e49',
        'scrollbar':            '#d8a0b0',
        'statusbar_bg':         '#fdf6f8',
        'statusbar_text':       '#825a69',
        'brand_mark_bg':        '#fce0e8',
        'sidebar_note':         '#c09098',
        'menu_bg':              '#ffffff',
        'menu_border':          '#f0c8d0',
        'menu_selected':        '#fff0f4',
        'tooltip_border':       '#d8a0b0',
        # Shelf / flourish artwork
        'shelf_book_1':         '#d44860',
        'shelf_book_2':         '#c0606e',
        'shelf_book_3':         '#3d1a2a',
        'shelf_book_4':         '#d8a0b0',
        'shelf_book_5':         '#b85468',
        'shelf_leaf':           '#d88898',
        'shelf_shelf':          '#f0c8d0',
        'flourish_circle':      '#fce0e8',
        'flourish_doc':         '#d44860',
        'flourish_dot_1':       '#c0606e',
        'flourish_dot_2':       '#d8a0b0',
        # Step badges
        'step_active':          '#bf3651',
        'step_done':            '#a9485a',
        'step_inactive_bg':     '#f0e0e4',
        'step_inactive_text':   '#795260',
        # Reason box
        'reason_bg':            '#fce0e8',
        'reason_text':          '#3d1a2a',
    },
}

# ---------------------------------------------------------------------------
# Active state
# ---------------------------------------------------------------------------
from .theme_starry import STARRY_PALETTE, STARRY_QSS
THEME_COLORS['starry'] = {**THEME_COLORS['ocean'], **STARRY_PALETTE}
CURRENT_THEME: str = 'ocean'
WORKBENCH_QSS: str = ''


def get_colors() -> dict[str, str]:
    """Return the colour dict for the currently active theme."""
    return THEME_COLORS[CURRENT_THEME]


def normalize_theme(name) -> str:
    """Recover safely from missing or malformed preferences."""
    return name if isinstance(name, str) and name in THEME_COLORS else 'ocean'


# ---------------------------------------------------------------------------
# QSS builder
# ---------------------------------------------------------------------------

def _build_qss(name: str) -> str:  # noqa: C901 – intentionally monolithic
    """Return the full QSS string for the given theme name."""
    c = THEME_COLORS[name]

    # --- radius tokens ---
    if name == 'ocean':
        r_card = '16px'
        r_btn = '12px'
        r_input = '10px'
        r_nav = '14px'
        r_footer = '14px'
    else:  # rose
        r_card = '18px'
        r_btn = '14px'
        r_input = '12px'
        r_nav = '16px'
        r_footer = '16px'

    qss = f"""
QWidget {{ font-family: 'Microsoft YaHei UI'; font-size: 14px; color: {c['text']}; }}
QMainWindow, QDialog {{ background: {c['page_bg']}; }}

/* ── Sidebar ────────────────────────────────────────────────────── */
QFrame#sidebar {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {c['sidebar']},stop:1 {'#0a1f33' if name == 'ocean' else '#2a1220'}); }}
QLabel#brand {{ color: #ffffff; font-size: 13px; font-weight: 600; }}
QLabel#brandMark {{ background: {c['brand_mark_bg']}; border-radius: 8px; }}
QLabel#sidebarNote {{ color: {c['sidebar_note']}; font-size: 12px; }}
QLabel#sidebarPath {{ color: #ffffff; font-size: 12px; }}

QPushButton#nav {{ text-align: left; padding: 12px 16px; background: transparent; border: 1px solid transparent; color: {c['nav_text']}; font-size: 16px; border-radius: {r_nav}; }}
QPushButton#nav:hover {{ background: {c['sidebar_hover']}; }}
QPushButton#nav:checked {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {c['nav_active']},stop:1 {c['nav_active']}); color: {c['nav_active_text']}; font-weight: 600; }}
QPushButton#sideButton {{ background: transparent; border: 0; color: {c['nav_text']}; text-align: left; padding: 8px; }}
QPushButton#sideButton:hover {{ background: {c['sidebar_hover']}; }}

/* ── Page titles / labels ───────────────────────────────────────── */
QLabel#pageTitle {{ font-size: 30px; font-weight: 700; color: {c['text']}; }}
QLabel#subtitle {{ color: {c['muted']}; font-size: 15px; }}
QLabel#steps {{ color: {c['muted']}; font-size: 13px; padding-top: 4px; }}
QLabel#muted {{ color: {c['muted']}; font-size: 13px; }}
QLabel#sectionTitle {{ font-size: 19px; font-weight: 600; }}

/* ── Panels / cards ─────────────────────────────────────────────── */
QFrame#dropzone, QFrame#detailPane, QFrame#emptyState, QFrame#list {{ background: {c['card_bg']}; border: 1px solid {c['border']}; border-radius: {r_card}; }}
QWidget#detailContent {{ background: {c['card_bg']}; border-radius: {r_card}; }}
QFrame#emptyState {{ border: 1px dashed {'#93b8d8' if name == 'ocean' else '#d8a0b0'}; }}
QLabel#emptyTitle {{ font-size: 20px; font-weight: 600; }}
QScrollArea, QWidget#cardContent {{ background: transparent; border: 0; }}

QFrame#fileCard {{ background: {c['card_bg']}; border: 1px solid {c['card_border']}; border-radius: {r_card}; }}
QFrame#fileCard[active="true"] {{ border: 2px solid {c['card_active_border']}; background: {c['card_active_bg']}; }}
QLabel#cardFilename {{ font-size: 15px; font-weight: 600; }}
QLabel#cardMeta, QLabel#cardStatus {{ color: {c['muted']}; font-size: 12px; }}
QLabel#categoryBadge {{ border-radius: 13px; padding: 6px 11px; font-size: 12px; font-weight: 600; }}

QPushButton#cardMore, QToolButton#cardMore, QPushButton#detailClose {{ background: transparent; border: 0; padding: 0; color: {c['muted']}; }}
QPushButton#cardMore:hover, QPushButton#detailClose:hover {{ background: {c['selection_bg']}; }}

/* ── Detail pane ────────────────────────────────────────────────── */
QLabel#detailHeading {{ font-size: 19px; font-weight: 600; }}
QLabel#detailFilename {{ font-size: 17px; font-weight: 600; }}
QLabel#detailBanner {{ border-radius: 12px; padding: 12px; font-size: 16px; font-weight: 600; }}
QFrame#reasonBox {{ background: {c['reason_bg']}; border: 0; border-radius: 12px; }}
QPlainTextEdit#bodyPreview {{ background: white; border: 1px solid {c['border']}; border-radius: 12px; padding: 14px; font-size: 12px; }}
QFrame#actionbar {{ border-top: 1px solid {c['border']}; }}

/* ── Inputs ─────────────────────────────────────────────────────── */
QLineEdit, QPlainTextEdit, QSpinBox {{ background: white; border: 1px solid {c['border']}; border-radius: {r_input}; padding: 8px 10px; selection-background-color: {c['selection_bg']}; selection-color: {c['text']}; }}
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{ border-color: {c['input_focus']}; }}

/* ── Buttons ────────────────────────────────────────────────────── */
QPushButton {{ background: #ffffff; border: 1px solid {c['border']}; padding: 9px 14px; border-radius: {r_btn}; }}
QPushButton:hover {{ background: {c['menu_selected']}; border-color: {c['scrollbar']}; }}
QPushButton:pressed {{ background: {c['accent_light']}; }}
QPushButton:focus {{ border-color: {c['input_focus']}; }}

QPushButton#primary {{ background: {c['primary_bg']}; color: white; border-color: {c['primary_bg']}; font-weight: 600; font-size: 15px; }}
QPushButton#primary:hover {{ background: {c['primary_hover']}; }}
QPushButton#primary:pressed {{ background: {c['sidebar']}; }}

QPushButton#addFile {{ background: {c['addfile_bg']}; color: white; border-color: {c['addfile_bg']}; font-size: 15px; font-weight: 600; }}
QPushButton#addFile:hover {{ background: {c['addfile_hover']}; }}

QPushButton:disabled, QPushButton#primary:disabled, QPushButton#addFile:disabled, QPushButton#nav:disabled {{ background: {c['disabled_bg']}; color: {c['disabled_text']}; border-color: {c['disabled_bg']}; }}

/* ── ComboBox ───────────────────────────────────────────────────── */
QComboBox {{ background: white; border: 1px solid {c['border']}; border-radius: {r_input}; padding: 5px 8px; min-height: 22px; }}
QComboBox:focus {{ border-color: {c['input_focus']}; }}
QComboBox:disabled {{ color: {c['disabled_text']}; background: {c['disabled_bg']}; }}
QComboBox QAbstractItemView {{ background: white; color: {c['text']}; selection-background-color: {c['menu_selected']}; selection-color: {c['text']}; border: 1px solid {c['border']}; }}

/* ── Table ──────────────────────────────────────────────────────── */
QTableWidget {{ background: {c['card_bg']}; alternate-background-color: {c['card_bg']}; border: 0; gridline-color: {c['border']}; selection-background-color: {c['selection_bg']}; }}
QTableWidget::item {{ padding: 10px 12px; border-bottom: 1px solid {c['border']}; }}
QTableWidget::item:selected {{ background: {c['selection_bg']}; color: {c['text']}; }}
QHeaderView::section {{ background: {c['header_bg']}; color: {c['muted']}; font-size: 12px; padding: 10px 12px; border: 0; border-bottom: 1px solid {c['border']}; }}

/* ── Checkbox ───────────────────────────────────────────────────── */
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border: 1px solid {c['scrollbar']}; border-radius: 4px; background: white; }}
QCheckBox::indicator:checked {{ background: {c['check_bg']}; border: 1px solid {c['check_bg']}; }}

/* ── ProgressBar ────────────────────────────────────────────────── */
QProgressBar {{ border: 0; background: {c['disabled_bg']}; border-radius: 4px; text-align: center; min-height: 18px; font-size: 11px; }}
QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}

/* ── StatusBar ──────────────────────────────────────────────────── */
QStatusBar {{ background: {c['statusbar_bg']}; color: {c['statusbar_text']}; font-size: 12px; border-top: 1px solid {c['border']}; }}
QStatusBar::item {{ border: 0; }}

/* ── Menu ───────────────────────────────────────────────────────── */
QMenu {{ background: {c['menu_bg']}; border: 1px solid {c['menu_border']}; padding: 6px; }}
QMenu::item {{ padding: 8px 16px; border-radius: 5px; }}
QMenu::item:selected {{ background: {c['menu_selected']}; }}
QMenu::separator {{ height: 1px; background: {c['border']}; margin: 6px; }}

/* ── Tooltip ────────────────────────────────────────────────────── */
QToolTip {{ background: {c['menu_bg']}; color: {c['text']}; border: 1px solid {c['tooltip_border']}; padding: 6px; }}

/* ── Scrollbar ──────────────────────────────────────────────────── */
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {c['scrollbar']}; border-radius: 4px; min-height: 24px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""

    # ComboBox drop-down arrow
    qss += f'\nQComboBox::drop-down {{ border: 0; width: 22px; }}'
    qss += f'\nQComboBox::down-arrow {{ width: 14px; height: 14px; image: url("{_CHEVRON_SVG}"); }}\n'

    # Checkbox tick mark
    qss += f'\nQCheckBox::indicator:checked {{ image: url("{_CHECK_SVG}"); }}\n'

    # Capture launch button
    qss += f"""
QPushButton#captureLaunch {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {c['capture_start']},stop:1 {c['capture_end']}); color:#ffffff; text-align:left; border:1px solid {'#38bdf8' if name == 'ocean' else '#d88898'}; border-radius:{r_nav}; padding:12px 14px; font-size:14px; font-weight:600; }}
QPushButton#captureLaunch:hover {{ background:{'#23a5d2' if name == 'ocean' else '#c45868'}; border-color:{'#6dcef0' if name == 'ocean' else '#e0a0a8'}; }}
QPushButton#captureLaunch:pressed {{ background:{'#0884b8' if name == 'ocean' else '#a04858'}; }}
QPushButton#captureLaunch:focus {{ border:2px solid {'#8ce0f0' if name == 'ocean' else '#e8b0b8'}; }}
"""

    # Filter chip
    qss += f"""
QPushButton#filterChip {{ background:{c['chip_bg']}; border-color:{c['chip_border']}; color:{c['chip_text']}; padding:5px 9px; font-size:12px; }}
QPushButton#filterChip:hover {{ background:{c['accent_light']}; border-color:{c['scrollbar']}; }}
"""

    # Sidebar footer
    qss += f"""
QFrame#sidebarFooter {{ background:{c['sidebar_footer']}; border:1px solid {c['sidebar_footer_border']}; border-radius:{r_footer}; }}
QLabel#footerCaption {{ color:{c['footer_text']}; font-size:11px; padding:0 8px; }}
QLabel#sidebarPath {{ color:{'#eef5ff' if name == 'ocean' else '#f5e0e8'}; font-size:13px; font-weight:600; }}
QFrame#footerSeparator {{ background:{c['sidebar_separator']}; border:0; margin:3px 8px; }}
QPushButton#footerAction {{ color:{c['footer_text']}; background:transparent; border:0; border-radius:{r_input}; text-align:left; padding:9px 10px; font-size:14px; }}
QPushButton#footerAction:hover {{ background:{c['footer_hover']}; }}
QPushButton#footerAction:pressed {{ background:{'#254a68' if name == 'ocean' else '#6a3848'}; }}
QPushButton#footerAction:focus {{ border:1px solid {c['scrollbar']}; }}
"""

    # Action menu & topbar
    qss += f"""
QMenu#actionMenu {{ background:{c['menu_bg']}; border:1px solid {c['menu_border']}; border-radius:13px; padding:32px 8px 9px 8px; color:{c['text']}; }}
QMenu#actionMenu::item {{ padding:10px 28px 10px 12px; margin:2px 0; border-radius:8px; font-size:13px; }}
QMenu#actionMenu::item:selected {{ background:{c['menu_selected']}; color:{c['primary_bg']}; }}
QMenu#actionMenu::item:disabled {{ color:{c['disabled_text']}; }}
QMenu#actionMenu::separator {{ background:{c['border']}; height:1px; margin:6px 10px; }}
QMenu#actionMenu::right-arrow {{ width:12px; height:12px; }}
QFrame#topbar[library="true"] {{ background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {c['topbar_gradient_start']},stop:0.68 {c['topbar_gradient_mid']},stop:1 {c['topbar_gradient_end']}); border-bottom:1px solid {c['border']}; }}
QLabel#libraryTitleIcon {{ background:{c['library_icon_bg']}; border:1px solid {c['library_icon_border']}; border-radius:{r_nav}; }}
"""

    return qss + (STARRY_QSS if name == 'starry' else '')


# ---------------------------------------------------------------------------
# Theme switching
# ---------------------------------------------------------------------------

def switch_theme(name: str) -> None:
    """Activate the named theme ('ocean' or 'rose')."""
    global CURRENT_THEME, WORKBENCH_QSS  # noqa: PLW0603
    if name not in THEME_COLORS:
        raise ValueError(f"Unknown theme '{name}'; choose from {list(THEME_COLORS)}")
    CURRENT_THEME = name
    WORKBENCH_QSS = _build_qss(name)


# ---------------------------------------------------------------------------
# Initialise on import
# ---------------------------------------------------------------------------
switch_theme('ocean')
