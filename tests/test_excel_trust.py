import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from ast_app.excel_trust import ensure_excel_trusted_folder, unblock_excel_file


class _Key:
    def __init__(self, path):
        self.path = path

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ExcelTrustTests(unittest.TestCase):
    def test_registers_only_the_selected_export_folder(self):
        values = []
        fake = types.SimpleNamespace(
            HKEY_CURRENT_USER=1, KEY_WRITE=2, REG_DWORD=3, REG_SZ=4,
            CreateKeyEx=lambda root, path, reserved, access: _Key(path),
            SetValueEx=lambda key, name, reserved, kind, value:
                values.append((key.path, name, kind, value)),
        )
        folder = Path(r"S:\AST\Stundennachweise\Muster_Max\2026")
        with (patch.dict(sys.modules, {"winreg": fake}),
              patch("ast_app.excel_trust.os.name", "nt"),
              patch("ast_app.excel_trust._is_network_path", return_value=True)):
            self.assertIsNone(ensure_excel_trusted_folder(folder))
        self.assertTrue(any(name == "AllowNetworkLocations" and value == 1
                            for _path, name, _kind, value in values))
        trusted_paths = [value for _path, name, _kind, value in values if name == "Path"]
        self.assertEqual(trusted_paths, [str(folder) + "\\"])
        self.assertTrue(any(name == "AllowSubfolders" and value == 1
                            for _path, name, _kind, value in values))

    def test_unblock_removes_only_the_zone_identifier_stream(self):
        with (patch("ast_app.excel_trust.os.name", "nt"),
              patch("ast_app.excel_trust.os.remove") as remove):
            unblock_excel_file(Path(r"C:\Exports\Stundennachweis.xlsm"))
        remove.assert_called_once_with(r"C:\Exports\Stundennachweis.xlsm:Zone.Identifier")


if __name__ == "__main__":
    unittest.main()
