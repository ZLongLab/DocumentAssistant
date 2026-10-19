"""Interactive preview of the real compact application using only disposable examples."""
import os
import sys
import tempfile
from pathlib import Path


def main():
    if '--smoke' in sys.argv:
        from validate_minimal_layout import main as validate
        return validate(['--layout', 'minimal'])
    os.environ['DOCUMENTASSISTANT_LAYOUT'] = 'minimal'
    from PySide6.QtWidgets import QApplication
    from document_assistant.gui import MainWindow, configure_app
    from document_assistant.service import scan_files
    from document_assistant.rules import DEFAULT_RULES
    root = Path(__file__).resolve().parent.parent / 'DocumentAssistant-local/tmp'
    root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='minimal-preview-', dir=root) as temporary:
        home = Path(temporary)
        app = QApplication([])
        configure_app(app)
        window = MainWindow(home / 'settings')
        window.setWindowTitle('DocumentAssistant · 星空毛玻璃 · 临时示例预览')
        source = home / '示例来源'
        source.mkdir()
        for name, body in (('[示例] 数据结构实验报告.txt', '实验报告\n实验目的：验证示例。\n实验步骤：检查。\n实验结果：通过。'),
                           ('[示例] 项目需求文档.txt', '项目实施方案\n任务分配与进度计划。'),
                           ('[示例] 算法课程笔记.txt', '课程笔记\n第三章：数据结构与算法。'),
                           ('[示例] 读书笔记.txt', '个人笔记\n示例阅读摘要与学习计划。')):
            (source / name).write_text(body, encoding='utf-8')
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        for name in ('[示例] 机器学习基础理论.pdf', '[示例] 深度学习综述.pdf'):
            writer = PdfWriter()
            page=writer.add_blank_page(width=595,height=842)
            font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
            page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):writer._add_object(font)})})
            stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 50 780 Td (Research paper. Abstract. Synthetic example.) Tj ET')
            page[NameObject('/Contents')]=writer._add_object(stream)
            with (source/name).open('wb') as handle:
                writer.write(handle)
        library=home/'示例文档库'
        window.set_library(library)
        window.items = scan_files(list(source.iterdir()), DEFAULT_RULES, library)[0]
        window.populate_scan()
        window.update_controls()
        window.show()
        if '--screenshot' in sys.argv:
            from PySide6.QtTest import QTest
            from tests.gui_wait import settle_search
            from PySide6.QtCore import QCoreApplication, QEvent
            target=Path(sys.argv[sys.argv.index('--screenshot')+1])
            target.parent.mkdir(parents=True,exist_ok=True)
            settle_search(window)
            QTest.qWait(300)
            window.grab().save(str(target))
            window.close();window.deleteLater()
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()
            return 0
        result = app.exec()
        window.details_panel.pdf.shutdown()
        return result


if __name__ == '__main__':
    raise SystemExit(main())
