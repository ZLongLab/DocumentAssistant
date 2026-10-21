import json,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtCore import QRect,QRectF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from document_assistant.long_capture import LongCaptureSession
from tests.test_long_capture import make_page


class FailureContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([]);cls.page=make_page()

    def test_context_preserves_pre_failure_frames_and_current_long_image(self):
        with TemporaryDirectory() as temp:
            current=[self.page.copy(0,0,900,900)]
            screen=SimpleNamespace(geometry=lambda:QRect(0,0,900,900),availableGeometry=lambda:QRect(0,0,1200,1300))
            session=LongCaptureSession(screen,QRectF(0,0,900,900),'测试',grabber=lambda:current[0])
            self.addCleanup(session.cancel);session.diagnostic_home=Path(temp)/'runtime'
            with patch('document_assistant.long_capture.CaptureKeys'):session.start()
            session.timer.stop()
            for offset in (60,120,180,1500,1560,1620):
                current[0]=self.page.copy(0,offset,900,900);session.poll()
            self.assertFalse(session.diagnostic_home.exists())
            session.save_diagnostics();target=session.diagnostic_path
            report=json.loads((target/'report.json').read_text(encoding='utf-8'))
            self.assertIn('appended',[entry['status'] for entry in report['context']])
            self.assertIn('no_overlap',[entry['status'] for entry in report['context']])
            self.assertLessEqual(len(report['context']),6)
            for entry in report['context']:self.assertFalse(QImage(str(target/entry['file'])).isNull())
            self.assertEqual(QImage(str(target/'captured.png')),session.stitcher.image())
            self.assertEqual(report['current_capture']['height'],1080)
            self.assertEqual(QImage(str(target/'reference.png')),self.page.copy(0,180,900,900))


if __name__=='__main__':unittest.main()
