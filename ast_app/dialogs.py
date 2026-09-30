from __future__ import annotations

from datetime import date, timedelta
from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QWidget, QTabWidget, QScrollArea,
    QFormLayout, QDialogButtonBox, QCheckBox, QFrame, QComboBox, QTimeEdit, QSpinBox)

from .domain import units, number, chf, KINDS, TIME_CODES, SALARY_AMOUNTS, SALARY_TEXT, SALARY_FLAGS, salary_totals
from .widgets import FormDialog, line, numeric, combo, day, day_value, label, button, guarded, Table, confirm, Disclosure


class CustomerDialog(FormDialog):
    def __init__(self, parent, db, row=None):
        super().__init__(parent, "Kunde bearbeiten" if row else "Neuer Kunde", "Kundendaten werden zentral für alle Rechnungen verwendet.")
        self.db, self.row = db, row or {}
        for key, title in [("name", "Name / Firma *"), ("customer_number", "Kunden-Nr."),
                           ("address", "Strasse"), ("postcode", "PLZ"), ("city", "Ort"), ("email", "E-Mail")]:
            self.add(key, title, line(self.row.get(key, "")))

    @guarded
    def submit(self):
        self.saved_id = self.db.save_customer(self.values(), self.row.get("id"))
        self.accept()


class EmployeeDialog(FormDialog):
    def __init__(self, parent, db, row=None, kind="employee"):
        super().__init__(parent, "Person bearbeiten" if row else "Neue Person", "Ein Stammdatensatz für Stunden, Ferien und Lohnausweise.", 650)
        self.db, self.row = db, row or {}
        r = self.row
        if not row:
            used = {e["code"] for e in db.employees()}
            candidate = len(used) + 1
            while f"AST-{candidate:03d}" in used: candidate += 1
            r["code"] = f"AST-{candidate:03d}"
        for key, title in [("first_name", "Vorname *"), ("last_name", "Nachname *")]:
            self.add(key, title, line(r.get(key, "")))
        self.add("kind", "Bereich", combo([("Mitarbeiter", "employee"), ("Lernende", "apprentice")], r.get("kind", kind)))
        self.add("hired", "Eintritt", day(r.get("hired")))
        self.add("allowance", "Ferienanspruch pro Jahr", numeric(r.get("allowance", 21625) / 100, " h"))
        self.form.addRow(label("Anspruch in Stunden eingeben. Das Pensum wird nicht nochmals abgezogen.", "muted"))
        basic = self.form
        extra = Disclosure("Personalangaben & Adresse (für Lohnausweise)")
        basic.addRow(extra)
        self.form = extra.form
        self.add("code", "Personalnummer *", line(r.get("code", "")))
        self.add("job", "Funktion", line(r.get("job")))
        self.add("workload", "Pensum", numeric(r.get("workload", 10000) / 100, " %"))
        self.fields["workload"].setRange(.01, 100)
        for key, title in [("salutation", "Anrede"), ("ahv", "AHV-Nr."), ("ahv_old", "Alte AHV-Nr."),
                           ("address", "Strasse"), ("postcode", "PLZ"), ("city", "Ort")]:
            self.add(key, title, line(r.get(key, "")))
        self.add("birth_date", "Geburtsdatum", line(r.get("birth_date", ""), "JJJJ-MM-TT"))
        active = QCheckBox("Aktiv")
        active.setChecked(bool(r.get("active", 1)))
        self.add("active", "Status", active)
        self.form = basic

    @guarded
    def submit(self):
        values = self.values()
        for k in ("workload", "allowance"):
            values[k] = units(values[k])
        self.saved_id = self.db.save_employee(values, self.row.get("id"))
        self.accept()


