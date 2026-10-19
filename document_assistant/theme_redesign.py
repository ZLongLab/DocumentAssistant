"""Redesigned theme system based on taste-design principles: clean, clear, efficient."""
from pathlib import Path

# Asset paths
_CHEVRON_SVG = Path(__file__).with_name('chevron-down.svg').as_posix()
_CHECK_SVG = Path(__file__).with_name('check-white.svg').as_posix()

# Refined color palette - more subdued, better hierarchy
THEME_COLORS: dict[str, dict[str, str]] = {
    'ocean': {
        # Core colors - simplified
        'sidebar': '#0f2942',
        'sidebar_gradient_end': '#081828',
        'sidebar_hover': 'rgba(255, 255, 255, 0.05)',
        'sidebar_text': '#94a3b8',
        'sidebar_text_hover': '#e2e8f0',

        # Navigation
        'nav_active': '#3b82f6',
        'nav_active_text': '#ffffff',

        # Primary actions
        'accent': '#3b82f6',
        'accent_hover': '#2563eb',
        'success': '#10b981',
        'success_hover': '#059669',
        'warning': '#f59e0b',
        'error': '#ef4444',

        # Text hierarchy
        'text_primary': '#1a1a1a',
        'text_secondary': '#64748b',
        'text_muted': '#94a3b8',
        'text_disabled': '#cbd5e1',

        # Backgrounds
        'page_bg': '#f9fafb',
        'card_bg': '#ffffff',
        'input_bg': '#ffffff',
        'disabled_bg': '#f1f5f9',

        # Borders
        'border': '#e5e7eb',
        'border_hover': '#cbd5e1',
        'border_focus': '#3b82f6',
        'border_active': '#3b82f6',

        # Interactive states
        'hover_bg': '#f9fafb',
        'selection_bg': '#eff6ff',

        # Category colors - more subtle
        'category_report_bg': '#dbeafe',
        'category_report_text': '#1e40af',
        'category_literature_bg': '#fed7aa',
        'category_literature_text': '#92400e',
        'category_course_bg': '#e9d5ff',
        'category_course_text': '#6b21a8',
        'category_project_bg': '#d1fae5',
        'category_project_text': '#065f46',
        'category_other_bg': '#f3f4f6',
        'category_other_text': '#374151',

        # Scrollbar
        'scrollbar': '#cbd5e1',
        'scrollbar_hover': '#94a3b8',

        # Legacy compatibility (for DetailPane and other components)
        'reason_bg': '#eff6ff',
        'reason_text': '#1e40af',
        'primary_bg': '#0f2942',
        'primary_hover': '#1a3a5a',
        'addfile_bg': '#3b82f6',
        'addfile_hover': '#2563eb',
        'capture_start': '#0891b2',
        'capture_end': '#0e7490',
        'sidebar_footer': '#0a1f33',
        'sidebar_footer_border': '#1a3a5a',
        'sidebar_separator': '#1a3a5a',
        'footer_text': '#94a3b8',
        'footer_hover': '#1a3a5a',
        'sidebar_note': '#94a3b8',
    },
    'rose': {
        # Core colors
        'sidebar': '#3d1a2a',
        'sidebar_gradient_end': '#2a1220',
        'sidebar_hover': 'rgba(255, 255, 255, 0.05)',
        'sidebar_text': '#c09098',
        'sidebar_text_hover': '#f5e0e8',

        # Navigation
        'nav_active': '#bf3651',
        'nav_active_text': '#ffffff',

        # Primary actions
        'accent': '#bf3651',
        'accent_hover': '#a02847',
        'success': '#10b981',
        'success_hover': '#059669',
        'warning': '#f59e0b',
        'error': '#ef4444',

        # Text hierarchy
        'text_primary': '#1a1a1a',
        'text_secondary': '#64748b',
        'text_muted': '#94a3b8',
        'text_disabled': '#cbd5e1',

        # Backgrounds
        'page_bg': '#fdf6f8',
        'card_bg': '#ffffff',
        'input_bg': '#ffffff',
        'disabled_bg': '#fce8ef',

        # Borders
        'border': '#f0c8d0',
        'border_hover': '#e0b0be',
        'border_focus': '#bf3651',
        'border_active': '#bf3651',

        # Interactive states
        'hover_bg': '#fff8fa',
        'selection_bg': '#fce0e8',

        # Category colors
        'category_report_bg': '#dbeafe',
        'category_report_text': '#1e40af',
        'category_literature_bg': '#fed7aa',
        'category_literature_text': '#92400e',
        'category_course_bg': '#e9d5ff',
        'category_course_text': '#6b21a8',
        'category_project_bg': '#d1fae5',
        'category_project_text': '#065f46',
        'category_other_bg': '#f8e8eb',
        'category_other_text': '#825a69',

        # Scrollbar
        'scrollbar': '#d8a0b0',
        'scrollbar_hover': '#c08898',

        # Legacy compatibility
        'reason_bg': '#fce0e8',
        'reason_text': '#831843',
        'primary_bg': '#3d1a2a',
        'primary_hover': '#5a2e42',
        'addfile_bg': '#bf3651',
        'addfile_hover': '#a02847',
        'capture_start': '#b04e63',
        'capture_end': '#a9485a',
        'sidebar_footer': '#2a1220',
        'sidebar_footer_border': '#6a3848',
        'sidebar_separator': '#6a3848',
        'footer_text': '#c09098',
        'footer_hover': '#5a3040',
        'sidebar_note': '#c09098',
    },
}

