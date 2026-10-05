"""Small Windows-DPAPI wrapper for local application secrets."""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
import os


class _Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def _blob(value: bytes):
    buffer = ctypes.create_string_buffer(value)
    return _Blob(len(value), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def protect_secret(value: str) -> str:
    """Encrypt text for the current Windows user and return portable ASCII ciphertext."""
    if not value:
        return ""
    if os.name != "nt":
        raise OSError("Die sichere Passwortspeicherung ist nur unter Windows verfügbar.")
    source, keepalive = _blob(value.encode("utf-8"))
    target = _Blob()
    if not ctypes.windll.crypt32.CryptProtectData(ctypes.byref(source), "AST Manager", None, None, None,
                                                  0, ctypes.byref(target)):
        raise ctypes.WinError()
    try:
        return base64.b64encode(ctypes.string_at(target.data, target.size)).decode("ascii")
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)


def unprotect_secret(value: str) -> str:
    """Decrypt a value created by :func:`protect_secret` for this Windows user."""
    if not value:
        return ""
    if os.name != "nt":
        raise OSError("Die sichere Passwortspeicherung ist nur unter Windows verfügbar.")
    try:
        encoded = base64.b64decode(value, validate=True)
    except (ValueError, TypeError) as exc:
        raise ValueError("Das gespeicherte Serverpasswort ist ungültig.") from exc
    source, keepalive = _blob(encoded)
    target = _Blob()
    if not ctypes.windll.crypt32.CryptUnprotectData(ctypes.byref(source), None, None, None, None,
                                                    0, ctypes.byref(target)):
        raise ValueError("Das Serverpasswort gehört zu einem anderen Windows-Benutzer.")
    try:
        return ctypes.string_at(target.data, target.size).decode("utf-8")
    finally:
        ctypes.windll.kernel32.LocalFree(target.data)
