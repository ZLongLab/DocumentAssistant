"""Shared native screenshot editor and settings styling."""
from pathlib import Path
CAPTURE_QSS = """
QDialog { background:#f7f4eb; }
QWidget { font-family:'Microsoft YaHei UI'; font-size:13px; color:#25382f; }
QFrame#captureHeader { background:#fffdf9; border-bottom:1px solid #e5ebe7; }
QLabel#captureTitle { font-size:20px; font-weight:700; color:#16372b; }
QLabel#captureMeta { color:#76847b; font-size:12px; }
QLabel#captureBadge { color:#148263; background:#e2f6ee; padding:7px 12px; border-radius:9px; font-size:12px; }
QFrame#toolGroup { background:#eef3f0; border-radius:12px; }
QPushButton { background:#ffffff; border:1px solid #dce5df; border-radius:10px; padding:9px 15px; }
QPushButton:hover { background:#f0f6f2; border-color:#a2c3b0; }
QPushButton:pressed { background:#e1f1e8; }
QPushButton:focus { border-color:#199a75; }
QPushButton:disabled { color:#a4afa8; background:#f3f5f3; border-color:#e8ece9; }
QPushButton#zoomButton { padding:6px 8px; font-size:12px; }
QPushButton#tool { border:1px solid transparent; background:transparent; border-radius:9px; padding:7px 8px; }
QPushButton#tool:hover { background:#e2ece6; }
QPushButton#tool:checked { background:#ffffff; border-color:#dbe8df; color:#11825f; font-weight:600; }
QPushButton#copyCapture { background:#16795f; border-color:#16795f; color:#ffffff; font-weight:600; padding:11px 22px; }
QPushButton#copyCapture:hover { background:#0d8865; border-color:#0d8865; }
QPushButton#copyCapture:pressed { background:#086c50; }
QPushButton#copyCapture:disabled { background:#a6c9b9; border-color:#a6c9b9; color:#edf5f0; }
QPushButton#cancelCapture { background:transparent; border-color:transparent; color:#738177; }
QPushButton#cancelCapture:hover { background:#f0f3f0; color:#30473a; }
QLabel#capturePath { color:#506356; font-size:12px; }
QLabel#captureHint { color:#667068; font-size:11px; }
QLabel#captureError { color:#aa543c; background:#fff1e8; border-radius:8px; padding:8px 12px; }
QLineEdit { background:#ffffff; border:1px solid #dce5df; padding:10px 12px; border-radius:9px; selection-background-color:#189970; }
QLineEdit:focus { border-color:#189970; }
QSpinBox { background:#fffdf9; border:1px solid #dce5df; border-radius:8px; padding:5px 18px 5px 6px; font-size:12px; min-height:20px; }
QSpinBox:focus { border-color:#16795f; }
QSpinBox::up-button { subcontrol-origin:border; subcontrol-position:top right; width:16px; border:0; background:#edf2e9; border-top-right-radius:8px; }
QSpinBox::down-button { subcontrol-origin:border; subcontrol-position:bottom right; width:16px; border:0; background:#edf2e9; border-bottom-right-radius:8px; }
QScrollArea { border:0; background:transparent; }
QPushButton#filterChip { background:#e9f3ec; color:#17604a; padding:5px 9px; }
QWidget#captureCanvas { background:transparent; }
QToolTip { background:#173c2e; color:#ffffff; border:0; padding:7px 10px; }
"""

CAPTURE_QSS += """
QPushButton#saveCapture { background:transparent; border-color:transparent; color:#6a8273; font-size:12px; font-weight:400; padding:9px 6px; }
QPushButton#saveCapture:hover { color:#0c8967; background:#e8f6ee; }
QPushButton#saveCapture:focus { border-color:#87bba1; }
"""
CAPTURE_QSS += '\nQSpinBox::up-arrow { width:10px; height:10px; image:url("' + Path(__file__).with_name('chevron-up.svg').as_posix() + '"); }\nQSpinBox::down-arrow { width:10px; height:10px; image:url("' + Path(__file__).with_name('chevron-down.svg').as_posix() + '"); }\n'
