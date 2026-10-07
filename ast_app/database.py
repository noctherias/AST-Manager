"""SQLite persistence, validation and transactional operations."""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import date, datetime
from pathlib import Path
from uuid import uuid4

from .domain import (KINDS, TIME_CODES, iso, invoice_state, normalize_time_code, period_balance,
                     salary_totals, scheduled_work_minutes, worked_minutes)

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS customers(
 id INTEGER PRIMARY KEY, name TEXT NOT NULL COLLATE NOCASE UNIQUE,
 customer_number TEXT NOT NULL DEFAULT '',
 address TEXT NOT NULL DEFAULT '', postcode TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
 email TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS employees(
 id INTEGER PRIMARY KEY, code TEXT NOT NULL COLLATE NOCASE UNIQUE, first_name TEXT NOT NULL,
 last_name TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('employee','apprentice')),
 salutation TEXT NOT NULL DEFAULT '', ahv TEXT NOT NULL DEFAULT '', ahv_old TEXT NOT NULL DEFAULT '', birth_date TEXT NOT NULL DEFAULT '',
 address TEXT NOT NULL DEFAULT '', postcode TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '',
 hired TEXT NOT NULL, job TEXT NOT NULL DEFAULT '', workload INTEGER NOT NULL DEFAULT 10000 CHECK(workload>0 AND workload<=10000),
 allowance INTEGER NOT NULL DEFAULT 21625 CHECK(allowance>=0), active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)));
CREATE TABLE IF NOT EXISTS periods(
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
 label TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, allowance INTEGER NOT NULL CHECK(allowance>=0),
 opening INTEGER NOT NULL DEFAULT 0, opening_sick INTEGER NOT NULL DEFAULT 0 CHECK(opening_sick>=0),
 opening_accident INTEGER NOT NULL DEFAULT 0 CHECK(opening_accident>=0),
 CHECK(start<=end), UNIQUE(employee_id,start));
CREATE TABLE IF NOT EXISTS entries(
 id INTEGER PRIMARY KEY, period_id INTEGER NOT NULL REFERENCES periods(id) ON DELETE RESTRICT,
 day TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('vacation','overtime','sick','accident')),
 hours INTEGER NOT NULL CHECK(hours!=0 AND (kind='overtime' OR hours>0)), note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS time_records(
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
 day TEXT NOT NULL, start_1 INTEGER, end_1 INTEGER, start_2 INTEGER, end_2 INTEGER,
 break_minutes INTEGER NOT NULL DEFAULT 0 CHECK(break_minutes>=0 AND break_minutes<=1440),
 worked_minutes INTEGER NOT NULL DEFAULT 0 CHECK(worked_minutes>=0 AND worked_minutes<=1440),
 code TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '',
 UNIQUE(employee_id,day));
CREATE TABLE IF NOT EXISTS invoices(
 id INTEGER PRIMARY KEY, number TEXT NOT NULL COLLATE NOCASE UNIQUE,
 customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
 issued TEXT NOT NULL, due TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), note TEXT NOT NULL DEFAULT '',
 reminder_level INTEGER NOT NULL DEFAULT 0 CHECK(reminder_level BETWEEN 0 AND 4), reminder_date TEXT NOT NULL DEFAULT '',
 CHECK(due>=issued));
CREATE TABLE IF NOT EXISTS payments(
 id INTEGER PRIMARY KEY, invoice_id INTEGER NOT NULL REFERENCES invoices(id) ON DELETE RESTRICT,
 day TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0), note TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS salaries(
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
 year INTEGER NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, fields TEXT NOT NULL, updated TEXT NOT NULL,
 UNIQUE(employee_id,year));