CURRENT_THEME: str = 'ocean'
WORKBENCH_QSS: str = ''

def get_colors() -> dict[str, str]:
    """Return current theme colors."""
    return THEME_COLORS[CURRENT_THEME]

def normalize_theme(name) -> str:
    """Validate theme name."""
    return name if isinstance(name, str) and name in THEME_COLORS else 'ocean'

def _build_qss(name: str) -> str:
    """Build complete QSS stylesheet for the theme."""
    c = THEME_COLORS[name]

    qss = f"""
/* ═══════════════════════════════════════════════════════════════
   Global Base Styles
   ═══════════════════════════════════════════════════════════════ */
QWidget {{
    font-family: 'Microsoft YaHei UI', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size: 13px;
    color: {c['text_primary']};
}}

QMainWindow, QDialog {{
    background: {c['page_bg']};
}}

/* ═══════════════════════════════════════════════════════════════
   Sidebar
   ═══════════════════════════════════════════════════════════════ */
QFrame#sidebar {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {c['sidebar']},
                stop:1 {c['sidebar_gradient_end']});
}}

QLabel#brand {{
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
}}

QLabel#brandMark {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {c['accent']},
                stop:1 {c['accent_hover']});
    border-radius: 8px;
}}

/* Navigation buttons - simplified */
QPushButton#nav {{
    text-align: left;
    padding: 10px 12px;
    background: transparent;
    border: none;
    color: {c['sidebar_text']};
    font-size: 14px;
    border-radius: 8px;
}}

QPushButton#nav:hover {{
    background: {c['sidebar_hover']};
    color: {c['sidebar_text_hover']};
}}

QPushButton#nav:checked {{
    background: {c['nav_active']};
    color: {c['nav_active_text']};
    font-weight: 500;
}}

/* ═══════════════════════════════════════════════════════════════
   Typography & Labels
   ═══════════════════════════════════════════════════════════════ */
QLabel#pageTitle {{
    font-size: 20px;
    font-weight: 600;
    color: {c['text_primary']};
}}

QLabel#subtitle {{
    color: {c['text_secondary']};
    font-size: 13px;
}}

QLabel#sectionTitle {{
    font-size: 15px;
    font-weight: 600;
    color: {c['text_primary']};
}}

QLabel#muted {{
    color: {c['text_secondary']};
    font-size: 12px;
}}

/* ═══════════════════════════════════════════════════════════════
   Buttons - Unified System
   ═══════════════════════════════════════════════════════════════ */
QPushButton {{
    background: {c['card_bg']};
    border: 1px solid {c['border']};
    padding: 8px 16px;
    border-radius: 8px;
    color: {c['text_primary']};
    font-size: 13px;
    font-weight: 500;
}}

QPushButton:hover {{
    border-color: {c['border_hover']};
    background: {c['hover_bg']};
}}

QPushButton:pressed {{
    background: {c['selection_bg']};
}}

QPushButton:focus {{
    border-color: {c['border_focus']};
    outline: none;
}}

QPushButton:disabled {{
    background: {c['disabled_bg']};
    color: {c['text_disabled']};
    border-color: {c['border']};
}}

/* Primary button */
QPushButton#primary {{
    background: {c['accent']};
    color: white;
    border-color: {c['accent']};
}}

QPushButton#primary:hover {{
    background: {c['accent_hover']};
    border-color: {c['accent_hover']};
}}

QPushButton#primary:pressed {{
    background: {c['accent_hover']};
}}

QPushButton#primary:disabled {{
    background: {c['disabled_bg']};
    color: {c['text_disabled']};
}}

/* Success button */
QPushButton#success {{
    background: {c['success']};
    color: white;
    border-color: {c['success']};
}}

QPushButton#success:hover {{
    background: {c['success_hover']};
}}

/* Add file button */
QPushButton#addFile {{
    background: {c['accent']};
    color: white;
    border-color: {c['accent']};
    font-weight: 600;
}}

QPushButton#addFile:hover {{
    background: {c['accent_hover']};
}}

/* ═══════════════════════════════════════════════════════════════
   Input Fields
   ═══════════════════════════════════════════════════════════════ */
QLineEdit, QPlainTextEdit, QSpinBox {{
    background: {c['input_bg']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px 12px;
    selection-background-color: {c['selection_bg']};
    selection-color: {c['text_primary']};
    color: {c['text_primary']};
}}

QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus {{
    border-color: {c['border_focus']};
}}

QLineEdit:disabled, QPlainTextEdit:disabled {{
    background: {c['disabled_bg']};
    color: {c['text_disabled']};
}}

/* ═══════════════════════════════════════════════════════════════
   ComboBox (Dropdown)
   ═══════════════════════════════════════════════════════════════ */
QComboBox {{
    background: {c['input_bg']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 18px;
    color: {c['text_primary']};
}}

QComboBox:hover {{
    border-color: {c['border_hover']};
}}

QComboBox:focus {{
    border-color: {c['border_focus']};
}}

QComboBox:disabled {{
    background: {c['disabled_bg']};
    color: {c['text_disabled']};
}}

QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

QComboBox::down-arrow {{
    width: 14px;
    height: 14px;
    image: url("{_CHEVRON_SVG}");
}}

QComboBox QAbstractItemView {{
    background: {c['card_bg']};
    color: {c['text_primary']};
    selection-background-color: {c['selection_bg']};
    selection-color: {c['text_primary']};
    border: 1px solid {c['border']};
    border-radius: 8px;
    padding: 4px;
}}

/* ═══════════════════════════════════════════════════════════════
   Cards & Panels
   ═══════════════════════════════════════════════════════════════ */
QFrame#dropzone, QFrame#detailPane, QFrame#list {{
    background: {c['card_bg']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}

QFrame#emptyState {{
    background: {c['card_bg']};
    border: 2px dashed {c['border']};
    border-radius: 12px;
}}

QFrame#fileCard {{
    background: {c['card_bg']};
    border: 1px solid {c['border']};
    border-radius: 12px;
}}

QFrame#fileCard:hover {{
    border-color: {c['border_hover']};
}}

QFrame#fileCard[active="true"] {{
    border: 2px solid {c['border_active']};
    background: {c['selection_bg']};
}}

/* Card labels */
QLabel#cardFilename {{
    font-size: 13px;
    font-weight: 500;
    color: {c['text_primary']};
}}

QLabel#cardMeta, QLabel#cardStatus {{
    color: {c['text_secondary']};
    font-size: 11px;
}}

QLabel#categoryBadge {{
    border-radius: 6px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 500;
}}

/* ═══════════════════════════════════════════════════════════════
   Topbar
   ═══════════════════════════════════════════════════════════════ */
QFrame#topbar {{
    background: {c['card_bg']};
    border-bottom: 1px solid {c['border']};
}}

/* ═══════════════════════════════════════════════════════════════
   Table
   ═══════════════════════════════════════════════════════════════ */
QTableWidget {{
    background: {c['card_bg']};
    border: none;
    gridline-color: {c['border']};
    selection-background-color: {c['selection_bg']};
    selection-color: {c['text_primary']};
}}

QTableWidget::item {{
    padding: 10px 12px;
    border-bottom: 1px solid {c['border']};
}}

QTableWidget::item:selected {{
    background: {c['selection_bg']};
}}

QHeaderView::section {{
    background: {c['page_bg']};
    color: {c['text_secondary']};
    font-size: 12px;
    font-weight: 600;
    padding: 10px 12px;
    border: none;
    border-bottom: 1px solid {c['border']};
}}

/* ═══════════════════════════════════════════════════════════════
   Checkbox
   ═══════════════════════════════════════════════════════════════ */
QCheckBox {{
    spacing: 8px;
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 1px solid {c['border_hover']};
    border-radius: 4px;
    background: {c['input_bg']};
}}

QCheckBox::indicator:checked {{
    background: {c['accent']};
    border-color: {c['accent']};
    image: url("{_CHECK_SVG}");
}}

QCheckBox::indicator:hover {{
    border-color: {c['accent']};
}}

/* ═══════════════════════════════════════════════════════════════
   Progress Bar
   ═══════════════════════════════════════════════════════════════ */
QProgressBar {{
    border: none;
    background: {c['disabled_bg']};
    border-radius: 4px;
    text-align: center;
    min-height: 18px;
    font-size: 11px;
    color: {c['text_secondary']};
}}

QProgressBar::chunk {{
    background: {c['accent']};
    border-radius: 4px;
}}

/* ═══════════════════════════════════════════════════════════════
   StatusBar
   ═══════════════════════════════════════════════════════════════ */
QStatusBar {{
    background: {c['card_bg']};
    color: {c['text_secondary']};
    font-size: 12px;
    border-top: 1px solid {c['border']};
}}

QStatusBar::item {{
    border: none;
}}

/* ═══════════════════════════════════════════════════════════════
   Menu
   ═══════════════════════════════════════════════════════════════ */
QMenu {{
    background: {c['card_bg']};
    border: 1px solid {c['border']};
    padding: 6px;
    border-radius: 8px;
}}

QMenu::item {{
    padding: 8px 16px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background: {c['hover_bg']};
}}

QMenu::separator {{
    height: 1px;
    background: {c['border']};
    margin: 6px;
}}

/* ═══════════════════════════════════════════════════════════════
   Tooltip
   ═══════════════════════════════════════════════════════════════ */
QToolTip {{
    background: {c['card_bg']};
    color: {c['text_primary']};
    border: 1px solid {c['border']};
    padding: 6px 10px;
    border-radius: 6px;
    font-size: 12px;
}}

/* ═══════════════════════════════════════════════════════════════
   Scrollbar
   ═══════════════════════════════════════════════════════════════ */
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {c['scrollbar']};
    border-radius: 5px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {c['scrollbar_hover']};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* ═══════════════════════════════════════════════════════════════
   Detail Panel
   ═══════════════════════════════════════════════════════════════ */
QLabel#detailHeading {{
    font-size: 15px;
    font-weight: 600;
    color: {c['text_primary']};
}}

QLabel#detailSectionTitle {{
    font-size: 11px;
    color: {c['text_secondary']};
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}}

QLabel#detailLabel {{
    font-size: 12px;
    color: {c['text_secondary']};
}}

QLabel#detailValue {{
    font-size: 13px;
    color: {c['text_primary']};
    background: {c['page_bg']};
    border: 1px solid {c['border']};
    border-radius: 6px;
    padding: 8px 12px;
}}

/* ═══════════════════════════════════════════════════════════════
   Action Bar
   ═══════════════════════════════════════════════════════════════ */
QFrame#actionbar {{
    border-top: 1px solid {c['border']};
    background: {c['card_bg']};
}}

/* ═══════════════════════════════════════════════════════════════
   Sidebar Footer
   ═══════════════════════════════════════════════════════════════ */
QPushButton#footerAction {{
    color: {c['sidebar_text']};
    background: transparent;
    border: none;
    border-radius: 6px;
    text-align: left;
    padding: 8px 12px;
    font-size: 13px;
}}

QPushButton#footerAction:hover {{
    background: {c['sidebar_hover']};
    color: {c['sidebar_text_hover']};
}}

/* ═══════════════════════════════════════════════════════════════
   Screenshot Button
   ═══════════════════════════════════════════════════════════════ */
QPushButton#captureLaunch {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                stop:0 #0891b2,
                stop:1 #0e7490);
    color: white;
    border: 1px solid #06b6d4;
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 13px;
    font-weight: 600;
}}

QPushButton#captureLaunch:hover {{
    background: #0e7490;
}}

/* ═══════════════════════════════════════════════════════════════
   Workflow Steps
   ═══════════════════════════════════════════════════════════════ */
QLabel#stepBadge {{
    border-radius: 10px;
    font-weight: 600;
    font-size: 11px;
}}

/* ═══════════════════════════════════════════════════════════════
   Empty States
   ═══════════════════════════════════════════════════════════════ */
QLabel#emptyTitle {{
    font-size: 16px;
    font-weight: 600;
    color: {c['text_primary']};
}}

QLabel#emptyText {{
    font-size: 13px;
    color: {c['text_secondary']};
}}
"""

    return qss

def switch_theme(name: str) -> None:
    """Switch to the specified theme."""
    global CURRENT_THEME, WORKBENCH_QSS
    if name not in THEME_COLORS:
        raise ValueError(f"Unknown theme '{name}'; choose from {list(THEME_COLORS)}")
    CURRENT_THEME = name
    WORKBENCH_QSS = _build_qss(name)

# Initialize with ocean theme
switch_theme('ocean')
