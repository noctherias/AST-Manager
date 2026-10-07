"""Versioned synchronisation between the desktop database and AST Manager Web."""
from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse


SCHEMA_VERSION = 1
SYNC_SETTING_KEYS = (
    "company", "address", "postcode", "city", "phone", "email", "website", "contact",
    "reminder_text_1", "reminder_text_2", "reminder_text_3", "reminder_text_4",
)
CODE_TO_REASON = {"": "Arbeit", "H": "Feiertag", "F": "Ferien", "K": "Krankheit", "U": "Unfall", "M": "Begründete Minderzeit", "HO": "Homeoffice", "B": "Berufsschule"}
REASON_TO_CODE = {value: key for key, value in CODE_TO_REASON.items()}
REFERENCE_TO_WEB = {"work": "Arbeitszeugnis", "interim": "Zwischenzeugnis", "apprentice": "Lehrzeugnis"}
REFERENCE_TO_DESKTOP = {value: key for key, value in REFERENCE_TO_WEB.items()}
CATEGORY_TO_WEB = {"trial": "Schnupperlehre", "installer": "Elektroinstallateur EFZ", "assembly": "Montage-Elektriker EFZ"}
CATEGORY_TO_DESKTOP = {value: key for key, value in CATEGORY_TO_WEB.items()}
SUITABILITY_TO_WEB = {"": "Offen", "unsuitable": "Nicht geeignet", "possible": "Eventuell", "suitable": "Geeignet"}
SUITABILITY_TO_DESKTOP = {value: key for key, value in SUITABILITY_TO_WEB.items()}


class WebSyncError(ValueError):
    pass