CREATE TABLE IF NOT EXISTS employment_references(
 id INTEGER PRIMARY KEY, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE RESTRICT,
 reference_type TEXT NOT NULL CHECK(reference_type IN ('work','interim','apprentice')),
 issue_date TEXT NOT NULL, end_date TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
 tasks TEXT NOT NULL DEFAULT '', ratings TEXT NOT NULL, text TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS applicants(
 id INTEGER PRIMARY KEY, source_id TEXT NOT NULL DEFAULT '' COLLATE NOCASE UNIQUE,
 category TEXT NOT NULL CHECK(category IN ('trial','installer','assembly')),
 status TEXT NOT NULL DEFAULT 'new' CHECK(status IN ('new','review','interview','trial','offer','rejected','hired')),
 first_name TEXT NOT NULL, last_name TEXT NOT NULL, address TEXT NOT NULL DEFAULT '',
 postcode TEXT NOT NULL DEFAULT '', city TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '',
 phone TEXT NOT NULL DEFAULT '', vocational_baccalaureate INTEGER NOT NULL DEFAULT 0 CHECK(vocational_baccalaureate IN (0,1)),
 trial_dates TEXT NOT NULL DEFAULT '', message TEXT NOT NULL DEFAULT '', notes TEXT NOT NULL DEFAULT '',
 suitability TEXT NOT NULL DEFAULT '' CHECK(suitability IN ('','unsuitable','possible','suitable')),
 server_deleted INTEGER NOT NULL DEFAULT 0 CHECK(server_deleted IN (0,1)),
 submitted_at TEXT NOT NULL, updated TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS applicant_files(
 id INTEGER PRIMARY KEY, applicant_id INTEGER NOT NULL REFERENCES applicants(id) ON DELETE CASCADE,
 category TEXT NOT NULL DEFAULT 'other', original_name TEXT NOT NULL, local_path TEXT NOT NULL,
 source_ref TEXT NOT NULL DEFAULT '', UNIQUE(applicant_id,source_ref));
CREATE TABLE IF NOT EXISTS audit_log(
 id INTEGER PRIMARY KEY, at TEXT NOT NULL, action TEXT NOT NULL, entity TEXT NOT NULL, entity_id INTEGER, detail TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS entries_period ON entries(period_id,day);
CREATE INDEX IF NOT EXISTS payments_invoice ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS periods_employee ON periods(employee_id,start);
CREATE INDEX IF NOT EXISTS time_records_employee ON time_records(employee_id,day);
CREATE INDEX IF NOT EXISTS references_employee ON employment_references(employee_id,issue_date);
CREATE INDEX IF NOT EXISTS applicants_status ON applicants(status,category,submitted_at);
CREATE INDEX IF NOT EXISTS applicant_files_applicant ON applicant_files(applicant_id);
"""

SCHEMA_VERSION = 13


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=15)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA busy_timeout=15000")
        version = self.conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            self.conn.close()
            raise ValueError("Diese Datenbank stammt aus einer neueren Programmversion.")
        self.conn.executescript(SCHEMA)
        customer_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(customers)")}
        if "customer_number" not in customer_columns:
            self.conn.execute("ALTER TABLE customers ADD COLUMN customer_number TEXT NOT NULL DEFAULT ''")
        employee_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(employees)")}
        if "birth_date" not in employee_columns:
            self.conn.execute("ALTER TABLE employees ADD COLUMN birth_date TEXT NOT NULL DEFAULT ''")
        time_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(time_records)")}
        if "worked_minutes" not in time_columns:
            self.conn.execute("ALTER TABLE time_records ADD COLUMN worked_minutes INTEGER NOT NULL DEFAULT 0")
            for record in self.rows("SELECT * FROM time_records"):
                self.conn.execute("UPDATE time_records SET worked_minutes=? WHERE id=?",
                                  (worked_minutes({**record, "worked_minutes": None}), record["id"]))
        if version < 13:
            self._migrate_time_codes(version < 12)
        invoice_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(invoices)")}
        if "reminder_level" not in invoice_columns:
            self.conn.execute("ALTER TABLE invoices ADD COLUMN reminder_level INTEGER NOT NULL DEFAULT 0")
        if "reminder_date" not in invoice_columns:
            self.conn.execute("ALTER TABLE invoices ADD COLUMN reminder_date TEXT NOT NULL DEFAULT ''")
        applicant_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(applicants)")}
        if "trial_dates" not in applicant_columns:
            self.conn.execute("ALTER TABLE applicants ADD COLUMN trial_dates TEXT NOT NULL DEFAULT ''")
        if "suitability" not in applicant_columns:
            self.conn.execute("ALTER TABLE applicants ADD COLUMN suitability TEXT NOT NULL DEFAULT ''")
        if "server_deleted" not in applicant_columns:
            self.conn.execute("ALTER TABLE applicants ADD COLUMN server_deleted INTEGER NOT NULL DEFAULT 0")
        self.conn.execute("""UPDATE settings SET value='/sites/ast-elektro.ch/uploads'
                             WHERE key='applications_ftp_root' AND value='/sites/private_applications'""")
        invoice_sql = self.conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='invoices'").fetchone()[0]
        if "BETWEEN 0 AND 3" in invoice_sql:
            self.conn.commit()
            self.conn.execute("PRAGMA foreign_keys=OFF")
            with self.conn:
                self.conn.execute("""CREATE TABLE invoices_new(
                    id INTEGER PRIMARY KEY, number TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE RESTRICT,
                    issued TEXT NOT NULL, due TEXT NOT NULL, amount INTEGER NOT NULL CHECK(amount>0),
                    note TEXT NOT NULL DEFAULT '', reminder_level INTEGER NOT NULL DEFAULT 0
                    CHECK(reminder_level BETWEEN 0 AND 4), reminder_date TEXT NOT NULL DEFAULT '', CHECK(due>=issued))""")
                self.conn.execute("""INSERT INTO invoices_new(id,number,customer_id,issued,due,amount,note,reminder_level,reminder_date)
                    SELECT id,number,customer_id,issued,due,amount,note,reminder_level,reminder_date FROM invoices""")
                self.conn.execute("DROP TABLE invoices")
                self.conn.execute("ALTER TABLE invoices_new RENAME TO invoices")
            self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        self.conn.commit()

    def _migrate_time_codes(self, original_codes=False):
        """Replace the old cryptic Excel codes without losing time records."""
        original = {
            "F": "T", "G": "F", "K": "K", "KR": "K", "A": "U", "AR": "U",
            "KU": "M", "KA": "M", "U": "F", "UH": "F", "H": "H", "B": "B",
            "E1": "M", "E2": "M", "E3": "M", "E4": "M", "E5": "M",
        }
        for record in self.rows("SELECT id,code FROM time_records"):
            raw = str(record["code"] or "").strip().upper()
            code = original.get(raw, normalize_time_code(raw)) if original_codes else normalize_time_code(raw)
            if code != record["code"]:
                self.conn.execute("UPDATE time_records SET code=? WHERE id=?", (code, record["id"]))

    def close(self):
        self.conn.close()

    def rows(self, sql, args=()):
        return [dict(r) for r in self.conn.execute(sql, args)]

    def one(self, sql, args=()):
        row = self.conn.execute(sql, args).fetchone()
        return dict(row) if row else None

    def log(self, action, entity, key, data):
        self.conn.execute("INSERT INTO audit_log(at,action,entity,entity_id,detail) VALUES(?,?,?,?,?)",
                          (datetime.now().isoformat(timespec="seconds"), action, entity, key,
                           json.dumps(data, ensure_ascii=False)))

    def _save(self, table, data, key=None):
        # Table and column names only come from fixed application call sites.
        try:
            with self.conn:
                if key:
                    cursor = self.conn.execute(f"UPDATE {table} SET " + ",".join(f"{c}=?" for c in data) + " WHERE id=?",
                                              [*data.values(), key])
                    if cursor.rowcount != 1:
                        raise ValueError("Der Datensatz existiert nicht mehr.")
                else:
                    cursor = self.conn.execute(f"INSERT INTO {table}(" + ",".join(data) + ") VALUES(" +
                                               ",".join("?" for _ in data) + ")", list(data.values()))
                    key = cursor.lastrowid
                self.log("update" if cursor.rowcount and data.get("id") else "save", table, key, data)
            return key
        except sqlite3.IntegrityError as e:
            if "UNIQUE" in str(e):
                raise ValueError("Dieser Datensatz existiert bereits (Nummer, Name oder Person/Jahr).") from None
            raise ValueError("Die Angaben sind unvollständig oder werden bereits verwendet.") from e

    def settings(self):
        return {r["key"]: r["value"] for r in self.rows("SELECT * FROM settings")}

    def save_settings(self, values):
        with self.conn:
            self.conn.executemany("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                  [(k, str(v).strip()) for k, v in values.items()])
            self.log("save", "settings", None, list(values))

    def customers(self):
        return self.rows("SELECT * FROM customers ORDER BY name")

    def save_customer(self, data, key=None):
        data = {k: str(data.get(k, "")).strip() for k in ("name", "customer_number", "address", "postcode", "city", "email")}
        if not data["name"]:
            raise ValueError("Bitte einen Kundennamen eingeben.")
        return self._save("customers", data, key)

    def employees(self, kind=None):
        return self.rows("SELECT * FROM employees" + (" WHERE kind=?" if kind else "") + " ORDER BY active DESC,last_name,first_name",
                         (kind,) if kind else ())

    def employee(self, key):
        return self.one("SELECT * FROM employees WHERE id=?", (key,))

    def save_employee(self, data, key=None):
        fields = ("code", "first_name", "last_name", "kind", "salutation", "ahv", "ahv_old", "birth_date", "address", "postcode", "city", "hired", "job", "workload", "allowance", "active")
        d = {k: data.get(k, "").strip() if isinstance(data.get(k, ""), str) else data.get(k) for k in fields}
        if not all(d[k] for k in ("code", "first_name", "last_name")):
            raise ValueError("Personalnummer, Vorname und Nachname sind erforderlich.")
        iso(d["hired"])
        if d["birth_date"]:
            iso(d["birth_date"])
        if d["kind"] not in ("employee", "apprentice") or not 0 < d["workload"] <= 10000 or d["allowance"] < 0:
            raise ValueError("Bitte Pensum und Ferienanspruch prüfen.")
        return self._save("employees", d, key)

    def invoices(self):
        rows = self.rows("""SELECT i.*,c.name AS customer,c.customer_number AS customer_number,c.address AS customer_address,
                            c.postcode AS customer_postcode,c.city AS customer_city,c.email AS customer_email,
                            COALESCE(SUM(p.amount),0) AS paid,MAX(p.day) AS valuta
                            FROM invoices i JOIN customers c ON c.id=i.customer_id
                            LEFT JOIN payments p ON p.invoice_id=i.id GROUP BY i.id ORDER BY i.issued DESC,i.id DESC""")
        for r in rows:
            r["open"] = r["amount"] - r["paid"]
            r["status"] = invoice_state(r["amount"], r["paid"], r["due"])
        return rows

    def save_invoice(self, data, key=None):
        d = {k: data[k] for k in ("number", "customer_id", "issued", "due", "amount", "note")}
        d["number"] = d["number"].strip()
        iso(d["issued"]); iso(d["due"])
        if not d["number"] or d["amount"] <= 0 or d["due"] < d["issued"]:
            raise ValueError("Rechnungsnummer, positiver Betrag und Fälligkeit ab Rechnungsdatum sind erforderlich.")
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            paid = self.one("SELECT COALESCE(SUM(amount),0) AS total FROM payments WHERE invoice_id=?", (key,))["total"]
            if d["amount"] < paid:
                raise ValueError("Der Rechnungsbetrag darf nicht kleiner als die erfassten Zahlungen sein.")
            return self._save("invoices", d, key)

    def payments(self, invoice_id):
        return self.rows("SELECT * FROM payments WHERE invoice_id=? ORDER BY day,id", (invoice_id,))

    def add_payment(self, invoice_id, day, amount, note=""):
        iso(day)
        with self.conn:
            self.conn.execute("BEGIN IMMEDIATE")
            r = self.one("""SELECT i.amount-COALESCE(SUM(p.amount),0) AS remaining FROM invoices i
                            LEFT JOIN payments p ON p.invoice_id=i.id WHERE i.id=? GROUP BY i.id""", (invoice_id,))
            if not r or amount <= 0 or amount > r["remaining"]:
                raise ValueError("Die Zahlung muss positiv sein und darf den offenen Betrag nicht übersteigen.")
            return self._save("payments", {"invoice_id": invoice_id, "day": day, "amount": amount, "note": note})

    def set_reminder(self, invoice_id, level, reminder_date=""):
        level = int(level)
        if level not in range(5):
            raise ValueError("Die Mahnstufe muss zwischen 0 und 4 liegen.")
        invoice = next((row for row in self.invoices() if row["id"] == invoice_id), None)
        if not invoice:
            raise ValueError("Die Rechnung existiert nicht mehr.")
        if invoice["open"] <= 0 and level:
            raise ValueError("Eine bezahlte Rechnung kann nicht gemahnt werden.")
        value = "" if level == 0 else iso(reminder_date)
        with self.conn:
            self.conn.execute("UPDATE invoices SET reminder_level=?,reminder_date=? WHERE id=?",
                              (level, value, invoice_id))
            self.log("reminder", "invoices", invoice_id, {"level": level, "date": value})

    def delete(self, table, key):
        if table not in ("entries", "time_records", "payments", "invoices", "salaries",
                         "employment_references", "applicants", "applicant_files"):
            raise ValueError("Dieser Datensatz kann nicht gelöscht werden.")
        try:
            with self.conn:
                row = self.one(f"SELECT * FROM {table} WHERE id=?", (key,))
                self.conn.execute(f"DELETE FROM {table} WHERE id=?", (key,))
                self.log("delete", table, key, row)
        except sqlite3.IntegrityError:
            raise ValueError("Zuerst die zugehörigen Zahlungen entfernen.") from None

    def periods(self, employee_id):
        return self.rows("SELECT * FROM periods WHERE employee_id=? ORDER BY start,id", (employee_id,))

    def save_period(self, data, key=None):
        d = {k: data[k] for k in ("employee_id", "label", "start", "end", "allowance", "opening", "opening_sick", "opening_accident")}
        iso(d["start"]); iso(d["end"])
        if not d["label"].strip() or d["end"] < d["start"] or min(d["allowance"], d["opening_sick"], d["opening_accident"]) < 0:
            raise ValueError("Bitte Bezeichnung, Zeitraum und Anspruch prüfen.")
        other = [p for p in self.periods(d["employee_id"]) if p["id"] != key]
        if any(d["start"] <= p["end"] and d["end"] >= p["start"] for p in other):
            raise ValueError("Die Zeiträume dieser Person dürfen sich nicht überschneiden.")
        if any(p["start"] < d["start"] for p in other) and any(d[k] for k in ("opening", "opening_sick", "opening_accident")):
            raise ValueError("Ein Startsaldo ist nur in der ersten Periode zulässig. Folgeperioden übernehmen automatisch.")
        if any(p["start"] > d["start"] and any(p[k] for k in ("opening", "opening_sick", "opening_accident")) for p in other):
            raise ValueError("Eine spätere Periode enthält Startsalden. Diese zuerst entfernen, bevor eine frühere Periode angelegt wird.")
        if key and self.one("SELECT id FROM entries WHERE period_id=? AND (day<? OR day>?) LIMIT 1", (key, d["start"], d["end"])):
            raise ValueError("Bestehende Buchungen würden ausserhalb der neuen Periode liegen.")
        return self._save("periods", d, key)

    def entries(self, period_id):
        return self.rows("SELECT * FROM entries WHERE period_id=? ORDER BY day DESC,id DESC", (period_id,))

    def save_entry(self, data, key=None):
        d = {k: data[k] for k in ("period_id", "day", "kind", "hours", "note")}
        iso(d["day"])
        period = self.one("SELECT * FROM periods WHERE id=?", (d["period_id"],))
        if not period or not period["start"] <= d["day"] <= period["end"]:
            raise ValueError("Das Datum muss innerhalb der ausgewählten Periode liegen.")
        if d["kind"] not in KINDS or not d["hours"] or (d["hours"] < 0 and d["kind"] != "overtime"):
            raise ValueError("Nur Überzeit darf negativ sein; Nullbuchungen sind nicht zulässig.")
        return self._save("entries", d, key)

    def time_records(self, employee_id, year=None):
        sql = "SELECT * FROM time_records WHERE employee_id=?"
        args = [employee_id]
        if year is not None:
            sql += " AND day>=? AND day<=?"
            args.extend((f"{int(year):04d}-01-01", f"{int(year):04d}-12-31"))
        return self.rows(sql + " ORDER BY day DESC,id DESC", args)

    def save_time_record(self, data, key=None):
        fields = ("employee_id", "day", "start_1", "end_1", "start_2", "end_2", "break_minutes",
                  "worked_minutes", "code", "note")
        d = {name: data.get(name) for name in fields}
        d["day"] = iso(d["day"])
        d["code"] = normalize_time_code(d.get("code"))
        d["note"] = str(d.get("note") or "").strip()
        d["break_minutes"] = int(d.get("break_minutes") or 0)
        valid_codes = set(TIME_CODES)
        if d["code"] not in valid_codes:
            raise ValueError("Bitte einen gültigen Abwesenheits- oder Arbeitscode auswählen.")
        if not self.employee(d["employee_id"]):
            raise ValueError("Die ausgewählte Person existiert nicht mehr.")
        values = [d[name] for name in ("start_1", "end_1", "start_2", "end_2")]
        if any(v is not None and not 0 <= int(v) < 1440 for v in values):
            raise ValueError("Bitte gültige Uhrzeiten eingeben.")
        first = d["start_1"] is not None or d["end_1"] is not None
        second = d["start_2"] is not None or d["end_2"] is not None
        if first != (d["start_1"] is not None and d["end_1"] is not None):
            raise ValueError("Für den ersten Arbeitsblock braucht es Kommt- und Geht-Zeit.")
        if second != (d["start_2"] is not None and d["end_2"] is not None):
            raise ValueError("Für den zweiten Arbeitsblock braucht es Kommt- und Geht-Zeit.")
        if second and not first:
            raise ValueError("Der zweite Arbeitsblock kann nur zusammen mit dem ersten erfasst werden.")
        if first:
            duration = (d["end_1"] - d["start_1"]) % 1440
            if second:
                duration += (d["end_2"] - d["start_2"]) % 1440
            if duration <= d["break_minutes"]:
                raise ValueError("Die zusätzliche Pause muss kürzer als die Arbeitszeit sein.")
        if d["worked_minutes"] is None:
            d["worked_minutes"] = worked_minutes(d)
        try:
            d["worked_minutes"] = int(d["worked_minutes"])
        except (TypeError, ValueError):
            raise ValueError("Bitte eine gültige Arbeitszeit eingeben.") from None
        if not 0 <= d["worked_minutes"] <= 1440:
            raise ValueError("Die Arbeitszeit muss zwischen 0 und 24 Stunden liegen.")
        if d["worked_minutes"] % 15:
            raise ValueError("Bitte die Arbeitszeit in 0.25-Stunden-Schritten eingeben.")
        if d["worked_minutes"] == 0 and not d["code"]:
            raise ValueError("Bitte eine Arbeitszeit oder einen Abwesenheitscode erfassen.")
        scheduled = scheduled_work_minutes(d["day"])
        absence_reasons = {"F", "K", "U", "M"}
        if d["code"] in absence_reasons and d["worked_minutes"] > scheduled:
            raise ValueError("Die Abwesenheitszeit darf die Sollzeit dieses Tages nicht überschreiten.")
        if d["worked_minutes"] < scheduled and d["code"] != "T" and d["code"] not in absence_reasons:
            raise ValueError("Bitte einen Grund für die geringere IST-Zeit auswählen.")
        if d["code"] == "M" and not d["note"]:
            raise ValueError("Bitte die andere Minderzeit unter Bemerkung kurz begründen.")
        return self._save("time_records", d, key)

    def save_time_records(self, records, overwrite=False):
        """Save a prepared date range, optionally replacing existing days."""
        created = updated = skipped = 0
        for record in records:
            existing = self.conn.execute(
                "SELECT id FROM time_records WHERE employee_id=? AND day=?",
                (record["employee_id"], record["day"]),
            ).fetchone()
            if existing and not overwrite:
                skipped += 1
                continue
            self.save_time_record(record, existing["id"] if existing else None)
            if existing:
                updated += 1
            else:
                created += 1
        return {"created": created, "updated": updated, "skipped": skipped}

    def balances(self, employee_id):
        results = []
        previous = None
        for p in self.periods(employee_id):
            totals = {r["kind"]: r["total"] for r in self.rows("SELECT kind,SUM(hours) AS total FROM entries WHERE period_id=? GROUP BY kind", (p["id"],))}
            b = period_balance(p["allowance"], totals.get("vacation", 0), totals.get("overtime", 0),
                               previous["balance"] if previous else p["opening"], totals.get("sick", 0), totals.get("accident", 0),
                               previous["sick_total"] if previous else p["opening_sick"],
                               previous["accident_total"] if previous else p["opening_accident"])
            results.append({**p, **b})
            previous = b
        return results

    def salaries(self):
        rows = self.rows("SELECT s.*,e.first_name||' '||e.last_name AS name FROM salaries s JOIN employees e ON e.id=s.employee_id ORDER BY s.year DESC,e.last_name")
        for r in rows:
            r["fields"] = json.loads(r["fields"])
        return rows

    def save_salary(self, employee_id, year, start, end, fields, key=None):
        iso(start); iso(end)
        if start > end or date.fromisoformat(start).year != year or date.fromisoformat(end).year != year:
            raise ValueError("Der Zeitraum muss vollständig im gewählten Kalenderjahr liegen.")
        clean = {k: str(v) for k, v in fields.items()}
        clean.update(salary_totals(clean))
        clean.update({"D": str(year), "E-von": date.fromisoformat(start).strftime("%d.%m."), "E-bis": date.fromisoformat(end).strftime("%d.%m.")})
        if clean.get("A") not in ("/Ja", "/Off") or clean.get("B") not in ("/Ja", "/Off") or (clean["A"] == clean["B"]):
            raise ValueError("Bitte entweder Lohnausweis oder Rentenbescheinigung wählen.")
        if not clean.get("HName", "").strip():
            raise ValueError("Der Name auf dem Lohnausweis fehlt.")
        return self._save("salaries", {"employee_id": employee_id, "year": year, "start": start, "end": end,
                                     "fields": json.dumps(clean, ensure_ascii=False), "updated": datetime.now().isoformat(timespec="seconds")}, key)

    def references(self, employee_id=None):
        sql = """SELECT r.*,e.first_name||' '||e.last_name AS name,e.kind AS employee_kind
                 FROM employment_references r JOIN employees e ON e.id=r.employee_id"""
        args = ()
        if employee_id is not None:
            sql += " WHERE r.employee_id=?"
            args = (employee_id,)
        rows = self.rows(sql + " ORDER BY r.issue_date DESC,r.id DESC", args)
        for row in rows:
            row["ratings"] = json.loads(row["ratings"])
        return rows

    def reference(self, key):
        row = self.one("SELECT * FROM employment_references WHERE id=?", (key,))
        if row:
            row["ratings"] = json.loads(row["ratings"])
        return row

    def save_reference(self, data, key=None):
        reference_type = str(data.get("reference_type", "")).strip()
        employee_id = int(data.get("employee_id") or 0)
        issue_date = iso(data.get("issue_date"))
        end_date = str(data.get("end_date", "")).strip()
        if end_date:
            end_date = iso(end_date)
        if reference_type not in ("work", "interim", "apprentice") or not self.employee(employee_id):
            raise ValueError("Bitte Person und Zeugnisart prüfen.")
        ratings = {str(k): int(v) for k, v in dict(data.get("ratings", {})).items()}
        if not ratings or any(value not in range(1, 6) for value in ratings.values()):
            raise ValueError("Bitte alle Beurteilungen beantworten.")
        text = str(data.get("text", "")).strip()
        if len(text) < 80:
            raise ValueError("Der Zeugnistext ist noch unvollständig.")
        values = {"employee_id": employee_id, "reference_type": reference_type,
                  "issue_date": issue_date, "end_date": end_date,
                  "reason": str(data.get("reason", "")).strip(),
                  "tasks": str(data.get("tasks", "")).strip(),
                  "ratings": json.dumps(ratings, ensure_ascii=False), "text": text,
                  "updated": datetime.now().isoformat(timespec="seconds")}
        return self._save("employment_references", values, key)

    def applicants(self):
        return self.rows("SELECT * FROM applicants ORDER BY submitted_at DESC,id DESC")

    def applicant(self, key):
        return self.one("SELECT * FROM applicants WHERE id=?", (key,))

    def save_applicant(self, data, key=None):
        category = str(data.get("category", "")).strip()
        status = str(data.get("status", "new")).strip()
        if category not in ("trial", "installer", "assembly"):
            raise ValueError("Bitte eine Bewerbungsart auswählen.")
        if status not in ("new", "review", "interview", "trial", "offer", "rejected", "hired"):
            raise ValueError("Bitte einen gültigen Bewerbungsstatus auswählen.")
        submitted_at = str(data.get("submitted_at") or datetime.now().isoformat(timespec="seconds")).strip()
        try:
            datetime.fromisoformat(submitted_at)
        except ValueError:
            raise ValueError("Das Eingangsdatum ist ungültig.") from None
        values = {field: str(data.get(field, "")).strip() for field in
                  ("source_id", "first_name", "last_name", "address", "postcode", "city",
                   "email", "phone", "trial_dates", "message", "notes")}
        if not values["source_id"]:
            values["source_id"] = f"manual-{uuid4().hex}"
        if not values["first_name"] or not values["last_name"]:
            raise ValueError("Vorname und Nachname sind erforderlich.")
        values.update({"category": category, "status": status,
                       "vocational_baccalaureate": 1 if data.get("vocational_baccalaureate") else 0,
                       "suitability": str(data.get("suitability", "")).strip(),
                       "server_deleted": 1 if data.get("server_deleted") else 0,
                       "submitted_at": submitted_at,
                       "updated": datetime.now().isoformat(timespec="seconds")})
        if values["suitability"] not in ("", "unsuitable", "possible", "suitable"):
            raise ValueError("Bitte eine gültige Beurteilung auswählen.")
        return self._save("applicants", values, key)

    def set_applicant_suitability(self, key, suitability, server_deleted=None):
        if suitability not in ("unsuitable", "possible", "suitable") or not self.applicant(key):
            raise ValueError("Bitte eine gültige Bewerbung und Beurteilung auswählen.")
        values = {"suitability": suitability, "updated": datetime.now().isoformat(timespec="seconds")}
        if server_deleted is not None:
            values["server_deleted"] = 1 if server_deleted else 0
        self._save("applicants", values, key)

    def set_applicant_notes(self, key, notes):
        if not self.applicant(key):
            raise ValueError("Die Bewerbung existiert nicht mehr.")
        self._save("applicants", {"notes": str(notes or "").strip(),
                                  "updated": datetime.now().isoformat(timespec="seconds")}, key)

    def applicant_files(self, applicant_id):
        return self.rows("SELECT * FROM applicant_files WHERE applicant_id=? ORDER BY category,original_name",
                         (applicant_id,))

    def save_applicant_file(self, applicant_id, category, original_name, local_path, source_ref=""):
        if not self.applicant(applicant_id):
            raise ValueError("Die Bewerbung existiert nicht mehr.")
        values = {"applicant_id": applicant_id, "category": str(category or "other").strip(),
                  "original_name": str(original_name).strip(), "local_path": str(local_path).strip(),
                  "source_ref": str(source_ref).strip()}
        if not values["original_name"] or not values["local_path"]:
            raise ValueError("Die Dokumentangaben sind unvollständig.")
        return self._save("applicant_files", values)

    def backup(self, destination):
        target = Path(destination)
        if target.resolve() == self.path.resolve():
            raise ValueError("Die Sicherung braucht einen anderen Dateinamen als die aktive Datenbank.")
        target.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(target)) as out:
            self.conn.backup(out)
        return target

    def restore(self, source):
        source = Path(source).resolve()
        if source == self.path.resolve():
            raise ValueError("Diese Datenbank ist bereits geöffnet.")
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as incoming:
            saved_version = incoming.execute("PRAGMA user_version").fetchone()[0]
            if incoming.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or not 1 <= saved_version <= SCHEMA_VERSION:
                raise ValueError("Die Sicherung ist beschädigt oder hat eine andere Version.")
            expected = {"settings", "customers", "employees", "periods", "entries", "invoices", "payments", "salaries", "audit_log"}
            actual = {r[0] for r in incoming.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not expected <= actual:
                raise ValueError("Das ist keine vollständige AST-Sicherung.")
            if incoming.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Die Sicherung enthält ungültige Verknüpfungen.")
            safety = self.path.parent / "backups" / ("vor-wiederherstellung-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sqlite3")
            self.backup(safety)
            incoming.backup(self.conn)
            self.conn.executescript(SCHEMA)
            time_columns = {row[1] for row in self.conn.execute("PRAGMA table_info(time_records)")}
            if "worked_minutes" not in time_columns:
                self.conn.execute("ALTER TABLE time_records ADD COLUMN worked_minutes INTEGER NOT NULL DEFAULT 0")
                for record in self.rows("SELECT * FROM time_records"):
                    self.conn.execute("UPDATE time_records SET worked_minutes=? WHERE id=?",
                                      (worked_minutes({**record, "worked_minutes": None}), record["id"]))
            if saved_version < 12:
                self._migrate_time_codes()
            self.conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
        return safety
