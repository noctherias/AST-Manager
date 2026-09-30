from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader
from ast_app.documents import salary_pdf, field_name, resource_path, csv_export, report_pdf
from ast_app.domain import SALARY_AMOUNTS, SALARY_TEXT, SALARY_FLAGS
from ast_app.reminders import reminder_pdf, validate_template
from PIL import Image


class DocumentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp.cleanup()

    def test_source_widgets_have_unambiguous_canonical_fields(self):
        r = PdfReader(resource_path("templates/Vorlage_Lohnausweis.pdf"))
        canonical = {}
        def visit(ref):
            obj = ref.get_object()
            canonical[field_name(obj)] = ref.idnum
            for kid in obj.get("/Kids", []): visit(kid)
        for ref in r.trailer["/Root"]["/AcroForm"]["/Fields"]: visit(ref)
        for page in r.pages:
            for ref in page.get("/Annots", []):
                obj = ref.get_object()
                if obj.get("/Subtype") == "/Widget":
                    self.assertEqual(canonical[field_name(obj)], ref.idnum)

    def test_all_fields_filled_and_sample_values_cleared(self):
        fields = {k: "100" for k, _ in SALARY_AMOUNTS}
        fields.update({k: "Testtext" for k, _ in SALARY_TEXT})
        fields.update({k: "/Ja" for k, _ in SALARY_FLAGS})
        fields.update({"A": "/Ja", "B": "/Off", "D": "2026", "E-von": "01.01.", "E-bis": "31.12.",
                       "C": "", "C2": "756.0000.0000.00", "HAnrede": "Frau", "HName": "Lena Muster", "HAdresse": "Musterstrasse 4",
                       "HPostfach": "", "HWohnort": "4663 Aarburg", "OrtDatum": "Aarburg, 20.09.2026"})
        fields.update({f"Unterschrift1.{i}": text for i, text in enumerate(["AST Muster AG", "Werkstrasse 12", "4663 Aarburg", "+41 62 000 00 00", "Administration"])})
        path = Path(self.temp.name) / "salary.pdf"
        salary_pdf(fields, path)
        r = PdfReader(path)
        self.assertNotIn("/AcroForm", r.trailer["/Root"])
        self.assertFalse(any(a.get_object().get("/Subtype") == "/Widget"
                             for page in r.pages for a in page.get("/Annots", [])))
        text = "\n".join(page.extract_text() or "" for page in r.pages)
        for value in ("Lena Muster", "Musterstrasse 4", "756.0000.0000.00", "900", "600"):
            self.assertIn(value, text)
        self.assertEqual(len(r.pages), 1)
        salary_pdf({"A": "/Ja", "B": "/Off", "HName": "Neue Person", "1": "1000"}, path)
        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        self.assertIn("Neue Person", text)
        self.assertIn("1000", text)
        self.assertNotIn("Lena Muster", text)

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError): salary_pdf({"not-a-field": "x"}, Path(self.temp.name) / "bad.pdf")

    def test_reminder_letter_with_custom_text_and_logo(self):
        logo = Path(self.temp.name) / "logo.png"
        Image.new("RGB", (320, 100), "#087e67").save(logo)
        invoice = {"number": "R-204", "customer": "Musterkunde AG", "customer_address": "Dorfstrasse 4",
                   "customer_postcode": "5000", "customer_city": "Aarau", "issued": "2026-08-01",
                   "due": "2026-08-31", "open": 125050}
        settings = {"company": "AST Muster AG", "address": "Werkstrasse 1", "postcode": "5000",
                    "city": "Aarau", "phone": "+41 62 000 00 00", "contact": "Administration",
                    "logo_path": str(logo)}
        path = Path(self.temp.name) / "mahnung.pdf"
        reminder_pdf(path, invoice, settings, 3,
                     "Bitte begleichen Sie {betrag} für Rechnung {rechnungsnummer} bis {frist}.")
        text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        for value in ("Mahnung 2", "R-204", "Musterkunde AG", "CHF 1’250.50", "AST Muster AG"):
            self.assertIn(value, text)
        self.assertGreater(path.stat().st_size, 2000)
        self.assertEqual(validate_template("Hallo {kunde}"), "Hallo {kunde}")
        with self.assertRaises(ValueError):
            validate_template("Hallo {unbekannt}")

    def test_csv_and_multipage_report(self):
        path = Path(self.temp.name) / "data.csv"
        csv_export(path, ["Text", "Betrag"], [["=1+1", "20.00"], ["Müller", "1.25"]])
        self.assertIn("'=1+1", path.read_text(encoding="utf-8-sig"))
        report = Path(self.temp.name) / "report.pdf"
        report_pdf(report, "Stundennachweis", "Test", ["Datum", "Bemerkung"],
                   [["01.01.2026", f"Buchung {i}"] for i in range(150)], "Summe: 150")
        self.assertGreater(len(PdfReader(report).pages), 1)


if __name__ == "__main__": unittest.main()
