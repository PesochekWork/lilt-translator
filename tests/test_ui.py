"""GUI concurrency checks with real Qt dispatch and mocked network services."""

import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent
from PySide6.QtWidgets import QApplication

from lilt.anki import AnkiError
from lilt.engine import GOOGLE_PROVIDER, TranslationResult
from lilt.storage import Store
from lilt.ui import Controller, MainWindow, TranslationPane


def sample_result(source="hello", translated="привет"):
    return TranslationResult(source, translated, "en", "ru", GOOGLE_PROVIDER)


class UiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.directory.name))
        with patch("lilt.ui.Credentials.read", return_value={}):
            self.controller = Controller(self.store)
        self.widgets = []
        self.gates = []

    def tearDown(self):
        for gate in self.gates:
            gate.set()
        self.controller.pool.waitForDone(4000)
        self.spin_until(lambda: not self.controller.jobs)
        for widget in self.widgets:
            widget.hide()
            widget.deleteLater()
        self.controller.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.app.processEvents()
        self.directory.cleanup()

    def spin_until(self, predicate, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if predicate():
                return
            time.sleep(0.005)
        self.fail("Qt operation did not finish before the test timeout")

    def pane(self):
        pane = TranslationPane(self.controller)
        self.widgets.append(pane)
        return pane

    def window(self):
        with patch("lilt.ui.QSystemTrayIcon.isSystemTrayAvailable", return_value=False):
            window = MainWindow(self.controller, listen=False)
        self.widgets.append(window)
        return window

    def gate(self):
        gate = threading.Event()
        self.gates.append(gate)
        return gate

    def test_worker_success_callback_runs_on_gui_thread(self):
        gui_thread = threading.get_ident()
        successes, failures = [], []
        self.controller.run(
            lambda: ("translated", threading.get_ident()),
            lambda value: successes.append((value, threading.get_ident())),
            failures.append,
        )
        self.spin_until(lambda: bool(successes or failures))
        self.assertFalse(failures)
        (value, worker_thread), callback_thread = successes[0]
        self.assertEqual(value, "translated")
        self.assertNotEqual(worker_thread, gui_thread)
        self.assertEqual(callback_thread, gui_thread)

    def test_worker_failure_callback_runs_on_gui_thread(self):
        gui_thread = threading.get_ident()
        worker_threads, successes, failures = [], [], []

        def work():
            worker_threads.append(threading.get_ident())
            raise RuntimeError("Connection is offline")

        self.controller.run(
            work,
            successes.append,
            lambda message: failures.append((message, threading.get_ident())),
        )
        self.spin_until(lambda: bool(successes or failures))
        self.assertFalse(successes)
        self.assertNotEqual(worker_threads[0], gui_thread)
        self.assertEqual(failures, [("Connection is offline", gui_thread)])

    def test_edit_during_request_discards_stale_translation(self):
        pane = self.pane()
        entered, release = self.gate(), self.gate()

        def lookup(text, language):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Test worker was not released")
            return sample_result(text, "старый перевод")

        with patch.object(self.controller, "lookup", side_effect=lookup):
            pane.source.setPlainText("first selection")
            pane.start_translation()
            self.spin_until(entered.is_set)
            pane.source.setPlainText("new selection")
            release.set()
            self.spin_until(lambda: not self.controller.jobs)
        self.assertEqual(pane.source.toPlainText(), "new selection")
        self.assertNotIn("старый перевод", pane.output.toPlainText())
        self.assertIsNone(pane.result)
        self.assertFalse(pane.add_button.isEnabled())

    def test_repeated_shortcut_does_not_queue_same_translation(self):
        pane = self.pane()
        entered, release = self.gate(), self.gate()

        def lookup(text, language):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Test worker was not released")
            return sample_result(text)

        with patch.object(self.controller, "lookup", side_effect=lookup) as lookup_mock:
            pane.source.setPlainText("hello")
            pane.start_translation()
            self.spin_until(entered.is_set)
            # Keyboard shortcuts invoke the method even while its button is disabled.
            pane.start_translation()
            pane.start_translation()
            release.set()
            self.spin_until(lambda: not self.controller.jobs)
            self.assertEqual(lookup_mock.call_count, 1)
        self.assertEqual(pane.output.toPlainText(), "привет")
        self.assertTrue(pane.add_button.isEnabled())

    def test_history_reuse_displays_saved_translation_without_network(self):
        result = sample_result()
        self.store.cache_put("hello", "auto", "google", result.to_dict())
        row = self.store.history()[0]
        # Saved results must remain usable even after switching provider offline.
        self.store.set_setting("provider", "deepl")
        window = self.window()
        with patch.object(self.controller, "lookup") as lookup, patch("lilt.ui.translate") as network:
            window.use_history(row)
            self.spin_until(lambda: bool(window.translator.output.toPlainText()))
            lookup.assert_not_called()
            network.assert_not_called()
        self.assertEqual(window.translator.source.toPlainText(), "hello")
        self.assertEqual(window.translator.output.toPlainText(), "привет")
        self.assertTrue(window.translator.result.from_cache)

    def test_offline_anki_keeps_exact_card_pending_for_retry(self):
        pane = self.pane()
        pane.source.setPlainText("hello")
        pane.result = sample_result()
        pane.output.setPlainText("привет")
        pane.context.setText("A greeting to a friend.")
        pane.deck.setCurrentText("Vocabulary")
        client = Mock()
        client.add_card.side_effect = AnkiError("Could not reach Anki. Open Anki Desktop.")
        with patch.object(self.controller, "anki", return_value=client):
            pane.add_card()
            self.spin_until(lambda: not pane.adding and not self.controller.jobs)
        cards = self.store.cards()
        self.assertEqual(len(cards), 1)
        card = cards[0]
        self.assertEqual((card["front"], card["back"], card["context"], card["deck"]),
                         ("hello", "привет", "A greeting to a friend.", "Vocabulary"))
        self.assertIsNone(card["note_id"])
        self.assertIn("Anki", pane.banner.text())
        self.assertTrue(pane.add_button.isEnabled())
        client.add_card.assert_called_once_with("hello", "привет", "A greeting to a friend.", "Vocabulary")


if __name__ == "__main__":
    unittest.main()
