"""Compact QSS overrides using the existing ocean/rose semantic palette."""


def build_minimal_qss(colors=None):
    if colors is None:
        from .theme import get_colors
        colors = get_colors()
    c = colors
    return f'''
    QWidget {{ font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 13px; }}
    QFrame#sidebar {{ background: {c['sidebar']}; }}
    QFrame#topbar {{ background: {c['page_bg']}; border-bottom: 1px solid {c['border']}; }}
    QLabel#pageTitle {{ font-size: 23px; font-weight: 700; color: {c['text']}; }}
    QLabel#subtitle {{ font-size: 13px; color: {c['muted']}; }}
    QLabel#sectionTitle {{ font-size: 15px; font-weight: 600; }}
    QLabel#brand {{ font-size: 12px; }}
    QPushButton#nav {{ padding: 8px 12px; border-radius: 8px; }}
    QPushButton#footerAction {{ padding: 7px 8px; font-size: 12px; }}
    QFrame#dropzone {{ background: {c['card_bg']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QFrame#fileCard {{ background: {c['card_bg']}; border: 1px solid {c['card_border']}; border-radius: 10px; }}
    QFrame#fileCard[active="true"] {{ border: 2px solid {c['accent']}; background: {c['card_active_bg']}; }}
    QFrame#fileCard:hover {{ border-color: {c['accent']}; }}
    QLabel#cardFilename {{ font-size: 13px; font-weight: 600; }}
    QLabel#cardState {{ font-size: 11px; }}
    QFrame#detailPane {{ background: {c['card_bg']}; border: 1px solid {c['border']}; border-radius: 10px; }}
    QLabel#detailHeading {{ font-size: 15px; }}
    QLabel#fieldTitle {{ font-size: 12px; font-weight: 600; }}
    QPushButton {{ padding: 7px 12px; border-radius: 8px; font-size: 13px; }}
    QLineEdit, QComboBox {{ padding: 6px 8px; border-radius: 7px; }}
    QPlainTextEdit#bodyPreview {{ padding: 8px; font-size: 12px; }}
    QFrame#actionbar {{ background: {c['page_bg']}; border-top: 1px solid {c['border']}; }}
    '''


MINIMAL_QSS = build_minimal_qss()
# Kept for external preview imports; colors are always sourced from the shared theme.
from .theme import get_colors
MINIMAL_COLORS = get_colors()
