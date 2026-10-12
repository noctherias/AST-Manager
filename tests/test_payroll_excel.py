import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ast_app.payroll_excel import export_payroll_book


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def cell(root, reference):
    return root.find(f".//x:c[@r='{reference}']", NS)


class PayrollExcelTests(unittest.TestCase):
    def test_template_is_filled_and_formulas_remain_active(self):
        employee = {
            "first_name": "Lena", "last_name": "Muster", "code": "AST-007",
            "ahv": "756.0000.0000.00", "birth_date": "2000-05-06",
            "address": "Testweg 4", "postcode": "5000", "city": "Aarau",
        }
        record = {
            "year": 2026, "month": 5, "gross": 600000, "allowance": 10000,
            "ahv_rate": 5300, "alv_rate": 1100, "nbuv_rate": 1670,
            "ktv_rate": 1855, "bvg_rate": 2000, "pk_rate": 1000,
            "ahv": 31800, "alv": 6600, "nbuv": 10000, "ktv": 11150,
            "bvg": 12000, "pk": 6000, "deductions": 77550, "net": 532450,
        }
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "lohn.xlsx"
            export_payroll_book(target, employee, 2026, [record], {"city": "Aarburg"})
            with zipfile.ZipFile(target) as exported:
                self.assertIsNone(exported.testzip())
                sheet = ET.fromstring(exported.read("xl/worksheets/sheet1.xml"))
                self.assertEqual(cell(sheet, "L3").find("x:v", NS).text, "2026")
                self.assertEqual(cell(sheet, "J13").find("x:is/x:t", NS).text, "Muster Lena")
                self.assertAlmostEqual(float(cell(sheet, "C34").find("x:v", NS).text), 6000)
                self.assertIn("C34*0.053", cell(sheet, "F34").find("x:f", NS).text)
                self.assertEqual(cell(sheet, "M34").find("x:f", NS).text,
                                 "C34-SUM(F34:K34)+L34")
                self.assertAlmostEqual(float(cell(sheet, "M34").find("x:v", NS).text), 5324.5)
                package = b"\n".join(exported.read(name) for name in exported.namelist()
                                     if name.endswith(".xml"))
                for private_value in (b"Manuel", b"756.8651.7713.19", b"Hauptstrasse 63"):
                    self.assertNotIn(private_value, package)
                for marker in (b"#REF!", b"#DIV/0!", b"#VALUE!", b"#NAME?", b"#N/A"):
                    self.assertNotIn(marker, package)


if __name__ == "__main__":
    unittest.main()
