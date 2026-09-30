"""Fictional data. Only loaded into the separate demo database."""
from datetime import date, timedelta


def seed_demo(db):
    if db.settings().get("demo_seeded") or db.employees() or db.customers():
        return
    today = date.today()
    year = today.year
    db.save_settings({"company": "AST Muster AG", "address": "Werkstrasse 12", "postcode": "4663",
                      "city": "Aarburg", "phone": "+41 62 000 00 00", "email": "info@ast-muster.ch",
                      "website": "www.ast-muster.ch", "contact": "Administration", "demo_seeded": "1"})
    customers = [db.save_customer({"name": n, "customer_number": code, "address": a,
                                   "postcode": z, "city": c, "email": ""})
                 for code, n, a, z, c in [("1001", "Alpenblick Immobilien AG", "Bergstrasse 8", "5000", "Aarau"),
                                          ("1002", "Werkraum Architektur", "Bahnhofstrasse 21", "4600", "Olten"),
                                          ("1003", "Gemeinde Musterwil", "Dorfplatz 1", "4800", "Musterwil")]]
    for index, (first, last, kind) in enumerate([("Lena", "Keller", "employee"), ("Marco", "Steiner", "employee"), ("Nora", "Frei", "apprentice")]):
        key = db.save_employee({"code": f"AST-{index+1:03}", "first_name": first, "last_name": last,
                               "kind": kind, "salutation": "", "ahv": "", "ahv_old": "", "address": "Musterstrasse 1",
                               "postcode": "4663", "city": "Aarburg", "hired": f"{year-1}-01-01", "job": "Lernende" if kind == "apprentice" else "Elektroinstallation",
                               "workload": 10000, "allowance": 21625, "active": 1})
        p = db.save_period({"employee_id": key, "label": "Lehrjahr 1" if kind == "apprentice" else str(year - 1),
                            "start": f"{year-1}-01-01", "end": f"{year-1}-12-31", "allowance": 21625, "opening": 0, "opening_sick": 0, "opening_accident": 0})
        db.save_entry({"period_id": p, "day": f"{year-1}-06-16", "kind": "vacation", "hours": 18000, "note": "Ferien Vorperiode"})
        p = db.save_period({"employee_id": key, "label": "Lehrjahr 2" if kind == "apprentice" else str(year),
                            "start": f"{year}-01-01", "end": f"{year}-12-31", "allowance": 21625, "opening": 0, "opening_sick": 0, "opening_accident": 0})
        for offset, kind_, hours, note in [(21, "vacation", 4325 + index * 865, "Sommerferien"), (8, "overtime", 650 + index * 125, "Projektabschluss"), (4, "sick", 865, "")]:
            db.save_entry({"period_id": p, "day": max(date(year, 1, 1), today - timedelta(days=offset)).isoformat(), "kind": kind_, "hours": hours, "note": note})
        for offset, code, note in ((3, "", "Baustelle Musterwil"), (2, "H", "Planung im Homeoffice"), (1, "", "Servicearbeiten")):
            workday = max(date(year, 1, 1), today - timedelta(days=offset))
            db.save_time_record({"employee_id": key, "day": workday.isoformat(), "start_1": 450, "end_1": 720,
                                 "start_2": 780, "end_2": 1035, "break_minutes": 0,
                                 "code": code, "note": note})
        if index == 0:
            db.save_salary(key, year, f"{year}-01-01", f"{year}-12-31", {
                "A": "/Ja", "B": "/Off", "HName": first + " " + last,
                "HAdresse": "Musterstrasse 1", "HWohnort": "4663 Aarburg", "1": "72000", "2-2": "1800",
                "3-1": "Bonus", "3-2": "2500", "9": "4800", "10-1": "3600", "12": "1500",
                "13-1-1-1": "/Ja", "13-1-1-2": "850", "G": "/Ja", "15-1": "DEMO - Fiktive Beispieldaten",
                "OrtDatum": "Aarburg, " + today.strftime("%d.%m.%Y"), "Unterschrift1.0": "AST Muster AG",
                "Unterschrift1.1": "Werkstrasse 12", "Unterschrift1.2": "4663 Aarburg",
                "Unterschrift1.3": "+41 62 000 00 00", "Unterschrift1.4": "Administration"})
    for idx, (customer, amount, days, paid) in enumerate([(customers[0], 842570, -12, 500000), (customers[1], 315000, 15, 0), (customers[2], 1284000, 8, 0), (customers[0], 267800, -20, 267800), (customers[1], 615050, -5, 0)]):
        due = today + timedelta(days=days)
        invoice = db.save_invoice({"number": f"{year}-{1041+idx}", "customer_id": customer, "issued": (due - timedelta(days=30)).isoformat(), "due": due.isoformat(), "amount": amount, "note": "Demodaten"})
        if paid:
            db.add_payment(invoice, min(due, today).isoformat(), paid, "Überweisung")
