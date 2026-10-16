"""Observe double-copy without intercepting or changing ordinary copying."""
import ctypes
from ctypes import wintypes
import sys
import time

from PySide6.QtCore import QThread, Signal


class DoubleCopyDetector:
    def __init__(self, interval=0.6):
        self.interval = interval
        self.last = None
        self.down = False

    def event(self, pressed, control, now=None):
        now = time.monotonic() if now is None else now
        if not pressed:
            self.down = False
            return False
        if self.down:
            return False
        self.down = True
        if not control:
            self.last = None
            return False
        if self.last is not None and 0 <= now - self.last <= self.interval:
            self.last = None
            return True
        self.last = now
        return False


class CaptureListener(QThread):
    captured = Signal()
    clipboard_requested = Signal()
    unavailable = Signal(str)
    warning = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.thread_id = None
        self.detector = DoubleCopyDetector()

    def run(self):
        if sys.platform != "win32":
            self.unavailable.emit("Double-copy is available on Windows. Paste text to translate.")
            return
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        callback_type = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

        class KeyboardData(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD), ("extra", ctypes.c_size_t)]

        user.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HANDLE
        user.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = ctypes.c_ssize_t
        user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        kernel.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
        kernel.GetModuleHandleW.restype = wintypes.HMODULE
        user.GetAsyncKeyState.argtypes = [ctypes.c_int]
        user.GetAsyncKeyState.restype = wintypes.SHORT
        user.GetMessageW.restype = wintypes.BOOL
        user.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT]
        user.PeekMessageW.restype = wintypes.BOOL
        user.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
        user.RegisterHotKey.restype = wintypes.BOOL
        kernel.GetCurrentThreadId.restype = wintypes.DWORD
        # Force creation of this thread's message queue before stop() can post.
        msg = wintypes.MSG()
        user.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0)
        self.thread_id = kernel.GetCurrentThreadId()
        if self.isInterruptionRequested():
            return

        @callback_type
        def callback(code, message, data_ptr):
            if code >= 0:
                data = ctypes.cast(data_ptr, ctypes.POINTER(KeyboardData)).contents
                if data.vkCode == 0x43:
                    down = message in (0x100, 0x104)
                    up = message in (0x101, 0x105)
                    if down or up:
                        if self.detector.event(down, bool(user.GetAsyncKeyState(0x11) & 0x8000)):
                            self.captured.emit()
            return user.CallNextHookEx(None, code, message, data_ptr)

        hook = user.SetWindowsHookExW(13, callback, kernel.GetModuleHandleW(None), 0)
        if not hook:
            self.unavailable.emit("Windows could not enable double-copy. Paste text into Lilt instead.")
            return
        registered = user.RegisterHotKey(None, 1, 0x4000 | 0x0002 | 0x0001, 0x20)
        if not registered:
            self.warning.emit("Ctrl+Alt+Space is in use by another app. Double-copy is still available.")
        try:
            while not self.isInterruptionRequested() and user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == 0x0312:
                    self.clipboard_requested.emit()
                user.TranslateMessage(ctypes.byref(msg))
                user.DispatchMessageW(ctypes.byref(msg))
        finally:
            if registered:
                user.UnregisterHotKey(None, 1)
            user.UnhookWindowsHookEx(hook)

    def stop(self):
        self.requestInterruption()
        if self.thread_id and sys.platform == "win32":
            user = ctypes.WinDLL("user32", use_last_error=True)
            user.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
            user.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)
        self.wait(2500)