class InvoiceDialog(FormDialog):
    def __init__(self, parent, db, row=None):
        super().__init__(parent, "Rechnung bearbeiten" if row else "Neue Rechnung", "Teilzahlungen werden anschliessend separat erfasst.", 650)
        self.db, self.row = db, row or {}
        r = self.row
        self.add("number", "Rechnungsnummer *", line(r.get("number", ""), "z. B. 2026-1042"))
        customer = combo([(c["name"], c["id"]) for c in db.customers()], r.get("customer_id"))
        self.add("customer_id", "Kunde *", customer)
        self.form.addRow("", button("+ Neuen Kunden erfassen", self.new_customer))
        self.add("issued", "Rechnungsdatum", day(r.get("issued")))
        self.add("due", "Fällig am", day(r.get("due", (date.today() + timedelta(days=30)).isoformat())))
        self.add("amount", "Rechnungsbetrag", numeric(r.get("amount", 0) / 100, " CHF"))
        self.add("note", "Bemerkung", line(r.get("note", "")))

    def new_customer(self):
        d = CustomerDialog(self, self.db)
        if d.exec():
            self.fields["customer_id"].clear()
            for c in self.db.customers():
                self.fields["customer_id"].addItem(c["name"], c["id"])
            self.fields["customer_id"].setCurrentIndex(self.fields["customer_id"].findData(d.saved_id))

    @guarded
    def submit(self):
        data = self.values()
        if not data["customer_id"]:
            raise ValueError("Bitte zuerst einen Kunden erfassen.")
        data["amount"] = units(data["amount"])
        self.saved_id = self.db.save_invoice(data, self.row.get("id"))
        self.accept()


class PaymentDialog(FormDialog):
    def __init__(self, parent, db, invoice):
        super().__init__(parent, "Zahlungen · " + invoice["number"], invoice["customer"], 690)
        self.db, self.invoice = db, invoice
        self.table = Table(["Valutadatum", "Betrag", "Bemerkung"])
        self.table.setMaximumHeight(220)
        previous = Disclosure("Bisherige Zahlungen anzeigen")
        previous.form.addRow(self.table)
        previous.form.addRow(button("Ausgewählte Zahlung entfernen", self.remove))
        self.summary = label("", "sectionTitle")
        self.form.addRow(self.summary)
        self.add("day", "Valutadatum", day())
        self.add("amount", "Zahlungsbetrag", numeric(invoice["open"] / 100, " CHF"))
        self.add("note", "Bemerkung", line())
        self.form.addRow(previous)
        self.save_button.setText("Zahlung speichern")
        self.cancel_button.setText("Schliessen")
        self.refresh()

    def refresh(self):
        from .domain import display_date
        rows = self.db.payments(self.invoice["id"])
        self.table.populate([[display_date(r["day"]), chf(r["amount"]), r["note"]] for r in rows], [r["id"] for r in rows], [1])
        remaining = self.invoice["amount"] - sum(r["amount"] for r in rows)
        self.summary.setText("Noch offen: " + chf(remaining))
        self.fields["amount"].setValue(remaining / 100)
        self.save_button.setEnabled(remaining > 0)

    @guarded
    def remove(self):
        key = self.table.selected_id()
        if key and confirm(self, "Diese Zahlung entfernen? Der offene Rechnungsbetrag wird neu berechnet."):
            self.db.delete("payments", key)
            self.refresh()

    @guarded
    def submit(self):
        d = self.values()
        self.db.add_payment(self.invoice["id"], d["day"], units(d["amount"]), d["note"])
        self.accept()


class ReminderDialog(FormDialog):
    def __init__(self, parent, db, invoice):
        super().__init__(parent, "Mahnstufe festlegen", f"Rechnung {invoice['number']} · {invoice['customer']}")
        self.db, self.invoice = db, invoice
        self.add("level", "Mahnstufe", combo([
            ("Keine Mahnung", 0), ("1. Zahlungserinnerung", 1),
            ("2. Mahnung 1", 2), ("3. Mahnung 2", 3), ("4. Betreibung", 4),
        ], invoice.get("reminder_level", 0)))
        self.add("reminder_date", "Mahndatum", day(invoice.get("reminder_date") or date.today().isoformat()))
        hint = label("Stufe 0 entfernt die aktuelle Mahnkennzeichnung. Bereits erfasste Zahlungen bleiben unverändert.", "muted")
        hint.setWordWrap(True)
        self.form.addRow("", hint)
        self.save_button.setText("Mahnstufe speichern")

    @guarded
    def submit(self):
        values = self.values()
        self.db.set_reminder(self.invoice["id"], values["level"], values["reminder_date"])
        self.accept()


