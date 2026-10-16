import io
import json
import threading
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from lilt.anki import AnkiClient, AnkiError


class FakeOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append((json.loads(request.data.decode("utf-8")), timeout))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        if isinstance(response, bytes):
            return io.BytesIO(response)
        return io.BytesIO(json.dumps({"result": response, "error": None}).encode("utf-8"))


class AnkiClientTests(unittest.TestCase):
    def client_with(self, *responses):
        client = AnkiClient(api_key="test-key")
        client._opener = FakeOpener(*responses)
        return client

    def test_check_is_read_only_v6_and_includes_api_key(self):
        client = self.client_with(["Default", "English"])
        self.assertEqual(client.check(), ["Default", "English"])
        self.assertEqual(client._opener.requests, [({"action": "deckNames", "version": 6, "params": {}, "key": "test-key"}, 3)])

    def test_add_creates_only_missing_model_and_escapes_text(self):
        client = self.client_with(["Basic"], {"id": 1}, 123, 789)
        note_id = client.add_card('<img src="x">\nhello & world', "привет > мир", "Line 1\r\nLine 2", "English", ["lilt", "my words", "lilt"])
        self.assertEqual(note_id, 789)
        requests = [request for request, _ in client._opener.requests]
        self.assertEqual([request["action"] for request in requests], ["modelNames", "createModel", "createDeck", "addNote"])
        self.assertEqual(requests[1]["params"]["modelName"], "Lilt")
        self.assertEqual(requests[1]["params"]["inOrderFields"], ["Front", "Back", "Context"])
        self.assertEqual(len(requests[1]["params"]["cardTemplates"]), 1)
        note = requests[-1]["params"]["note"]
        self.assertEqual(note["fields"]["Front"], "&lt;img src=&quot;x&quot;&gt;<br>hello &amp; world")
        self.assertEqual(note["fields"]["Back"], "привет &gt; мир")
        self.assertEqual(note["fields"]["Context"], "Line 1<br>Line 2")
        self.assertFalse(note["options"]["allowDuplicate"])
        self.assertEqual(note["options"]["duplicateScope"], "deck")
        self.assertEqual(note["tags"], ["lilt", "my_words"])
        self.assertTrue(all(request["key"] == "test-key" for request in requests))

    def test_add_uses_existing_model_without_altering_it(self):
        client = self.client_with(["Basic", "Lilt"], ["Front", "Back", "Context"], 5, 42)
        self.assertEqual(client.add_card("front", "back"), 42)
        self.assertEqual([request["action"] for request, _ in client._opener.requests], ["modelNames", "modelFieldNames", "createDeck", "addNote"])

    def test_conflicting_existing_model_is_not_modified(self):
        client = self.client_with(["Lilt"], ["Question", "Answer"])
        with self.assertRaisesRegex(AnkiError, "different fields"):
            client.add_card("front", "back")
        self.assertEqual(len(client._opener.requests), 2)

    def test_duplicate_error_is_clear(self):
        error = json.dumps({"result": None, "error": "cannot create note because it is a duplicate"}).encode()
        client = self.client_with(["Lilt"], ["Front", "Back", "Context"], 5, error)
        with self.assertRaisesRegex(AnkiError, "already exists"):
            client.add_card("front", "back")

    def test_unconfirmed_note_id_is_not_reported_as_success(self):
        for result in (None, False, True, 0, -1, "123"):
            with self.subTest(result=result):
                client = self.client_with(["Lilt"], ["Front", "Back", "Context"], 5, result)
                with self.assertRaisesRegex(AnkiError, "did not confirm"):
                    client.add_card("front", "back")

    def test_unavailable_anki_and_auth_errors_are_actionable(self):
        client = self.client_with(urllib.error.URLError("connection refused"))
        with self.assertRaisesRegex(AnkiError, "Open Anki Desktop"):
            client.check()
        client = self.client_with(json.dumps({"result": None, "error": "valid api key must be provided"}).encode())
        with self.assertRaisesRegex(AnkiError, "API key"):
            client.check()

    def test_invalid_server_payloads_are_rejected(self):
        for response in (b"not json", b"[]", b'{}', b'{"result": 1, "error": null}', b'{"result": [1], "error": null}'):
            with self.subTest(response=response):
                client = self.client_with(response)
                with self.assertRaises(AnkiError):
                    client.check()

    def test_only_loopback_endpoints_are_accepted(self):
        for endpoint in ("http://example.com:8765", "http://192.168.1.2:8765", "file:///tmp/anki", "http://127.0.0.1:8765/path", "http://user:password@localhost:8765", "http://localhost:8765?key=x", "http://localhost:99999"):
            with self.subTest(endpoint=endpoint), self.assertRaises(AnkiError):
                AnkiClient(endpoint)
        self.assertEqual(AnkiClient("http://localhost:8765").endpoint, "http://127.0.0.1:8765")
        self.assertEqual(AnkiClient("http://[::1]:8765").endpoint, "http://[::1]:8765")

    def test_empty_card_does_not_mutate_anki(self):
        client = self.client_with()
        with self.assertRaises(AnkiError):
            client.add_card(" ", "back")
        self.assertEqual(client._opener.requests, [])

    def test_http_round_trip_uses_isolated_local_server(self):
        received = []

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
                data = json.dumps({"result": ["English", "Русский"], "error": None}, ensure_ascii=False).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            client = AnkiClient(f"http://127.0.0.1:{server.server_port}")
            self.assertEqual(client.check(), ["English", "Русский"])
            self.assertEqual(received, [{"action": "deckNames", "version": 6, "params": {}}])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
