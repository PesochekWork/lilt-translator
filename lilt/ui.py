from dataclasses import asdict
from datetime import datetime
import sys

from PySide6.QtCore import Qt, QObject, Signal, Slot, QRunnable, QThreadPool, QTimer, QSize
from PySide6.QtGui import QColor, QFont, QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QPushButton, QScrollArea,
    QSizePolicy, QStackedWidget, QSystemTrayIcon, QTextEdit, QVBoxLayout, QWidget,
)

from .anki import AnkiClient, AnkiError
from . import startup
from .cards import enrich_translation, prepare_vocabulary_card
from .credentials import Credentials
from .engine import TranslationResult, translate
from .hotkeys import CaptureListener
from .popup import CursorPopup
from .storage import Store
from .theme import STYLE


def label(text, name=None):
    w = QLabel(text)
    w.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        w.setObjectName(name)
    return w


def button(text, callback, primary=False, quiet=False):
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setObjectName("primary" if primary else "quiet" if quiet else "button")
    b.clicked.connect(callback)
    return b


def panel():
    w = QFrame()
    w.setObjectName("panel")
    layout = QVBoxLayout(w)
    layout.setContentsMargins(18, 15, 18, 15)
    layout.setSpacing(10)
    return w, layout


def icon():
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#ff9a21"))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawRoundedRect(2, 2, 60, 60, 3, 3)
    p.setPen(QColor("#151515"))
    p.setFont(QFont("Segoe UI", 31, QFont.Weight.DemiBold))
    p.drawText(pix.rect().adjusted(0, -3, 0, 0), Qt.AlignmentFlag.AlignCenter, "l")
    p.end()
    return QIcon(pix)


class JobSignals(QObject):
    success = Signal(object)
    failure = Signal(str)