class ManualReminderDialog(FormDialog):
    """Collect a complete reminder letter without creating an invoice first."""
    def __init__(self, parent, db):
        super().__init__(parent, "Mahnung manuell erstellen",
                         "Empfänger und Forderung direkt erfassen. Es wird keine Rechnung in den Debitoren angelegt.", 680)
        self.db = db
        customers = [("– Empfänger manuell eingeben –", None)] + [
            (customer["name"], customer["id"]) for customer in db.customers()
        ]
        self.customer_picker = self.add("customer_id", "Aus Stammdaten übernehmen", combo(customers, None))
        self.add("customer", "Name / Firma *", line())
        self.add("customer_number", "Kunden-Nr.", line())
        self.add("customer_address", "Strasse", line())
        self.add("customer_postcode", "PLZ", line())
        self.add("customer_city", "Ort", line())
        self.add("customer_email", "E-Mail", line())
        self.add("number", "Rechnungsnummer *", line(placeholder="z. B. 2026-1042"))
        self.add("issued", "Rechnungsdatum", day())
        self.add("due", "Fällig am", day((date.today() + timedelta(days=30)).isoformat()))
        self.add("open", "Geforderter Betrag", numeric(0, " CHF"))
        self.add("level", "Mahnstufe", combo([
            ("1. Zahlungserinnerung", 1), ("2. Mahnung 1", 2),
            ("3. Mahnung 2", 3), ("4. Betreibung", 4),
        ], 1))
        hint = label("Der passende Mahntext und das Firmenlogo werden automatisch aus den Einstellungen übernommen.", "muted")
        hint.setWordWrap(True)
        self.form.addRow("", hint)
        self.customer_picker.currentIndexChanged.connect(self.use_customer)
        self.save_button.setText("Mahnbrief erstellen")
        self.invoice = None
        self.level = 1

    def use_customer(self):
        key = self.customer_picker.currentData()
        customer = next((row for row in self.db.customers() if row["id"] == key), None)
        if not customer:
            return
        for field, source in (("customer", "name"), ("customer_number", "customer_number"),
                              ("customer_address", "address"),
                              ("customer_postcode", "postcode"), ("customer_city", "city"),
                              ("customer_email", "email")):
            self.fields[field].setText(customer.get(source, ""))

    @guarded
    def submit(self):
        values = self.values()
        if not values["customer"] or not values["number"]:
            raise ValueError("Bitte Name/Firma und Rechnungsnummer eingeben.")
        if values["due"] < values["issued"]:
            raise ValueError("Das Fälligkeitsdatum darf nicht vor dem Rechnungsdatum liegen.")
        amount = units(values["open"])
        if amount <= 0:
            raise ValueError("Bitte einen positiven geforderten Betrag eingeben.")
        self.invoice = {
            "customer": values["customer"],
            "customer_number": values["customer_number"],
            "customer_address": values["customer_address"],
            "customer_postcode": values["customer_postcode"],
            "customer_city": values["customer_city"],
            "customer_email": values["customer_email"],
            "number": values["number"],
            "issued": values["issued"],
            "due": values["due"],
            "open": amount,
        }
        self.level = int(values["level"])
        self.accept()


class PeriodDialog(FormDialog):
    def __init__(self, parent, db, employee, row=None):
        super().__init__(parent, "Jahr bearbeiten" if row else "Jahr einrichten",
                         "Guthaben aus dem vorherigen Jahr werden automatisch übernommen.", 690)
        self.db, self.employee, self.row = db, employee, row or {}
        periods = db.periods(employee["id"])
        start = date.fromisoformat(periods[-1]["end"]) + timedelta(days=1) if periods else date(date.today().year, 1, 1)
        if not periods and employee["kind"] == "apprentice":
            start = date.fromisoformat(employee["hired"])
        try:
            end = start.replace(year=start.year + 1) - timedelta(days=1)
        except ValueError:
            end = date(start.year + 1, 2, 28) - timedelta(days=1)
        r = self.row
        caption = f"Lehrjahr {len(periods)+1}" if employee["kind"] == "apprentice" else str(start.year)
        self.add("label", "Bezeichnung", line(r.get("label", caption)))
        self.add("start", "Von", day(r.get("start", start.isoformat())))
        self.add("end", "Bis", day(r.get("end", end.isoformat())))
        self.add("allowance", "Ferienanspruch", numeric(r.get("allowance", employee["allowance"]) / 100, " h"))
        first = not periods or (r and periods[0]["id"] == r["id"])
        basic = self.form
        opening = Disclosure("Bestehende Guthaben beim Einstieg übernehmen")
        basic.addRow(opening)
        self.form = opening.form
        for key, title in [("opening", "Startsaldo Guthaben"), ("opening_sick", "Startsaldo Krankheit"), ("opening_accident", "Startsaldo Unfall")]:
            w = self.add(key, title, numeric(r.get(key, 0) / 100, " h", negative=key == "opening"))
            w.setEnabled(bool(first))
        note = label("Startsalden sind nur für den Einstieg mit bestehenden Guthaben nötig.\nIn späteren Perioden wird der Übertrag aus den Vorperioden berechnet.", "muted")
        note.setWordWrap(True)
        self.form.addRow(note)
        self.form = basic

    @guarded
    def submit(self):
        d = self.values()
        for k in ("allowance", "opening", "opening_sick", "opening_accident"):
            d[k] = units(d[k])
        d["employee_id"] = self.employee["id"]
        self.saved_id = self.db.save_period(d, self.row.get("id"))
        self.accept()


