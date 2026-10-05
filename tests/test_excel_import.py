from datetime import date
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from ast_app.database import Database
from ast_app.excel_import import import_debtors, import_timesheet
from ast_app.timesheet_excel import export_timesheet


class ExcelImportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "import.sqlite3")
        self.employee = self.db.save_employee({
            "code": "AST-001", "first_name": "Max", "last_name": "Muster", "kind": "employee",
            "salutation": "", "ahv": "", "ahv_old": "", "birth_date": "", "address": "",
            "postcode": "", "city": "", "hired": "2026-01-01", "job": "", "workload": 10000,
            "allowance": 20000, "active": 1,
        })

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_debtor_import_creates_customer_invoice_and_payment(self):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Datum Rechnung", "Nummer Rechnung", "Name", "Valuta Datum", "Betrag Rechnung", "Betrag Bezahlt"])
        sheet.append([date(2026, 1, 5), "R-100", "Beispiel AG", date(2026, 1, 20), 1250.50, 250.50])
        path = self.root / "debitoren.xlsx"
        workbook.save(path)
        result = import_debtors(self.db, path)
        self.assertEqual((result["imported"], result["payments"]), (1, 1))
        invoice = self.db.invoices()[0]
        self.assertEqual((invoice["amount"], invoice["paid"], invoice["open"]), (125050, 25050, 100000))
        self.assertEqual(import_debtors(self.db, path)["skipped"], 1)

    def test_exported_timesheet_can_be_imported_for_another_person(self):
        source = [{"day": "2026-09-30", "worked_minutes": 525,
                   "code": "H", "note": "Baustelle"}]
        path = self.root / "zeiten.xlsm"
        export_timesheet(path, self.db.employee(self.employee), 2026, source, "AST AG")
        result = import_timesheet(self.db, path, self.employee)
        self.assertEqual(result["created"], 1)
        record = self.db.time_records(self.employee, 2026)[0]
        self.assertEqual((record["worked_minutes"], record["start_1"], record["note"]),
                         (525, None, "Baustelle"))


if __name__ == "__main__":
    unittest.main()
