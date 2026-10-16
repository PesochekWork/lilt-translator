import csv
import io
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
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
