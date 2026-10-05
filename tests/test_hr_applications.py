import json
from pathlib import Path
import tempfile
import unittest

from pypdf import PdfReader

from ast_app.applications import sync_manifests
from ast_app.database import Database
from ast_app.references import generate_reference_text, reference_pdf


class HrApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = Database(self.root / "ast.sqlite3")
        self.employee_id = self.db.save_employee({
            "code": "AST-01", "first_name": "Anna", "last_name": "Muster", "kind": "employee",
            "salutation": "Frau", "birth_date": "1995-05-14", "hired": "2020-02-01",
            "job": "Elektroinstallateurin EFZ", "workload": 10000, "allowance": 21625, "active": 1,
        })

    def tearDown(self):
        self.db.close()
        self.temp.cleanup()

    def test_reference_generation_persistence_and_pdf(self):
        employee = self.db.employee(self.employee_id)
        ratings = {key: 4 for key in ("knowledge", "quality", "quantity", "independence",
                                      "reliability", "initiative", "learning", "conduct")}
        text = generate_reference_text(employee, "interim", "2026-10-05", "2026-10-05", "auf Wunsch",
                                       "Servicearbeiten\nInstallationen", ratings)
        self.assertIn("Anna Muster", text)
        self.assertIn("stets zu unserer vollen Zufriedenheit", text)
        key = self.db.save_reference({"employee_id": self.employee_id, "reference_type": "interim",
                                      "issue_date": "2026-10-05", "end_date": "2026-10-05",
                                      "reason": "auf Wunsch", "tasks": "Servicearbeiten\nInstallationen",
                                      "ratings": ratings, "text": text})
        row = self.db.reference(key)
        self.assertEqual(row["ratings"]["quality"], 4)
        path = self.root / "zeugnis.pdf"
        reference_pdf(path, row, employee, {"company": "AST Elektro Tüscher AG", "city": "Aarburg"})
        pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)
        self.assertIn("Zwischenzeugnis", pdf_text)
        self.assertIn("Anna Muster", pdf_text)

    def test_manifest_import_creates_one_dossier_and_copies_files(self):
        import_root = self.root / "private_applications"
        files = import_root / "files"
        files.mkdir(parents=True)
        (files / "upload_1.pdf").write_bytes(b"%PDF-1.4\n%%EOF")
        payload = {"id": "web-20261005-1", "submitted_at": "2026-10-05T10:30:00",
                   "application_for": "Lehrstelle Montage-Elektriker EFZ", "first_name": "Max",
                   "last_name": "Beispiel", "address": "Testweg 1", "postcode": "5000", "city": "Aarau",
                   "email": "max@example.invalid", "phone": "079 111 22 33", "vocational_baccalaureate": "ja",
                   "message": "Guten Tag", "files": [{"category": "cv", "original_name": "Lebenslauf Max.pdf",
                                                        "stored_path": "files/upload_1.pdf"}]}
        (import_root / "web-20261005-1.json").write_text(json.dumps(payload), encoding="utf-8")
        result = sync_manifests(self.db, import_root)
        self.assertEqual(result, {"created": 1, "updated": 0, "files": 1})
        applicant = self.db.applicants()[0]
        self.assertEqual((applicant["category"], applicant["first_name"]), ("assembly", "Max"))
        records = self.db.applicant_files(applicant["id"])
        self.assertEqual(records[0]["original_name"], "Lebenslauf Max.pdf")
        self.assertTrue(Path(records[0]["local_path"]).is_file())
        again = sync_manifests(self.db, import_root)
        self.assertEqual(again, {"created": 0, "updated": 1, "files": 0})


if __name__ == "__main__":
    unittest.main()
