"""Register only AST export folders as trusted Excel locations on Windows."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path


def _is_network_path(folder: Path) -> bool:
    text = str(folder)
    if text.startswith("\\\\"):
        return True
    if os.name != "nt" or not folder.drive:
        return False
    try:
        from ctypes import windll
        return windll.kernel32.GetDriveTypeW(folder.drive + "\\") == 4
    except Exception:
        return False


def ensure_excel_trusted_folder(folder) -> str | None:
    """Trust one export directory and its employee/year subfolders.

    Returns an error description when Windows or Office rejected the setting.
    Export itself remains successful in that case.
    """
    if os.name != "nt":
        return None
    try:
        import winreg

        folder = Path(folder).absolute()
        path_text = str(folder).rstrip("\\/") + "\\"
        digest = sha256(path_text.casefold().encode("utf-8")).hexdigest()[:8]
        locations = r"Software\Microsoft\Office\16.0\Excel\Security\Trusted Locations"
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, locations, 0, winreg.KEY_WRITE) as root:
            if _is_network_path(folder):
                winreg.SetValueEx(root, "AllowNetworkLocations", 0, winreg.REG_DWORD, 1)
        # Office conventionally discovers trusted locations through LocationN
        # subkeys. A path-derived number keeps the entry stable across exports.
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                locations + "\\Location" + str(int(digest, 16)),
                                0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, "Path", 0, winreg.REG_SZ, path_text)
            winreg.SetValueEx(key, "AllowSubfolders", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "Description", 0, winreg.REG_SZ,
                              "AST Manager · Stundennachweise")
        return None
    except Exception as exc:
        return str(exc)


def unblock_excel_file(path) -> None:
    """Remove Windows' downloaded-file marker from a generated workbook."""
    if os.name != "nt":
        return
    try:
        os.remove(str(Path(path)) + ":Zone.Identifier")
    except (FileNotFoundError, OSError):
        pass
