from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import patch

from lilt import startup


class FakeKey:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class FakeRegistry:
    """In-memory registry substitute; these tests never touch Windows settings."""
    HKEY_CURRENT_USER = object()
    KEY_QUERY_VALUE = 1
    KEY_SET_VALUE = 2
    REG_SZ = 1
    REG_EXPAND_SZ = 2
    REG_DWORD = 4

    def __init__(self):
        self.key_exists = True
        self.values = {"Another application": ("other.exe --background", self.REG_SZ)}
        self.operations = []

    def OpenKey(self, hive, path, reserved, access):
        self.operations.append(("open", hive, path, access))
        if not self.key_exists:
            raise FileNotFoundError("Missing Run key")
        return FakeKey()

    def CreateKeyEx(self, hive, path, reserved, access):
        self.operations.append(("create", hive, path, access))
        self.key_exists = True
        return FakeKey()

    def QueryValueEx(self, key, name):
        self.operations.append(("query", name))
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name]

    def SetValueEx(self, key, name, reserved, kind, value):
        self.operations.append(("set", name))
        self.values[name] = (value, kind)

    def DeleteValue(self, key, name):
        self.operations.append(("delete", name))
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


class StartupRegistryTests(unittest.TestCase):
    def setUp(self):
        self.registry = FakeRegistry()
        self.command = r'"C:\Programs\Lilt app\Lilt.exe" --startup'
        self.addCleanup(patch.stopall)
        patch.object(startup.sys, "platform", "win32").start()
        patch.object(startup, "winreg", self.registry).start()
        patch.object(startup, "command", return_value=self.command).start()

    def test_enable_registers_only_lilt_for_current_user(self):
        original_other = self.registry.values["Another application"]
        self.registry.key_exists = False
        startup.set_enabled(True)
        self.assertEqual(self.registry.values["Lilt"], (self.command, self.registry.REG_SZ))
        self.assertTrue(startup.is_enabled())
        self.assertEqual(self.registry.values["Another application"], original_other)
        self.assertIn(("create", self.registry.HKEY_CURRENT_USER, startup.RUN_KEY, self.registry.KEY_SET_VALUE), self.registry.operations)
        self.assertEqual([op for op in self.registry.operations if op[0] == "set"], [("set", "Lilt")])

    def test_disable_removes_only_lilt_and_does_not_create_a_key(self):
        self.registry.values["Lilt"] = (self.command, self.registry.REG_SZ)
        startup.set_enabled(False)
        self.assertNotIn("Lilt", self.registry.values)
        self.assertIn("Another application", self.registry.values)
        self.assertFalse(startup.is_enabled())
        self.assertNotIn("create", [op[0] for op in self.registry.operations])
        self.assertIn(("open", self.registry.HKEY_CURRENT_USER, startup.RUN_KEY, self.registry.KEY_SET_VALUE), self.registry.operations)

    def test_missing_key_or_value_means_disabled_and_deletion_succeeds(self):
        self.assertFalse(startup.is_enabled())
        startup.set_enabled(False)
        self.registry.key_exists = False
        self.assertFalse(startup.is_enabled())
        startup.set_enabled(False)
        self.assertFalse(self.registry.key_exists)

    def test_stale_empty_custom_or_invalid_value_is_not_managed_enabled_state(self):
        values = [
            ("", self.registry.REG_SZ),
            (r"C:\old\Lilt.exe --startup", self.registry.REG_SZ),
            (self.command + " --custom", self.registry.REG_SZ),
            (self.command, self.registry.REG_EXPAND_SZ),
            (1, self.registry.REG_DWORD),
            (b"not a string", self.registry.REG_SZ),
        ]
        for value in values:
            with self.subTest(value=value):
                self.registry.values["Lilt"] = value
                self.assertFalse(startup.is_enabled())
        self.assertFalse(any(op[0] in {"set", "delete", "create"} for op in self.registry.operations))

    def test_explicit_enable_repairs_stale_entry_and_disable_removes_it(self):
        self.registry.values["Lilt"] = (r"C:\old\Lilt.exe", self.registry.REG_SZ)
        startup.set_enabled(True)
        self.assertTrue(startup.is_enabled())
        self.registry.values["Lilt"] = ("custom command", self.registry.REG_SZ)
        startup.set_enabled(False)
        self.assertNotIn("Lilt", self.registry.values)

    def test_permission_failures_are_actionable_without_raw_details(self):
        for operation, function in [
            ("OpenKey", startup.is_enabled),
            ("CreateKeyEx", lambda: startup.set_enabled(True)),
            ("SetValueEx", lambda: startup.set_enabled(True)),
            ("DeleteValue", lambda: startup.set_enabled(False)),
        ]:
            with self.subTest(operation=operation), patch.object(self.registry, operation, side_effect=PermissionError("private details")):
                with self.assertRaisesRegex(startup.StartupError, "permissions") as error:
                    function()
                self.assertNotIn("private details", str(error.exception))

    def test_invalid_boolean_does_not_mutate_registry(self):
        with self.assertRaises(startup.StartupError):
            startup.set_enabled("false")
        self.assertEqual(self.registry.operations, [])

    def test_invalid_command_prevents_registry_writes_but_still_allows_disable(self):
        with patch.object(startup, "command", side_effect=startup.StartupError("command too long")):
            with self.assertRaisesRegex(startup.StartupError, "too long"):
                startup.set_enabled(True)
            self.assertEqual(self.registry.operations, [])
            startup.set_enabled(False)


class StartupCommandTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="Lilt startup тест ")
        self.addCleanup(self.directory.cleanup)
        self.base = Path(self.directory.name)
        self.project = self.base / "project source"
        (self.project / "lilt").mkdir(parents=True)
        (self.project / "launch.pyw").write_text("# test launcher", encoding="utf-8")
        self.executable = self.base / "Python runtime" / "python.exe"
        self.executable.parent.mkdir()
        self.executable.touch()
        self.addCleanup(patch.stopall)
        patch.object(startup.sys, "platform", "win32").start()
        patch.object(startup.sys, "executable", str(self.executable)).start()
        patch.object(startup.sys, "frozen", False, create=True).start()
        patch.object(startup, "__file__", str(self.project / "lilt" / "startup.py")).start()

    def test_frozen_command_quotes_spaces_and_unicode(self):
        executable = self.base / "Installed приложение" / "Lilt.exe"
        with patch.object(startup.sys, "frozen", True), patch.object(startup.sys, "executable", str(executable)):
            self.assertEqual(startup.command(), f'"{executable.resolve()}" --startup')

    def test_source_prefers_sibling_pythonw_and_absolute_launcher(self):
        pythonw = self.executable.with_name("pythonw.exe")
        pythonw.touch()
        launcher = self.project / "launch.pyw"
        self.assertEqual(startup.command(), f'"{pythonw.resolve()}" "{launcher.resolve()}" --startup')

    def test_source_fallback_works_from_an_unrelated_working_directory(self):
        previous = Path.cwd()
        elsewhere = self.base / "unrelated folder"
        elsewhere.mkdir()
        try:
            os.chdir(elsewhere)
            self.assertEqual(startup.command(), f'"{self.executable.resolve()}" "{(self.project / "launch.pyw").resolve()}" --startup')
        finally:
            os.chdir(previous)

    def test_missing_source_launcher_is_actionable(self):
        (self.project / "launch.pyw").unlink()
        with self.assertRaisesRegex(startup.StartupError, "launcher is missing"):
            startup.command()

    def test_run_command_length_limit_is_actionable(self):
        executable = self.base / ("nested" * 36) / "Lilt.exe"
        with patch.object(startup.sys, "frozen", True), patch.object(startup.sys, "executable", str(executable)):
            with self.assertRaisesRegex(startup.StartupError, "260 characters"):
                startup.command()

    def test_unsupported_platform_is_friendly_and_never_accesses_registry(self):
        registry = FakeRegistry()
        with patch.object(startup.sys, "platform", "linux"), patch.object(startup, "winreg", registry):
            for function in (startup.command, startup.is_enabled, lambda: startup.set_enabled(True), lambda: startup.set_enabled(False)):
                with self.subTest(function=function), self.assertRaisesRegex(startup.StartupError, "Windows only"):
                    function()
        self.assertEqual(registry.operations, [])


if __name__ == "__main__":
    unittest.main()