class Job(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = JobSignals()

    def run(self):
        try:
            value = self.fn()
        except Exception as exc:
            self.signals.failure.emit(str(exc))
        else:
            self.signals.success.emit(value)


class JobReceiver(QObject):
    """A QObject receiver keeps all completion callbacks on the GUI thread."""
    def __init__(self, controller, job, success, failure):
        super().__init__(controller)
        self.controller, self.job = controller, job
        self.on_success, self.on_failure = success, failure

    @Slot(object)
    def success(self, value):
        self.controller.jobs.discard(self)
        try:
            self.on_success(value)
        finally:
            self.deleteLater()

    @Slot(str)
    def failure(self, message):
        self.controller.jobs.discard(self)
        try:
            self.on_failure(message)
        finally:
            self.deleteLater()


class Controller(QObject):
    library_changed = Signal()
    preferences_changed = Signal()

    def __init__(self, store):
        super().__init__()
        self.store = store
        self.credentials = Credentials(store.data_dir)
        self.secrets = self.credentials.read()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(3)
        self.jobs = set()
        self.inflight_cards = set()

    def run(self, fn, success, failure):
        job = Job(fn)
        receiver = JobReceiver(self, job, success, failure)
        self.jobs.add(receiver)
        job.signals.success.connect(receiver.success, Qt.ConnectionType.QueuedConnection)
        job.signals.failure.connect(receiver.failure, Qt.ConnectionType.QueuedConnection)
        self.pool.start(job)

    def anki(self):
        return AnkiClient(api_key=self.secrets.get("anki", ""))

    def lookup(self, text, language):
        provider = self.store.get_setting("provider", "google")
        cached = self.store.cache_get(text, language, provider)
        if cached:
            cached["from_cache"] = True
            return TranslationResult.from_dict(cached)
        result = enrich_translation(translate(text, language, provider, self.secrets.get("deepl", "")))
        self.store.cache_put(text, language, provider, asdict(result))
        return result


class TranslationPane(QWidget):
    def __init__(self, controller, compact=False):
        super().__init__()
        self.c = controller
        self.compact = compact
        self.result = None
        self.revision = 0
        self.adding = False
        self.previewing = False
        self.pending_translation = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(13 if compact else 9)
        if compact:
            root.addWidget(label("QUICK TRANSLATE", "eyebrow"))
        self.banner = label("")
        self.banner.setObjectName("banner")
        self.banner.setWordWrap(True)
        self.banner.hide()
        root.addWidget(self.banner)
        editors = QVBoxLayout() if compact else QHBoxLayout()
        editors.setSpacing(12)
        source_box, source_layout = panel()
        source_top = QHBoxLayout()
        self.language = QComboBox()
        self.language.addItem("Detect language", "auto")
        self.language.addItem("English", "en")
        self.language.addItem("Русский", "ru")
        self.language.setMinimumWidth(155)
        source_top.addWidget(self.language)
        source_top.addStretch()
        source_top.addWidget(button("Paste", self.paste, quiet=True))
        source_layout.addLayout(source_top)
        self.source = QTextEdit()
        self.source.setObjectName("source")
        self.source.setAcceptRichText(False)
        self.source.setPlaceholderText("Enter text…")
        self.source.setMinimumHeight(90 if compact else 64)
        source_layout.addWidget(self.source, 1)
        source_bottom = QHBoxLayout()
        self.count = label("0 / 5,000", "muted")
        source_bottom.addWidget(self.count)
        source_bottom.addStretch()
        source_bottom.addWidget(button("Clear", self.clear, quiet=True))
        source_layout.addLayout(source_bottom)
        editors.addWidget(source_box, 1)
        target_box, target_layout = panel()
        target_top = QHBoxLayout()
        self.target = label("Translation", "eyebrow")
        target_top.addWidget(self.target)
        target_top.addStretch()
        self.copy_button = button("Copy", self.copy, quiet=True)
        self.copy_button.setEnabled(False)
        target_top.addWidget(self.copy_button)
        target_layout.addLayout(target_top)
        self.output = QTextEdit()
        self.output.setObjectName("translation")
        self.output.setAcceptRichText(False)
        self.output.setPlaceholderText("Translation")
        self.output.setMinimumHeight(85 if compact else 64)
        target_layout.addWidget(self.output, 1)
        target_bottom = QHBoxLayout()
        target_bottom.addStretch()
        self.swap = button("Swap", self.swap_languages, quiet=True)
        self.swap.setEnabled(False)
        target_bottom.addWidget(self.swap)
        target_layout.addLayout(target_bottom)
        editors.addWidget(target_box, 1)
        root.addLayout(editors, 1)
        translate_row = QHBoxLayout()
        self.state = label("Ctrl+Enter to translate", "muted")
        self.state.setWordWrap(True)
        translate_row.addWidget(self.state, 1)
        self.translate_button = button("Translate", self.start_translation, primary=True)
        self.translate_button.setToolTip("Ctrl+Enter")
        translate_row.addWidget(self.translate_button)
        root.addLayout(translate_row)
        self.meanings = QTextEdit()
        self.meanings.setObjectName("details")
        self.meanings.setReadOnly(True)
        self.meanings.setAcceptRichText(False)
        self.meanings.setMinimumHeight(90)
        self.meanings.hide()
        root.addWidget(self.meanings, 1)
        anki_box, anki_layout = panel()
        anki_top = QHBoxLayout()
        anki_top.addWidget(label("ANKI CARD", "eyebrow"))
        anki_top.addStretch()
        anki_layout.addLayout(anki_top)
        self.context = QLineEdit()
        self.context.setPlaceholderText("Context or note (optional)")
        self.context.setClearButtonEnabled(True)
        anki_layout.addWidget(self.context)
        anki_row = QHBoxLayout()
        self.deck = QComboBox()
        self.deck.setEditable(True)
        self.deck.addItem(self.c.store.get_setting("deck", "Lilt"))
        self.deck.setToolTip("Anki deck. Type a new name to create it when adding a card.")
        self.deck.setMinimumWidth(125)
        anki_row.addWidget(self.deck, 1)
        self.preview = button("Preview", self.preview_card)
        anki_row.addWidget(self.preview)
        self.add_button = button("+ Add to Anki", self.add_card, primary=True)
        self.add_button.setToolTip("Ctrl+Shift+A")
        anki_row.addWidget(self.add_button)
        anki_layout.addLayout(anki_row)
        root.addWidget(anki_box)
        foot = label("Ctrl+Enter  translate      Ctrl+Shift+A  add card      Esc  hide" if compact else
                     "Ctrl+Enter  translate      Ctrl+Shift+A  add card", "muted")
        foot.setWordWrap(True)
        root.addWidget(foot)
        self.source.textChanged.connect(self.source_changed)
        self.language.currentIndexChanged.connect(self.source_changed)
        self.output.textChanged.connect(self.update_actions)
        self.c.preferences_changed.connect(self.refresh_provider)
        QShortcut(QKeySequence("Ctrl+Return"), self, self.start_translation)
        QShortcut(QKeySequence("Ctrl+Enter"), self, self.start_translation)
        QShortcut(QKeySequence("Ctrl+Shift+A"), self, self.add_card)
        self.refresh_provider()
        self.update_actions()

    def heightForWidth(self, width):
        # Editors can shrink and scroll instead of forcing their preferred height.
        return self.layout().minimumHeightForWidth(width)

    def refresh_provider(self):
        self.revision += 1
        self.result = None
        self.update_actions()

    def notify(self, message, error=False):
        self.banner.setProperty("error", error)
        self.banner.style().unpolish(self.banner)
        self.banner.style().polish(self.banner)
        self.banner.setText(message)
        self.banner.show()

    def source_changed(self):
        self.revision += 1
        n = len(self.source.toPlainText())
        self.count.setText(f"{n:,} / 5,000")
        self.result = None
        self.meanings.hide()
        self.state.setText("Ready" if n else "Ctrl+Enter to translate")
        self.translate_button.setText("Translate")
        self.banner.hide()
        self.update_actions()

    def update_actions(self):
        source = self.source.toPlainText().strip()
        target = self.output.toPlainText().strip()
        valid = bool(self.result and source and target)
        self.translate_button.setEnabled(bool(source) and len(source) <= 5000)
        self.add_button.setEnabled(valid and not self.adding and not self.previewing)
        self.preview.setEnabled(valid and not self.previewing and not self.adding)
        self.copy_button.setEnabled(bool(target))
        self.swap.setEnabled(valid)

    def paste(self):
        self.source.setPlainText(QApplication.clipboard().text())
        self.source.setFocus()

    def clear(self):
        self.source.clear()
        self.output.clear()
        self.context.clear()
        self.target.setText("Translation")
        self.source.setFocus()

    def copy(self):
        QApplication.clipboard().setText(self.output.toPlainText())
        self.notify("Translation copied.")

    def capture(self, text):
        self.language.setCurrentIndex(0)
        self.context.clear()
        self.output.clear()
        self.source.setPlainText(text)
        self.start_translation()

    def start_translation(self):
        text = self.source.toPlainText().strip()
        if not text:
            return
        if len(text) > 5000:
            self.notify("Choose up to 5,000 characters at a time.", True)
            return
        language = self.language.currentData()
        request_key = (text, language, self.revision)
        if self.pending_translation == request_key:
            return
        if len(self.c.jobs) >= 3:
            self.notify("Finishing earlier requests. Try again in a moment.")
            return
        self.revision += 1
        revision = self.revision
        self.pending_translation = (text, language, revision)
        self.result = None
        self.output.clear()
        self.meanings.hide()
        self.banner.hide()
        self.state.setText("Translating…")
        self.translate_button.setText("Translating…")
        self.update_actions()
        self.translate_button.setEnabled(False)
        def success(result):
            if revision != self.revision:
                return
            self.pending_translation = None
            self.present_result(result)
            self.c.library_changed.emit()
        def failure(message):
            if revision != self.revision:
                return
            self.pending_translation = None
            self.notify(message, True)
            self.state.setText("You can retry when the connection is back.")
            self.translate_button.setText("Try again")
            self.update_actions()
        self.c.run(lambda: self.c.lookup(text, language), success, failure)

    def present_result(self, result):
        self.result = result
        self.output.setPlainText(result.translated_text)
        self.state.setText("From your local history" if result.from_cache else "Translated")
        self.translate_button.setText("Translate")
        lines = []
        if result.english_pronunciation:
            lines.append(result.english_pronunciation)
        lines.extend(result.english_definitions)
        for meaning in result.definitions:
            terms = "; ".join(meaning.get("terms", []))
            if terms:
                lines.append(f"{meaning.get('part_of_speech', 'Also')}  ·  {terms}")
        self.meanings.setPlainText("\n".join(lines))
        self.meanings.setVisible(bool(lines))
        self.update_actions()

    def swap_languages(self):
        if not self.result:
            return
        new_source = self.result.target_lang
        text = self.output.toPlainText()
        self.language.setCurrentIndex(self.language.findData(new_source))
        self.source.setPlainText(text)
        self.start_translation()

    def preview_card(self):
        if not self.result or self.previewing or self.adding:
            return
        result = self.result
        source = self.source.toPlainText()
        translated = self.output.toPlainText()
        context = self.context.text()
        deck = self.deck.currentText()
        revision = self.revision
        self.previewing = True
        self.preview.setText("Loading…")
        self.update_actions()
        def success(card):
            self.previewing = False
            self.preview.setText("Preview")
            self.update_actions()
            # Never show a preview for text that changed during the lookup.
            if (revision == self.revision and translated == self.output.toPlainText()
                    and context == self.context.text() and deck == self.deck.currentText()):
                self._show_card_preview(card)
        def failure(message):
            self.previewing = False
            self.preview.setText("Preview")
            self.update_actions()
            self.notify(message, True)
        self.c.run(lambda: prepare_vocabulary_card(result, source, translated, context, deck), success, failure)

    def _show_card_preview(self, card):
        d = QDialog(self)
        d.setWindowTitle("Card preview · Lilt")
        d.resize(560, 480)
        layout = QVBoxLayout(d)
        layout.setContentsMargins(24, 24, 24, 24)
        front_heading = label("FRONT", "eyebrow")
        front_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(front_heading)
        front = label(card.english)
        front.setWordWrap(True)
        front.setStyleSheet("font-size: 24px;")
        front.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(front)
        layout.addSpacing(15)
        back_heading = label("BACK", "eyebrow")
        back_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(back_heading)
        back = QTextEdit()
        back.setObjectName("details")
        back.setReadOnly(True)
        back.setAcceptRichText(False)
        parts = [card.russian, card.pronunciation or "Pronunciation unavailable.",
                 card.definition or "English definition unavailable; the translation can still be saved."]
        if card.context:
            parts.append(card.context)
        back.setPlainText("\n\n".join(parts))
        text_option = back.document().defaultTextOption()
        text_option.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        back.document().setDefaultTextOption(text_option)
        layout.addWidget(back)
        layout.addWidget(button("Done", d.accept, primary=True))
        d.exec()

    def add_card(self):
        if not self.result or self.adding or self.previewing or not self.output.toPlainText().strip():
            return
        result = self.result
        source = self.source.toPlainText().strip()
        translated = self.output.toPlainText().strip()
        front, back = (source, translated) if result.source_lang == "en" else (translated, source)
        context = self.context.text().strip()
        deck = self.deck.currentText().strip() or "Lilt"
        existing = self.c.store.find_card(front, back, deck, card_version=2)
        if existing and existing.get("note_id"):
            self.notify(f"Already added to Anki · {deck}")
            return
        card_key = (front, back, deck, 2)
        if card_key in self.c.inflight_cards:
            self.notify("This card is already being sent to Anki.")
            return
        self.c.inflight_cards.add(card_key)
        self.c.store.set_setting("deck", deck)
        self.adding = True
        self.add_button.setText("Adding…")
        self.update_actions()
        def work():
            card = self.c.store.find_card(front, back, deck, card_version=2)
            if card is None:
                content = prepare_vocabulary_card(result, source, translated, context, deck)
                # Save the complete snapshot before contacting Anki, even offline.
                self.c.store.save_card(content.english, content.russian, content.context, content.deck,
                                       card_version=2, definition=content.definition,
                                       pronunciation=content.pronunciation,
                                       definition_source=content.definition_source)
                card = self.c.store.find_card(front, back, deck, card_version=2)
            note_id = self.c.anki().add_vocabulary_card(
                card["front"], card["back"], definition=card["definition"],
                pronunciation=card["pronunciation"], context=card["context"],
                deck=card["deck"], definition_source=card["definition_source"])
            if card:
                self.c.store.mark_card_sent(card["id"], note_id, identity=card_key[:3], card_version=2)
            return note_id
        def success(_):
            self.c.inflight_cards.discard(card_key)
            self.adding = False
            self.add_button.setText("+ Add to Anki")
            self.notify(f"Added to Anki · {deck}")
            self.update_actions()
            self.c.library_changed.emit()
        def failure(message):
            self.c.inflight_cards.discard(card_key)
            self.adding = False
            self.add_button.setText("+ Add to Anki")
            self.notify(f"Kept in Cards for retry. {message}", True)
            self.update_actions()
            self.c.library_changed.emit()
        self.c.run(work, success, failure)


class MainWindow(QMainWindow):
    def __init__(self, controller, listen=True):
        super().__init__()
        self.c = controller
        self.quitting = False
        self.popup = None
        self.listener = None
        self.setWindowTitle("Lilt")
        self.setWindowIcon(icon())
        self.resize(960, 600)
        self.setMinimumSize(900, 540)
        body = QWidget()
        body.setObjectName("body")
        self.setCentralWidget(body)
        outer = QHBoxLayout(body)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(178)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(17, 26, 17, 21)
        brand_row = QHBoxLayout()
        mark = QLabel()
        mark.setPixmap(icon().pixmap(30, 30))
        brand_row.addWidget(mark)
        brand_row.addWidget(label("lilt", "brand"))
        brand_row.addStretch()
        side.addLayout(brand_row)
        side.addSpacing(24)
        self.nav = []
        for i, name in enumerate(["Translate", "Cards", "History", "Preferences"]):
            b = button(name, lambda checked=False, n=i: self.show_page(n))
            b.setObjectName("nav")
            b.setCheckable(True)
            self.nav.append(b)
            side.addWidget(b)
        side.addStretch()
        outer.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(24, 18, 24, 18)
        content.setSpacing(12)
        title_row = QHBoxLayout()
        self.heading = label("Translator", "heading")
        title_row.addWidget(self.heading)
        title_row.addStretch()
        content.addLayout(title_row)
        self.pages = QStackedWidget()
        self.translator = TranslationPane(controller)
        translator_scroll = QScrollArea()
        translator_scroll.setWidgetResizable(True)
        translator_scroll.setWidget(self.translator)
        self.pages.addWidget(translator_scroll)
        self.cards_page = self.make_library_page(True)
        self.pages.addWidget(self.cards_page)
        self.history_page = self.make_library_page(False)
        self.pages.addWidget(self.history_page)
        self.pages.addWidget(self.make_preferences())
        content.addWidget(self.pages, 1)
        outer.addLayout(content, 1)
        self.c.library_changed.connect(self.refresh_library_if_visible)
        self.tray = None
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray = QSystemTrayIcon(icon(), self)
            self.tray.setToolTip("Lilt")
            menu = QMenu()
            menu.addAction("Open Lilt", self.show_main)
            menu.addAction("Translate clipboard", self.capture_clipboard)
            menu.addSeparator()
            menu.addAction("Quit Lilt", self.quit)
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda reason: self.show_main() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
            self.tray.show()
        if listen:
            self.listener = CaptureListener(self)
            self.listener.captured.connect(self.schedule_capture)
            self.listener.clipboard_requested.connect(self.capture_clipboard)
            self.listener.unavailable.connect(self.capture_unavailable)
            self.listener.warning.connect(self.capture_warning)
            self.listener.start()
            QApplication.instance().aboutToQuit.connect(self.listener.stop)
        self.show_page(0)

    def show_main(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    @Slot(str)
    def capture_unavailable(self, message):
        self.translator.notify(message, True)

    @Slot(str)
    def capture_warning(self, message):
        self.translator.notify(message)

    def schedule_capture(self):
        if self.c.store.get_setting("double_copy", True):
            QTimer.singleShot(140, self.capture_clipboard)

    def capture_clipboard(self):
        text = QApplication.clipboard().text().strip()
        if not text:
            return
        if len(text) > 5000:
            self.show_main()
            self.show_page(0)
            self.translator.notify("Choose up to 5,000 characters at a time.", True)
            return
        if self.popup is None:
            self.popup = CursorPopup(self)
            self.popup.setWindowTitle("Quick translate · Lilt")
            self.popup.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
            self.popup.setWindowIcon(icon())
            self.popup.resize(590, 710)
            self.popup.setMinimumSize(520, 660)
            layout = QVBoxLayout(self.popup)
            layout.setContentsMargins(22, 20, 22, 20)
            self.quick = TranslationPane(self.c, compact=True)
            quick_scroll = QScrollArea()
            quick_scroll.setWidgetResizable(True)
            quick_scroll.setWidget(self.quick)
            layout.addWidget(quick_scroll)
            QShortcut(QKeySequence("Escape"), self.popup, self.popup.hide)
        self.quick.capture(text)
        self.popup.show_near_cursor()
        self.popup.raise_()
        self.popup.activateWindow()

    def make_library_page(self, cards):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        tools = QHBoxLayout()
        search = QLineEdit()
        search.setPlaceholderText("Search your cards…" if cards else "Search translations…")
        tools.addWidget(search, 1)
        if cards:
            tools.addWidget(button("Export for Anki", self.export_cards))
        else:
            tools.addWidget(button("Clear history", self.clear_history))
        layout.addLayout(tools)
        info = label("", "muted")
        layout.addWidget(info)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        items = QWidget()
        listing = QVBoxLayout(items)
        listing.setContentsMargins(0, 2, 7, 0)
        listing.setSpacing(10)
        listing.addStretch()
        scroll.setWidget(items)
        layout.addWidget(scroll)
        setattr(self, "cards_search" if cards else "history_search", search)
        setattr(self, "cards_info" if cards else "history_info", info)
        setattr(self, "cards_listing" if cards else "history_listing", listing)
        search.textChanged.connect(lambda: self.refresh_library(cards))
        return page

    def refresh_library_if_visible(self):
        if self.pages.currentIndex() in (1, 2):
            self.refresh_library(self.pages.currentIndex() == 1)

    def refresh_library(self, cards):
        listing = self.cards_listing if cards else self.history_listing
        while listing.count():
            item = listing.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        query = (self.cards_search if cards else self.history_search).text().casefold()
        data = self.c.store.cards(limit=10000) if cards else self.c.store.history(limit=500)
        data = [r for r in data if query in " ".join(str(v) for v in r.values()).casefold()]
        info = self.cards_info if cards else self.history_info
        info.setText(f"{len(data)} cards · {sum(1 for r in data if not r.get('note_id'))} waiting for Anki" if cards else f"{len(data)} translations · stored on this computer")
        if not data:
            empty, box = panel()
            box.addWidget(label("No cards" if cards else "No translations", "heading"))
            hint = label("Add a card from Translator." if cards else "Your translations will appear here.", "muted")
            hint.setWordWrap(True)
            box.addWidget(hint)
            listing.addWidget(empty)
        for row in data[:200]:
            item, box = panel()
            front = label(row["front"] if cards else row["source_text"])
            front.setWordWrap(True)
            front.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            front.setStyleSheet("font-size: 17px; font-weight: 600;")
            box.addWidget(front)
            back = label(row["back"] if cards else row["translated_text"])
            back.setWordWrap(True)
            back.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            back.setStyleSheet("color: #ffad4a;")
            box.addWidget(back)
            if cards and row.get("card_version", 1) == 2:
                for text in (row.get("pronunciation"), row.get("definition")):
                    if text:
                        details = label(text)
                        details.setWordWrap(True)
                        details.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                        details.setStyleSheet("font-size: 18px;")
                        box.addWidget(details)
            if cards and row.get("context"):
                context = label(row["context"], "muted")
                context.setWordWrap(True)
                box.addWidget(context)
            footer = QHBoxLayout()
            if cards:
                footer.addWidget(label(f"{row['deck']} · " + ("In Anki" if row.get("note_id") else "Waiting for Anki"), "muted"))
            footer.addStretch()
            if cards:
                if not row.get("note_id"):
                    footer.addWidget(button("Send to Anki", lambda checked=False, r=row: self.retry_card(r)))
                footer.addWidget(button("Remove", lambda checked=False, r=row: self.remove_card(r), quiet=True))
            else:
                footer.addWidget(button("Use again", lambda checked=False, r=row: self.use_history(r)))
            box.addLayout(footer)
            listing.addWidget(item)
        listing.addStretch()

    def use_history(self, row):
        self.show_page(0)
        self.translator.language.setCurrentIndex(self.translator.language.findData(row["source_lang"]))
        self.translator.source.setPlainText(row["source_text"])
        self.translator.context.clear()
        cached = self.c.store.cache_get(row["source_text"], row.get("request_lang", row["source_lang"]),
                                        row.get("provider_key", "google"))
        if cached:
            cached["from_cache"] = True
            result = TranslationResult.from_dict(cached)
        else:
            result = TranslationResult(
                source_text=row["source_text"], translated_text=row["translated_text"],
                source_lang=row["source_lang"], target_lang=row["target_lang"],
                provider=row["provider"], from_cache=True)
        self.translator.present_result(result)

    def retry_card(self, row):
        version = row.get("card_version", 1)
        card_key = (row["front"], row["back"], row["deck"], version)
        if card_key in self.c.inflight_cards:
            return
        self.c.inflight_cards.add(card_key)
        def work():
            if version == 2:
                note_id = self.c.anki().add_vocabulary_card(
                    row["front"], row["back"], definition=row.get("definition", ""),
                    pronunciation=row.get("pronunciation", ""), context=row.get("context", ""),
                    deck=row["deck"], definition_source=row.get("definition_source", ""))
            else:
                note_id = self.c.anki().add_card(row["front"], row["back"], row.get("context", ""), row["deck"])
            self.c.store.mark_card_sent(row["id"], note_id, identity=card_key[:3], card_version=version)
        self.cards_info.setText("Sending card to Anki…")
        def success(_):
            self.c.inflight_cards.discard(card_key)
            self.refresh_library(True)
        def failure(message):
            self.c.inflight_cards.discard(card_key)
            self.cards_info.setText(message)
        self.c.run(work, success, failure)

    def remove_card(self, row):
        card_key = (row["front"], row["back"], row["deck"], row.get("card_version", 1))
        if card_key in self.c.inflight_cards:
            self.cards_info.setText("This card is being sent. Wait until the request finishes.")
            return
        answer = QMessageBox.question(self, "Remove local card?", "Remove this card from Lilt? A card already in Anki will stay in Anki.")
        if answer == QMessageBox.StandardButton.Yes:
            self.c.store.delete_card(row["id"])
            self.refresh_library(True)

    def export_cards(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export cards for Anki", "Lilt-cards.tsv", "Anki text import (*.tsv)")
        if path:
            try:
                n = self.c.store.export_cards(path)
                self.cards_info.setText(f"Exported {n} cards. Review the note types and field mapping in Anki's import preview.")
            except OSError as exc:
                self.cards_info.setText(f"Could not export: {exc}")

    def clear_history(self):
        if QMessageBox.question(self, "Clear local history?", "Remove translation history and cached translations? Your cards will stay.") == QMessageBox.StandardButton.Yes:
            self.c.store.clear_history()
            self.refresh_library(False)

    def make_preferences(self):
        page = QWidget()
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)
        service, box = panel()
        box.addWidget(label("TRANSLATION", "eyebrow"))
        self.provider = QComboBox()
        self.provider.addItem("Google web · no account", "google")
        self.provider.addItem("DeepL API · your API key", "deepl")
        self.provider.setCurrentIndex(max(0, self.provider.findData(self.c.store.get_setting("provider", "google"))))
        box.addWidget(self.provider)
        notice = label("Google: unofficial, no key required. DeepL: official API, your key required. Translation sends the selected text to that provider.", "muted")
        notice.setWordWrap(True)
        box.addWidget(notice)
        self.deepl_key = QLineEdit(self.c.secrets.get("deepl", ""))
        self.deepl_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.deepl_key.setPlaceholderText("DeepL API key (optional)")
        box.addWidget(self.deepl_key)
        root.addWidget(service)
        anki, box = panel()
        box.addWidget(label("ANKI CONNECTION", "eyebrow"))
        setup = label("Anki → Tools → Add-ons → Get Add-ons: 2055492159. Restart Anki. Connection: 127.0.0.1:8765.", "muted")
        setup.setWordWrap(True)
        box.addWidget(setup)
        self.anki_key = QLineEdit(self.c.secrets.get("anki", ""))
        self.anki_key.setEchoMode(QLineEdit.EchoMode.Password)
        self.anki_key.setPlaceholderText("AnkiConnect API key, only if you configured one")
        box.addWidget(self.anki_key)
        row = QHBoxLayout()
        self.anki_status = label("No connection test yet", "muted")
        self.anki_status.setWordWrap(True)
        row.addWidget(self.anki_status, 1)
        row.addWidget(button("Test connection", self.check_anki))
        box.addLayout(row)
        root.addWidget(anki)
        behavior, box = panel()
        box.addWidget(label("BEHAVIOR", "eyebrow"))
        self.start_with_windows = QCheckBox("Start Lilt with Windows")
        self.start_with_windows.setToolTip("Start quietly in the system tray after you sign in.")
        startup_error = ""
        try:
            self.start_with_windows.setChecked(startup.is_enabled())
        except startup.StartupError as exc:
            startup_error = str(exc)
            self.start_with_windows.setEnabled(False)
            self.start_with_windows.setToolTip(startup_error)
        box.addWidget(self.start_with_windows)
        self.double_copy = QCheckBox("Open a quick popup when I press Ctrl+C twice")
        self.double_copy.setChecked(self.c.store.get_setting("double_copy", True))
        box.addWidget(self.double_copy)
        self.to_tray = QCheckBox("Keep Lilt in the system tray when I close its window")
        self.to_tray.setChecked(self.c.store.get_setting("close_to_tray", True))
        box.addWidget(self.to_tray)
        hint = label("Ctrl+Alt+Space: translate clipboard. Tray menu → Quit Lilt: exit.", "muted")
        hint.setWordWrap(True)
        box.addWidget(hint)
        root.addWidget(behavior)
        self.settings_status = label(startup_error or "Optional keys are encrypted for your Windows account.", "muted")
        self.settings_status.setWordWrap(True)
        root.addWidget(self.settings_status)
        root.addWidget(button("Save preferences", self.save_preferences, primary=True))
        root.addStretch()
        # Keep this taller page from imposing its height on the translator.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(page)
        return scroll

    def save_preferences(self):
        provider = self.provider.currentData()
        if provider == "deepl" and not self.deepl_key.text().strip():
            self.settings_status.setText("Enter a DeepL API key or select Google web.")
            return
        secrets = {"deepl": self.deepl_key.text().strip(), "anki": self.anki_key.text().strip()}
        try:
            self.c.credentials.write(secrets)
        except (OSError, RuntimeError) as exc:
            self.settings_status.setText(str(exc))
            return
        self.c.secrets = secrets
        self.c.store.set_setting("provider", provider)
        self.c.store.set_setting("double_copy", self.double_copy.isChecked())
        self.c.store.set_setting("close_to_tray", self.to_tray.isChecked())
        self.c.preferences_changed.emit()
        if self.start_with_windows.isEnabled():
            try:
                requested = self.start_with_windows.isChecked()
                if requested != startup.is_enabled():
                    startup.set_enabled(requested)
            except startup.StartupError as exc:
                self.settings_status.setText(f"Other preferences saved. {exc}")
                try:
                    self.start_with_windows.setChecked(startup.is_enabled())
                except startup.StartupError:
                    pass
                return
        self.settings_status.setText("Saved. Keys are encrypted for your Windows account.")

    def check_anki(self):
        self.anki_status.setText("Checking Anki…")
        client = AnkiClient(api_key=self.anki_key.text().strip())
        def success(decks):
            self.anki_status.setText(f"Connected · {len(decks)} decks available")
            panes = [self.translator] + ([self.quick] if self.popup else [])
            for pane in panes:
                selected = pane.deck.currentText()
                pane.deck.clear()
                pane.deck.addItems(decks)
                pane.deck.setCurrentText(selected)
        self.c.run(client.check, success, lambda msg: self.anki_status.setText(msg))

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        for i, nav in enumerate(self.nav):
            nav.setChecked(i == index)
        self.heading.setText(["Translator", "Cards", "History", "Preferences"][index])
        if index in (1, 2):
            self.refresh_library(index == 1)

    def closeEvent(self, event):
        if not self.quitting and self.tray and self.c.store.get_setting("close_to_tray", True):
            event.ignore()
            self.hide()
            if self.popup:
                self.popup.hide()
            if not self.c.store.get_setting("tray_notice_seen", False):
                self.tray.showMessage("Lilt is still here", "Use the tray menu to reopen or quit.")
                self.c.store.set_setting("tray_notice_seen", True)
        else:
            self.quit()
            event.accept()

    def quit(self):
        self.quitting = True
        if self.tray:
            self.tray.hide()
        if self.popup:
            self.popup.hide()
        QApplication.instance().quit()
