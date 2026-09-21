"""Repository credentials encrypted for the current Windows user using DPAPI."""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path


class Blob(ctypes.Structure):
    _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_byte))]


def crypt(data: bytes, decrypt=False):
    if os.name != "nt":
        raise ValueError("Geschützter GitHub-Zugang ist in der Windows-App verfügbar.")
    buffer = ctypes.create_string_buffer(data)
    source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))
    output = Blob()
    api = ctypes.WinDLL("crypt32", use_last_error=True)
    operation = api.CryptUnprotectData if decrypt else api.CryptProtectData
    operation.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.POINTER(Blob),
                          ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    operation.restype = wintypes.BOOL
    if not operation(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(output)):
        raise ValueError("Der GitHub-Zugang kann unter diesem Windows-Konto nicht geschützt gespeichert oder geöffnet werden (Windows-Fehler " + str(ctypes.get_last_error()) + "). Bitte unter deinem normalen Windows-Konto erneut versuchen.")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    try:
        return ctypes.string_at(output.data, output.size)
    finally:
        kernel.LocalFree(output.data)


def credential_path(directory, repository):
    name = hashlib.sha256(repository.casefold().encode()).hexdigest() + ".bin"
    return Path(directory) / "credentials" / name


def load_token(directory, repository):
    path = credential_path(directory, repository)
    return crypt(path.read_bytes(), True).decode("utf-8") if path.exists() else ""


def save_token(directory, repository, token):
    token = token.strip()
    if not token or len(token) > 512 or not token.isascii() or any(c.isspace() for c in token):
        raise ValueError("Bitte einen gültigen GitHub-Zugangstoken eingeben.")
    payload = crypt(token.encode("utf-8"))
    path = credential_path(directory, repository)
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".tmp")
    partial.write_bytes(payload)
    partial.replace(path)


def delete_token(directory, repository):
    credential_path(directory, repository).unlink(missing_ok=True)
