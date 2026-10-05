import unittest
from datetime import date

from ast_app.domain import (units, invoice_state, period_balance, salary_totals, GROSS_FIELDS,
                            scheduled_work_minutes, worked_minutes)


class DomainTests(unittest.TestCase):
    def test_regular_working_time_and_legacy_conversion(self):
        self.assertEqual(scheduled_work_minutes("2026-01-05"), 525)
        self.assertEqual(scheduled_work_minutes("2026-01-09"), 495)
        self.assertEqual(scheduled_work_minutes("2026-01-10"), 0)
        self.assertEqual(worked_minutes({"start_1": 420, "end_1": 720, "start_2": 780,
                                         "end_2": 1020, "break_minutes": 15}), 525)

    def test_exact_numbers_and_swiss_format(self):
        self.assertEqual(units("1’234,50"), 123450)
        self.assertEqual(units("216.25"), 21625)
        self.assertEqual(units("-8.65"), -865)
        for invalid in ["1.001", "NaN", "Infinity", "abc"]:
            with self.assertRaises(ValueError): units(invalid)

    def test_invoice_status_boundaries(self):
        today = date(2026, 9, 20)
        self.assertEqual(invoice_state(10000, 0, "2026-09-20", today), "Offen")
        self.assertEqual(invoice_state(10000, 2000, "2026-09-20", today), "Teilbezahlt")
        self.assertEqual(invoice_state(10000, 2000, "2026-09-19", today), "Überfällig")
        self.assertEqual(invoice_state(10000, 10000, "2026-09-19", today), "Bezahlt")

    def test_negative_balance_and_cumulative_absences(self):
        b = period_balance(21625, 23000, -150, -400, 865, 1730, 1000, 2000)
        self.assertEqual(b["balance"], -1925)
        self.assertEqual(b["sick_total"], 1865)
        self.assertEqual(b["accident_total"], 3730)

    def test_salary_original_calculation(self):
        fields = {k: "1000" for k in GROSS_FIELDS}
        fields.update({"9": "500", "10-1": "300", "10-2": "200", "12": "700", "13-1-1-2": "400"})
        self.assertEqual(salary_totals(fields), {"8": "9000", "abzuege": "1000", "11": "8000"})
        self.assertEqual(salary_totals({}), {"8": "", "abzuege": "0", "11": ""})
        with self.assertRaises(ValueError): salary_totals({"1": "5.5"})
        with self.assertRaises(ValueError): salary_totals({"1": "100", "9": "101"})


if __name__ == "__main__": unittest.main()
