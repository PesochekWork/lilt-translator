"""Small, thread-safe local store for translations, settings and Anki cards.

Each operation opens its own SQLite connection, so the UI and network workers
can share a Store. Settings are JSON values. API credentials belong in the
Windows credential protection layer, never in this store as plaintext.
"""

from __future__ import annotations

import csv
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


MAX_HISTORY = 500
MAX_CACHE = 1000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _default_data_dir() -> Path:
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "Lilt"
    if os.name == "nt":
        return Path.home() / "AppData" / "Local" / "Lilt"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")) / "Lilt"


def _limit(value: int) -> int:
    return max(0, min(int(value), 10000))


class Store:
    """Durable application data, stored under %LOCALAPPDATA%/Lilt by default."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.data_dir = Path(data_dir) if data_dir is not None else _default_data_dir()
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.data_dir / "lilt.sqlite3"
        with self._connection() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS translation_cache (
                    text TEXT NOT NULL,
                    request_lang TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    result_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY (text, request_lang, provider_key)
                );
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY,
                    source_text TEXT NOT NULL,
                    translated_text TEXT NOT NULL,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    request_lang TEXT NOT NULL,
                    provider_key TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE (source_text, request_lang, provider_key)
                );
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY,
                    front TEXT NOT NULL,
                    back TEXT NOT NULL,
                    context TEXT NOT NULL DEFAULT '',
                    deck TEXT NOT NULL,
                    note_id INTEGER,
                    created_at TEXT NOT NULL,
                    card_version INTEGER NOT NULL DEFAULT 1,
                    definition TEXT NOT NULL DEFAULT '',
                    pronunciation TEXT NOT NULL DEFAULT '',
                    definition_source TEXT NOT NULL DEFAULT '',
                    UNIQUE (front, back, deck, card_version)
                );
                """
            )
            self._migrate_cards(conn)

    @staticmethod
    def _migrate_cards(conn: sqlite3.Connection) -> None:
        """Replace the old uniqueness constraint atomically, keeping each row intact."""
        conn.execute("BEGIN IMMEDIATE")
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(cards)")}
        rich_columns = {"card_version", "definition", "pronunciation", "definition_source"}
        if rich_columns <= columns:
            return
        conn.execute(
            "CREATE TABLE cards_v2_migration ("
            "id INTEGER PRIMARY KEY, front TEXT NOT NULL, back TEXT NOT NULL, "
            "context TEXT NOT NULL DEFAULT '', deck TEXT NOT NULL, note_id INTEGER, "
            "created_at TEXT NOT NULL, card_version INTEGER NOT NULL DEFAULT 1, "
            "definition TEXT NOT NULL DEFAULT '', pronunciation TEXT NOT NULL DEFAULT '', "
            "definition_source TEXT NOT NULL DEFAULT '', UNIQUE (front, back, deck, card_version))"
        )
        # The previous release has none of these extra fields. Respect any fields
        # already present in a partially upgraded database as well.
        extra_values = [name if name in columns else default for name, default in (
            ("card_version", "1"), ("definition", "''"), ("pronunciation", "''"), ("definition_source", "''")
        )]
        conn.execute(
            "INSERT INTO cards_v2_migration "
            "(id, front, back, context, deck, note_id, created_at, card_version, definition, pronunciation, definition_source) "
            "SELECT id, front, back, context, deck, note_id, created_at, " + ", ".join(extra_values) + " FROM cards"
        )
        conn.execute("DROP TABLE cards")
        conn.execute("ALTER TABLE cards_v2_migration RENAME TO cards")

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._connection() as conn:
            row = conn.execute("SELECT value_json FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["value_json"])
        except (ValueError, TypeError):
            return default

    def set_setting(self, key: str, value: Any) -> None:
        normalized = key.lower().replace("-", "_")
        protected = any(word in normalized for word in ("encrypted", "protected", "dpapi"))
        if not protected and any(word in normalized for word in ("api_key", "apikey", "password", "secret")):
            raise ValueError("Store API credentials with Windows protection, not as a plaintext setting.")
        value_json = json.dumps(value, ensure_ascii=False, allow_nan=False)
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO settings (key, value_json) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_json = excluded.value_json",
                (key, value_json),
            )

    def cache_get(self, text: str, source_lang: str, provider: str) -> dict | None:
        with self._connection() as conn:
            row = conn.execute(
                "SELECT result_json FROM translation_cache "
                "WHERE text = ? AND request_lang = ? AND provider_key = ?",
                (text.strip(), source_lang.strip().lower(), provider.strip()),
            ).fetchone()
        if row is None:
            return None
        try:
            result = json.loads(row["result_json"])
            return result if isinstance(result, dict) else None
        except (ValueError, TypeError):
            return None

    def cache_put(self, text: str, source_lang: str, provider: str, result: dict) -> None:
        """Cache a result and refresh its single history entry, capped at 500."""
        text, request_lang, provider_key = text.strip(), source_lang.strip().lower(), provider.strip()
        result_json = json.dumps(result, ensure_ascii=False, allow_nan=False)
        actual_source = str(result.get("source_lang") or request_lang)
        target = str(result.get("target_lang") or ("ru" if actual_source == "en" else "en"))
        translation = str(result.get("translated_text", result.get("translation", "")))
        actual_provider = str(result.get("provider") or provider_key)
        created_at = _now()
        with self._connection() as conn:
            conn.execute(
                "INSERT INTO translation_cache VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(text, request_lang, provider_key) DO UPDATE SET "
                "result_json = excluded.result_json, created_at = excluded.created_at",
                (text, request_lang, provider_key, result_json, created_at),
            )
            conn.execute(
                "INSERT INTO history (source_text, translated_text, source_lang, target_lang, "
                "provider, request_lang, provider_key, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(source_text, request_lang, provider_key) DO UPDATE SET "
                "translated_text = excluded.translated_text, source_lang = excluded.source_lang, "
                "target_lang = excluded.target_lang, provider = excluded.provider, "
                "created_at = excluded.created_at",
                (text, translation, actual_source, target, actual_provider, request_lang, provider_key, created_at),
            )
            conn.execute(
                "DELETE FROM history WHERE id NOT IN "
                "(SELECT id FROM history ORDER BY created_at DESC, id DESC LIMIT ?)",
                (MAX_HISTORY,),
            )
            conn.execute(
                "DELETE FROM translation_cache WHERE rowid NOT IN "
                "(SELECT rowid FROM translation_cache ORDER BY created_at DESC, rowid DESC LIMIT ?)",
                (MAX_CACHE,),
            )

    def history(self, limit: int = 100) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id, source_text, translated_text, source_lang, target_lang, provider, created_at, request_lang, provider_key "
                "FROM history ORDER BY created_at DESC, id DESC LIMIT ?", (_limit(limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    def save_card(
        self, front: str, back: str, context: str = "", deck: str = "English", note_id: int | None = None,
        *, card_version: int = 1, definition: str = "", pronunciation: str = "", definition_source: str = ""
    ) -> bool:
        front, back, deck = front.strip(), back.strip(), deck.strip()
        if not front or not back or not deck:
            raise ValueError("A card needs a front, back and deck name.")
        if note_id is not None and (isinstance(note_id, bool) or not isinstance(note_id, int) or note_id <= 0):
            raise ValueError("Anki note ID must be a positive integer.")
        self._validate_card_version(card_version)
        with self._connection() as conn:
            cursor = conn.execute(
                "INSERT OR IGNORE INTO cards "
                "(front, back, context, deck, note_id, created_at, card_version, definition, pronunciation, definition_source) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (front, back, context.strip(), deck, note_id, _now(), card_version,
                 definition.strip(), pronunciation.strip(), definition_source.strip()),
            )
            added = cursor.rowcount == 1
            if not added and note_id is not None:
                conn.execute(
                    "UPDATE cards SET note_id = ? WHERE front = ? AND back = ? AND deck = ? "
                    "AND card_version = ? AND note_id IS NULL",
                    (note_id, front, back, deck, card_version),
                )
        return added

    def cards(self, limit: int = 200) -> list[dict]:
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT id, front, back, context, deck, note_id, created_at, "
                "card_version, definition, pronunciation, definition_source FROM cards "
                "ORDER BY created_at DESC, id DESC LIMIT ?", (_limit(limit),)
            ).fetchall()
        return [dict(row) for row in rows]

    @staticmethod
    def _validate_card_version(card_version: int) -> None:
        if isinstance(card_version, bool) or not isinstance(card_version, int) or card_version not in (1, 2):
            raise ValueError("Unsupported card version.")

    def find_card(self, front: str, back: str, deck: str, *, card_version: int = 1) -> dict | None:
        self._validate_card_version(card_version)
        with self._connection() as conn:
            row = conn.execute(
                "SELECT id, front, back, context, deck, note_id, created_at, "
                "card_version, definition, pronunciation, definition_source FROM cards "
                "WHERE front = ? AND back = ? AND deck = ? AND card_version = ?",
                (front.strip(), back.strip(), deck.strip(), card_version),
            ).fetchone()
        return dict(row) if row is not None else None

    def mark_card_sent(
        self, card_id: int, note_id: int, *, identity: tuple[str, str, str] | None = None,
        card_version: int | None = None
    ) -> None:
        if isinstance(note_id, bool) or not isinstance(note_id, int) or note_id <= 0:
            raise ValueError("Anki note ID must be a positive integer.")
        if card_version is not None:
            self._validate_card_version(card_version)
        with self._connection() as conn:
            version_clause = " AND card_version = ?" if card_version is not None else ""
            version_params = (card_version,) if card_version is not None else ()
            if identity is None:
                conn.execute("UPDATE cards SET note_id = ? WHERE id = ?" + version_clause,
                             (note_id, card_id) + version_params)
            else:
                front, back, deck = (part.strip() for part in identity)
                conn.execute(
                    "UPDATE cards SET note_id = ? WHERE id = ? AND front = ? AND back = ? AND deck = ?" + version_clause,
                    (note_id, card_id, front, back, deck) + version_params,
                )

    def delete_card(self, card_id: int) -> None:
        with self._connection() as conn:
            conn.execute("DELETE FROM cards WHERE id = ?", (card_id,))

    def stats(self) -> dict:
        with self._connection() as conn:
            history = conn.execute("SELECT COUNT(*) FROM history").fetchone()[0]
            cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
        return {"history": history, "cards": cards}

    def export_cards(self, path: Path | str) -> int:
        """Export every local card as UTF-8 Anki text with quoted multiline fields."""
        with self._connection() as conn:
            rows = conn.execute(
                "SELECT front, back, context, deck, card_version, definition, pronunciation, definition_source "
                "FROM cards ORDER BY id"
            ).fetchall()
        with Path(path).open("w", encoding="utf-8", newline="") as file:
            file.write("#separator:Tab\n#html:false\n#tags:lilt\n")
            writer = csv.writer(file, delimiter="\t", lineterminator="\n")
            if all(row["card_version"] == 1 for row in rows):
                file.write("#deck column:4\n#columns:Front\tBack\tContext\tDeck\n")
                writer.writerows((row["front"], row["back"], row["context"], row["deck"]) for row in rows)
            else:
                # With a note-type column Anki maps the remaining fields by
                # position in each model, rather than the displayed column name.
                file.write("#notetype column:1\n#deck column:2\n")
                file.write("#columns:NoteType\tDeck\tFront / English\tBack / Russian\tContext / Definition\tPronunciation\tContext\tDictionarySource\n")
                for row in rows:
                    if row["card_version"] == 1:
                        writer.writerow(("Lilt", row["deck"], row["front"], row["back"], row["context"], "", "", ""))
                    else:
                        writer.writerow(("Lilt Vocabulary v2", row["deck"], row["front"], row["back"], row["definition"],
                                         row["pronunciation"], row["context"], row["definition_source"]))
        return len(rows)

    def clear_history(self) -> None:
        """Remove saved translations, including the cache containing their text."""
        with self._connection() as conn:
            conn.execute("DELETE FROM history")
            conn.execute("DELETE FROM translation_cache")
