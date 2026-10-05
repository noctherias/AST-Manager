import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pypdf import PdfReader

from ast_app.applications import (DEFAULT_FTP_ROOT, FtpDeleteWorker, delete_remote_application,
                                  normalize_ftp_root, sync_manifests, sync_ftp)
from ast_app.database import Database
from ast_app.references import generate_reference_text, reference_pdf, question_groups


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
        ratings = {f"{key}_{index}": 4 for key, _, questions in question_groups("interim")
                   for index, _ in enumerate(questions, 1)}
        text = generate_reference_text(employee, "interim", "2026-10-05", "2026-10-05", "auf Wunsch",
                                       "Servicearbeiten\nInstallationen", ratings)
        self.assertIn("Anna Muster", text)
        self.assertIn("Gesamtleistung", text)
        self.assertIn("sehr gut", text)
        self.assertIn("gegenüber Vorgesetzten", text)
        key = self.db.save_reference({"employee_id": self.employee_id, "reference_type": "interim",
                                      "issue_date": "2026-10-05", "end_date": "2026-10-05",
                                      "reason": "auf Wunsch", "tasks": "Servicearbeiten\nInstallationen",
                                      "ratings": ratings, "text": text})
        row = self.db.reference(key)
        self.assertEqual(row["ratings"]["quality_1"], 4)
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
                   "trial_dates": ["2026-11-02", "2026-11-05"],
                   "message": "Guten Tag", "files": [{"category": "cv", "original_name": "Lebenslauf Max.pdf",
                                                        "stored_path": "files/upload_1.pdf"}]}
        (import_root / "web-20261005-1.json").write_text(json.dumps(payload), encoding="utf-8")
        result = sync_manifests(self.db, import_root)
        self.assertEqual(result, {"created": 1, "updated": 0, "files": 1})
        applicant = self.db.applicants()[0]
        self.assertEqual((applicant["category"], applicant["first_name"]), ("assembly", "Max"))
        self.assertEqual(applicant["trial_dates"], "02.11.2026\n05.11.2026")
        records = self.db.applicant_files(applicant["id"])
        self.assertEqual(records[0]["original_name"], "Lebenslauf Max.pdf")
        self.assertTrue(Path(records[0]["local_path"]).is_file())
        again = sync_manifests(self.db, import_root)
        self.assertEqual(again, {"created": 0, "updated": 1, "files": 0})

        self.db.set_applicant_suitability(applicant["id"], "possible")
        sync_manifests(self.db, import_root)
        self.assertEqual(self.db.applicant(applicant["id"])["suitability"], "possible")

    def test_ftps_manifest_and_document_import(self):
        payload = {"id": "ftp-20261005-1", "submitted_at": "2026-10-05T12:00:00",
                   "application_for": "Elektroinstallateur EFZ", "first_name": "Lia", "last_name": "Test",
                   "trial_dates": ["2026-11-10"],
                   "files": [{"category": "application", "original_name": "Bewerbung.pdf",
                              "stored_path": "upload_1.pdf"}]}

        class FakeFtp:
            def __init__(self, **kwargs): self.cwd_value = ""
            def connect(self, host, port): self.host = host
            def auth(self): pass
            def login(self, user, password): self.user = user
            def prot_p(self): pass
            def cwd(self, value): self.cwd_value = value
            def nlst(self):
                return ["Lia_Test_20261005"] if self.cwd_value == DEFAULT_FTP_ROOT else ["application.json", "upload_1.pdf"]
            def retrbinary(self, command, callback):
                callback(json.dumps(payload).encode() if command.endswith(".json") else b"%PDF-1.4\n%%EOF")
            def quit(self): pass
            def close(self): pass

        result = sync_ftp(self.db, "ftp.example.test", "user", "secret", ftp_factory=FakeFtp)
        self.assertEqual(result, {"created": 1, "updated": 0, "files": 1})
        applicant = self.db.applicants()[0]
        self.assertEqual((applicant["first_name"], applicant["category"]), ("Lia", "installer"))
        self.assertEqual(applicant["trial_dates"], "10.11.2026")
        self.assertTrue(Path(self.db.applicant_files(applicant["id"])[0]["local_path"]).is_file())

    def test_verified_remote_application_folder_is_deleted(self):
        source_id = "Lia_Test_20261005"
        payload = {"id": source_id}

        class FakeFtp:
            instance = None

            def __init__(self, **kwargs):
                self.deleted = []
                self.removed = []
                FakeFtp.instance = self
            def connect(self, host, port): pass
            def auth(self): pass
            def login(self, user, password): pass
            def prot_p(self): pass
            def retrbinary(self, command, callback): callback(json.dumps(payload).encode())
            def cwd(self, value): self.cwd_value = value
            def nlst(self): return ["application.json", "Lebenslauf.pdf"]
            def delete(self, path): self.deleted.append(path)
            def rmd(self, path): self.removed.append(path)
            def quit(self): pass
            def close(self): pass

        delete_remote_application("ftp.example.test", "user", "secret", source_id,
                                  ftp_factory=FakeFtp)
        folder = f"{DEFAULT_FTP_ROOT}/{source_id}"
        self.assertEqual(FakeFtp.instance.deleted,
                         [f"{folder}/application.json", f"{folder}/Lebenslauf.pdf"])
        self.assertEqual(FakeFtp.instance.removed, [folder])
        with self.assertRaises(ValueError):
            delete_remote_application("ftp.example.test", "user", "secret", "../fremd",
                                      ftp_factory=FakeFtp)
        with self.assertRaises(ValueError):
            delete_remote_application("ftp.example.test", "user", "secret", source_id, "/",
                                      ftp_factory=FakeFtp)

    def test_full_ftp_url_is_normalized_to_remote_upload_path(self):
        self.assertEqual(
            normalize_ftp_root("ftp://lp2qfs_admin@lp2qfs.ftp.infomaniak.com/sites/ast-elektro.ch/uploads"),
            DEFAULT_FTP_ROOT)
        self.assertEqual(normalize_ftp_root(r"\sites\ast-elektro.ch\uploads"), DEFAULT_FTP_ROOT)

    def test_delete_worker_passes_source_id_before_remote_root(self):
        connection = ("ftp.example.test", "user", "secret", DEFAULT_FTP_ROOT)
        worker = FtpDeleteWorker(connection, "Lia_Test_20261005")
        with patch("ast_app.applications.delete_remote_application") as delete:
            worker.run()
        delete.assert_called_once_with("ftp.example.test", "user", "secret",
                                       "Lia_Test_20261005", DEFAULT_FTP_ROOT)


if __name__ == "__main__":
    unittest.main()
