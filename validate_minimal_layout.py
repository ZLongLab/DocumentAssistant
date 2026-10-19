"""Create the real window in an isolated home; string matching is not runtime validation."""
import argparse
import os
import tempfile
import sys
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--layout', choices=['minimal', 'classic'], default='minimal')
    args = parser.parse_args(argv)
    os.environ['DOCUMENTASSISTANT_LAYOUT'] = args.layout
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QCoreApplication, QEvent
    from document_assistant.gui import MainWindow, configure_app
    from document_assistant.layout_minimal import build_minimal_window
    from document_assistant.layout import build_window
    app = QApplication.instance() or QApplication([])
    configure_app(app)
    callback_errors = []
    previous_hook = sys.excepthook
    sys.excepthook = lambda kind, value, trace: callback_errors.append(str(value))
    temporary_root = Path(__file__).resolve().parent.parent / 'DocumentAssistant-local/tmp'
    temporary_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='layout-check-', dir=temporary_root) as temporary:
        # Construct the production entry point, then compare actual widget contracts.
        window = MainWindow(Path(temporary) / 'home')
        try:
            assert window.layout_variant == args.layout
            window.update_controls()
            for name in ('source_edit', 'search_scope', 'reason_label', 'settings_button', 'rule_button',
                         'remember_category_action', 'category_rules_action', 'watch_action',
                         'reading_button', 'full_backup_action', 'restore_backup_action', 'steps_label'):
                assert hasattr(window, name), name
            window.show()
            app.processEvents()
            window.tabs.setCurrentIndex(1)
            window.tabs.setCurrentIndex(0)
            window.toggle_theme()
            assert not window.archive_button.isEnabled()
            assert window.tabs.count() == 2
        finally:
            window.close()
            window.deleteLater()
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
            app.processEvents()
    sys.excepthook = previous_hook
    if callback_errors:
        raise AssertionError('Qt callback errors: ' + '; '.join(callback_errors))
    print(f'PASS: real {args.layout} MainWindow, actions, navigation, theme, empty state and clean shutdown')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
