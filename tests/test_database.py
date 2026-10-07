import tempfile
import unittest
from pathlib import Path

from ast_app.database import Database
from ast_app.backups import run_automatic_backups


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        self.db = Database(self.path)
        self.person = self.db.save_employee({"code": "01", "first_name": "Test", "last_name": "Person", "kind": "apprentice",
                "salutation": "", "ahv": "", "ahv_old": "", "address": "", "postcode": "", "city": "", "hired": "2024-08-01",
                "job": "", "workload": 8000, "allowance": 21625, "active": 1})

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def period(self, year, **extra):
        return self.db.save_period({"employee_id": self.person, "label": str(year), "start": f"{year}-08-01", "end": f"{year+1}-07-31",
                                   "allowance": 21625, "opening": 0, "opening_sick": 0, "opening_accident": 0, **extra})

    def entry(self, p, year, kind, hours):
        return self.db.save_entry({"period_id": p, "day": f"{year}-08-01", "kind": kind, "hours": hours, "note": "Test"})

    def test_three_year_carry_retroactive_and_persistence(self):
        p1, p2, p3 = [self.period(y) for y in (2024, 2025, 2026)]
        key = self.entry(p1, 2024, "vacation", 4325)
        self.entry(p1, 2024, "overtime", 825)
        self.entry(p1, 2024, "sick", 865)
        self.entry(p2, 2025, "vacation", 5000)
        self.entry(p2, 2025, "accident", 1730)
        b = self.db.balances(self.person)
        self.assertEqual([x["balance"] for x in b], [18125, 34750, 56375])
        self.assertEqual(b[2]["sick_total"], 865)
        self.assertEqual(b[2]["accident_total"], 1730)
        self.db.delete("entries", key)
        self.assertEqual(self.db.balances(self.person)[2]["balance"], 60700)
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.balances(self.person)[2]["balance"], 60700)

    def test_period_validation_and_entry_boundaries(self):
        p = self.period(2024)
        with self.assertRaises(ValueError): self.period(2024)
        with self.assertRaises(ValueError): self.period(2025, opening=100)
        with self.assertRaises(ValueError): self.entry(p, 2023, "vacation", 100)
        with self.assertRaises(ValueError): self.entry(p, 2024, "sick", -100)
        self.entry(p, 2024, "overtime", -100)
        self.db.save_entry({"period_id": p, "day": "2025-07-31", "kind": "vacation", "hours": 100, "note": ""})
        row = self.db.periods(self.person)[0]
        with self.assertRaises(ValueError): self.db.save_period({**row, "end": "2025-07-30"}, p)

    def test_insert_earlier_period_does_not_erase_opening(self):
        self.period(2025, opening=500)
        with self.assertRaises(ValueError): self.period(2024)

    def test_payments_and_uniqueness(self):
        customer = self.db.save_customer({"name": "Test AG", "customer_number": "K-2043"})
        data = {"number": "001", "customer_id": customer, "issued": "2026-01-01", "due": "2026-02-01", "amount": 10000, "note": ""}
        invoice = self.db.save_invoice(data)
        with self.assertRaises(ValueError): self.db.save_invoice(data)
        self.db.add_payment(invoice, "2026-01-15", 3333)
        self.assertEqual(self.db.invoices()[0]["open"], 6667)
        self.assertEqual(self.db.invoices()[0]["customer_number"], "K-2043")
        with self.assertRaises(ValueError): self.db.add_payment(invoice, "2026-01-15", 6668)
        with self.assertRaises(ValueError): self.db.save_invoice({**data, "amount": 3000}, invoice)
        with self.assertRaises(ValueError): self.db.delete("invoices", invoice)
        self.db.add_payment(invoice, "2026-01-31", 6667)
        self.assertEqual(self.db.invoices()[0]["status"], "Bezahlt")
        self.assertEqual(self.db.invoices()[0]["valuta"], "2026-01-31")
        self.assertEqual(sum(p["amount"] for p in self.db.payments(invoice)), 10000)

    def test_invoice_reminder_levels(self):
        customer = self.db.save_customer({"name": "Mahnkunde AG"})
        invoice = self.db.save_invoice({"number": "M-1", "customer_id": customer, "issued": "2026-01-01",
                                        "due": "2026-01-31", "amount": 10000, "note": ""})
        self.db.set_reminder(invoice, 2, "2026-02-15")
        row = next(r for r in self.db.invoices() if r["id"] == invoice)
        self.assertEqual((row["reminder_level"], row["reminder_date"]), (2, "2026-02-15"))
        self.db.set_reminder(invoice, 0)
        row = next(r for r in self.db.invoices() if r["id"] == invoice)
        self.assertEqual((row["reminder_level"], row["reminder_date"]), (0, ""))
        self.db.set_reminder(invoice, 4, "2026-03-01")
        self.assertEqual(next(r for r in self.db.invoices() if r["id"] == invoice)["reminder_level"], 4)
        with self.assertRaises(ValueError):
            self.db.set_reminder(invoice, 5, "2026-03-02")

    def test_backup_restore_validation(self):
        self.period(2024)
        backup = Path(self.temp.name) / "backup.sqlite3"
        self.db.backup(backup)
        self.period(2025)
        safety = self.db.restore(backup)
        self.assertTrue(safety.exists())
        self.assertEqual(len(self.db.periods(self.person)), 1)
        self.assertEqual(self.db.conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        self.assertEqual(self.db.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        with self.assertRaises(ValueError): self.db.backup(self.path)

    def test_automatic_external_backup_and_safe_retention(self):
        external = Path(self.temp.name) / "external"
        external.mkdir()
        keep = external / "anderer-name.sqlite3"
        keep.write_text("nicht von AST", encoding="utf-8")
        old = external / "AST-Auto-2026-01-01.sqlite3"
        old.write_text("alt", encoding="utf-8")
        made = run_automatic_backups(self.db, Path(self.temp.name) / "local", external, 30,
                                     __import__("datetime").date(2026, 9, 30))
        self.assertTrue((external / "AST-Auto-2026-09-30.sqlite3").exists())
        self.assertFalse(old.exists())
        self.assertTrue(keep.exists())
        self.assertEqual(len(made), 2)

    def test_salary_snapshot_and_year_constraint(self):
        fields = {"A": "/Ja", "B": "/Off", "HName": "Test Person", "1": "50000", "9": "4000"}
        self.db.save_salary(self.person, 2026, "2026-01-01", "2026-12-31", fields)
        with self.assertRaises(ValueError): self.db.save_salary(self.person, 2026, "2026-01-01", "2026-12-31", fields)
        with self.assertRaises(ValueError): self.db.save_salary(self.person, 2025, "2025-12-01", "2026-01-31", fields)
        e = self.db.employee(self.person)
        self.db.save_employee({**e, "last_name": "Neuer Name"}, self.person)
        self.assertEqual(self.db.salaries()[0]["fields"]["HName"], "Test Person")
        self.assertEqual(self.db.salaries()[0]["fields"]["11"], "46000")

    def test_daily_time_records_are_unique_and_persisted(self):
        data = {"employee_id": self.person, "day": "2026-01-05", "worked_minutes": 525,
                "code": "HO", "note": "Test"}
        key = self.db.save_time_record(data)
        self.assertEqual(self.db.time_records(self.person, 2026)[0]["id"], key)
        self.assertEqual(self.db.time_records(self.person, 2026)[0]["code"], "HO")
        with self.assertRaises(ValueError):
            self.db.save_time_record(data)
        with self.assertRaises(ValueError):
            self.db.save_time_record({**data, "day": "2026-01-06", "worked_minutes": -1})
        with self.assertRaises(ValueError):
            self.db.save_time_record({**data, "day": "2026-01-06", "worked_minutes": 500})
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.time_records(self.person, 2026)[0]["note"], "Test")

    def test_reduced_actual_time_requires_a_reason(self):
        data = {"employee_id": self.person, "day": "2026-01-05", "worked_minutes": 480,
                "code": "", "note": ""}
        with self.assertRaisesRegex(ValueError, "Grund"):
            self.db.save_time_record(data)
        with self.assertRaisesRegex(ValueError, "Bemerkung"):
            self.db.save_time_record({**data, "code": "E1"})
        key = self.db.save_time_record({**data, "code": "E1", "note": "Arzttermin"})
        self.assertEqual(self.db.time_records(self.person, 2026)[0]["id"], key)

    def test_bulk_time_records_skip_or_overwrite_existing_days(self):
        base = {"employee_id": self.person, "worked_minutes": 525,
                "code": "", "note": "Serie"}
        records = [{**base, "day": f"2026-01-0{day}"} for day in (5, 6, 7)]
        first = self.db.save_time_records(records)
        self.assertEqual(first, {"created": 3, "updated": 0, "skipped": 0})
        second = self.db.save_time_records([{**records[0], "note": "Neu"}], overwrite=False)
        self.assertEqual(second["skipped"], 1)
        third = self.db.save_time_records([{**records[0], "note": "Neu"}], overwrite=True)
        self.assertEqual(third["updated"], 1)
        self.assertEqual(self.db.time_records(self.person, 2026)[2]["note"], "Neu")

    def test_old_clock_record_is_converted_to_effective_minutes(self):
        key = self.db.save_time_record({"employee_id": self.person, "day": "2026-01-08",
                                        "start_1": 420, "end_1": 720, "start_2": 780,
                                        "end_2": 1020, "break_minutes": 15, "code": "", "note": "Alt"})
        record = next(row for row in self.db.time_records(self.person, 2026) if row["id"] == key)
        self.assertEqual(record["worked_minutes"], 525)

    def test_version_6_database_migrates_old_clock_records(self):
        self.db.save_time_record({"employee_id": self.person, "day": "2026-01-09",
                                  "start_1": 420, "end_1": 720, "start_2": 780,
                                  "end_2": 990, "break_minutes": 15, "code": "", "note": "Altbestand"})
        with self.db.conn:
            self.db.conn.execute("ALTER TABLE time_records RENAME TO time_records_v7")
            self.db.conn.execute("""CREATE TABLE time_records(
                id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
                day TEXT NOT NULL, start_1 INTEGER, end_1 INTEGER, start_2 INTEGER, end_2 INTEGER,
                break_minutes INTEGER NOT NULL DEFAULT 0, code TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
                UNIQUE(employee_id,day))""")
            self.db.conn.execute("""INSERT INTO time_records(id,employee_id,day,start_1,end_1,start_2,end_2,break_minutes,code,note)
                SELECT id,employee_id,day,start_1,end_1,start_2,end_2,break_minutes,code,note FROM time_records_v7""")
            self.db.conn.execute("DROP TABLE time_records_v7")
            self.db.conn.execute("PRAGMA user_version=6")
        self.db.close()
        self.db = Database(self.path)
        record = next(row for row in self.db.time_records(self.person, 2026) if row["note"] == "Altbestand")
        self.assertEqual(record["worked_minutes"], 495)

    def test_old_time_codes_are_migrated_to_clear_codes(self):
        key = self.db.save_time_record({"employee_id": self.person, "day": "2026-02-02",
                                        "worked_minutes": 0, "code": "U", "note": "Altbestand"})
        self.assertEqual(self.db.one("SELECT code FROM time_records WHERE id=?", (key,))["code"], "U")
        with self.db.conn:
            self.db.conn.execute("UPDATE time_records SET code='KR' WHERE id=?", (key,))
            self.db.conn.execute("PRAGMA user_version=11")
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.one("SELECT code FROM time_records WHERE id=?", (key,))["code"], "K")

        with self.db.conn:
            self.db.conn.execute("UPDATE time_records SET code='T' WHERE id=?", (key,))
            self.db.conn.execute("PRAGMA user_version=13")
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.one("SELECT code FROM time_records WHERE id=?", (key,))["code"], "H")

        homeoffice = self.db.save_time_record({
            "employee_id": self.person, "day": "2026-02-03",
            "worked_minutes": 525, "code": "HO", "note": "Homeoffice",
        })
        with self.db.conn:
            self.db.conn.execute("UPDATE time_records SET code='FT' WHERE id=?", (key,))
            self.db.conn.execute("UPDATE time_records SET code='H' WHERE id=?", (homeoffice,))
            self.db.conn.execute("PRAGMA user_version=14")
        self.db.close()
        self.db = Database(self.path)
        self.assertEqual(self.db.one("SELECT code FROM time_records WHERE id=?", (key,))["code"], "H")
        self.assertEqual(self.db.one("SELECT code FROM time_records WHERE id=?", (homeoffice,))["code"], "HO")


if __name__ == "__main__": unittest.main()
