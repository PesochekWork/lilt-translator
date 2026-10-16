import unittest
from lilt.hotkeys import DoubleCopyDetector


class DoubleCopyTests(unittest.TestCase):
    def test_two_distinct_ctrl_c_presses(self):
        d = DoubleCopyDetector()
        self.assertFalse(d.event(True, True, 1.0))
        self.assertFalse(d.event(False, True, 1.1))
        self.assertTrue(d.event(True, True, 1.3))

    def test_held_key_is_not_double_copy(self):
        d = DoubleCopyDetector()
        self.assertFalse(d.event(True, True, 1.0))
        self.assertFalse(d.event(True, True, 1.1))
        self.assertFalse(d.event(True, True, 1.2))

    def test_slow_or_unmodified_c_does_not_capture(self):
        d = DoubleCopyDetector()
        d.event(True, True, 1.0)
        d.event(False, True, 1.1)
        self.assertFalse(d.event(True, True, 2.0))
        d.event(False, True, 2.1)
        self.assertFalse(d.event(True, False, 2.2))


if __name__ == "__main__":
    unittest.main()
