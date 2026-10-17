"""Optional English dictionary enrichment, independent of translation success.

Free Dictionary API supplies actual English definitions and phonetic text from
Wiktionary. All returned values are plain text; callers must escape them when
rendering HTML. No audio is fetched and importing this module makes no requests.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from http.client import HTTPException
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen


REQUEST_TIMEOUT = 3.0
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_WORD_LENGTH = 80
MAX_WORD_COUNT = 4


@dataclass
class EnglishEntry:
    word: str = ""
    definitions: list[str] = field(default_factory=list)
    pronunciation: str = ""
    source: str = ""


def _candidate(value: str) -> str:
    if not isinstance(value, str) or len(value) > MAX_WORD_LENGTH:
        return ""
    value = value.strip()
    if not re.fullmatch(r"[A-Za-z' -]+", value):
        return ""
    words = [word for word in value.split(" ") if word]
    if not words or len(words) > MAX_WORD_COUNT or any(not re.search(r"[A-Za-z]", word) for word in words):
        return ""
    return " ".join(words)


def _text(value) -> str:
    return value.strip() if isinstance(value, str) else ""


def _url(value) -> str:
    value = _text(value)
    if not value or any(ord(char) < 32 for char in value):
        return ""
    try:
        parts = urlsplit(value)
        if parts.scheme not in {"http", "https"} or not parts.netloc or parts.username or parts.password:
            return ""
    except ValueError:
        return ""
    return value


def _parse(data, requested_word: str) -> EnglishEntry:
    if not isinstance(data, list):
        return EnglishEntry()
    definitions: list[str] = []
    pronunciation = ""
    word = ""
    attribution: list[str] = []

    def add_source(entry: dict) -> None:
        urls = entry.get("sourceUrls", [])
        if isinstance(urls, list):
            attribution.extend(url for item in urls if (url := _url(item)))
        source_url = _url(entry.get("sourceUrl"))
        if source_url:
            attribution.append(source_url)
        license_data = entry.get("license")
        if isinstance(license_data, dict):
            name = _text(license_data.get("name"))
            url = _url(license_data.get("url"))
            if name or url:
                attribution.append(" — ".join(part for part in (name, url) if part))

    for entry in data:
        if not isinstance(entry, dict):
            continue
        entry_word = _candidate(entry.get("word", ""))
        if entry_word and entry_word.casefold() != requested_word.casefold():
            continue
        if not word:
            word = entry_word or requested_word
        add_source(entry)
        if not pronunciation:
            pronunciation = _text(entry.get("phonetic"))
            phonetics = entry.get("phonetics", [])
            if not pronunciation and isinstance(phonetics, list):
                for phonetic in phonetics:
                    if isinstance(phonetic, dict) and (phonetic_text := _text(phonetic.get("text"))):
                        pronunciation = phonetic_text
                        add_source(phonetic)
                        break
        meanings = entry.get("meanings", [])
        if not isinstance(meanings, list):
            continue
        for meaning in meanings:
            if not isinstance(meaning, dict) or not isinstance(meaning.get("definitions"), list):
                continue
            part_of_speech = _text(meaning.get("partOfSpeech"))
            for item in meaning["definitions"]:
                definition = _text(item.get("definition")) if isinstance(item, dict) else ""
                if definition:
                    definitions.append(f"{part_of_speech}: {definition}" if part_of_speech else definition)
    if not definitions and not pronunciation:
        return EnglishEntry()
    return EnglishEntry(
        word=word or requested_word,
        definitions=list(dict.fromkeys(definitions)),
        pronunciation=pronunciation,
        source="\n".join(dict.fromkeys(attribution)),
    )


def lookup_english(word: str) -> EnglishEntry:
    """Look up a short English entry; dictionary failures always return empty.

    Sentences, Cyrillic, and other unsupported input are skipped locally. A
    bounded request is intended for the existing background translation worker.
    """
    word = _candidate(word)
    if not word:
        return EnglishEntry()
    request = Request(
        "https://api.dictionaryapi.dev/api/v2/entries/en/" + quote(word, safe=""),
        headers={"User-Agent": "Lilt/0.1", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
            raw = response.read(MAX_RESPONSE_BYTES + 1)
        if len(raw) > MAX_RESPONSE_BYTES:
            return EnglishEntry()
        return _parse(json.loads(raw.decode("utf-8")), word)
    except HTTPError as error:
        error.close()
        return EnglishEntry()
    except (URLError, OSError, HTTPException, ValueError, TypeError, AttributeError, RecursionError):
        return EnglishEntry()
