from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader
from ast_app.documents import salary_pdf, field_name, resource_path, csv_export, report_pdf
from ast_app.domain import SALARY_AMOUNTS, SALARY_TEXT, SALARY_FLAGS


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
        actual = r.get_fields()
        for k, v in fields.items(): self.assertEqual(str(actual[k].get("/V", "")), v)
        self.assertEqual(actual["8"]["/V"], "900")
        self.assertEqual(actual["11"]["/V"], "600")
        self.assertEqual(len(r.pages), 1)
        self.assertFalse(any("Anthony" in str(f.get("/V", "")) for f in actual.values()))
        salary_pdf({"A": "/Ja", "B": "/Off", "HName": "Neue Person", "1": "1000"}, path)
        actual = PdfReader(path).get_fields()
        self.assertEqual(actual["E-bis"]["/V"], "")
        self.assertEqual(actual["OrtDatum"]["/V"], "")
        self.assertEqual(actual["1"]["/V"], "1000")
        self.assertEqual(actual["11"]["/V"], "1000")

    def test_unknown_field_rejected(self):
        with self.assertRaises(ValueError): salary_pdf({"not-a-field": "x"}, Path(self.temp.name) / "bad.pdf")

    def test_csv_and_multipage_report(self):
        path = Path(self.temp.name) / "data.csv"
        csv_export(path, ["Text", "Betrag"], [["=1+1", "20.00"], ["Müller", "1.25"]])
        self.assertIn("'=1+1", path.read_text(encoding="utf-8-sig"))
        report = Path(self.temp.name) / "report.pdf"
        report_pdf(report, "Stundennachweis", "Test", ["Datum", "Bemerkung"],
                   [["01.01.2026", f"Buchung {i}"] for i in range(150)], "Summe: 150")
        self.assertGreater(len(PdfReader(report).pages), 1)


if __name__ == "__main__": unittest.main()