class EntryDialog(FormDialog):
    def __init__(self, parent, db, period, row=None):
        super().__init__(parent, "Buchung bearbeiten" if row else "Stunden erfassen", period["label"])
        self.db, self.period, self.row = db, period, row or {}
        r = self.row
        initial = max(period["start"], min(period["end"], date.today().isoformat()))
        w = self.add("day", "Datum", day(r.get("day", initial)))
        w.setDateRange(QDate.fromString(period["start"], "yyyy-MM-dd"), QDate.fromString(period["end"], "yyyy-MM-dd"))
        self.add("kind", "Kategorie", combo([(v, k) for k, v in KINDS.items()], r.get("kind")))
        self.add("hours", "Stunden", numeric(r.get("hours", 0) / 100, " h", negative=True))
        self.add("note", "Bemerkung", line(r.get("note", "")))
        self.form.addRow(label("Dezimalstunden: 1.50 h = 1 Stunde 30 Minuten.\nÜberzeit kann für eine Korrektur oder Kompensation negativ sein.", "muted"))

    @guarded
    def submit(self):
        d = self.values()
        d["hours"] = units(d["hours"])
        d["period_id"] = self.period["id"]
        self.saved_id = self.db.save_entry(d, self.row.get("id"))
        self.accept()


class TimeRecordDialog(FormDialog):
    """Simple front end for the seven editable columns in each Excel day row."""
    def __init__(self, parent, db, employee, row=None):
        super().__init__(parent, "Tag bearbeiten" if row else "Arbeitstag erfassen",
                         employee["first_name"] + " " + employee["last_name"], 680)
        self.db, self.employee, self.row = db, employee, row or {}
        r = self.row
        self.add("day", "Datum", day(r.get("day")))
        self.add("code", "Art des Tages", combo([(title, code) for code, title in TIME_CODES.items()], r.get("code", "")))

        self.has_times = QCheckBox("Arbeitszeiten erfassen")
        self.has_times.setChecked(r.get("start_1") is not None if row else not bool(r.get("code")))
        self.form.addRow("", self.has_times)
        self.start_1 = self._time(r.get("start_1"), 7, 30)
        self.end_1 = self._time(r.get("end_1"), 12, 0)
        self.form.addRow("Kommt", self.start_1)
        self.form.addRow("Geht", self.end_1)

        self.has_second = QCheckBox("Zweiten Arbeitsblock verwenden")
        self.has_second.setChecked(r.get("start_2") is not None if row else True)
        self.form.addRow("", self.has_second)
        self.start_2 = self._time(r.get("start_2"), 13, 0)
        self.end_2 = self._time(r.get("end_2"), 17, 15)
        self.form.addRow("Kommt 2", self.start_2)
        self.form.addRow("Geht 2", self.end_2)

        pause = QSpinBox()
        pause.setRange(0, 1440)
        pause.setSuffix(" min")
        pause.setValue(r.get("break_minutes", 0))
        pause.setMinimumHeight(38)
        self.add("break_minutes", "Zusätzliche Pause", pause)
        self.add("note", "Bemerkung", line(r.get("note", ""), "z. B. Baustelle Zürich"))
        hint = label("Die Pause zwischen Geht und Kommt 2 berechnet Excel automatisch. Hier nur weitere Pausen eintragen.", "muted")
        hint.setWordWrap(True)
        self.form.addRow("", hint)
        self.has_times.toggled.connect(self._state)
        self.has_second.toggled.connect(self._state)
        self.fields["code"].currentIndexChanged.connect(self._code_changed)
        self._state()

    @staticmethod
    def _time(minutes, hour, minute):
        widget = QTimeEdit()
        widget.setDisplayFormat("HH:mm")
        value = int(minutes) if minutes is not None else hour * 60 + minute
        widget.setTime(QTime(value // 60, value % 60))
        widget.setMinimumHeight(38)
        return widget

    def _code_changed(self):
        if self.fields["code"].currentData() and not self.row:
            self.has_times.setChecked(False)

    def _state(self):
        enabled = self.has_times.isChecked()
        self.has_second.setEnabled(enabled)
        for widget in (self.start_1, self.end_1):
            widget.setEnabled(enabled)
        for widget in (self.start_2, self.end_2):
            widget.setEnabled(enabled and self.has_second.isChecked())
        self.fields["break_minutes"].setEnabled(enabled)

    @staticmethod
    def _minutes(widget):
        value = widget.time()
        return value.hour() * 60 + value.minute()

    @guarded
    def submit(self):
        values = self.values()
        values["employee_id"] = self.employee["id"]
        if self.has_times.isChecked():
            values.update(start_1=self._minutes(self.start_1), end_1=self._minutes(self.end_1))
            if self.has_second.isChecked():
                values.update(start_2=self._minutes(self.start_2), end_2=self._minutes(self.end_2))
            else:
                values.update(start_2=None, end_2=None)
        else:
            values.update(start_1=None, end_1=None, start_2=None, end_2=None, break_minutes=0)
        self.saved_id = self.db.save_time_record(values, self.row.get("id"))
        self.accept()


class BulkTimeDialog(FormDialog):
    """Apply one work schedule or absence to weekdays in a date range."""
    def __init__(self, parent, db, employee, year):
        super().__init__(parent, "Zeitraum erfassen",
                         employee["first_name"] + " " + employee["last_name"], 700)
        self.db, self.employee = db, employee
        today = date.today()
        initial = today if today.year == year else date(year, 1, 1)
        self.add("start_day", "Von", day(initial.isoformat()))
        self.add("end_day", "Bis", day(initial.isoformat()))
        for widget in (self.fields["start_day"], self.fields["end_day"]):
            widget.setDateRange(QDate(year, 1, 1), QDate(year, 12, 31))
        week = QWidget()
        week_row = QHBoxLayout(week)
        week_row.setContentsMargins(0, 0, 0, 0)
        self.weekdays = []
        for index, title in enumerate(("Mo", "Di", "Mi", "Do", "Fr", "Sa", "So")):
            check = QCheckBox(title)
            check.setChecked(index < 5)
            week_row.addWidget(check)
            self.weekdays.append(check)
        week_row.addStretch()
        self.form.addRow("Wochentage", week)
        self.add("code", "Art des Tages", combo([(title, code) for code, title in TIME_CODES.items()], ""))
        self.has_times = QCheckBox("Arbeitszeiten erfassen")
        self.has_times.setChecked(True)
        self.form.addRow("", self.has_times)
        self.start_1 = TimeRecordDialog._time(None, 7, 30)
        self.end_1 = TimeRecordDialog._time(None, 12, 0)
        self.start_2 = TimeRecordDialog._time(None, 13, 0)
        self.end_2 = TimeRecordDialog._time(None, 17, 15)
        self.form.addRow("Kommt / Geht", self._pair(self.start_1, self.end_1))
        self.has_second = QCheckBox("Zweiten Arbeitsblock verwenden")
        self.has_second.setChecked(True)
        self.form.addRow("", self.has_second)
        self.form.addRow("Kommt 2 / Geht 2", self._pair(self.start_2, self.end_2))
        self.pause = QSpinBox()
        self.pause.setRange(0, 1440)
        self.pause.setSuffix(" min")
        self.pause.setMinimumHeight(38)
        self.add("break_minutes", "Zusätzliche Pause", self.pause)
        self.add("note", "Bemerkung", line("", "gilt für alle ausgewählten Tage"))
        self.overwrite = QCheckBox("Bereits erfasste Tage überschreiben")
        self.form.addRow("", self.overwrite)
        hint = label("Bestehende Einträge bleiben standardmässig unverändert. Samstag und Sonntag sind abgewählt.", "muted")
        hint.setWordWrap(True)
        self.form.addRow("", hint)
        self.has_times.toggled.connect(self._state)
        self.has_second.toggled.connect(self._state)
        self.fields["code"].currentIndexChanged.connect(self._code_changed)
        self._state()

    @staticmethod
    def _pair(first, second):
        pane = QWidget()
        row = QHBoxLayout(pane)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(first)
        row.addWidget(label("bis", "muted"))
        row.addWidget(second)
        return pane

    def _code_changed(self):
        if self.fields["code"].currentData():
            self.has_times.setChecked(False)

    def _state(self):
        enabled = self.has_times.isChecked()
        self.has_second.setEnabled(enabled)
        for widget in (self.start_1, self.end_1):
            widget.setEnabled(enabled)
        for widget in (self.start_2, self.end_2):
            widget.setEnabled(enabled and self.has_second.isChecked())
        self.pause.setEnabled(enabled)

    @guarded
    def submit(self):
        start = date.fromisoformat(day_value(self.fields["start_day"]))
        end = date.fromisoformat(day_value(self.fields["end_day"]))
        if start > end:
            raise ValueError("Das Enddatum muss nach dem Startdatum liegen.")
        selected = {index for index, check in enumerate(self.weekdays) if check.isChecked()}
        if not selected:
            raise ValueError("Bitte mindestens einen Wochentag auswählen.")
        common = {"employee_id": self.employee["id"], "code": self.fields["code"].currentData() or "",
                  "note": self.fields["note"].text(), "break_minutes": self.pause.value() if self.has_times.isChecked() else 0}
        if self.has_times.isChecked():
            common.update(start_1=TimeRecordDialog._minutes(self.start_1), end_1=TimeRecordDialog._minutes(self.end_1),
                          start_2=TimeRecordDialog._minutes(self.start_2) if self.has_second.isChecked() else None,
                          end_2=TimeRecordDialog._minutes(self.end_2) if self.has_second.isChecked() else None)
        else:
            common.update(start_1=None, end_1=None, start_2=None, end_2=None)
        records = []
        current = start
        while current <= end:
            if current.weekday() in selected:
                records.append({**common, "day": current.isoformat()})
            current += timedelta(days=1)
        self.result_counts = self.db.save_time_records(records, self.overwrite.isChecked())
        self.accept()


class SalaryDialog(QDialog):
    def __init__(self, parent, db, row=None):
        super().__init__(parent)
        self.db, self.row = db, row or {}
        self.saved_id = None
        self.pdf = {}
        self.setWindowTitle("Lohnausweis bearbeiten" if row else "Neuer Lohnausweis")
        self.resize(890, 760)
        self.setMinimumSize(730, 600)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 18)
        layout.addWidget(label(self.windowTitle(), "dialogTitle"))
        layout.addWidget(label("Originalformular · alle Beträge in ganzen CHF · Berechnung erfolgt automatisch", "muted"))
        self.step_label = label("", "sectionTitle")
        layout.addWidget(self.step_label)
        tabs = self.tabs = QTabWidget()
        tabs.tabBar().hide()
        layout.addWidget(tabs, 1)

        def tab(name):
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            pane = QWidget()
            form = QFormLayout(pane)
            form.setContentsMargins(18, 18, 22, 18)
            form.setSpacing(11)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            scroll.setWidget(pane)
            tabs.addTab(scroll, name)
            return form

        identity = tab("Person && Zeitraum")
        self.person = combo([(f"{e['first_name']} {e['last_name']} · {e['code']}", e["id"]) for e in db.employees()], self.row.get("employee_id"))
        identity.addRow("Person", self.person)
        self.year = numeric(self.row.get("year", date.today().year), integer=True)
        self.year.setRange(1900, 2200)
        self.year.setGroupSeparatorShown(False)
        identity.addRow("Jahr", self.year)
        self.start = day(self.row.get("start", f"{self.year.value()}-01-01"))
        self.end = day(self.row.get("end", f"{self.year.value()}-12-31"))
        identity.addRow("Von", self.start)
        identity.addRow("Bis", self.end)
        self.doc_type = combo([("Lohnausweis (A)", "A"), ("Rentenbescheinigung (B)", "B")], "B" if self.row.get("fields", {}).get("B") == "/Ja" else "A")
        identity.addRow("Formularart", self.doc_type)
        address = Disclosure("Übernommene Personalangaben prüfen / ändern")
        identity.addRow(address)
        identity = address.form
        for k, title in [("C", "Alte AHV-Nr."), ("C2", "AHV-Nr."), ("CGebDatum", "Geburtsdatum"), ("HAnrede", "Anrede"), ("HName", "Name im Formular"),
                          ("HAdresse", "Strasse"), ("HPostfach", "Adresszusatz / Postfach"), ("HWohnort", "PLZ und Ort")]:
            self.pdf[k] = line(max_length=100)
            identity.addRow(title, self.pdf[k])
        identity.addRow(button("Aktuelle Stammdaten übernehmen", self.prefill))
        money_form = tab("Lohn && Abzüge")
        expenses = tab("Spesen && Angaben")
        extra_wage = Disclosure("Weitere Lohnbestandteile & Abzüge")
        for idx, (k, title) in enumerate(SALARY_AMOUNTS):
            self.pdf[k] = numeric(0, " CHF", integer=True)
            target = money_form if k in ("1", "9", "10-1", "12") else extra_wage.form if idx < 13 else expenses
            target.addRow(title, self.pdf[k])
            self.pdf[k].valueChanged.connect(self.update_totals)
        money_form.addRow(extra_wage)
        for k, title in SALARY_TEXT:
            self.pdf[k] = line(max_length=180)
            expenses.addRow(title, self.pdf[k])
        for k, title in SALARY_FLAGS:
            self.pdf[k] = QCheckBox(title)
            expenses.addRow(self.pdf[k])
        issuer = tab("Prüfen & speichern")
        self.review_label = label("", "sectionTitle")
        self.review_label.setWordWrap(True)
        issuer.addRow(self.review_label)
        issuer.addRow(label("Bitte kontrolliere Person, Zeitraum und Beträge. Danach den Ausweis speichern.\nDas PDF kannst du anschliessend in der Übersicht ansehen und speichern.", "muted"))
        self.pdf["OrtDatum"] = line(max_length=100)
        issuer.addRow("Ort und Datum", self.pdf["OrtDatum"])
        for idx, title in enumerate(["Arbeitgeber", "Strasse", "PLZ und Ort", "Telefon", "Verantwortliche Person"]):
            k = f"Unterschrift1.{idx}"
            self.pdf[k] = line(max_length=80)
            issuer.addRow(title, self.pdf[k])
        issuer.addRow(label("Gespeicherte Ausweise behalten ihre damaligen Adress- und Firmendaten.\nDie PDF bettet alle Werte sichtbar und druckfest ein. Änderungen bitte in AST speichern\nund anschliessend neu exportieren, damit die Summen aktuell bleiben.", "muted"))
        self.totals_label = label("", "sectionTitle")
        layout.addWidget(self.totals_label)
        buttons = QDialogButtonBox()
        buttons.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        self.back_button = buttons.addButton("Zurück", QDialogButtonBox.ButtonRole.ActionRole)
        self.back_button.clicked.connect(lambda: self.set_step(self.tabs.currentIndex() - 1))
        self.next_button = buttons.addButton("Weiter", QDialogButtonBox.ButtonRole.ActionRole)
        self.next_button.setObjectName("primary")
        self.next_button.clicked.connect(self.next_step)
        self.save_button = save = buttons.addButton("Ausweis speichern", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("primary")
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.submit)
        layout.addWidget(buttons)
        self.person.currentIndexChanged.connect(self.prefill)
        self.year.valueChanged.connect(self.change_year)
        self.prefill()
        if self.row:
            for k, value in self.row["fields"].items():
                widget = self.pdf.get(k)
                if widget is None:
                    continue
                if isinstance(widget, QCheckBox): widget.setChecked(value == "/Ja")
                elif hasattr(widget, "setValue"): widget.setValue(int(value or 0))
                else: widget.setText(value)
        self.update_totals()
        self.set_step(0)

    @guarded
    def next_step(self):
        if self.tabs.currentIndex() == 0:
            if not self.person.currentData(): raise ValueError("Bitte eine Person auswählen.")
            if self.start.date() > self.end.date(): raise ValueError("Das Enddatum muss nach dem Anfangsdatum liegen.")
            if self.start.date().year() != self.year.value() or self.end.date().year() != self.year.value():
                raise ValueError("Der Zeitraum muss im gewählten Jahr liegen.")
        if self.tabs.currentIndex() == 1: salary_totals(self.values())
        self.set_step(self.tabs.currentIndex() + 1)

    def set_step(self, index):
        index = max(0, min(3, index))
        self.tabs.setCurrentIndex(index)
        names = ["Person & Zeitraum", "Lohn & Abzüge", "Spesen & Zusatzangaben", "Prüfen & speichern"]
        self.step_label.setText(f"Schritt {index + 1} von 4 · {names[index]}")
        self.back_button.setVisible(index > 0)
        self.next_button.setVisible(index < 3)
        self.next_button.setText("Weiter" if index != 2 else "Zur Prüfung")
        self.save_button.setVisible(index == 3)
        self.review_label.setText(f"{self.pdf['HName'].text()} · {self.year.value()}\n{self.start.date().toString('dd.MM.yyyy')} – {self.end.date().toString('dd.MM.yyyy')}\n{self.totals_label.text()}")

    def change_year(self):
        self.start.setDate(QDate(self.year.value(), 1, 1))
        self.end.setDate(QDate(self.year.value(), 12, 31))

    def prefill(self):
        e = self.db.employee(self.person.currentData())
        if not e:
            return
        s = self.db.settings()
        birth = date.fromisoformat(e["birth_date"]).strftime("%d.%m.%Y") if e.get("birth_date") else ""
        values = {"C": e["ahv_old"], "C2": e["ahv"], "CGebDatum": birth, "HAnrede": e["salutation"], "HName": e["first_name"] + " " + e["last_name"],
                  "HAdresse": e["address"], "HPostfach": "", "HWohnort": (e["postcode"] + " " + e["city"]).strip(),
                  "OrtDatum": (s.get("city", "") + ", " if s.get("city") else "") + date.today().strftime("%d.%m.%Y"),
                  "Unterschrift1.0": s.get("company", ""), "Unterschrift1.1": s.get("address", ""),
                  "Unterschrift1.2": (s.get("postcode", "") + " " + s.get("city", "")).strip(),
                  "Unterschrift1.3": s.get("phone", ""), "Unterschrift1.4": s.get("contact", "")}
        for k, value in values.items():
            self.pdf[k].setText(value)

    def values(self):
        values = {}
        for k, widget in self.pdf.items():
            if isinstance(widget, QCheckBox): values[k] = "/Ja" if widget.isChecked() else "/Off"
            elif hasattr(widget, "value"): values[k] = str(widget.value()) if widget.value() else ""
            else: values[k] = widget.text().strip()
        values["A"] = "/Ja" if self.doc_type.currentData() == "A" else "/Off"
        values["B"] = "/Ja" if self.doc_type.currentData() == "B" else "/Off"
        return values

    def update_totals(self):
        if not hasattr(self, "totals_label"):
            return
        try:
            totals = salary_totals(self.values())
            self.totals_label.setText(f"Brutto {chf(int(totals['8'] or 0)*100)}     Abzüge {chf(int(totals['abzuege'])*100)}     Netto {chf(int(totals['11'] or 0)*100)}")
            self.totals_label.setStyleSheet("")
        except ValueError as e:
            self.totals_label.setText(str(e))
            self.totals_label.setStyleSheet("color:#bd3c40")

    @guarded
    def submit(self):
        if not self.person.currentData():
            raise ValueError("Bitte zuerst eine Person in den Stammdaten erfassen.")
        self.saved_id = self.db.save_salary(self.person.currentData(), self.year.value(), day_value(self.start),
                                           day_value(self.end), self.values(), self.row.get("id"))
        self.accept()
