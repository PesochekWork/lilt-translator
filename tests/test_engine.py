import io
import json
import socket
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

from lilt.engine import (
    DEEPL_PROVIDER,
    GOOGLE_PROVIDER,
    MAX_RESPONSE_BYTES,
    REQUEST_TIMEOUT,
    TranslationError,
    TranslationResult,
    detect_language,
    translate,
)


class FakeResponse(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8"))


class LanguageTests(unittest.TestCase):
    def test_direction_with_punctuation_and_cyrillic(self):
        self.assertEqual(detect_language("Hello, friend!"), "en")
        self.assertEqual(detect_language("Привет, друг!"), "ru")
        self.assertEqual(detect_language("Ёжик!"), "ru")
        self.assertEqual(detect_language("123..."), "en")
        self.assertEqual(detect_language("cat — кошка"), "ru")
        self.assertEqual(detect_language("Я read an English sentence"), "en")

    def test_empty_oversize_and_unsupported_inputs_do_not_make_requests(self):
        with patch("lilt.engine.urlopen") as request:
            for text in ("", " \n ", None, "x" * 5001):
                with self.subTest(text=str(text)[:10]), self.assertRaises(TranslationError):
                    translate(text)
            with self.assertRaises(TranslationError):
                translate("hello", source_lang="de")
            with self.assertRaises(TranslationError):
                translate("hello", provider="unknown")
            request.assert_not_called()


class GoogleTests(unittest.TestCase):
    @patch("lilt.engine.urlopen")
    def test_english_translation_dictionary_and_encoding(self, request):
        request.return_value = FakeResponse({
            "sentences": [{"trans": "Кошка &amp; собака. ", "orig": "Cat & dog. "}, {"trans": "Привет!"}],
            "src": "en",
            "dict": [{"pos": "noun", "terms": ["кошка", "кот", "кот", None]}],
        })
        result = translate("Cat & dog. Hello!")
        self.assertEqual(result.translated_text, "Кошка & собака. Привет!")
        self.assertEqual((result.source_lang, result.target_lang), ("en", "ru"))
        self.assertEqual(result.provider, GOOGLE_PROVIDER)
        self.assertEqual(result.definitions, [{"part_of_speech": "noun", "terms": ["кошка", "кот"]}])
        actual_request = request.call_args.args[0]
        query = parse_qs(urlparse(actual_request.full_url).query)
        self.assertEqual(query["q"], ["Cat & dog. Hello!"])
        self.assertEqual(query["dt"], ["t", "bd", "rm"])
        self.assertEqual(query["sl"], ["en"])
        self.assertEqual(query["tl"], ["ru"])
        self.assertEqual(request.call_args.kwargs["timeout"], REQUEST_TIMEOUT)
        self.assertFalse(result.from_cache)

    @patch("lilt.engine.urlopen")
    def test_russian_direction_and_source_romanization(self, request):
        request.return_value = FakeResponse({
            "sentences": [
                {"trans": "Hello", "orig": "Привет"},
                {"src_translit": "Privet", "translit": "target transliteration"},
            ],
        })
        result = translate("Привет")
        self.assertEqual(result.translated_text, "Hello")
        self.assertEqual(result.pronunciation, "Privet")
        self.assertEqual((result.source_lang, result.target_lang), ("ru", "en"))
        self.assertEqual(result.definitions, [])

    @patch("lilt.engine.urlopen")
    def test_manual_language_overrides_detection(self, request):
        request.return_value = FakeResponse({"sentences": [{"trans": "Пример"}]})
        result = translate("Пример", source_lang="en")
        self.assertEqual((result.source_lang, result.target_lang), ("en", "ru"))

    def test_malformed_response_is_friendly(self):
        for payload in (b"not json", None, [], {}, {"sentences": []}, {"sentences": [None]}, {"sentences": [{"trans": 1}]}):
            with self.subTest(payload=payload), patch("lilt.engine.urlopen", return_value=FakeResponse(payload)):
                with self.assertRaisesRegex(TranslationError, "response"):
                    translate("hello")


class DeepLTests(unittest.TestCase):
    @patch("lilt.engine.urlopen")
    def test_free_endpoint_auth_header_and_plain_text(self, request):
        request.return_value = FakeResponse({"translations": [{"text": "Hello &amp; goodbye", "detected_source_language": "RU"}]})
        result = translate("Привет", provider="deepl", api_key="secret-key:fx")
        self.assertEqual(result.provider, DEEPL_PROVIDER)
        self.assertEqual(result.translated_text, "Hello &amp; goodbye")
        self.assertEqual(result.definitions, [])
        actual = request.call_args.args[0]
        self.assertEqual(actual.full_url, "https://api-free.deepl.com/v2/translate")
        self.assertEqual(actual.get_header("Authorization"), "DeepL-Auth-Key secret-key:fx")
        self.assertNotIn("secret-key", actual.full_url)
        self.assertEqual(actual.method, "POST")
        body = json.loads(actual.data)
        self.assertEqual(body["source_lang"], "RU")
        self.assertEqual(body["target_lang"], "EN")
        self.assertEqual(body["text"], ["Привет"])
        self.assertEqual(body["model_type"], "prefer_quality_optimized")

    @patch("lilt.engine.urlopen")
    def test_pro_endpoint(self, request):
        request.return_value = FakeResponse({"translations": [{"text": "Привет"}]})
        translate("hello", provider="deepl", api_key="pro-key")
        self.assertEqual(request.call_args.args[0].full_url, "https://api.deepl.com/v2/translate")

    def test_key_validation(self):
        with patch("lilt.engine.urlopen") as request:
            for key in ("", None, "key\nInjected: value", "неверный"):
                with self.subTest(key=key), self.assertRaisesRegex(TranslationError, "key"):
                    translate("hello", provider="deepl", api_key=key)
            request.assert_not_called()

    def test_bad_payload(self):
        for payload in ({}, [], {"translations": []}, {"translations": [None]}, {"translations": [{"text": ""}]}):
            with self.subTest(payload=payload), patch("lilt.engine.urlopen", return_value=FakeResponse(payload)):
                with self.assertRaisesRegex(TranslationError, "unexpected response"):
                    translate("hello", provider="deepl", api_key="key")


class RequestFailureTests(unittest.TestCase):
    def test_network_failure_never_exposes_raw_error(self):
        for error in (URLError("private-key in URL"), OSError("private-key"), socket.timeout("private-key")):
            with self.subTest(error=type(error)), patch("lilt.engine.urlopen", side_effect=error):
                with self.assertRaises(TranslationError) as caught:
                    translate("hello")
                self.assertNotIn("private-key", str(caught.exception))
                self.assertIn("connection", str(caught.exception))

    def test_status_specific_actionable_errors(self):
        cases = [(403, "key"), (429, "Wait"), (456, "allowance"), (503, "temporarily"), (414, "shorter")]
        for code, expected in cases:
            error = HTTPError("https://example.com?private-key", code, "secret error body", {}, None)
            with self.subTest(code=code), patch("lilt.engine.urlopen", side_effect=error):
                with self.assertRaisesRegex(TranslationError, expected) as caught:
                    translate("hello", provider="deepl", api_key="private-key")
                self.assertNotIn("private-key", str(caught.exception))

    @patch("lilt.engine.urlopen")
    def test_response_size_limit(self, request):
        request.return_value = FakeResponse(b" " * (MAX_RESPONSE_BYTES + 1))
        with self.assertRaisesRegex(TranslationError, "too much data"):
            translate("hello")

    def test_result_round_trip(self):
        result = TranslationResult("hello", "привет", "en", "ru", GOOGLE_PROVIDER, [{"part_of_speech": "noun", "terms": ["привет"]}], "privet")
        restored = TranslationResult.from_dict(result.to_dict())
        self.assertEqual(result, restored)
        restored.definitions[0]["terms"].append("test")
        self.assertEqual(result.definitions[0]["terms"], ["привет"])


if __name__ == "__main__":
    unittest.main()
