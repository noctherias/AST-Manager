import json
import tempfile
import unittest
from pathlib import Path

from ast_app.database import Database
from ast_app.web_sync import apply_snapshot, build_snapshot, snapshot_fingerprint


def seed(db):
    with db.conn:
        db.conn.execute("INSERT INTO customers VALUES(1,'Muster AG','K-1','Hauptstrasse 1','5000','Aarau','info@example.ch')")
        db.conn.execute("""INSERT INTO employees(id,code,first_name,last_name,kind,salutation,ahv,ahv_old,birth_date,address,postcode,city,hired,job,workload,allowance,active)
                           VALUES(1,'AST-1','Anna','Muster','employee','Frau','756.0000.0000.00','','1990-01-01','Weg 2','5000','Aarau','2020-01-01','Monteurin',10000,17300,1)""")
        db.conn.execute("INSERT INTO invoices VALUES(1,'R-100',1,'2026-01-01','2026-01-31',123450,'Bemerkung',2,'2026-02-14')")
        db.conn.execute("INSERT INTO payments VALUES(1,1,'2026-01-20',23450,'Teilzahlung')")
        db.conn.execute("""INSERT INTO time_records(id,employee_id,day,start_1,end_1,start_2,end_2,break_minutes,worked_minutes,code,note)
                           VALUES(1,1,'2026-01-05',NULL,NULL,NULL,NULL,0,525,'','Baustelle')""")
        db.conn.execute("""INSERT INTO employment_references(id,employee_id,reference_type,issue_date,end_date,reason,tasks,ratings,text,updated)
                           VALUES(1,1,'work','2026-02-01','','Austritt','Installationen','{}','Zeugnistext','2026-02-01T12:00:00')""")
        db.conn.execute("""INSERT INTO applicants(id,source_id,category,status,first_name,last_name,address,postcode,city,email,phone,vocational_baccalaureate,trial_dates,message,notes,suitability,server_deleted,submitted_at,updated)
                           VALUES(1,'web-1','trial','review','Lina','Test','Gasse 3','5000','Aarau','lina@example.ch','0790000000',0,'[\"2026-03-01\"]','Hallo','Notiz','possible',0,'2026-02-01T10:00:00','2026-02-01T10:00:00')""")
        db.conn.execute("INSERT INTO applicant_files VALUES(1,1,'cv','Lebenslauf.pdf','C:/AST/Lebenslauf.pdf','Lebenslauf.pdf')")
        db.conn.execute("INSERT INTO salaries VALUES(1,1,2026,'2026-01-01','2026-12-31',?,'2026-12-31T12:00:00')", (json.dumps({'8': '90000'}),))
        db.conn.execute("INSERT INTO settings VALUES('company','AST Elektro Tüscher AG')")
        db.conn.execute("INSERT INTO settings VALUES('applications_ftp_password','must-not-leave-device')")


class WebSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.source = Database(root / "source.sqlite3")
        self.target = Database(root / "target.sqlite3")
        seed(self.source)

    def tearDown(self):
        self.source.close()
        self.target.close()
        self.temp.cleanup()

    def test_snapshot_round_trip_preserves_business_values(self):
        apply_snapshot(self.target, {**build_snapshot(self.source), "revision": 4})
        self.assertEqual(self.target.one("SELECT * FROM customers WHERE id=1")["customer_number"], "K-1")
        self.assertEqual(self.target.one("SELECT * FROM employees WHERE id=1")["allowance"], 17300)
        self.assertEqual(self.target.one("SELECT * FROM invoices WHERE id=1")["amount"], 123450)
        self.assertEqual(self.target.one("SELECT * FROM invoices WHERE id=1")["reminder_level"], 2)
        self.assertEqual(self.target.one("SELECT * FROM payments WHERE id=1")["amount"], 23450)
        self.assertEqual(self.target.one("SELECT * FROM time_records WHERE id=1")["worked_minutes"], 525)
        self.assertEqual(self.target.one("SELECT * FROM employment_references WHERE id=1")["text"], "Zeugnistext")
        self.assertEqual(self.target.one("SELECT * FROM applicants WHERE id=1")["suitability"], "possible")
        self.assertEqual(self.target.one("SELECT * FROM applicant_files WHERE id=1")["original_name"], "Lebenslauf.pdf")
        self.assertEqual(json.loads(self.target.one("SELECT * FROM salaries WHERE id=1")["fields"])["8"], "90000")

    def test_snapshot_never_contains_local_secrets(self):
        encoded = json.dumps(build_snapshot(self.source), ensure_ascii=False)
        self.assertNotIn("must-not-leave-device", encoded)
        self.assertNotIn("applications_ftp_password", encoded)

    def test_snapshot_fingerprint_is_stable(self):
        self.assertEqual(snapshot_fingerprint(build_snapshot(self.source)), snapshot_fingerprint(build_snapshot(self.source)))


if __name__ == "__main__":
    unittest.main()
