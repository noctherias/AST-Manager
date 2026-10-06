import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ast_app import export_paths


class Settings:
    def __init__(self, values=None):
        self.values = values or {}

    def settings(self):
        return self.values


class ExportPathTests(unittest.TestCase):
    def test_every_export_uses_its_server_subfolder_by_default(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for subfolder in set(export_paths.DEFAULT_EXPORT_FOLDERS.values()):
                (root / subfolder).mkdir()
            with patch.object(export_paths, "DEFAULT_EXPORT_ROOT", root), \
                 patch.object(export_paths.os, "name", "nt"):
                for key, subfolder in export_paths.DEFAULT_EXPORT_FOLDERS.items():
                    self.assertEqual(export_paths.configured_directory(Settings(), key),
                                     root / subfolder)

    def test_saved_path_overrides_default(self):
        expected = Path(r"D:\Eigene Exporte")
        db = Settings({export_paths.setting_key("salary_pdf"): str(expected)})
        self.assertEqual(export_paths.configured_directory(db, "salary_pdf"), expected)

    def test_old_common_reference_path_remains_compatible(self):
        expected = Path(r"D:\Alte Zeugnisse")
        db = Settings({export_paths.setting_key("references_pdf"): str(expected)})
        self.assertEqual(export_paths.configured_directory(db, "references_work_pdf"), expected)


if __name__ == "__main__":
    unittest.main()
