import io
import json
import socket
import unittest
from http.client import IncompleteRead
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from lilt.dictionary import EnglishEntry, MAX_RESPONSE_BYTES, REQUEST_TIMEOUT, lookup_english


class FakeResponse(io.BytesIO):
    def __init__(self, data):
        super().__init__(data if isinstance(data, bytes) else json.dumps(data).encode("utf-8"))


class DictionaryTests(unittest.TestCase):
    @patch("lilt.dictionary.urlopen")
    def test_real_english_definitions_ipa_and_attribution(self, request):
        request.return_value = FakeResponse([{
            "word": "hello",
            "phonetics": [
                {"audio": "https://example.com/not-fetched.mp3"},
                {"text": "/həˈləʊ/", "sourceUrl": "https://example.com/pronunciation", "license": {"name": "BY 3.0", "url": "https://creativecommons.org/licenses/by/3.0/"}},
            ],
            "meanings": [{"partOfSpeech": "noun", "definitions": [
                {"definition": "A greeting."}, {"definition": "A greeting."},
                {"definition": "An expression of surprise."},
            ]}],
            "license": {"name": "CC BY-SA 3.0", "url": "https://creativecommons.org/licenses/by-sa/3.0/"},
            "sourceUrls": ["https://en.wiktionary.org/wiki/hello", "https://en.wiktionary.org/wiki/hello"],
        }])
        entry = lookup_english("hello")
        self.assertEqual(entry.word, "hello")
        self.assertEqual(entry.definitions, ["noun: A greeting.", "noun: An expression of surprise."])
        self.assertEqual(entry.pronunciation, "/həˈləʊ/")
        self.assertEqual(entry.source.count("https://en.wiktionary.org/wiki/hello"), 1)
        self.assertIn("CC BY-SA 3.0 — https://creativecommons.org/licenses/by-sa/3.0/", entry.source)
        self.assertIn("https://example.com/pronunciation", entry.source)
        self.assertIn("BY 3.0 — https://creativecommons.org/licenses/by/3.0/", entry.source)
        self.assertEqual(request.call_args.args[0].full_url, "https://api.dictionaryapi.dev/api/v2/entries/en/hello")
        self.assertEqual(request.call_args.kwargs["timeout"], REQUEST_TIMEOUT)
        self.assertLessEqual(REQUEST_TIMEOUT, 3)
        request.assert_called_once()

    @patch("lilt.dictionary.urlopen")
    def test_all_valid_definitions_are_kept_across_entries(self, request):
        definitions = [{"definition": f"Meaning {index}."} for index in range(35)]
        request.return_value = FakeResponse([
            {"word": "test", "phonetic": "/test/", "meanings": [{"partOfSpeech": "noun", "definitions": definitions}]},
            {"word": "test", "meanings": [{"definitions": [{"definition": "Another meaning."}]}]},
        ])
        entry = lookup_english("test")
        self.assertEqual(len(entry.definitions), 36)
        self.assertEqual(entry.definitions[-1], "Another meaning.")
        self.assertEqual(entry.pronunciation, "/test/")

    @patch("lilt.dictionary.urlopen")
    def test_optional_fields_and_malformed_entries_do_not_crash(self, request):
        request.return_value = FakeResponse([
            None,
            {"word": None, "phonetic": 7, "phonetics": [None, {"text": None}], "sourceUrls": [None, "javascript:alert(1)", "https://example.com/source"], "license": None,
             "meanings": [None, {"definitions": None}, {"partOfSpeech": 4, "definitions": [None, {}, {"definition": 7}, {"definition": "Useful English definition."}]}]},
        ])
        entry = lookup_english("hello")
        self.assertEqual(entry.word, "hello")
        self.assertEqual(entry.definitions, ["Useful English definition."])
        self.assertEqual(entry.pronunciation, "")
        self.assertEqual(entry.source, "https://example.com/source")

    def test_no_dictionary_data_returns_empty(self):
        for data in (None, {}, [], [None], [{"word": "hello"}], [{"meanings": {}}], [{"phonetics": {}, "meanings": []}]):
            with self.subTest(data=data), patch("lilt.dictionary.urlopen", return_value=FakeResponse(data)):
                self.assertEqual(lookup_english("hello"), EnglishEntry())

    @patch("lilt.dictionary.urlopen")
    def test_phonetic_alone_is_usable_and_does_not_require_definition(self, request):
        request.return_value = FakeResponse([{"phonetic": "/test/"}])
        self.assertEqual(lookup_english("test"), EnglishEntry("test", [], "/test/", ""))

    def test_unsupported_input_is_skipped_without_network(self):
        invalid = ("", "   ", None, 123, "привет", "Hello!", "one two three four five", "a" * 81, "hello\nworld", "hello\tworld", "https://example.com", "123", "--", "one - two", "café")
        with patch("lilt.dictionary.urlopen") as request:
            for value in invalid:
                with self.subTest(value=value):
                    self.assertEqual(lookup_english(value), EnglishEntry())
            request.assert_not_called()

    def test_short_phrases_apostrophes_hyphens_and_boundaries(self):
        for value, encoded in (("look  up", "look%20up"), ("don't", "don%27t"), ("well-known", "well-known"), ("pick it right up", "pick%20it%20right%20up"), ("a" * 80, "a" * 80)):
            with self.subTest(value=value), patch("lilt.dictionary.urlopen", return_value=FakeResponse([{"phonetic": "/x/"}])) as request:
                entry = lookup_english(value)
                self.assertTrue(entry.pronunciation)
                self.assertTrue(request.call_args.args[0].full_url.endswith("/" + encoded))

    def test_network_http_and_invalid_payload_failures_are_optional(self):
        failures = (
            HTTPError("https://example.com", 404, "missing", {}, None),
            HTTPError("https://example.com", 429, "slow down", {}, None),
            URLError("unavailable"), OSError("network error"), socket.timeout("timeout"),
            IncompleteRead(b"partial"),
        )
        for error in failures:
            with self.subTest(error=type(error).__name__), patch("lilt.dictionary.urlopen", side_effect=error):
                self.assertEqual(lookup_english("hello"), EnglishEntry())
        for payload in (b"not json", b"\xff", b"null", b"[" * 2000 + b"]" * 2000):
            with self.subTest(payload=payload), patch("lilt.dictionary.urlopen", return_value=FakeResponse(payload)):
                self.assertEqual(lookup_english("hello"), EnglishEntry())

    @patch("lilt.dictionary.urlopen")
    def test_response_is_read_with_a_strict_size_bound(self, request):
        response = FakeResponse(b" " * (MAX_RESPONSE_BYTES + 1))
        with patch.object(response, "read", wraps=response.read) as read:
            request.return_value = response
            self.assertEqual(lookup_english("hello"), EnglishEntry())
            read.assert_called_once_with(MAX_RESPONSE_BYTES + 1)
        self.assertLessEqual(MAX_RESPONSE_BYTES, 1024 * 1024)

    def test_empty_entries_do_not_share_mutable_definition_lists(self):
        first, second = EnglishEntry(), EnglishEntry()
        first.definitions.append("test")
        self.assertEqual(second.definitions, [])

    @patch("lilt.dictionary.urlopen")
    def test_dictionary_entries_for_another_word_are_not_attached(self, request):
        request.return_value = FakeResponse([
            {"word": "different", "phonetic": "/x/", "meanings": [{"definitions": [{"definition": "Unrelated."}]}]},
        ])
        self.assertEqual(lookup_english("hello"), EnglishEntry())


if __name__ == "__main__":
    unittest.main()
