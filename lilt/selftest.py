"""Noninteractive package check; no network, hooks, or personal Anki collection."""
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory


def main(report_path):
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    from PySide6 import __version__ as qt_version
    from PySide6.QtWidgets import QApplication
    from . import __version__
    from .anki import AnkiClient
    from .credentials import Credentials
    from .engine import TranslationResult, detect_language
    from .storage import Store
    from .ui import Controller, TranslationPane, STYLE
    from . import theme
    from . import startup
    report = {"ok": False, "app_version": __version__, "qt_version": qt_version}
    try:
        app = QApplication([])
        app.setStyleSheet(STYLE)
        with TemporaryDirectory(prefix="Lilt-check-") as directory:
            store = Store(Path(directory))
            c = Controller(store)
            pane = TranslationPane(c)
            pane.source.setPlainText("hello")
            result = TranslationResult("hello", "привет", "en", "ru", "Package check",
                                       english_word="hello", english_definitions=["A greeting."],
                                       english_pronunciation="/həˈləʊ/", dictionary_checked=True)
            pane.present_result(result)
            assert pane.output.toPlainText() == "привет" and pane.add_button.isEnabled()
            store.cache_put("hello", "auto", "google", result.to_dict())
            assert c.lookup("hello", "auto").from_cache
            assert c.lookup("hello", "auto").english_definitions == ["A greeting."]
            store.save_card("hello", "привет", "sample context", "Lilt")
            assert store.find_card("hello", "привет", "Lilt")["note_id"] is None
            store.save_card("hello", "привет", "sample context", "Lilt", card_version=2,
                            definition="A greeting.", pronunciation="/həˈləʊ/", definition_source="Dictionary fixture")
            rich_card = store.find_card("hello", "привет", "Lilt", card_version=2)
            assert rich_card["definition"] == "A greeting." and rich_card["pronunciation"] == "/həˈləʊ/"
            assert store.stats()["cards"] == 2
            assert AnkiClient.VOCABULARY_MODEL_NAME == "Lilt Vocabulary v2"
            assert detect_language("привет") == "ru"
            assert AnkiClient().endpoint == "http://127.0.0.1:8765"
            assert (Path(theme.__file__).parent / "assets" / "check.svg").is_file()
            if sys.platform == "win32":
                c.credentials.write({"anki": "package-check"})
                assert c.credentials.read() == {"anki": "package-check"}
                # Validate the packaged entry point without reading/writing Run.
                assert startup.command().endswith(" --startup")
            report.update(ok=True, checks=["Qt widgets", "enriched translation cache", "legacy and vocabulary cards",
                                          "language detection", "versioned Anki client", "credential protection",
                                          "Windows startup command"])
            pane.deleteLater()
            app.processEvents()
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    Path(report_path).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["ok"] else 1
