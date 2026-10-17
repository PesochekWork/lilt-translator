import csv
import io
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from lilt.storage import Store


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = Store(self.root)

    def test_settings_are_durable_json_values(self):
        self.assertEqual(self.store.get_setting("missing", "fallback"), "fallback")
        self.store.set_setting("ui", {"theme": "light", "decks": ["English", "Русский"]})
        self.store.set_setting("enabled", True)
        restored = Store(self.root)
        self.assertEqual(restored.get_setting("ui"), {"theme": "light", "decks": ["English", "Русский"]})
        self.assertIs(restored.get_setting("enabled"), True)
        self.store.set_setting("enabled", False)
        self.assertIs(restored.get_setting("enabled"), False)

    def test_plaintext_credential_settings_are_rejected(self):
        for key in ("api_key", "anki_api_key", "openai-api-key", "password"):
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.store.set_setting(key, "do-not-store-me")
        self.store.set_setting("protected_api_key", "dpapi-ciphertext")
        self.assertEqual(self.store.get_setting("protected_api_key"), "dpapi-ciphertext")

    def test_default_directory_uses_local_appdata(self):
        with patch.dict("os.environ", {"LOCALAPPDATA": str(self.root)}):
            store = Store()
        self.assertEqual(store.data_dir, self.root / "Lilt")

    def test_cache_separates_language_and_provider_and_upserts_history(self):
        result = {"translated_text": "привет", "source_lang": "en", "target_lang": "ru", "provider": "Quality"}
        self.store.cache_put("  hello  ", "auto", "quality:model-a", result)
        self.assertEqual(self.store.cache_get("hello", "auto", "quality:model-a"), result)
        self.assertIsNone(self.store.cache_get("hello", "en", "quality:model-a"))
        self.assertIsNone(self.store.cache_get("hello", "auto", "quality:model-b"))
        first_id = self.store.history()[0]["id"]
        result["translated_text"] = "здравствуй"
        self.store.cache_put("hello", "AUTO", "quality:model-a", result)
        history = self.store.history()
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["id"], first_id)
        self.assertEqual(history[0]["source_text"], "hello")
        self.assertEqual(history[0]["translated_text"], "здравствуй")
        self.assertEqual(history[0]["source_lang"], "en")
        self.assertEqual(history[0]["provider"], "Quality")
        self.assertEqual(history[0]["request_lang"], "auto")
        self.assertEqual(history[0]["provider_key"], "quality:model-a")

    def test_history_is_bounded_and_recent_first(self):
        with patch("lilt.storage.MAX_HISTORY", 3), patch("lilt.storage.MAX_CACHE", 4):
            for number in range(5):
                self.store.cache_put(str(number), "en", "test", {"translated_text": f"tr-{number}"})
        self.assertEqual([item["source_text"] for item in self.store.history()], ["4", "3", "2"])
        self.assertIsNone(self.store.cache_get("0", "en", "test"))
        self.assertEqual(self.store.stats(), {"history": 3, "cards": 0})
        self.assertEqual(self.store.history(0), [])

    def test_card_identity_pending_queue_and_sent_id_persistence(self):
        self.assertTrue(self.store.save_card("hello", "привет", "I said hello.", "English"))
        first = self.store.find_card(" hello ", "привет", "English")
        self.assertIsNone(first["note_id"])
        self.assertFalse(self.store.save_card("hello", "привет", "changed", "English"))
        self.assertEqual(self.store.find_card("hello", "привет", "English")["context"], "I said hello.")
        self.store.mark_card_sent(first["id"], 123456)
        self.assertFalse(self.store.save_card("hello", "привет", deck="English"))
        self.assertEqual(Store(self.root).cards()[0]["note_id"], 123456)
        self.assertTrue(self.store.save_card("hello", "привет", deck="Russian"))
        self.assertEqual(self.store.stats()["cards"], 2)
        self.store.delete_card(first["id"])
        self.assertIsNone(self.store.find_card("hello", "привет", "English"))

    def test_duplicate_can_record_success_without_downgrading_sent_id(self):
        self.store.save_card("one", "один", deck="English")
        self.assertFalse(self.store.save_card("one", "один", deck="English", note_id=9))
        self.assertFalse(self.store.save_card("one", "один", deck="English", note_id=10))
        self.assertEqual(self.store.cards()[0]["note_id"], 9)

    def test_legacy_database_migrates_without_changing_existing_cards(self):
        legacy_root = self.root / "legacy"
        legacy_root.mkdir()
        path = legacy_root / "lilt.sqlite3"
        original = (41, "hello", "привет", "  original\ncontext  ", "English", 123456, "2025-03-01T02:03:04+00:00")
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(
                "CREATE TABLE cards (id INTEGER PRIMARY KEY, front TEXT NOT NULL, back TEXT NOT NULL, "
                "context TEXT NOT NULL DEFAULT '', deck TEXT NOT NULL, note_id INTEGER, created_at TEXT NOT NULL, "
                "UNIQUE (front, back, deck))"
            )
            conn.execute("INSERT INTO cards VALUES (?, ?, ?, ?, ?, ?, ?)", original)
        migrated = Store(legacy_root)
        row = migrated.find_card("hello", "привет", "English")
        self.assertEqual(tuple(row[key] for key in ("id", "front", "back", "context", "deck", "note_id", "created_at")), original)
        self.assertEqual([row[key] for key in ("card_version", "definition", "pronunciation", "definition_source")], [1, "", "", ""])
        self.assertTrue(migrated.save_card("hello", "привет", deck="English", card_version=2,
                                           definition="A greeting.", pronunciation="həˈləʊ", definition_source="Dictionary"))
        reopened = Store(legacy_root)
        self.assertEqual(reopened.find_card("hello", "привет", "English"), row)
        self.assertEqual(reopened.find_card("hello", "привет", "English", card_version=2)["definition"], "A greeting.")
        self.assertEqual(reopened.stats()["cards"], 2)

    def test_failed_migration_rolls_back_original_table_and_data(self):
        legacy_root = self.root / "rollback"
        legacy_root.mkdir()
        path = legacy_root / "lilt.sqlite3"
        with closing(sqlite3.connect(path)) as conn, conn:
            conn.execute(
                "CREATE TABLE cards (id INTEGER PRIMARY KEY, front TEXT NOT NULL, back TEXT NOT NULL, "
                "context TEXT NOT NULL DEFAULT '', deck TEXT NOT NULL, note_id INTEGER, created_at TEXT NOT NULL, "
                "UNIQUE (front, back, deck))"
            )
            conn.execute("INSERT INTO cards VALUES (7, 'word', 'слово', 'example', 'Lilt', 99, 'original-time')")
        connect = sqlite3.connect

        class FailedMigrationConnection(sqlite3.Connection):
            def execute(self, sql, *args, **kwargs):
                if sql == "ALTER TABLE cards_v2_migration RENAME TO cards":
                    raise sqlite3.OperationalError("simulated migration interruption")
                return super().execute(sql, *args, **kwargs)

        def failing_connect(*args, **kwargs):
            return connect(*args, **kwargs, factory=FailedMigrationConnection)

        with patch("lilt.storage.sqlite3.connect", side_effect=failing_connect):
            with self.assertRaisesRegex(sqlite3.OperationalError, "simulated"):
                Store(legacy_root)
        with closing(connect(path)) as conn:
            self.assertEqual(conn.execute("SELECT * FROM cards").fetchall(), [(7, "word", "слово", "example", "Lilt", 99, "original-time")])
            self.assertIsNone(conn.execute("SELECT name FROM sqlite_master WHERE name = 'cards_v2_migration'").fetchone())
        self.assertEqual(Store(legacy_root).cards()[0]["note_id"], 99)

    def test_vocabulary_metadata_is_durable_and_duplicates_preserve_original_values(self):
        self.store.save_card("hello", "привет", "legacy context", "English", 12)
        self.assertTrue(self.store.save_card("hello", "привет", "new context", "English", card_version=2,
                                            definition="A greeting.", pronunciation="həˈləʊ", definition_source="Dictionary / CC BY-SA"))
        original = self.store.find_card("hello", "привет", "English", card_version=2)
        self.assertFalse(self.store.save_card("hello", "привет", "replacement", "English", 17, card_version=2,
                                             definition="Other definition", pronunciation="other", definition_source="Other"))
        rich = Store(self.root).find_card("hello", "привет", "English", card_version=2)
        self.assertEqual(rich, {**original, "note_id": 17})
        self.assertEqual(self.store.find_card("hello", "привет", "English")["note_id"], 12)
        self.assertEqual(self.store.stats()["cards"], 2)

    def test_vocabulary_card_with_no_dictionary_data_can_remain_pending(self):
        self.assertTrue(self.store.save_card("example", "пример", card_version=2))
        row = Store(self.root).find_card("example", "пример", "English", card_version=2)
        self.assertIsNone(row["note_id"])
        self.assertEqual([row[key] for key in ("definition", "pronunciation", "definition_source")], ["", "", ""])

    def test_version_guard_does_not_mark_reused_id_with_same_text(self):
        self.store.save_card("word", "слово", deck="Lilt")
        old = self.store.find_card("word", "слово", "Lilt")
        self.store.delete_card(old["id"])
        self.store.save_card("word", "слово", deck="Lilt", card_version=2)
        new = self.store.find_card("word", "слово", "Lilt", card_version=2)
        self.assertEqual(new["id"], old["id"])
        self.store.mark_card_sent(old["id"], 99, identity=("word", "слово", "Lilt"), card_version=1)
        self.assertIsNone(self.store.find_card("word", "слово", "Lilt", card_version=2)["note_id"])
        self.store.mark_card_sent(new["id"], 100, identity=("word", "слово", "Lilt"), card_version=2)
        self.assertEqual(self.store.find_card("word", "слово", "Lilt", card_version=2)["note_id"], 100)

    def test_sent_confirmation_cannot_mark_a_different_card_after_id_reuse(self):
        self.store.save_card("old front", "old back", deck="English")
        old = self.store.find_card("old front", "old back", "English")
        # The network request has captured old's ID and content. Its row is then
        # removed and SQLite reuses the highest INTEGER PRIMARY KEY for a new card.
        self.store.delete_card(old["id"])
        self.store.save_card("new front", "new back", deck="English")
        new = self.store.find_card("new front", "new back", "English")
        self.assertEqual(new["id"], old["id"])
        self.store.mark_card_sent(old["id"], 123, identity=("old front", "old back", "English"))
        self.assertIsNone(self.store.find_card("new front", "new back", "English")["note_id"])
        self.store.mark_card_sent(new["id"], 456, identity=(" new front ", "new back", "English"))
        self.assertEqual(self.store.find_card("new front", "new back", "English")["note_id"], 456)

    def test_invalid_empty_card_and_note_ids_fail_before_save(self):
        with self.assertRaises(ValueError):
            self.store.save_card(" ", "back")
        for note_id in (0, -1, True, "5"):
            with self.subTest(note_id=note_id), self.assertRaises(ValueError):
                self.store.save_card("front", "back", note_id=note_id)
        for version in (0, -1, True, "2", 3):
            with self.subTest(version=version), self.assertRaises(ValueError):
                self.store.save_card("front", "back", card_version=version)
        self.assertEqual(self.store.stats()["cards"], 0)

    def test_export_round_trips_tabs_quotes_newlines_and_literal_html(self):
        front = 'A "quoted"\tword\nsecond line <tag>'
        back = "Русский перевод\nещё строка"
        context = "Example\tcontext"
        self.store.save_card(front, back, context, "English::Words")
        path = self.root / "cards.tsv"
        self.assertEqual(self.store.export_cards(path), 1)
        text = path.read_text(encoding="utf-8")
        self.assertIn("#separator:Tab\n", text)
        self.assertIn("#html:false\n", text)
        self.assertIn("#tags:lilt\n", text)
        self.assertIn("#deck column:4\n", text)
        self.assertIn("#columns:Front\tBack\tContext\tDeck\n", text)
        payload = text.split("#columns:Front\tBack\tContext\tDeck\n", 1)[1]
        self.assertEqual(list(csv.reader(io.StringIO(payload), delimiter="\t")), [[front, back, context, "English::Words"]])

    def test_mixed_export_preserves_each_note_types_field_order_and_metadata(self):
        self.store.save_card("old front", "старый перевод", "legacy context", "Legacy::Words", 7)
        definition = 'A "quoted"\tdefinition\nwith <literal HTML> & symbols.'
        context = "English\ncontext\tfor example"
        self.store.save_card("example", "пример", context, "Rich::Words", card_version=2,
                             definition=definition, pronunciation="/ɪɡˈzɑːmpəl/", definition_source="Dictionary\nhttps://example.com/?a=1&b=2")
        path = self.root / "mixed.tsv"
        self.assertEqual(self.store.export_cards(path), 2)
        text = path.read_text(encoding="utf-8")
        self.assertIn("#notetype column:1\n#deck column:2\n", text)
        header = "#columns:NoteType\tDeck\tFront / English\tBack / Russian\tContext / Definition\tPronunciation\tContext\tDictionarySource\n"
        rows = list(csv.reader(io.StringIO(text.split(header, 1)[1]), delimiter="\t"))
        self.assertEqual(rows, [
            ["Lilt", "Legacy::Words", "old front", "старый перевод", "legacy context", "", "", ""],
            ["Lilt Vocabulary v2", "Rich::Words", "example", "пример", definition, "/ɪɡˈzɑːmpəl/", context, "Dictionary\nhttps://example.com/?a=1&b=2"],
        ])
        self.assertEqual(self.store.find_card("old front", "старый перевод", "Legacy::Words")["note_id"], 7)

    def test_clear_history_removes_cache_but_keeps_cards_and_settings(self):
        self.store.cache_put("word", "en", "test", {"translated_text": "слово"})
        self.store.save_card("word", "слово")
        self.store.set_setting("theme", "light")
        self.store.clear_history()
        self.assertEqual(self.store.history(), [])
        self.assertIsNone(self.store.cache_get("word", "en", "test"))
        self.assertEqual(self.store.stats(), {"history": 0, "cards": 1})
        self.assertEqual(self.store.get_setting("theme"), "light")

    def test_background_threads_can_share_store(self):
        def save(number):
            self.store.cache_put(str(number), "en", "test", {"translated_text": str(number)})
            self.store.save_card(str(number), f"back-{number}")
            self.store.set_setting(f"worker-{number}", number)
            return self.store.cache_get(str(number), "en", "test")

        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(save, range(20)))
        self.assertEqual(len(results), 20)
        self.assertEqual(self.store.stats(), {"history": 20, "cards": 20})
        self.assertEqual(self.store.get_setting("worker-19"), 19)


if __name__ == "__main__":
    unittest.main()
