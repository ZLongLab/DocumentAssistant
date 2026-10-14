"""Warm paper, forest green and orange; implemented with native Qt QSS."""
from pathlib import Path

WORKBENCH_QSS = """
QWidget { font-family: 'Microsoft YaHei UI'; font-size: 14px; color: #202923; }
QMainWindow, QDialog { background: #f7f4eb; }
QFrame#sidebar { background: #183d32; }
QLabel#brand { color: #ffffff; font-size: 13px; font-weight: 600; }
QLabel#brandMark { background: #fffdf7; border-radius: 8px; }
QLabel#sidebarNote { color: #c3d5ca; font-size: 12px; }
QLabel#sidebarPath { color: #ffffff; font-size: 12px; }
QPushButton#nav { text-align: left; padding: 12px 16px; background: transparent; border: 1px solid transparent; color: #e5efe8; font-size: 16px; border-radius: 14px; }
QPushButton#nav:hover { background: #285145; }
QPushButton#nav:checked { background: #e76632; color: white; font-weight: 600; }
QPushButton#sideButton { background: transparent; border: 0; color: #dce9df; text-align: left; padding: 8px; }
QPushButton#sideButton:hover { background: #285145; }
QLabel#pageTitle { font-size: 30px; font-weight: 700; color: #121c18; }
QLabel#subtitle { color: #586059; font-size: 15px; }
QLabel#steps { color: #697268; font-size: 12px; padding-top: 4px; }
QLabel#muted { color: #667068; font-size: 12px; }
QLabel#sectionTitle { font-size: 19px; font-weight: 600; }
QFrame#dropzone, QFrame#detailPane, QFrame#emptyState, QFrame#list { background: #fffdf9; border: 1px solid #ebe5da; border-radius: 16px; }
QWidget#detailContent { background: #fffdf9; border-radius: 16px; }
QFrame#emptyState { border: 1px dashed #c8cbbc; }
QLabel#emptyTitle { font-size: 20px; font-weight: 600; }
QScrollArea, QWidget#cardContent { background: transparent; border: 0; }
QFrame#fileCard { background: #fffdf9; border: 1px solid #e7e2d9; border-radius: 16px; }
QFrame#fileCard[active="true"] { border: 2px solid #178765; background: #fcfefd; }
QLabel#cardFilename { font-size: 15px; font-weight: 600; }
QLabel#cardMeta, QLabel#cardStatus { color: #697268; font-size: 11px; }
QLabel#categoryBadge { border-radius: 13px; padding: 5px 10px; font-size: 11px; font-weight: 600; }
QPushButton#cardMore, QToolButton#cardMore, QPushButton#detailClose { background: transparent; border: 0; padding: 0; color: #667068; }
QPushButton#cardMore:hover, QPushButton#detailClose:hover { background: #edece5; }
QLabel#detailHeading { font-size: 19px; font-weight: 600; }
QLabel#detailFilename { font-size: 17px; font-weight: 600; }
QLabel#detailBanner { border-radius: 12px; padding: 12px; font-size: 16px; font-weight: 600; }
QFrame#reasonBox { background: #edf2e9; border: 0; border-radius: 12px; }
QPlainTextEdit#bodyPreview { background: white; border: 1px solid #e4e4dc; border-radius: 12px; padding: 14px; font-size: 12px; }
QFrame#actionbar { border-top: 1px solid #e5e0d4; }
QLineEdit, QPlainTextEdit, QSpinBox { background: white; border: 1px solid #d9ddd5; border-radius: 9px; padding: 8px 10px; selection-background-color: #17604a; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus { border-color: #17604a; }
QPushButton { background: #fffefd; border: 1px solid #dcddd6; padding: 9px 14px; border-radius: 10px; }
QPushButton:hover { background: #f1f2eb; border-color: #9cae9f; }
QPushButton:pressed { background: #e4eadd; }
QPushButton:focus { border-color: #17604a; }
QPushButton#primary { background: #164b3c; color: white; border-color: #164b3c; font-weight: 600; font-size: 15px; }
QPushButton#primary:hover { background: #23604d; }
QPushButton#primary:pressed { background: #0d382d; }
QPushButton#addFile { background: #ec602c; color: white; border-color: #ec602c; font-size: 15px; font-weight: 600; }
QPushButton#addFile:hover { background: #d95323; }
QPushButton:disabled, QPushButton#primary:disabled, QPushButton#addFile:disabled, QPushButton#nav:disabled { background: #e4e8df; color: #849083; border-color: #dce1d6; }
QComboBox { background: white; border: 1px solid #d9ddd5; border-radius: 9px; padding: 5px 8px; min-height: 22px; }
QComboBox:focus { border-color: #17604a; }
QComboBox:disabled { color: #849083; background: #edf0e8; }
QComboBox QAbstractItemView { background: white; color: #202923; selection-background-color: #edf2e9; selection-color: #202923; border: 1px solid #ccd4c9; }
QTableWidget { background: #fffdf9; alternate-background-color: #fffdf9; border: 0; gridline-color: #e9e7dd; selection-background-color: #edf2e9; }
QTableWidget::item { padding: 10px 12px; border-bottom: 1px solid #ece9df; }
QTableWidget::item:selected { background: #edf2e9; color: #202923; }
QHeaderView::section { background: #f2f3eb; color: #667068; font-size: 12px; padding: 10px 12px; border: 0; border-bottom: 1px solid #e3e4da; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 17px; height: 17px; border: 1px solid #a1aca0; border-radius: 4px; background: white; }
QCheckBox::indicator:checked { background: #17604a; border: 1px solid #17604a; }
QProgressBar { border: 0; background: #e5e9df; border-radius: 4px; text-align: center; min-height: 18px; font-size: 11px; }
QProgressBar::chunk { background: #17604a; border-radius: 4px; }
QStatusBar { background: #f7f4eb; color: #667068; font-size: 11px; border-top: 1px solid #e8e3d7; }
QStatusBar::item { border: 0; }
QMenu { background: #fffdf9; border: 1px solid #d9ddd5; padding: 6px; }
QMenu::item { padding: 8px 16px; border-radius: 5px; }
QMenu::item:selected { background: #edf2e9; }
QMenu::separator { height: 1px; background: #e0e4da; margin: 6px; }
QToolTip { background: #fffdf9; color: #202923; border: 1px solid #c8d0c3; padding: 6px; }
QScrollBar:vertical { background: transparent; width: 9px; margin: 0; }
QScrollBar::handle:vertical { background: #c7cec0; border-radius: 4px; min-height: 24px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""
WORKBENCH_QSS += '\nQComboBox::drop-down { border: 0; width: 22px; }\nQComboBox::down-arrow { width: 14px; height: 14px; image: url("' + Path(__file__).with_name('chevron-down.svg').as_posix() + '"); }\n'
WORKBENCH_QSS += '\nQCheckBox::indicator:checked { image: url("' + Path(__file__).with_name('check-white.svg').as_posix() + '"); }\n'

WORKBENCH_QSS += """
QPushButton#captureLaunch { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #16795f,stop:1 #209d7b); color:#ffffff; text-align:left; border:1px solid #42a68c; border-radius:14px; padding:12px 14px; font-size:14px; font-weight:600; }
QPushButton#captureLaunch:hover { background:#23a582; border-color:#6dc9aa; }
QPushButton#captureLaunch:pressed { background:#13624f; }
QPushButton#captureLaunch:focus { border:2px solid #8ce0c1; }
"""

WORKBENCH_QSS += """
QPushButton#filterChip { background:#e7f1e9; border-color:#d3e3d6; color:#17604a; padding:5px 9px; font-size:12px; }
QPushButton#filterChip:hover { background:#d5e8dc; border-color:#9fbeaa; }
"""

WORKBENCH_QSS += """
QFrame#sidebarFooter { background:#21483b; border:1px solid #335b49; border-radius:14px; }
QLabel#footerCaption { color:#a9c5b5; font-size:11px; padding:0 8px; }
QLabel#sidebarPath { color:#eef5ef; font-size:13px; font-weight:600; }
QFrame#footerSeparator { background:#365e4c; border:0; margin:3px 8px; }
QPushButton#footerAction { color:#e6f1e9; background:transparent; border:0; border-radius:9px; text-align:left; padding:7px 8px; font-size:14px; }
QPushButton#footerAction:hover { background:#315b48; }
QPushButton#footerAction:pressed { background:#3d6b56; }
QPushButton#footerAction:focus { border:1px solid #86b79b; }
"""

WORKBENCH_QSS += """
QMenu#actionMenu { background:#fffdf9; border:1px solid #cdddcf; border-radius:13px; padding:32px 8px 9px 8px; color:#274737; }
QMenu#actionMenu::item { padding:10px 28px 10px 12px; margin:2px 0; border-radius:8px; font-size:13px; }
QMenu#actionMenu::item:selected { background:#e2eee4; color:#164b3c; }
QMenu#actionMenu::item:disabled { color:#99a99d; }
QMenu#actionMenu::separator { background:#e1e9df; height:1px; margin:6px 10px; }
QMenu#actionMenu::right-arrow { width:12px; height:12px; }
QFrame#topbar[library="true"] { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #eaf2e7,stop:0.68 #f7f4eb,stop:1 #f4f0e5); border-bottom:1px solid #dde6d6; }
QLabel#libraryTitleIcon { background:#dcebdc; border:1px solid #c8ddcc; border-radius:14px; }
"""
