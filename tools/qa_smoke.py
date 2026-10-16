"""Render the real Qt widgets in isolation; never use a personal collection."""
import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFontDatabase
from lilt.engine import translate
from lilt.storage import Store
from lilt.ui import Controller, MainWindow, STYLE


def main():
    app = QApplication([])
    # The offscreen Windows platform does not enumerate system fonts itself.
    for font in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        QFontDatabase.addApplicationFont(str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font))
    app.setStyle("Fusion")
    app.setStyleSheet(STYLE)
    output = Path(__file__).resolve().parents[1] / "qa-output"
    output.mkdir(exist_ok=True)
    result = translate("resilient")
    with TemporaryDirectory() as directory:
        store = Store(Path(directory))
        c = Controller(store)
        window = MainWindow(c, listen=False)
        window.show()
        window.translator.source.setPlainText(result.source_text)
        window.translator.present_result(result)
        window.translator.context.setText("She remained resilient in the face of change.")
        app.processEvents()
        window.grab().save(str(output / "translator.png"))
        store.save_card("resilient", result.translated_text, "She remained resilient in the face of change.", "English")
        window.show_page(1)
        app.processEvents()
        window.grab().save(str(output / "cards.png"))
        window.show_page(3)
        app.processEvents()
        window.grab().save(str(output / "preferences.png"))
        # Build popup without another network call.
        c.lookup = lambda text, language: result
        QApplication.clipboard().setText("resilient")
        window.capture_clipboard()
        while c.jobs:
            app.processEvents()
        app.processEvents()
        window.quick.context.setText("She remained resilient in the face of change.")
        app.processEvents()
        window.popup.grab().save(str(output / "popup.png"))
        print({"main_size": [window.width(), window.height()], "popup_size": [window.popup.width(), window.popup.height()], "translation": result.translated_text, "images": str(output)})
        window.quitting = True
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
