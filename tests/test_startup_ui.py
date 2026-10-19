"""Startup integration without registry writes, hooks or visible windows."""

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication, QLabel

from lilt import __main__ as entry
from lilt import startup
from lilt.storage import Store
from lilt.ui import Controller, MainWindow


class StartupPreferencesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name))
        self.read = patch("lilt.ui.Credentials.read", return_value={}).start()
        self.write = patch("lilt.ui.Credentials.write", return_value=None).start()
        self.enabled = patch("lilt.ui.startup.is_enabled", return_value=False).start()
        self.set_enabled = patch("lilt.ui.startup.set_enabled").start()
        self.addCleanup(patch.stopall)
        self.controller = Controller(self.store)
        self.window = None

    def tearDown(self):
        self.controller.pool.waitForDone(1000)
        if self.window is not None:
            self.window.hide()
            self.window.deleteLater()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.directory.cleanup()

    def make_window(self):
        with patch("lilt.ui.QSystemTrayIcon.isSystemTrayAvailable", return_value=False):
            self.window = MainWindow(self.controller, listen=False)
        return self.window

    def test_checkbox_reflects_windows_registration_without_writing(self):
        self.enabled.return_value = True
        window = self.make_window()
        self.assertEqual(window.start_with_windows.text(), "Start Lilt with Windows")
        self.assertTrue(window.start_with_windows.isChecked())
        self.assertTrue(window.start_with_windows.isEnabled())
        self.enabled.assert_called()
        self.set_enabled.assert_not_called()
        self.write.assert_not_called()

    def test_registration_read_failure_disables_checkbox_and_displays_reason(self):
        message = "Windows could not read Lilt's startup setting."
        self.enabled.side_effect = startup.StartupError(message)
        window = self.make_window()
        self.assertFalse(window.start_with_windows.isEnabled())
        self.assertTrue(any(message in label.text() and not label.isHidden()
                            for label in window.findChildren(QLabel)))
        self.set_enabled.assert_not_called()

    def test_unchanged_choice_does_not_rewrite_registration(self):
        window = self.make_window()
        window.save_preferences()
        self.set_enabled.assert_not_called()
        self.write.assert_called_once_with({"deepl": "", "anki": ""})
        self.assertEqual(self.store.get_setting("provider"), "google")
        self.assertIn("Saved", window.settings_status.text())

    def test_enable_happens_after_other_preferences_and_keys_are_saved(self):
        window = self.make_window()
        window.start_with_windows.setChecked(True)
        window.double_copy.setChecked(False)
        window.to_tray.setChecked(False)
        window.anki_key.setText("test-anki-key")

        def enable(desired):
            self.assertTrue(desired)
            self.write.assert_called_once_with({"deepl": "", "anki": "test-anki-key"})
            self.assertEqual(self.controller.secrets["anki"], "test-anki-key")
            self.assertEqual(self.store.get_setting("provider"), "google")
            self.assertIs(self.store.get_setting("double_copy"), False)
            self.assertIs(self.store.get_setting("close_to_tray"), False)

        self.set_enabled.side_effect = enable
        window.save_preferences()
        self.set_enabled.assert_called_once_with(True)

    def test_unchecking_enabled_startup_applies_disable(self):
        self.enabled.return_value = True
        window = self.make_window()
        window.start_with_windows.setChecked(False)
        window.save_preferences()
        self.set_enabled.assert_called_once_with(False)

    def test_startup_write_failure_keeps_saved_preferences_and_restores_actual_state(self):
        window = self.make_window()
        window.start_with_windows.setChecked(True)
        window.double_copy.setChecked(False)
        self.set_enabled.side_effect = startup.StartupError("Access denied.")
        window.save_preferences()
        self.assertEqual(window.settings_status.text(), "Other preferences saved. Access denied.")
        self.assertFalse(window.start_with_windows.isChecked())
        self.assertIs(self.store.get_setting("double_copy"), False)
        self.write.assert_called_once()
        self.set_enabled.assert_called_once_with(True)

    def test_startup_read_failure_during_save_does_not_write_registration(self):
        window = self.make_window()
        window.start_with_windows.setChecked(True)
        self.enabled.side_effect = startup.StartupError("Startup permissions changed.")
        window.save_preferences()
        self.assertEqual(window.settings_status.text(), "Other preferences saved. Startup permissions changed.")
        self.set_enabled.assert_not_called()
        self.write.assert_called_once()
        self.assertEqual(self.store.get_setting("provider"), "google")

    def test_failed_key_save_does_not_change_startup_or_other_preferences(self):
        window = self.make_window()
        window.start_with_windows.setChecked(True)
        self.enabled.reset_mock()
        self.write.side_effect = OSError("Credential protection failed.")
        window.save_preferences()
        self.assertEqual(window.settings_status.text(), "Credential protection failed.")
        self.enabled.assert_not_called()
        self.set_enabled.assert_not_called()
        self.assertIsNone(self.store.get_setting("provider"))


class StartupLaunchTests(unittest.TestCase):
    def launch(self, *, startup_launch, acquired=True, tray=True):
        app, timer, lock, window = Mock(), Mock(), Mock(), Mock()
        app.exec.return_value = 17
        lock.acquire.return_value = acquired
        window.tray = object() if tray else None
        store = Mock(data_dir=Path("C:/isolated-startup-test"))
        argv = ["Lilt.exe"] + (["--startup"] if startup_launch else [])
        with patch.object(entry.sys, "argv", argv), patch.object(entry.sys, "excepthook"), \
                patch.object(entry, "QApplication", return_value=app), \
                patch.object(entry, "QTimer", return_value=timer), \
                patch.object(entry, "Store", return_value=store), \
                patch.object(entry, "InstanceLock", return_value=lock), \
                patch.object(entry, "Controller") as controller_factory, \
                patch.object(entry, "MainWindow", return_value=window) as window_factory:
            result = entry.main()
        return result, app, lock, window, controller_factory, window_factory

    def test_primary_startup_with_tray_does_not_show_main_window(self):
        result, app, lock, window, _, _ = self.launch(startup_launch=True)
        self.assertEqual(result, 17)
        window.show.assert_not_called()
        window.show_main.assert_not_called()
        app.exec.assert_called_once()
        lock.release.assert_called_once()

    def test_primary_startup_without_tray_shows_accessible_window(self):
        _, _, _, window, _, _ = self.launch(startup_launch=True, tray=False)
        window.show.assert_called_once()

    def test_primary_manual_launch_shows_window_even_with_tray(self):
        _, _, _, window, _, _ = self.launch(startup_launch=False)
        window.show.assert_called_once()

    def test_duplicate_startup_does_not_activate_existing_window_or_create_another(self):
        result, app, lock, _, controller_factory, window_factory = self.launch(startup_launch=True, acquired=False)
        self.assertEqual(result, 0)
        lock.activate_existing.assert_not_called()
        controller_factory.assert_not_called()
        window_factory.assert_not_called()
        app.exec.assert_not_called()

    def test_duplicate_manual_launch_activates_existing_window(self):
        result, app, lock, _, controller_factory, window_factory = self.launch(startup_launch=False, acquired=False)
        self.assertEqual(result, 0)
        lock.activate_existing.assert_called_once()
        controller_factory.assert_not_called()
        window_factory.assert_not_called()
        app.exec.assert_not_called()


if __name__ == "__main__":
    unittest.main()
