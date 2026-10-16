"""Windows single-instance ownership without GUI or third-party dependencies."""

from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import sys
import threading


ERROR_ALREADY_EXISTS = 183
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0
WAIT_FAILED = 0xFFFFFFFF


class InstanceLock:
    """Keep one Lilt process per data directory in this Windows session.

    The named mutex's existence is the lock: its handle stays open until
    ``release`` or process termination. We do not acquire thread ownership or
    wait on the mutex, so ``ReleaseMutex`` is deliberately unnecessary.
    Keep this object alive for the entire application lifetime.
    """

    def __init__(self, data_dir: Path):
        normalized = os.path.normcase(str(Path(data_dir).expanduser().resolve())).casefold()
        digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        self.server_name = "LiltDesktop-" + digest
        self.mutex_name = "Local\\" + self.server_name
        self.event_name = self.mutex_name + "-show"
        self._handle = None
        self._event_handle = None
        self._state_lock = threading.Lock()
        self._kernel = None
        if sys.platform == "win32":
            kernel = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateMutexW.restype = wintypes.HANDLE
            kernel.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.CreateEventW.restype = wintypes.HANDLE
            kernel.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
            kernel.OpenEventW.restype = wintypes.HANDLE
            kernel.SetEvent.argtypes = [wintypes.HANDLE]
            kernel.SetEvent.restype = wintypes.BOOL
            kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel.WaitForSingleObject.restype = wintypes.DWORD
            kernel.CloseHandle.argtypes = [wintypes.HANDLE]
            kernel.CloseHandle.restype = wintypes.BOOL
            self._kernel = kernel

    def acquire(self) -> bool:
        """Return False if another instance exists; raise on a Windows API error.

        Calling this again on the instance that already holds the lock is safe.
        A rejected attempt closes its duplicate handle immediately.
        """
        if self._kernel is None:
            raise RuntimeError("Lilt single-instance locking requires Windows.")
        with self._state_lock:
            if self._handle is not None:
                return True
            ctypes.set_last_error(0)
            handle = self._kernel.CreateMutexW(None, False, self.mutex_name)
            error = ctypes.get_last_error()
            if not handle:
                raise ctypes.WinError(error)
            if error == ERROR_ALREADY_EXISTS:
                if not self._kernel.CloseHandle(handle):
                    raise ctypes.WinError(ctypes.get_last_error())
                return False
            event = self._kernel.CreateEventW(None, False, False, self.event_name)
            if not event:
                error = ctypes.get_last_error()
                self._kernel.CloseHandle(handle)
                raise ctypes.WinError(error)
            self._handle = handle
            self._event_handle = event
            return True

    def activate_existing(self) -> bool:
        """Ask the owner to show its window, without loading Qt or blocking.

        False means the owner has no activation event available (for example,
        it is still starting or has just exited). The caller may retry briefly.
        """
        if self._kernel is None:
            return False
        handle = self._kernel.OpenEventW(EVENT_MODIFY_STATE, False, self.event_name)
        if not handle:
            return False
        try:
            return bool(self._kernel.SetEvent(handle))
        finally:
            self._kernel.CloseHandle(handle)

    def consume_activation(self) -> bool:
        """Poll once from the owner's GUI timer; an activation is consumed once."""
        with self._state_lock:
            if self._event_handle is None:
                return False
            status = self._kernel.WaitForSingleObject(self._event_handle, 0)
            if status == WAIT_FAILED:
                raise ctypes.WinError(ctypes.get_last_error())
            return status == WAIT_OBJECT_0

    def release(self) -> None:
        """Close the held handle; repeated calls are harmless."""
        with self._state_lock:
            handles = (self._event_handle, self._handle)
            self._event_handle = self._handle = None
            error = None
            for handle in handles:
                if handle is not None and not self._kernel.CloseHandle(handle):
                    error = error or ctypes.get_last_error()
            if error is not None:
                raise ctypes.WinError(error)

    def __del__(self):
        # Normal shutdown should call release explicitly. Windows also closes
        # every process handle after a crash or forced process termination.
        try:
            self.release()
        except Exception:
            pass
