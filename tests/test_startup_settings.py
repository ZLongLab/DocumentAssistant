import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt
from document_assistant.gui import MainWindow
from document_assistant.settings_dialog import SettingsDialog
from document_assistant.startup_registration import StartupRegistration
from tests.gui_wait import settle_search
from test_upgrade import Fixture

class StartupSettingsTests(Fixture):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])
    def test_toggle_saves_and_failure_restores_actual_state(self):
        window=MainWindow(self.root/'settings');service=SimpleNamespace(state=False)
        service.enabled=lambda:service.state
        def write(value):service.state=value
        service.set_enabled=write
        dialog=SettingsDialog(window,service);dialog.show();self.app.processEvents()
        QTest.mouseClick(dialog.startup_switch,Qt.MouseButton.LeftButton)
        self.assertTrue(service.state);self.assertIn('已开启',dialog.status.text())
        def failure(value):raise PermissionError('synthetic failure')
        service.set_enabled=failure
        QTest.mouseClick(dialog.startup_switch,Qt.MouseButton.LeftButton)
        self.assertTrue(dialog.startup_switch.isChecked());self.assertIn('未成功',dialog.status.text())
        dialog.reject();settle_search(window);window.close()
    def test_startup_command_quotes_paths_and_uses_absolute_entry(self):
        service=StartupRegistration(self.root/'runtime space',project=self.root/'project space',pythonw=self.root/'python space/pythonw.exe')
        self.assertEqual(service.arguments[2],str((self.root/'project space/startup.py').resolve()))
        self.assertIn('--home',service.command);self.assertIn('"',service.command)
    def test_foreign_value_is_never_replaced_or_deleted(self):
        service=StartupRegistration(self.root)
        with patch.object(service,'read',return_value='foreign program'):
            for value in (True,False):
                with self.assertRaises(ValueError):service.set_enabled(value)
    def test_sidebar_has_one_library_name_and_matching_actions(self):
        window=MainWindow(self.root/'settings');window.show();self.app.processEvents()
        window.sidebar_path.setText('D:/文件分类')
        self.assertNotIn('\n',window.sidebar_path.text());self.assertEqual(window.sidebar_path.toolTip(),'D:/文件分类')
        self.assertEqual(window.more_button.objectName(),'footerAction');self.assertEqual(window.settings_button.objectName(),'footerAction')
        self.assertEqual(window.more_button.minimumHeight(),window.settings_button.minimumHeight())
        settle_search(window);window.close()

if __name__=='__main__':unittest.main()
