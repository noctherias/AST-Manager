import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ast_app.timesheet_excel import export_timesheet


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def cell(root, reference):
    return root.find(f".//x:c[@r='{reference}']", NS)


def number_format_id(styles, sheet, reference):
    style_id = int(cell(sheet, reference).get("s", "0"))
    return styles.find("x:cellXfs", NS)[style_id].get("numFmtId", "0")


class TimesheetExcelTests(unittest.TestCase):
    def test_original_package_and_macros_survive_exact_cell_export(self):
        template = Path("templates/Zeiterfassung_Vorlage.xlsm")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "export.xlsm"
            employee = {"first_name": "Max", "last_name": "Muster", "code": "AST-999"}
            records = [
                {"day": "2026-01-05", "start_1": 450, "end_1": 720, "start_2": 780,
                 "end_2": 1035, "break_minutes": 15, "code": "", "note": "Baustelle Zürich"},
                {"day": "2026-01-06", "start_1": None, "end_1": None, "start_2": None,
                 "end_2": None, "break_minutes": 0, "code": "U", "note": "Ferien"},
                {"day": "2026-09-30", "start_1": 420, "end_1": 720, "start_2": 780,
                 "end_2": 1020, "break_minutes": 15, "code": "", "note": ""},
            ]
            export_timesheet(target, employee, 2026, records, "AST Elektro AG")
            with zipfile.ZipFile(template) as source, zipfile.ZipFile(target) as exported:
                self.assertEqual(set(source.namelist()), set(exported.namelist()))
                self.assertEqual(hashlib.sha256(source.read("xl/vbaProject.bin")).digest(),
                                 hashlib.sha256(exported.read("xl/vbaProject.bin")).digest())
                january = ET.fromstring(exported.read("xl/worksheets/sheet6.xml"))
                self.assertAlmostEqual(float(cell(january, "D8").find("x:v", NS).text), 450 / 1440)
                self.assertAlmostEqual(float(cell(january, "H8").find("x:v", NS).text), 15 / 1440)
                self.assertEqual(cell(january, "J9").find("x:is/x:t", NS).text, "U")
                self.assertEqual(cell(january, "O8").find("x:is/x:t", NS).text, "Baustelle Zürich")
                september = ET.fromstring(exported.read("xl/worksheets/sheet14.xml"))
                styles = ET.fromstring(exported.read("xl/styles.xml"))
                self.assertAlmostEqual(float(cell(september, "D33").find("x:v", NS).text), 420 / 1440)
                for reference in ("D33", "E33", "F33", "G33", "H33", "K33", "L33", "N33"):
                    self.assertEqual(number_format_id(styles, september, reference), "185")
                self.assertEqual(number_format_id(styles, september, "M33"), "183")
                self.assertEqual(number_format_id(styles, september, "P33"), "175")
                self.assertTrue(cell(september, "N4").find("x:f", NS).text.endswith("/24"))
                self.assertTrue(cell(september, "L4").find("x:f", NS).text.startswith("IF(AND(D4="))
                self.assertTrue(cell(september, "M4").find("x:f", NS).text.startswith("IF(AND(D4="))
                annual = ET.fromstring(exported.read("xl/worksheets/sheet18.xml"))
                self.assertEqual(number_format_id(styles, annual, "AA33"), "185")
                self.assertEqual(number_format_id(styles, annual, "Z37"), "183")
                settings = ET.fromstring(exported.read("xl/worksheets/sheet1.xml"))
                self.assertEqual(cell(settings, "C2").find("x:v", NS).text, "2026")
                self.assertEqual(cell(settings, "C3").find("x:is/x:t", NS).text, "Max Muster")
                package = b"\n".join(exported.read(name) for name in exported.namelist()
                                     if name.endswith((".xml", ".rels")))
                for private_value in (b"Devinsan", b"Tudisco", b"Hubeli", b"Lehmann"):
                    self.assertNotIn(private_value, package)


if __name__ == "__main__":
    unittest.main()
