"""Literal text matching for excerpts and painted highlights; never interpret HTML."""
import re
from .organization import query_terms


def match_spans(text, terms):
    spans = []
    for term in terms:
        if term:
            spans.extend(m.span() for m in re.finditer(re.escape(term), text, re.IGNORECASE))
    merged = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end,merged[-1][1]))
        else:
            merged.append((start,end))
    return merged


def body_snippet(body, query, limit=180):
    spans = match_spans(body, query_terms(query))
    if not spans:
        return ''
    start = max(0,spans[0][0]-30)
    return body[start:start+limit].replace('\n',' ').replace('\r',' ')


def paint_matches(painter, rect, text, terms):
    from PySide6.QtCore import Qt, QRectF
    from PySide6.QtGui import QColor
    metrics = painter.fontMetrics()
    height = metrics.height()
    top = rect.top()+(rect.height()-height)/2
    for start,end in match_spans(text,terms):
        x = rect.left()+metrics.horizontalAdvance(text[:start])
        width = metrics.horizontalAdvance(text[start:end])
        painter.fillRect(QRectF(x,top,width,height),QColor('#ffdf7d'))
    painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, text)
