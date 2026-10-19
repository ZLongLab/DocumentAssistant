"""Compact presentation backed by the full workbench's shared action contracts."""
import json
import os
from pathlib import Path


def selected_layout(home: Path) -> str:
    override = os.environ.get('DOCUMENTASSISTANT_LAYOUT')
    if override is not None:
        if override not in ('minimal', 'classic'):
            raise ValueError('DOCUMENTASSISTANT_LAYOUT 必须为 minimal 或 classic')
        return override
    path = Path(home) / 'ui-layout.json'
    if not path.exists():
        return 'minimal'
    try:
        value = json.loads(path.read_text(encoding='utf-8')).get('layout')
    except (OSError, ValueError, AttributeError):
        return 'minimal'
    return value if value in ('minimal', 'classic') else 'minimal'


def build_minimal_window(window):
    from .layout import build_window
    build_window(window, compact=True)
