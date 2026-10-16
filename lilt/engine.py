"""Small, synchronous translation clients with no GUI or third-party dependencies.

Google's default endpoint is an unofficial web endpoint. It needs no account,
but can be rate-limited or changed by Google. DeepL uses the supported API and
requires the user's own API key. Call ``translate`` from a worker thread.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import html
import json
import socket
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


MAX_TEXT_LENGTH = 5_000
REQUEST_TIMEOUT = 8.0
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
GOOGLE_PROVIDER = "Google · unofficial"
DEEPL_PROVIDER = "DeepL API"


class TranslationError(Exception):
    """An error safe to display to the user, without request URLs or API keys."""


@dataclass
class TranslationResult:
    source_text: str
    translated_text: str
    source_lang: str
    target_lang: str
    provider: str
    definitions: list[dict] = field(default_factory=list)
    pronunciation: str = ""
    from_cache: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "TranslationResult":
        """Restore a result written by ``to_dict`` (for local history/cache)."""
        if not isinstance(data, dict):
            raise ValueError("Invalid saved translation")
        required = ("source_text", "translated_text", "source_lang", "target_lang", "provider")
        if any(not isinstance(data.get(key), str) for key in required):
            raise ValueError("Invalid saved translation")
        if data["source_lang"] not in {"en", "ru"} or data["target_lang"] not in {"en", "ru"}:
            raise ValueError("Invalid saved translation language")
        return cls(
            **{key: data[key] for key in required},
            definitions=_definitions(data.get("definitions", [])),
            pronunciation=data.get("pronunciation", "") if isinstance(data.get("pronunciation", ""), str) else "",
            from_cache=bool(data.get("from_cache", False)),
        )


def detect_language(text: str) -> str:
    """Choose Russian or English by Cyrillic/Latin letter counts.

    Cyrillic wins a nonempty tie; numbers or punctuation alone default to English.
    The user can always override this lightweight heuristic in the app.
    """
    cyrillic = sum("\u0400" <= char <= "\u04ff" and char.isalpha() for char in text)
    latin = sum("a" <= char.lower() <= "z" for char in text)
    return "ru" if cyrillic and cyrillic >= latin else "en"


def translate(
    text: str,
    source_lang: str = "auto",
    provider: str = "google",
    api_key: str = "",
) -> TranslationResult:
    """Translate between Russian and English; never silently truncate input.

    The direction is chosen locally so even short selections always have a
    consistent opposite target language. Keys are only sent in DeepL's HTTPS
    Authorization header and are never stored here.
    """
    if not isinstance(text, str) or not text.strip():
        raise TranslationError("Select or enter some text to translate.")
    text = text.strip()
    if len(text) > MAX_TEXT_LENGTH:
        raise TranslationError("Select a shorter passage (up to 5,000 characters).")
    if source_lang not in {"auto", "en", "ru"}:
        raise TranslationError("Choose English, Russian, or automatic language detection.")
    source = detect_language(text) if source_lang == "auto" else source_lang
    target = "en" if source == "ru" else "ru"
    if provider == "google":
        return _google(text, source, target)
    if provider == "deepl":
        if not isinstance(api_key, str) or not api_key.strip():
            raise TranslationError("Add your DeepL API key in Settings, or choose Google.")
        api_key = api_key.strip()
        if any(ord(char) < 33 or ord(char) > 126 for char in api_key):
            raise TranslationError("Check your DeepL API key in Settings; it contains invalid characters.")
        return _deepl(text, source, target, api_key)
    raise TranslationError("Choose Google or DeepL in Settings.")


def _request_json(request: Request, provider: str) -> Any:
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            raise TranslationError(f"{provider} returned too much data. Try a shorter selection.")
        return json.loads(raw.decode("utf-8"))
    except HTTPError as error:
        # Do not expose error bodies, request URLs, or headers; they can contain
        # selected text or credentials, and are not helpful to the end user.
        code = error.code
        error.close()
        if code in {401, 403} and provider == DEEPL_PROVIDER:
            message = "DeepL rejected the API key. Check the key and API plan in Settings."
        elif code == 456 and provider == DEEPL_PROVIDER:
            message = "Your DeepL translation allowance is used up. Check your API plan or choose Google."
        elif code == 429:
            message = f"{provider} is receiving too many requests. Wait a little, then try again."
        elif code in {413, 414}:
            message = "The translation service cannot accept this much text. Select a shorter passage."
        elif code in {401, 403}:
            message = "Google blocked this request. Try again later or choose DeepL in Settings."
        elif code >= 500:
            message = f"{provider} is temporarily unavailable. Please try again shortly."
        else:
            message = f"{provider} could not translate this selection. Try again or change provider in Settings."
        raise TranslationError(message) from None
    except (socket.timeout, TimeoutError):
        raise TranslationError(f"{provider} took too long to respond. Check your connection and try again.") from None
    except (URLError, ssl.SSLError, OSError):
        raise TranslationError(f"Cannot reach {provider}. Check your internet connection and try again.") from None
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise TranslationError(f"{provider} returned an unreadable response. Try again or change provider in Settings.") from None


def _google(text: str, source: str, target: str) -> TranslationResult:
    parameters = [
        ("client", "gtx"), ("sl", source), ("tl", target),
        ("dt", "t"), ("dt", "bd"), ("dt", "rm"),
        ("dj", "1"), ("ie", "UTF-8"), ("oe", "UTF-8"), ("q", text),
    ]
    request = Request(
        "https://translate.googleapis.com/translate_a/single?" + urlencode(parameters),
        headers={"User-Agent": "Lilt/0.1", "Accept": "application/json"},
    )
    data = _request_json(request, GOOGLE_PROVIDER)
    if not isinstance(data, dict) or not isinstance(data.get("sentences"), list):
        raise _invalid_response(GOOGLE_PROVIDER)

    translated_parts = []
    source_pronunciations = []
    target_pronunciations = []
    for sentence in data["sentences"]:
        if not isinstance(sentence, dict):
            raise _invalid_response(GOOGLE_PROVIDER)
        if "trans" in sentence:
            if not isinstance(sentence["trans"], str):
                raise _invalid_response(GOOGLE_PROVIDER)
            translated_parts.append(sentence["trans"])
        if isinstance(sentence.get("src_translit"), str):
            source_pronunciations.append(sentence["src_translit"])
        if isinstance(sentence.get("translit"), str):
            target_pronunciations.append(sentence["translit"])

    translated = html.unescape("".join(translated_parts)).strip()
    if not translated:
        raise _invalid_response(GOOGLE_PROVIDER)
    definitions = []
    dictionary = data.get("dict")
    if isinstance(dictionary, list):
        for entry in dictionary:
            if not isinstance(entry, dict):
                continue
            definitions.append({"part_of_speech": entry.get("pos", ""), "terms": entry.get("terms", [])})
    return TranslationResult(
        text, translated, source, target, GOOGLE_PROVIDER,
        definitions=_definitions(definitions),
        pronunciation=html.unescape("".join(source_pronunciations or target_pronunciations)).strip(),
    )


def _deepl(text: str, source: str, target: str, api_key: str) -> TranslationResult:
    base_url = "https://api-free.deepl.com" if api_key.endswith(":fx") else "https://api.deepl.com"
    body = json.dumps({
        "text": [text],
        "source_lang": source.upper(),
        "target_lang": target.upper(),
        "preserve_formatting": True,
        "model_type": "prefer_quality_optimized",
    }).encode("utf-8")
    request = Request(
        base_url + "/v2/translate", data=body, method="POST",
        headers={
            "Authorization": "DeepL-Auth-Key " + api_key,
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json", "User-Agent": "Lilt/0.1",
        },
    )
    data = _request_json(request, DEEPL_PROVIDER)
    translations = data.get("translations") if isinstance(data, dict) else None
    if not isinstance(translations, list) or len(translations) != 1:
        raise _invalid_response(DEEPL_PROVIDER)
    entry = translations[0]
    if not isinstance(entry, dict) or not isinstance(entry.get("text"), str) or not entry["text"].strip():
        raise _invalid_response(DEEPL_PROVIDER)
    # DeepL returns plain text, so HTML entities in the original remain literal.
    return TranslationResult(text, entry["text"].strip(), source, target, DEEPL_PROVIDER)


def _definitions(entries: Any) -> list[dict]:
    """Keep optional dictionary data predictable even when the provider omits it."""
    result = []
    if not isinstance(entries, list):
        return result
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("terms"), list):
            continue
        terms = list(dict.fromkeys(html.unescape(term).strip() for term in entry["terms"] if isinstance(term, str) and term.strip()))
        if not terms:
            continue
        part_of_speech = entry.get("part_of_speech", "")
        result.append({
            "part_of_speech": html.unescape(part_of_speech) if isinstance(part_of_speech, str) else "",
            "terms": terms,
        })
    return result


def _invalid_response(provider: str) -> TranslationError:
    return TranslationError(f"{provider} returned an unexpected response. Try again or change provider in Settings.")
