from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

from lilt.instance import InstanceLock


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHILD_SCRIPT = """
import os
from pathlib import Path
import sys
from lilt.instance import InstanceLock

lock = InstanceLock(Path(sys.argv[1]))
if sys.argv[2] == 'activate':
    print('activated' if lock.activate_existing() else 'missing', flush=True)
    sys.exit(0)
acquired = lock.acquire()
print('acquired' if acquired else 'duplicate', flush=True)
if sys.argv[2] == 'abrupt':
    os._exit(0)
lock.release()
"""


class InstanceIdentityTests(unittest.TestCase):
    def test_equivalent_directories_share_private_stable_names(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            first = InstanceLock(path)
            equivalent = InstanceLock(path / "unused-child" / "..")
            other = InstanceLock(path / "other-profile")
            self.assertEqual(first.server_name, equivalent.server_name)
            self.assertEqual(first.mutex_name, "Local\\" + first.server_name)
            self.assertNotEqual(first.server_name, other.server_name)
            self.assertTrue(first.server_name.startswith("LiltDesktop-"))
            self.assertNotIn(str(path), first.server_name)
            self.assertTrue(first.server_name.isascii())

    @unittest.skipUnless(sys.platform == "win32", "Windows paths are case-insensitive")
    def test_windows_path_casing_does_not_create_a_second_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual(InstanceLock(Path(temporary)).server_name,
                             InstanceLock(Path(temporary.swapcase())).server_name)


@unittest.skipUnless(sys.platform == "win32", "Native Windows named mutex tests")
class InstanceLockTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        self.locks = []

    def tearDown(self):
        for lock in self.locks:
            lock.release()
        self.directory.cleanup()

    def lock(self, path=None):
        lock = InstanceLock(path or self.path)
        self.locks.append(lock)
        return lock

    def child(self, mode="release"):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        result = subprocess.run(
            [sys.executable, "-c", CHILD_SCRIPT, str(self.path), mode],
            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True,
            timeout=10, creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_subprocess_rejects_duplicate_then_can_acquire_after_release(self):
        first = self.lock()
        self.assertTrue(first.acquire())
        self.assertTrue(first.acquire(), "Acquiring twice must retain the original handle")
        self.assertEqual(self.child(), "duplicate")
        self.assertEqual(self.child(), "duplicate")
        first.release()
        first.release()
        self.assertEqual(self.child(), "acquired", "Rejected attempts must not leak duplicate handles")
        self.assertTrue(first.acquire())

    def test_distinct_data_directories_can_run_together(self):
        first = self.lock()
        second = self.lock(self.path / "separate-profile")
        self.assertTrue(first.acquire())
        self.assertTrue(second.acquire())

    def test_abrupt_process_exit_releases_native_handle(self):
        self.assertEqual(self.child(mode="abrupt"), "acquired")
        self.assertTrue(self.lock().acquire(), "A terminated process must not leave a stale lock")

    def test_subprocess_activation_is_consumed_once_and_closed_on_release(self):
        owner = self.lock()
        self.assertFalse(owner.consume_activation())
        self.assertEqual(self.child(mode="activate"), "missing")
        self.assertTrue(owner.acquire())
        self.assertFalse(owner.consume_activation())
        self.assertEqual(self.child(mode="activate"), "activated")
        self.assertTrue(owner.consume_activation())
        self.assertFalse(owner.consume_activation(), "Auto-reset events must consume the request only once")
        self.assertEqual(self.child(mode="activate"), "activated")
        self.assertEqual(self.child(mode="activate"), "activated")
        self.assertTrue(owner.consume_activation())
        self.assertFalse(owner.consume_activation(), "Repeated pending requests may safely coalesce")
        owner.release()
        self.assertFalse(owner.consume_activation())
        self.assertEqual(self.child(mode="activate"), "missing", "The owner must close its activation handle")

    def test_activation_is_scoped_to_data_directory(self):
        owner = self.lock()
        other = self.lock(self.path / "other-profile")
        self.assertTrue(owner.acquire())
        self.assertFalse(other.activate_existing())
        self.assertFalse(owner.consume_activation())


if __name__ == "__main__":
    unittest.main()
