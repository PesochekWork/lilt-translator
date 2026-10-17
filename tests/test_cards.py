import unittest
from unittest.mock import patch

from lilt.cards import enrich_translation, prepare_vocabulary_card
from lilt.dictionary import EnglishEntry
from lilt.engine import TranslationResult


class VocabularyCardTests(unittest.TestCase):
    def result(self, source="hello", translated="привет", language="en"):
        return TranslationResult(source, translated, language, "ru" if language == "en" else "en", "test",
                                 definitions=[{"part_of_speech": "noun", "terms": ["приветствие"]}],
                                 pronunciation="Privet")

    @patch("lilt.cards.lookup_english")
    def test_english_source_gets_real_definition_and_phonetics(self, lookup):
        lookup.return_value = EnglishEntry("hello", ["A greeting."], "/həˈləʊ/", "Wiktionary; CC BY-SA")
        card = prepare_vocabulary_card(self.result(), " hello ", " привет ", " In context ", " Vocabulary ")
        self.assertEqual((card.english, card.russian, card.definition, card.pronunciation),
                         ("hello", "привет", "A greeting.", "/həˈləʊ/"))
        self.assertEqual((card.context, card.deck, card.definition_source),
                         ("In context", "Vocabulary", "Wiktionary; CC BY-SA"))
        lookup.assert_called_once_with("hello")

    @patch("lilt.cards.lookup_english")
    def test_russian_source_still_has_english_front(self, lookup):
        lookup.return_value = EnglishEntry("hello", ["A greeting."], "/həˈləʊ/", "source")
        card = prepare_vocabulary_card(self.result("привет", "hello", "ru"), "привет", "hello")
        self.assertEqual((card.english, card.russian, card.definition, card.pronunciation),
                         ("hello", "привет", "A greeting.", "/həˈləʊ/"))
        lookup.assert_called_once_with("hello")

    @patch("lilt.cards.lookup_english", return_value=EnglishEntry())
    def test_missing_dictionary_never_relabels_russian_alternatives_or_romanization(self, lookup):
        card = prepare_vocabulary_card(self.result("привет", "hello", "ru"), "привет", "hello")
        self.assertEqual((card.english, card.russian), ("hello", "привет"))
        self.assertEqual((card.definition, card.pronunciation, card.definition_source), ("", "", ""))

    @patch("lilt.cards.lookup_english")
    def test_known_dictionary_data_is_reused_without_network(self, lookup):
        result = self.result()
        result.english_word = "hello"
        result.english_definitions = ["A greeting."]
        result.english_pronunciation = "/həˈləʊ/"
        result.dictionary_source = "source"
        card = prepare_vocabulary_card(result, "Hello", "здравствуйте")
        self.assertEqual((card.definition, card.pronunciation), ("A greeting.", "/həˈləʊ/"))
        lookup.assert_not_called()

    @patch("lilt.cards.lookup_english")
    def test_edited_english_translation_does_not_reuse_another_words_definition(self, lookup):
        result = self.result("кошка", "cat", "ru")
        result.english_word = "cat"
        result.english_definitions = ["A feline."]
        result.english_pronunciation = "/kæt/"
        lookup.return_value = EnglishEntry("kitten", ["A young cat."], "/ˈkɪtən/", "source")
        card = prepare_vocabulary_card(result, "кошка", "kitten")
        lookup.assert_called_once_with("kitten")
        self.assertEqual((card.english, card.definition, card.pronunciation), ("kitten", "A young cat.", "/ˈkɪtən/"))

    @patch("lilt.cards.lookup_english")
    def test_enriched_translation_cache_round_trip_keeps_separate_dictionary_fields(self, lookup):
        lookup.return_value = EnglishEntry("hello", ["A greeting."], "/həˈləʊ/", "source")
        result = enrich_translation(self.result())
        restored = TranslationResult.from_dict(result.to_dict())
        self.assertEqual(restored, result)
        self.assertEqual(restored.english_definitions, ["A greeting."])
        self.assertEqual(restored.definitions, [{"part_of_speech": "noun", "terms": ["приветствие"]}])
        self.assertTrue(restored.dictionary_checked)
        restored.english_definitions.append("different")
        self.assertEqual(result.english_definitions, ["A greeting."])

    def test_legacy_cache_remains_readable(self):
        saved = {key: value for key, value in self.result().to_dict().items() if not key.startswith("english_")
                 and not key.startswith("dictionary_")}
        restored = TranslationResult.from_dict(saved)
        self.assertEqual(restored.english_definitions, [])
        self.assertFalse(restored.dictionary_checked)


if __name__ == "__main__":
    unittest.main()
