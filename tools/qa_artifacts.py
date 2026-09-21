"""Generate reproducible fictional samples for PDF and UI visual review."""
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ast_app.database import Database
from ast_app.demo import seed_demo
from ast_app.documents import salary_pdf, time_report, report_pdf
from ast_app.domain import chf, number, display_date


def main():
    folder = Path(sys.argv[1])
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as temporary:
        db = Database(Path(temporary) / "samples.sqlite3")
        seed_demo(db)
        person = db.employees()[0]
        period = db.balances(person["id"])[-1]
        fields = {"A": "/Ja", "B": "/Off", "D": "2026", "E-von": "01.01.", "E-bis": "31.12.",
                  "HName": "Lena Keller", "HAdresse": "Musterstrasse 1", "HWohnort": "4663 Aarburg",
                  "1": "72000", "2-2": "1800", "3-1": "Bonus", "3-2": "2500", "9": "4800", "10-1": "3600",
                  "12": "1500", "13-1-1-1": "/Ja", "13-1-1-2": "850", "G": "/Ja",
                  "15-1": "DEMO - Fiktive Beispieldaten", "OrtDatum": "Aarburg, 20.09.2026",
                  "Unterschrift1.0": "AST Muster AG", "Unterschrift1.1": "Werkstrasse 12", "Unterschrift1.2": "4663 Aarburg",
                  "Unterschrift1.3": "+41 62 000 00 00", "Unterschrift1.4": "Administration"}
        salary_pdf(fields, folder / "Beispiel-Lohnausweis.pdf")
        time_report(folder / "Beispiel-Stundennachweis.pdf", person, period, db.entries(period["id"]))
        invoices = db.invoices()
        report_pdf(folder / "Beispiel-Debitoren.pdf", "Debitoren", "DEMO - Fiktive Beispieldaten",
                   ["Rechnung", "Kunde", "Datum", "Fällig", "Valuta", "Betrag CHF", "Bezahlt CHF", "Offen CHF", "Status"],
                   [[r["number"], r["customer"], display_date(r["issued"]), display_date(r["due"]), display_date(r["valuta"]), number(r["amount"]), number(r["paid"]), number(r["open"]), r["status"]] for r in invoices],
                   f"Offen {chf(sum(r['open'] for r in invoices))}", [72, 142, 62, 62, 62, 75, 75, 75, 75])
        db.close()


if __name__ == "__main__": main()
