"""Minimal AnkiConnect v6 client; only talks to Anki on this computer."""

from __future__ import annotations

import html
import ipaddress
import json
import socket
import urllib.error
import urllib.parse
import urllib.request


class AnkiError(Exception):
    """An actionable Anki integration error suitable for display in the UI."""


def _html_text(value: str) -> str:
    return html.escape(value.replace("\r\n", "\n").replace("\r", "\n"), quote=True).replace("\n", "<br>")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise AnkiError("AnkiConnect redirected the request. Check the local address in Settings.")


class AnkiClient:
    MODEL_NAME = "Lilt"

    def __init__(self, endpoint: str = "http://127.0.0.1:8765", api_key: str = "") -> None:
        self.endpoint = self._validate_endpoint(endpoint)
        self.api_key = api_key
        self.timeout = 3
        # Avoid system proxies for this local request; redirects must not leak text.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())

    @staticmethod
    def _validate_endpoint(endpoint: str) -> str:
        try:
            parts = urllib.parse.urlsplit(endpoint.strip())
            host = (parts.hostname or "").lower()
            if host == "localhost":
                host = "127.0.0.1"  # Avoid hostname resolution outside the loopback interface.
            if not ipaddress.ip_address(host).is_loopback:
                raise ValueError
            if parts.scheme not in ("http", "https") or parts.username or parts.password:
                raise ValueError
            if parts.query or parts.fragment or parts.path not in ("", "/"):
                raise ValueError
            port = parts.port or (443 if parts.scheme == "https" else 80)
            netloc = f"[{host}]:{port}" if ":" in host else f"{host}:{port}"
            return urllib.parse.urlunsplit((parts.scheme, netloc, "", "", ""))
        except (ValueError, TypeError, AttributeError):
            raise AnkiError("Use a local AnkiConnect address, such as http://127.0.0.1:8765.") from None

    def _request(self, action: str, **params):
        payload = {"action": action, "version": 6, "params": params}
        if self.api_key:
            payload["key"] = self.api_key
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with self._opener.open(request, timeout=self.timeout) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise AnkiError("AnkiConnect returned an unexpectedly large response.")
            data = json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise AnkiError(f"AnkiConnect returned HTTP {exc.code}. Check AnkiConnect and its API key.") from None
        except (urllib.error.URLError, ConnectionError, TimeoutError, socket.timeout, OSError):
            raise AnkiError("Could not reach Anki. Open Anki Desktop and make sure AnkiConnect is installed.") from None
        except (UnicodeError, ValueError):
            raise AnkiError("The local service did not return a valid AnkiConnect response.") from None
        if not isinstance(data, dict) or "error" not in data or "result" not in data:
            raise AnkiError("The local service did not return a valid AnkiConnect response.")
        error = data["error"]
        if error is not None:
            message = str(error)
            if "duplicate" in message.lower():
                raise AnkiError("This card already exists in the selected Anki deck.")
            if any(word in message.lower() for word in ("api key", "apikey", "unauthorized", "forbidden")):
                raise AnkiError("AnkiConnect rejected the API key. Enter its configured key in Settings.")
            raise AnkiError(f"AnkiConnect: {message[:300]}")
        return data["result"]

    def check(self) -> list[str]:
        """Read deck names without changing the user's collection."""
        result = self._request("deckNames")
        if not isinstance(result, list) or not all(isinstance(deck, str) for deck in result):
            raise AnkiError("AnkiConnect returned an invalid deck list.")
        return result

    def _ensure_model(self) -> None:
        models = self._request("modelNames")
        if not isinstance(models, list) or not all(isinstance(model, str) for model in models):
            raise AnkiError("AnkiConnect returned an invalid note type list.")
        if self.MODEL_NAME in models:
            fields = self._request("modelFieldNames", modelName=self.MODEL_NAME)
            if not isinstance(fields, list) or fields[:3] != ["Front", "Back", "Context"]:
                raise AnkiError("The existing Lilt note type has different fields. Rename it in Anki, then try again.")
            return
        self._request(
            "createModel",
            modelName=self.MODEL_NAME,
            inOrderFields=["Front", "Back", "Context"],
            css=(
                ".card {font-family: Arial, sans-serif; font-size: 24px; text-align: left; "
                "line-height: 1.55; padding: 24px;} "
                ".context {font-size: 17px; color: #777; margin-top: 22px;} "
                ".nightMode .context {color: #aaa;}"
            ),
            isCloze=False,
            cardTemplates=[{
                "Name": "Translation",
                "Front": "{{Front}}",
                "Back": "{{FrontSide}}<hr id=answer>{{Back}}{{#Context}}<div class=context>{{Context}}</div>{{/Context}}",
            }],
        )

    def add_card(
        self, front: str, back: str, context: str = "", deck: str = "Lilt", tags: list[str] | None = None
    ) -> int:
        front, back, deck = front.strip(), back.strip(), deck.strip()
        if not front or not back or not deck:
            raise AnkiError("A card needs a front, back and deck name.")
        self._ensure_model()
        self._request("createDeck", deck=deck)
        clean_tags = [tag.strip().replace(" ", "_") for tag in (tags or ["lilt"]) if tag.strip()]
        result = self._request(
            "addNote",
            note={
                "deckName": deck,
                "modelName": self.MODEL_NAME,
                "fields": {"Front": _html_text(front), "Back": _html_text(back), "Context": _html_text(context.strip())},
                "options": {
                    "allowDuplicate": False,
                    "duplicateScope": "deck",
                    "duplicateScopeOptions": {"deckName": deck, "checkChildren": False, "checkAllModels": False},
                },
                "tags": list(dict.fromkeys(clean_tags)),
            },
        )
        if isinstance(result, bool) or not isinstance(result, int) or result <= 0:
            raise AnkiError("Anki did not confirm the new card. Check Anki before trying again.")
        return result
