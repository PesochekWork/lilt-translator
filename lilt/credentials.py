"""Protect optional service credentials with the signed-in Windows account."""
import base64
import ctypes
from ctypes import wintypes
import json
import os
import sys
from pathlib import Path


def _protect(data: bytes, decrypt=False) -> bytes:
    if sys.platform != "win32":
        raise RuntimeError("Credential storage requires Windows.")
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel.LocalFree.restype = wintypes.HLOCAL
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptProtectData.restype = wintypes.BOOL
    crypt.CryptUnprotectData.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    if decrypt:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(target))
    else:
        ok = crypt.CryptProtectData(ctypes.byref(source), "Lilt", None, None, None, 1, ctypes.byref(target))
    if not ok:
        raise RuntimeError("Windows could not protect this credential.")
    try:
        return ctypes.string_at(target.data, target.size)
    finally:
        kernel.LocalFree(ctypes.cast(target.data, wintypes.HLOCAL))


class Credentials:
    def __init__(self, directory: Path):
        self.path = directory / "credentials.dpapi"

    def read(self):
        try:
            values = json.loads(_protect(base64.b64decode(self.path.read_bytes()), decrypt=True))
            return values if isinstance(values, dict) and all(isinstance(k, str) and isinstance(v, str) for k, v in values.items()) else {}
        except (OSError, ValueError, RuntimeError):
            return {}

    def write(self, values):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        encrypted = base64.b64encode(_protect(json.dumps(values).encode("utf-8")))
        temporary = self.path.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        os.replace(temporary, self.path)
