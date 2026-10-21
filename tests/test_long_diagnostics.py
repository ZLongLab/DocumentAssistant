import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from PySide6.QtCore import QRect,QRectF
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication
from document_assistant.long_capture import LongCaptureSession
from document_assistant.long_stitch import VerticalStitcher
from tests.test_long_capture import make_page


class LongDiagnosticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([]);cls.page=make_page()

    def session(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup)
        home=Path(temp.name)/'runtime';current=[self.page.copy(0,0,900,900)]
        screen=SimpleNamespace(geometry=lambda:QRect(0,0,900,900),availableGeometry=lambda:QRect(0,0,1100,1200))
        session=LongCaptureSession(screen,QRectF(0,0,900,900),'测试',grabber=lambda:current[0])
        session.diagnostic_home=home;self.addCleanup(session.cancel)
        with patch('document_assistant.long_capture.CaptureKeys'):session.start()
        session.timer.stop();return session,current,home

    def test_no_images_are_written_before_user_requests_save(self):
        session,current,home=self.session()
        self.assertFalse(session.controls.diagnostic_button.isEnabled())
        current[0]=self.page.copy(0,1500,900,900);session.poll()
        self.assertTrue(session.controls.diagnostic_button.isEnabled())
        self.assertFalse(home.exists())
        self.assertEqual(session.stitcher.height,900)

    def test_saved_pair_reproduces_failure_without_changing_capture(self):
        session,current,home=self.session();reference=session.stitcher.previous.copy()
        current[0]=self.page.copy(0,1500,900,900);session.poll();before=session.stitcher.image()
        session.controls.diagnostic_button.click()
        target=session.diagnostic_path;self.assertTrue(target.is_relative_to(home))
        saved_reference=QImage(str(target/'reference.png'));failed=QImage(str(target/'first-failed.png'))
        self.assertEqual(saved_reference,reference);self.assertEqual(failed,current[0])
        self.assertEqual(VerticalStitcher(saved_reference).append(failed).status,'no_overlap')
        report=json.loads((target/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['first_failure']['status'],'no_overlap')
        self.assertEqual(len(report['source_sha256']),64)
        self.assertEqual(session.stitcher.image(),before)
        self.assertFalse(session.done)

    def test_second_failure_keeps_its_own_reference_and_history_is_bounded(self):
        session,current,home=self.session()
        current[0]=self.page.copy(0,1500,900,900);session.poll()
        current[0]=self.page.copy(0,220,900,900);session.poll()
        current[0]=self.page.copy(0,2000,900,900)
        for _ in range(95):session.poll()
        session.save_diagnostics();target=session.diagnostic_path
        self.assertEqual(QImage(str(target/'reference.png')),self.page.copy(0,0,900,900))
        self.assertEqual(QImage(str(target/'latest-reference.png')),self.page.copy(0,220,900,900))
        self.assertEqual(QImage(str(target/'latest-failed.png')),current[0])
        report=json.loads((target/'report.json').read_text(encoding='utf-8'))
        self.assertEqual(len(report['recent_results']),90)

    def test_repeat_save_does_not_overwrite_previous_report(self):
        session,current,_=self.session();current[0]=self.page.copy(0,1500,900,900);session.poll()
        session.save_diagnostics();first=session.diagnostic_path;report=(first/'report.json').read_bytes()
        session.save_diagnostics();self.assertNotEqual(session.diagnostic_path,first)
        self.assertEqual((first/'report.json').read_bytes(),report)

    def test_write_error_is_visible_and_does_not_claim_success(self):
        session,current,home=self.session();home.parent.mkdir(exist_ok=True)
        home.write_text('blocked',encoding='utf-8')
        current[0]=self.page.copy(0,1500,900,900);session.poll();session.save_diagnostics()
        self.assertIsNone(session.diagnostic_path)
        self.assertIn('失败',session.controls.diagnostic_hint.text())
        self.assertFalse(session.done)


if __name__=='__main__':unittest.main()
