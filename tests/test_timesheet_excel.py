import hashlib
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

from ast_app.timesheet_excel import export_timesheet, monthly_summary, monthly_target_minutes


NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def cell(root, reference):
    return root.find(f".//x:c[@r='{reference}']", NS)


def number_format_id(styles, sheet, reference):
    style_id = int(cell(sheet, reference).get("s", "0"))
    return styles.find("x:cellXfs", NS)[style_id].get("numFmtId", "0")


def fill_id(styles, sheet, reference):
    style_id = int(cell(sheet, reference).get("s", "0"))
    return styles.find("x:cellXfs", NS)[style_id].get("fillId", "0")


def fill_rgb(styles, sheet, reference):
    fill = styles.find("x:fills", NS)[int(fill_id(styles, sheet, reference))]
    color = fill.find("x:patternFill/x:fgColor", NS)
    return color.get("rgb") if color is not None else None


class TimesheetExcelTests(unittest.TestCase):
    def test_original_package_and_macros_survive_exact_cell_export(self):
        template = Path("templates/Zeiterfassung_Vorlage.xlsm")
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "export.xlsm"
            employee = {"first_name": "Max", "last_name": "Muster", "code": "AST-999"}
            records = [
                {"day": "2026-01-05", "worked_minutes": 525, "code": "", "note": "Baustelle Zürich"},
                {"day": "2026-01-06", "worked_minutes": 525, "code": "F", "note": "Ferien"},
                {"day": "2026-01-07", "worked_minutes": 225, "code": "K", "note": "Krank am Vormittag"},
                {"day": "2026-01-08", "worked_minutes": 45, "code": "M", "note": "Arzttermin"},
                {"day": "2026-01-09", "worked_minutes": 600, "code": "", "note": "Mehrarbeit"},
                {"day": "2026-01-12", "worked_minutes": 300, "code": "U", "note": "Unfall"},
                {"day": "2026-09-30", "worked_minutes": 525, "code": "", "note": ""},
            ]
            export_timesheet(target, employee, 2026, records, "AST Elektro AG")
            with zipfile.ZipFile(template) as source, zipfile.ZipFile(target) as exported:
                expected_members = set(source.namelist()) - {"xl/calcChain.xml"}
                self.assertEqual(expected_members, set(exported.namelist()))
                self.assertNotIn(b"calcChain.xml", exported.read("[Content_Types].xml"))
                self.assertNotIn(b"calcChain.xml", exported.read("xl/_rels/workbook.xml.rels"))
                self.assertEqual(hashlib.sha256(source.read("xl/vbaProject.bin")).digest(),
                                 hashlib.sha256(exported.read("xl/vbaProject.bin")).digest())
                for sheet_name in [f"xl/worksheets/sheet{number}.xml" for number in range(6, 18)]:
                    removed_formulas = (source.read(sheet_name).count(b"<f")
                                        - exported.read(sheet_name).count(b"<f"))
                    self.assertIn(removed_formulas, {20, 21, 22})
                january = ET.fromstring(exported.read("xl/worksheets/sheet6.xml"))
                self.assertAlmostEqual(float(cell(january, "D8").find("x:v", NS).text), 8.75)
                self.assertEqual(cell(january, "D3").find("x:is/x:t", NS).text, "Arbeitszeit (h)")
                self.assertIsNone(cell(january, "E8").find("x:v", NS))
                self.assertEqual(cell(january, "J9").find("x:is/x:t", NS).text, "F")
                self.assertEqual(cell(january, "J3").find("x:is/x:t", NS).text, "Grund")
                self.assertEqual(cell(january, "O8").find("x:is/x:t", NS).text, "Baustelle Zürich")
                expected_summary = {"P36": 1.75, "P37": 8.75, "P38": 3.75,
                                    "P39": 5.0, "P40": 0.75}
                for reference, expected in expected_summary.items():
                    self.assertAlmostEqual(float(cell(january, reference).find("x:v", NS).text), expected)
                    self.assertIsNotNone(cell(january, reference).find("x:f", NS))
                self.assertEqual(cell(january, "K36").find("x:v", NS).text,
                                 "Überstunden geleistet · automatisch (h)")
                styles = ET.fromstring(exported.read("xl/styles.xml"))
                self.assertIsNone(cell(january, "J36").find("x:f", NS))
                self.assertIsNone(cell(january, "J37").find("x:f", NS))
                self.assertEqual(cell(january, "K39").find("x:v", NS).text,
                                 "Unfall · U (h)")
                self.assertIn("F Ferien/Freizeit", cell(january, "K41").find("x:is/x:t", NS).text)
                self.assertIn("H Feiertag", cell(january, "K42").find("x:is/x:t", NS).text)
                self.assertIn("HO Homeoffice", cell(january, "K42").find("x:is/x:t", NS).text)
                expected_colours = {
                    36: "FFDDF3E4", 37: "FFDCEEFF", 38: "FFFFF2CC",
                    39: "FFF7D6D6", 40: "FFFCE4D6",
                }
                for row, expected_colour in expected_colours.items():
                    self.assertEqual(fill_rgb(styles, january, f"K{row}"), expected_colour)
                    self.assertEqual(fill_rgb(styles, january, f"P{row}"), expected_colour)
                positive_balance = next(
                    rule for rule in january.findall("x:conditionalFormatting", NS)
                    if rule.get("sqref") == "P4:P34"
                ).find("x:cfRule", NS)
                self.assertEqual(positive_balance.get("operator"), "greaterThan")
                self.assertEqual(positive_balance.find("x:formula", NS).text, "0")
                dxf = styles.find("x:dxfs", NS)[int(positive_balance.get("dxfId"))]
                self.assertEqual(dxf.find("x:font/x:color", NS).get("rgb"), "FF008A67")
                hidden_ranges = [(int(item.get("min")), int(item.get("max")))
                                 for item in january.find("x:cols", NS) if item.get("hidden") == "1"]
                self.assertTrue(all(any(first <= column <= last for first, last in hidden_ranges)
                                    for column in range(5, 10)))
                self.assertIn('J4="K"', cell(january, "K4").find("x:f", NS).text)
                self.assertIn('MAX(0,L4-', cell(january, "K4").find("x:f", NS).text)
                self.assertIn('J5="K"', cell(january, "K5").find("x:f", NS).text)
                self.assertIn('J4="H"', cell(january, "L4").find("x:f", NS).text)
                self.assertAlmostEqual(float(cell(january, "F37").find("x:v", NS).text),
                                       monthly_target_minutes(2026, 1) / 60)
                self.assertEqual(cell(january, "F40").find("x:f", NS).text,
                                 "ROUND(F36+SUM(M4:M34),14)")
                september = ET.fromstring(exported.read("xl/worksheets/sheet14.xml"))
                self.assertAlmostEqual(float(cell(september, "D33").find("x:v", NS).text), 8.75)
                for reference in ("D33", "E33", "F33", "G33", "H33", "K33", "L33", "N33"):
                    self.assertEqual(number_format_id(styles, september, reference), "176")
                self.assertEqual(number_format_id(styles, september, "M33"), "176")
                self.assertEqual(number_format_id(styles, september, "P33"), "176")
                self.assertFalse(cell(september, "N4").find("x:f", NS).text.endswith("/24"))
                self.assertTrue(cell(september, "L4").find("x:f", NS).text.startswith('IF(A4=""'))
                self.assertTrue(cell(september, "M4").find("x:f", NS).text.startswith("IF(AND(D4="))
                self.assertTrue(cell(september, "M34").find("x:f", NS).text.startswith("IF(AND(D34="))
                annual = ET.fromstring(exported.read("xl/worksheets/sheet18.xml"))
                self.assertEqual(fill_rgb(styles, annual, "B4"), "FFF4B6D7")
                # 1 August 2026 is a Saturday: the holiday colour must win.
                self.assertEqual(fill_rgb(styles, annual, "W4"), "FFF4B6D7")
                self.assertEqual(fill_rgb(styles, annual, "B6"), "FFFFD59A")
                self.assertEqual(fill_rgb(styles, annual, "B7"), "FFFFD59A")
                self.assertNotIn(fill_rgb(styles, annual, "B8"), {"FFF4B6D7", "FFFFD59A"})
                self.assertEqual(fill_rgb(styles, annual, "B9"), "FFDCEEFF")
                self.assertEqual(number_format_id(styles, annual, "AA33"), "176")
                self.assertEqual(number_format_id(styles, annual, "Z37"), "176")
                self.assertEqual(cell(annual, "A37").find("x:is/x:t", NS).text,
                                 "Überstunden · automatisch (h)")
                self.assertEqual(cell(annual, "B37").find("x:f", NS).text, "Januar!P36")
                self.assertAlmostEqual(float(cell(annual, "B35").find("x:v", NS).text),
                                       monthly_target_minutes(2026, 1) / 60)
                self.assertEqual(cell(annual, "B35").find("x:f", NS).text, "Januar!F37")
                self.assertEqual(cell(annual, "AL35").find("x:f", NS).get("t"), "shared")
                self.assertEqual(cell(annual, "AL35").find("x:f", NS).get("ref"), "AL35:AL50")
                self.assertIn('Januar!J4:J34="F"', cell(annual, "B43").find("x:f", NS).text)
                annual_colours = {row + 1: colour for row, colour in expected_colours.items()}
                for row, expected_colour in annual_colours.items():
                    self.assertEqual(fill_rgb(styles, annual, f"A{row}"), expected_colour)
                    self.assertEqual(fill_rgb(styles, annual, f"B{row}"), expected_colour)
                    self.assertEqual(fill_rgb(styles, annual, f"AL{row}"), expected_colour)
                self.assertEqual(cell(annual, "A40").find("x:is/x:t", NS).text,
                                 "Unfall · U (h)")
                self.assertEqual(cell(annual, "B40").find("x:f", NS).text, "Januar!P39")
                self.assertIsNone(annual.find(".//x:row[@r='42']", NS).get("hidden"))
                self.assertEqual(annual.find(".//x:row[@r='43']", NS).get("hidden"), "1")
                self.assertIsNone(annual.find(".//x:row[@r='44']", NS).get("hidden"))
                self.assertEqual(cell(annual, "A44").find("x:is/x:t", NS).text, "Ferien-Soll (h)")
                self.assertAlmostEqual(float(cell(annual, "AL44").find("x:v", NS).text), 173.0)
                settings = ET.fromstring(exported.read("xl/worksheets/sheet1.xml"))
                self.assertEqual(cell(settings, "C2").find("x:v", NS).text, "2026")
                self.assertEqual(cell(settings, "C3").find("x:is/x:t", NS).text, "Max Muster")
                expected_codes = ["F", "K", "U", "M", "H", "HO", "B"]
                self.assertEqual([cell(settings, f"B{row}").find("x:is/x:t", NS).text
                                  for row in range(20, 27)], expected_codes)
                self.assertEqual(cell(settings, "A23").find("x:is/x:t", NS).text,
                                 "Andere begründete Minderzeit")
                october_xml = exported.read("xl/worksheets/sheet15.xml").decode("utf-8")
                self.assertIn('$J4=&quot;F&quot;', october_xml)
                self.assertIn('$J4=&quot;K&quot;', october_xml)
                self.assertNotIn('$J4=Voreinstellungen!$B$33', october_xml)
                for reference in ("D12", "E12", "F12", "G12"):
                    self.assertEqual(float(cell(settings, reference).find("x:v", NS).text), 8.75)
                self.assertEqual(float(cell(settings, "H12").find("x:v", NS).text), 8.25)
                locations = ET.fromstring(exported.read("xl/worksheets/sheet5.xml"))
                self.assertEqual(cell(locations, "A2").find("x:is/x:t", NS).text, "Max Muster")
                self.assertEqual(Path(cell(locations, "B2").find("x:is/x:t", NS).text), target.parent)
                package = b"\n".join(exported.read(f"xl/worksheets/sheet{number}.xml")
                                     for number in range(6, 19))
                for private_value in (b"Devinsan", b"Tudisco", b"Hubeli", b"Lehmann"):
                    self.assertNotIn(private_value, package)

    def test_monthly_summary_counts_only_recorded_reasons(self):
        records = [
            {"day": "2026-02-02", "worked_minutes": 600, "code": ""},
            {"day": "2026-02-03", "worked_minutes": 525, "code": "F"},
            {"day": "2026-02-04", "worked_minutes": 225, "code": "K"},
            {"day": "2026-02-05", "worked_minutes": 45, "code": "M"},
            {"day": "2026-02-06", "worked_minutes": 0, "code": "T"},
        ]
        self.assertEqual(monthly_summary(records, 2026, 2), {
            "overtime": 75, "vacation": 525, "sick": 225, "accident": 0, "other": 45,
        })

    def test_sickness_summary_adds_entered_absence_hours(self):
        records = [
            {"day": "2025-10-08", "worked_minutes": 0, "code": "K"},
            {"day": "2025-10-09", "worked_minutes": 240, "code": "K"},
        ]
        self.assertEqual(monthly_summary(records, 2025, 10)["sick"], 240)
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "october.xlsm"
            export_timesheet(target, {"first_name": "Max", "last_name": "Muster",
                                      "code": "AST-999"}, 2025, records, "AST Elektro AG")
            with zipfile.ZipFile(target) as exported:
                october = ET.fromstring(exported.read("xl/worksheets/sheet15.xml"))
                annual = ET.fromstring(exported.read("xl/worksheets/sheet18.xml"))
                self.assertAlmostEqual(float(cell(october, "P38").find("x:v", NS).text), 4.0)
                self.assertEqual(cell(october, "P38").find("x:f", NS).text,
                                 'SUMIF(J4:J34,"K",D4:D34)')
                self.assertAlmostEqual(float(cell(october, "K11").find("x:v", NS).text), 8.75)
                self.assertAlmostEqual(float(cell(october, "K12").find("x:v", NS).text), 4.75)
                self.assertAlmostEqual(float(cell(october, "M12").find("x:v", NS).text), -4.0)
                self.assertAlmostEqual(float(cell(annual, "AC39").find("x:v", NS).text), 4.0)
                self.assertAlmostEqual(float(cell(annual, "AL39").find("x:v", NS).text), 4.0)
                package = b"\n".join(exported.read(name) for name in exported.namelist()
                                     if name.endswith((".xml", ".rels")))
                for marker in (b"#REF!", b"#VALUE!", b"#N/A"):
                    self.assertNotIn(marker, package)

    def test_apprentice_receives_annual_vacation_target(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "apprentice.xlsm"
            export_timesheet(target, {
                "first_name": "Lena", "last_name": "Lernende", "code": "AST-007",
                "kind": "apprentice", "allowance": 17300,
            }, 2026, [], "AST Elektro AG")
            with zipfile.ZipFile(target) as exported:
                annual = ET.fromstring(exported.read("xl/worksheets/sheet18.xml"))
                self.assertAlmostEqual(float(cell(annual, "B44").find("x:v", NS).text),
                                       216.25 / 12)
                self.assertAlmostEqual(float(cell(annual, "AL44").find("x:v", NS).text), 216.25)


if __name__ == "__main__":
    unittest.main()