class WebSyncConflict(WebSyncError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _rows(db, table: str) -> list[dict]:
    return db.rows(f"SELECT * FROM {table} ORDER BY id")


def build_snapshot(db) -> dict:
    """Translate the lossless desktop values into the web API schema."""
    # Desktop rows do not store creation timestamps. A stable value keeps the
    # change fingerprint deterministic between synchronisation cycles.
    timestamp = "1970-01-01T00:00:00Z"
    customers = _rows(db, "customers")
    customer_names = {row["id"]: row["name"] for row in customers}
    employees = _rows(db, "employees")
    payments = _rows(db, "payments")
    paid = {}
    for row in payments:
        paid[row["invoice_id"]] = paid.get(row["invoice_id"], 0) + row["amount"]
    invoices = _rows(db, "invoices")
    web_invoices = [{
        "id": row["id"], "invoice_number": row["number"], "customer": customer_names[row["customer_id"]],
        "invoice_date": row["issued"], "due_date": row["due"], "amount": row["amount"] / 100,
        "paid_amount": paid.get(row["id"], 0) / 100, "notes": row["note"],
        "created_at": timestamp, "updated_at": timestamp,
    } for row in invoices]
    reminders = [{
        "id": row["id"], "invoice_id": row["id"], "customer": customer_names[row["customer_id"]],
        "invoice_number": row["number"], "level": row["reminder_level"], "amount": row["amount"] / 100,
        "reminder_date": row["reminder_date"], "reminder_text": "", "status": "Erstellt", "created_at": timestamp,
    } for row in invoices if row["reminder_level"]]
    settings = db.settings()
    tables = {
        "customers": [{**row, "created_at": timestamp, "updated_at": timestamp} for row in customers],
        "employees": [{
            "id": row["id"], "first_name": row["first_name"], "last_name": row["last_name"],
            "personnel_number": row["code"], "employee_type": row["kind"], "entry_date": row["hired"],
            "vacation_hours": row["allowance"] / 100, "active": row["active"], "created_at": timestamp,
            "updated_at": timestamp, "salutation": row["salutation"], "ahv": row["ahv"],
            "ahv_old": row["ahv_old"], "birth_date": row["birth_date"], "address": row["address"],
            "postcode": row["postcode"], "city": row["city"], "job": row["job"],
            "workload": row["workload"] / 100,
        } for row in employees],
        "invoices": web_invoices,
        "invoice_payments": [{
            "id": row["id"], "invoice_id": row["invoice_id"], "payment_date": row["day"],
            "amount": row["amount"] / 100, "notes": row["note"], "created_at": timestamp,
        } for row in payments],
        "reminders": reminders,
        "time_entries": [{
            "id": row["id"], "employee_id": row["employee_id"], "work_date": row["day"],
            "hours": row["worked_minutes"] / 60, "reason": CODE_TO_REASON.get(row["code"], "Begründete Minderzeit"),
            "notes": row["note"], "created_at": timestamp,
        } for row in _rows(db, "time_records")],
        "certificates": [{
            "id": row["id"], "employee_id": row["employee_id"], "certificate_type": REFERENCE_TO_WEB[row["reference_type"]],
            "reference_date": row["issue_date"], "status": "Gespeichert", "notes": "", "created_at": row["updated"],
            "reason": row["reason"], "tasks": row["tasks"], "ratings": row["ratings"], "generated_text": row["text"],
        } for row in _rows(db, "employment_references")],
        "applications": [{
            "id": row["id"], "applicant_name": (row["first_name"] + " " + row["last_name"]).strip(),
            "email": row["email"], "phone": row["phone"], "application_type": CATEGORY_TO_WEB[row["category"]],
            "received_date": row["submitted_at"][:10], "rating": SUITABILITY_TO_WEB[row["suitability"]],
            "notes": row["notes"], "source": row["source_id"], "created_at": row["submitted_at"],
            "first_name": row["first_name"], "last_name": row["last_name"], "address": row["address"],
            "postcode": row["postcode"], "city": row["city"], "status": row["status"],
            "trial_dates": row["trial_dates"], "vocational_baccalaureate": row["vocational_baccalaureate"],
            "message": row["message"], "server_deleted": row["server_deleted"],
        } for row in _rows(db, "applicants")],
        "application_files": [{
            "id": row["id"], "application_id": row["applicant_id"], "category": row["category"],
            "original_name": row["original_name"], "source_ref": row["source_ref"], "created_at": timestamp,
        } for row in _rows(db, "applicant_files")],
        "salary_certificates": [{
            "id": row["id"], "employee_id": row["employee_id"], "tax_year": row["year"],
            "gross_salary": _salary_gross(row["fields"]), "status": "Gespeichert", "notes": "",
            "created_at": row["updated"], "period_start": row["start"], "period_end": row["end"],
            "fields_json": row["fields"],
        } for row in _rows(db, "salaries")],
        "app_settings": [{"setting_key": key, "setting_value": settings.get(key, ""), "updated_at": timestamp}
                         for key in SYNC_SETTING_KEYS],
        "reminder_templates": [{"level": level, "title": title, "body": settings.get(f"reminder_text_{level}", ""), "updated_at": timestamp}
                               for level, title in ((1, "Zahlungserinnerung"), (2, "Mahnung 1"), (3, "Mahnung 2"), (4, "Betreibung"))],
    }
    return {"schema": SCHEMA_VERSION, "tables": tables}


def _salary_gross(raw: str) -> float:
    try:
        fields = json.loads(raw or "{}")
        value = fields.get("8", fields.get("8Brutto", 0))
        return float(str(value).replace("'", "").replace(",", ".") or 0)
    except (TypeError, ValueError, json.JSONDecodeError):
        return 0.0


def apply_snapshot(db, payload: dict) -> None:
    """Replace desktop business data with a validated web snapshot in one transaction."""
    if payload.get("schema") != SCHEMA_VERSION or not isinstance(payload.get("tables"), dict):
        raise WebSyncError("Der Server verwendet ein nicht unterstütztes Datenformat.")
    tables = payload["tables"]
    required = {"customers", "employees", "invoices", "invoice_payments", "time_entries", "certificates", "applications", "salary_certificates"}
    if not required.issubset(tables) or any(not isinstance(tables[name], list) for name in required):
        raise WebSyncError("Der Serverdatenstand ist unvollständig.")
    customer_by_name = {str(row.get("name", "")): int(row["id"]) for row in tables["customers"]}
    try:
        with db.conn:
            for table in ("applicant_files", "entries", "periods", "payments", "invoices", "time_records", "employment_references", "salaries", "applicants", "employees", "customers"):
                db.conn.execute(f"DELETE FROM {table}")
            _insert(db.conn, "customers", ("id", "name", "customer_number", "address", "postcode", "city", "email"), tables["customers"])
            employee_rows = [{
                "id": row["id"], "code": row.get("personnel_number") or f"WEB-{row['id']}", "first_name": row.get("first_name", ""), "last_name": row.get("last_name", ""),
                "kind": row.get("employee_type", "employee"), "salutation": row.get("salutation", ""), "ahv": row.get("ahv", ""), "ahv_old": row.get("ahv_old", ""),
                "birth_date": row.get("birth_date", ""), "address": row.get("address", ""), "postcode": row.get("postcode", ""), "city": row.get("city", ""),
                "hired": row.get("entry_date") or "1900-01-01", "job": row.get("job", ""), "workload": round(float(row.get("workload", 100)) * 100),
                "allowance": round(float(row.get("vacation_hours", 173)) * 100), "active": int(row.get("active", 1)),
            } for row in tables["employees"]]
            _insert(db.conn, "employees", tuple(employee_rows[0].keys()) if employee_rows else ("id", "code", "first_name", "last_name", "kind", "salutation", "ahv", "ahv_old", "birth_date", "address", "postcode", "city", "hired", "job", "workload", "allowance", "active"), employee_rows)
            invoice_rows = [{
                "id": row["id"], "number": row.get("invoice_number", ""), "customer_id": customer_by_name[row.get("customer", "")],
                "issued": row.get("invoice_date", ""), "due": row.get("due_date", ""), "amount": round(float(row.get("amount", 0)) * 100),
                "note": row.get("notes", ""), "reminder_level": 0, "reminder_date": "",
            } for row in tables["invoices"]]
            reminders = {int(row["invoice_id"]): row for row in tables.get("reminders", []) if row.get("invoice_id")}
            for row in invoice_rows:
                reminder = reminders.get(row["id"])
                if reminder:
                    row["reminder_level"] = int(reminder.get("level", 0))
                    row["reminder_date"] = reminder.get("reminder_date", "")
            _insert(db.conn, "invoices", tuple(invoice_rows[0].keys()) if invoice_rows else ("id", "number", "customer_id", "issued", "due", "amount", "note", "reminder_level", "reminder_date"), invoice_rows)
            payment_rows = [{"id": row["id"], "invoice_id": row["invoice_id"], "day": row.get("payment_date", ""), "amount": round(float(row.get("amount", 0)) * 100), "note": row.get("notes", "")} for row in tables["invoice_payments"]]
            _insert(db.conn, "payments", ("id", "invoice_id", "day", "amount", "note"), payment_rows)
            time_rows = [{"id": row["id"], "employee_id": row["employee_id"], "day": row.get("work_date", ""), "start_1": None, "end_1": None, "start_2": None, "end_2": None, "break_minutes": 0, "worked_minutes": round(float(row.get("hours", 0)) * 60), "code": REASON_TO_CODE.get(row.get("reason", "Arbeit"), "M"), "note": row.get("notes", "")} for row in tables["time_entries"]]
            _insert(db.conn, "time_records", tuple(time_rows[0].keys()) if time_rows else ("id", "employee_id", "day", "start_1", "end_1", "start_2", "end_2", "break_minutes", "worked_minutes", "code", "note"), time_rows)
            reference_rows = [{"id": row["id"], "employee_id": row["employee_id"], "reference_type": REFERENCE_TO_DESKTOP.get(row.get("certificate_type"), "work"), "issue_date": row.get("reference_date", ""), "end_date": "", "reason": row.get("reason", ""), "tasks": row.get("tasks", ""), "ratings": row.get("ratings", "{}"), "text": row.get("generated_text", ""), "updated": row.get("created_at", _now())} for row in tables["certificates"]]
            _insert(db.conn, "employment_references", tuple(reference_rows[0].keys()) if reference_rows else ("id", "employee_id", "reference_type", "issue_date", "end_date", "reason", "tasks", "ratings", "text", "updated"), reference_rows)
            application_rows = [{"id": row["id"], "source_id": row.get("source") if row.get("source") not in (None, "", "Manuell") else f"web-{row['id']}", "category": CATEGORY_TO_DESKTOP.get(row.get("application_type"), "trial"), "status": row.get("status", "new") if row.get("status") in ("new", "review", "interview", "trial", "offer", "rejected", "hired") else "new", "first_name": row.get("first_name", ""), "last_name": row.get("last_name", ""), "address": row.get("address", ""), "postcode": row.get("postcode", ""), "city": row.get("city", ""), "email": row.get("email", ""), "phone": row.get("phone", ""), "vocational_baccalaureate": int(row.get("vocational_baccalaureate", 0)), "trial_dates": row.get("trial_dates", ""), "message": row.get("message", ""), "notes": row.get("notes", ""), "suitability": SUITABILITY_TO_DESKTOP.get(row.get("rating"), ""), "server_deleted": int(row.get("server_deleted", 0)), "submitted_at": row.get("created_at", _now()), "updated": _now()} for row in tables["applications"]]
            _insert(db.conn, "applicants", tuple(application_rows[0].keys()) if application_rows else ("id", "source_id", "category", "status", "first_name", "last_name", "address", "postcode", "city", "email", "phone", "vocational_baccalaureate", "trial_dates", "message", "notes", "suitability", "server_deleted", "submitted_at", "updated"), application_rows)
            file_rows = [{"id": row["id"], "applicant_id": row["application_id"], "category": row.get("category", "other"), "original_name": row.get("original_name", ""), "local_path": "", "source_ref": row.get("source_ref", "")} for row in tables.get("application_files", [])]
            _insert(db.conn, "applicant_files", ("id", "applicant_id", "category", "original_name", "local_path", "source_ref"), file_rows)
            salary_rows = [{"id": row["id"], "employee_id": row["employee_id"], "year": row.get("tax_year"), "start": row.get("period_start", ""), "end": row.get("period_end", ""), "fields": row.get("fields_json", "{}"), "updated": row.get("created_at", _now())} for row in tables["salary_certificates"]]
            _insert(db.conn, "salaries", ("id", "employee_id", "year", "start", "end", "fields", "updated"), salary_rows)
            for row in tables.get("app_settings", []):
                if row.get("setting_key") in SYNC_SETTING_KEYS:
                    db.conn.execute("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (row["setting_key"], str(row.get("setting_value", ""))))
    except (sqlite3.Error, KeyError, TypeError, ValueError) as exc:
        raise WebSyncError("Der Serverdatenstand konnte nicht übernommen werden: " + str(exc)) from exc


def _insert(conn, table: str, columns: tuple[str, ...], rows: list[dict]) -> None:
    if not rows:
        return
    sql = f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})"
    conn.executemany(sql, ([row.get(column) for column in columns] for row in rows))


