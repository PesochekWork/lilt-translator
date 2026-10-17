"""English-oriented vocabulary cards, separate from translated alternatives."""

from dataclasses import dataclass, replace

from .dictionary import lookup_english
from .engine import TranslationResult


@dataclass(frozen=True)
class VocabularyCard:
    english: str
    russian: str
    definition: str = ""
    pronunciation: str = ""
    context: str = ""
    deck: str = "Lilt"
    definition_source: str = ""


def prepare_vocabulary_card(
    result: TranslationResult,
    source_text: str,
    translated_text: str,
    context: str = "",
    deck: str = "Lilt",
) -> VocabularyCard:
    """Run in a worker: dictionary failure never prevents a basic card.

    The editors may have been changed after translation, especially the English
    output of a Russian query. Only reuse dictionary data for the same English
    text; Google's translated alternatives/romanization are never a definition
    or an English phonetic transcription.
    """
    source_text, translated_text = source_text.strip(), translated_text.strip()
    english, russian = ((source_text, translated_text) if result.source_lang == "en"
                        else (translated_text, source_text))
    same_word = english.casefold() == result.english_word.strip().casefold()
    definitions = list(result.english_definitions) if same_word else []
    pronunciation = result.english_pronunciation if same_word else ""
    attribution = result.dictionary_source if same_word else ""
    if not definitions or not pronunciation:
        entry = lookup_english(english)
        if entry.definitions:
            definitions = entry.definitions
            attribution = entry.source
        if entry.pronunciation:
            pronunciation = entry.pronunciation
            attribution = attribution or entry.source
    return VocabularyCard(english, russian, "\n".join(definitions), pronunciation,
                          context.strip(), deck.strip() or "Lilt", attribution)


def enrich_translation(result: TranslationResult) -> TranslationResult:
    """Attach optional dictionary data to a fresh translation before caching it."""
    card = prepare_vocabulary_card(result, result.source_text, result.translated_text)
    return replace(result, english_word=card.english,
                   english_definitions=card.definition.splitlines(),
                   english_pronunciation=card.pronunciation,
                   dictionary_source=card.definition_source, dictionary_checked=True)
