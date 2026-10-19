"""Explicit, per-user Windows startup registration with no GUI dependency.

Importing this module never accesses the registry. Only an explicit
``set_enabled`` call changes the Lilt value under the user's Run key.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys

try:
    import winreg
except ImportError:  # Keep imports and source tests usable on other platforms.
    winreg = None


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Lilt"
MAX_COMMAND_LENGTH = 260


class StartupError(Exception):
    """A startup-setting error suitable for display in Preferences."""


def _require_windows() -> None:
    if sys.platform != "win32":
        raise StartupError("Starting Lilt with the system is available on Windows only.")


def command() -> str:
    """Return an absolute Windows command line, independent of the login folder.

    A packaged app runs itself. A source checkout runs its absolute launch.pyw
    through pythonw.exe when available, so no console window appears at login.
    No shell, working-directory assumption, or environment expansion is used.
    """
    _require_windows()
    try:
        executable = Path(sys.executable).resolve()
        if getattr(sys, "frozen", False):
            arguments = [str(executable), "--startup"]
        else:
            pythonw = executable.with_name("pythonw.exe")
            interpreter = pythonw if pythonw.is_file() else executable
            launcher = Path(__file__).resolve().parents[1] / "launch.pyw"
            if not launcher.is_file():
                raise StartupError("Lilt's source launcher is missing. Keep the source folder intact or use the installed app.")
            arguments = [str(interpreter), str(launcher), "--startup"]
        result = subprocess.list2cmdline(arguments)
    except (OSError, ValueError):
        raise StartupError("Windows could not find Lilt's startup path. Run Lilt from its installed or source folder and try again.") from None
    # The Run key accepts a command line of at most 260 Windows characters.
    if len(result.encode("utf-16-le")) // 2 > MAX_COMMAND_LENGTH:
        raise StartupError("Lilt's startup command is too long for Windows (260 characters). Move Lilt to a shorter folder path, then enable startup again.")
    return result


def is_enabled() -> bool:
    """Read whether this copy of Lilt has the exact managed REG_SZ command.

    A stale path, custom command, empty value, or different registry value type
    is not treated as this copy's startup entry. Missing keys/values mean off;
    access failures are reported instead of silently pretending startup is off.
    """
    _require_windows()
    registry = _registry()
    try:
        with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_QUERY_VALUE) as key:
            value, value_type = registry.QueryValueEx(key, VALUE_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        raise StartupError("Windows could not read Lilt's startup setting. Check your Windows account permissions and try again.") from None
    return value_type == registry.REG_SZ and isinstance(value, str) and bool(value) and value == command()


def set_enabled(enabled: bool) -> None:
    """Write or remove only HKCU Run's Lilt value, never another startup app."""
    _require_windows()
    registry = _registry()
    if not isinstance(enabled, bool):
        raise StartupError("Choose whether Lilt should start with Windows.")
    if enabled:
        value = command()  # Validate before opening a key for writing.
        try:
            with registry.CreateKeyEx(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
                registry.SetValueEx(key, VALUE_NAME, 0, registry.REG_SZ, value)
        except OSError:
            raise StartupError("Windows could not enable startup for Lilt. Check your Windows account permissions and try again.") from None
    else:
        try:
            with registry.OpenKey(registry.HKEY_CURRENT_USER, RUN_KEY, 0, registry.KEY_SET_VALUE) as key:
                registry.DeleteValue(key, VALUE_NAME)
        except FileNotFoundError:
            pass  # Neither a missing Run key nor an absent Lilt value needs repair.
        except OSError:
            raise StartupError("Windows could not disable startup for Lilt. Check your Windows account permissions and try again.") from None


def _registry():
    if winreg is None:
        raise StartupError("Windows startup settings are unavailable in this Python installation.")
    return winreg