class WebSyncClient:
    def __init__(self, base_url: str, email: str, password: str, timeout: int = 30):
        parsed = urlparse(base_url.strip())
        if parsed.scheme != "https" or not parsed.netloc:
            raise WebSyncError("Die Webadresse muss eine vollständige HTTPS-Adresse sein.")
        self.endpoint = base_url.rstrip("/") + "/sync.php"
        token = base64.b64encode(f"{email.strip()}:{password}".encode("utf-8")).decode("ascii")
        self.headers = {"Authorization": "Basic " + token, "Accept": "application/json", "User-Agent": "AST-Verwaltung-Desktop"}
        self.timeout = timeout

    def fetch(self) -> dict:
        return self._request("GET")

    def push(self, snapshot: dict, revision: int) -> int:
        response = self._request("POST", snapshot, {"If-Match": str(revision)})
        return int(response["revision"])

    def _request(self, method: str, payload: dict | None = None, extra: dict | None = None) -> dict:
        data = None if payload is None else json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        headers = {**self.headers, **(extra or {})}
        if data is not None:
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(self.endpoint, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("error", "")
            except Exception:
                detail = ""
            if exc.code == 409:
                raise WebSyncConflict(detail or "Der Webdatenstand wurde inzwischen geändert.") from exc
            if exc.code == 401:
                raise WebSyncError("Anmeldung fehlgeschlagen. Bitte E-Mail und Passwort prüfen.") from exc
            raise WebSyncError(detail or f"Der Webserver antwortete mit Fehler {exc.code}.") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise WebSyncError("Die Webversion ist derzeit nicht erreichbar oder antwortet ungültig.") from exc
        if not isinstance(result, dict):
            raise WebSyncError("Die Webversion hat keine gültige Antwort gesendet.")
        return result


def snapshot_fingerprint(snapshot: dict) -> str:
    payload = json.dumps(snapshot.get("tables", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def push_desktop(db, client: WebSyncClient) -> int:
    remote = client.fetch()
    snapshot = build_snapshot(db)
    revision = client.push(snapshot, int(remote.get("revision", 0)))
    db.save_settings({"web_sync_revision": revision, "web_sync_fingerprint": snapshot_fingerprint(snapshot)})
    return revision


def pull_web(db, client: WebSyncClient) -> int:
    remote = client.fetch()
    backup = db.path.parent / "backups" / f"vor-web-sync-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
    backup.parent.mkdir(parents=True, exist_ok=True)
    db.backup(backup)
    apply_snapshot(db, remote)
    revision = int(remote.get("revision", 0))
    db.save_settings({"web_sync_revision": revision, "web_sync_fingerprint": snapshot_fingerprint(build_snapshot(db))})
    return revision


def automatic_sync(db, client: WebSyncClient) -> str:
    """Synchronise one side when only that side changed; never guess on conflicts."""
    settings = db.settings()
    if not settings.get("web_sync_revision") or not settings.get("web_sync_fingerprint"):
        raise WebSyncConflict("Bitte die erste Synchronisation einmal in den Einstellungen festlegen.")
    remote = client.fetch()
    previous_revision = int(settings["web_sync_revision"])
    current_snapshot = build_snapshot(db)
    current_fingerprint = snapshot_fingerprint(current_snapshot)
    local_changed = current_fingerprint != settings["web_sync_fingerprint"]
    remote_changed = int(remote.get("revision", 0)) != previous_revision
    if local_changed and remote_changed:
        raise WebSyncConflict("Desktop und Web wurden seit der letzten Synchronisation geändert. Bitte den gewünschten Datenstand in den Einstellungen wählen.")
    if local_changed:
        revision = client.push(current_snapshot, previous_revision)
        db.save_settings({"web_sync_revision": revision, "web_sync_fingerprint": current_fingerprint})
        return "Desktop-Änderungen wurden ins Web übertragen."
    if remote_changed:
        backup = db.path.parent / "backups" / f"vor-web-sync-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
        backup.parent.mkdir(parents=True, exist_ok=True)
        db.backup(backup)
        apply_snapshot(db, remote)
        db.save_settings({"web_sync_revision": int(remote["revision"]), "web_sync_fingerprint": snapshot_fingerprint(build_snapshot(db))})
        return "Web-Änderungen wurden auf diesen PC übernommen."
    return "Desktop und Web sind bereits auf demselben Stand."

