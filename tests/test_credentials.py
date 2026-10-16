from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from lilt.credentials import Credentials


@unittest.skipUnless(sys.platform == "win32", "Windows account encryption")
class CredentialTests(unittest.TestCase):
    def test_encrypted_round_trip_without_plaintext(self):
        with TemporaryDirectory() as directory:
            c = Credentials(Path(directory))
            self.assertEqual(c.read(), {})
            values = {"deepl": "test-credential:fx", "anki": "другой ключ"}
            c.write(values)
            self.assertEqual(c.read(), values)
            self.assertNotIn(b"test-credential", c.path.read_bytes())
            c.path.write_bytes(b"damaged")
            self.assertEqual(c.read(), {})


if __name__ == "__main__":
    unittest.main()
