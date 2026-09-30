"""Task-focused screens; the shared data and calculation services remain central."""
from datetime import date
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QStackedWidget,
                              QMenu, QButtonGroup, QDialog, QHeaderView, QMessageBox, QFileDialog)
from .widgets import Page, Table, Metric, Disclosure, label, button, combo, line, selection_bar, guarded, confirm
from .pages import Receivables, SettingsPage, SalaryPage, save_path
from .dialogs import EmployeeDialog, InvoiceDialog, TimeRecordDialog, BulkTimeDialog
from .domain import TIME_CODES, chf, number, display_date
from .timesheet_excel import export_timesheet
from .excel_import import import_timesheet
from .update_ui import UpdateSettings


def menu_button(title, entries):
    control = button(title)
    menu = QMenu(control)
    actions = []
    for text, callback in entries:
        action = menu.addAction(text)
        action.triggered.connect(lambda checked=False, callback=callback: callback())
        actions.append(action)
    control.setMenu(menu)
    return control, actions


def segments(row, choices, callback):
    group = QButtonGroup(row.parentWidget())
    group.setExclusive(True)
    for i, (title, value) in enumerate(choices):
        b = button(title, lambda value=value: callback(value))
        b.setObjectName("segment")
        b.setCheckable(True)
        b.setChecked(i == 0)
        group.addButton(b)
        row.addWidget(b)
    return group


class Start(Page):
    def __init__(self, db, window):
        super().__init__("Was möchtest du erledigen?", "Dein Arbeitsbereich für Rechnungen, Zeiten und Lohnausweise.")
        self.db, self.window = db, window
        row = QHBoxLayout()
        row.setSpacing(16)
        for title, text, action, callback in [
            ("Rechnung", "Eine Rechnung erfassen oder\neine Zahlung verbuchen.", "Neue Rechnung", self.new_invoice),
            ("Ferien & Stunden", "Ferien, Überzeit oder eine\nAbwesenheit erfassen.", "Zeit erfassen", self.quick_time),
            ("Lohnausweis", "Schritt für Schritt ausfüllen\nund als PDF speichern.", "Ausweis erstellen", self.new_salary)]:
            card = QFrame()
            card.setObjectName("card")
            col = QVBoxLayout(card)
            col.setContentsMargins(22, 22, 22, 22)
            col.setSpacing(14)
            col.addWidget(label(title, "sectionTitle"))
            col.addWidget(label(text, "muted"))
            col.addWidget(button(action + "  →", callback, True))
            row.addWidget(card, 1)
        self.layout.addLayout(row)
        self.setup = QFrame()
        self.setup.setObjectName("accentCard")
        setup_row = QHBoxLayout(self.setup)
        setup_row.setContentsMargins(20, 14, 20, 14)
        self.setup_text = label("", "muted")
        self.setup_text.setWordWrap(True)
        setup_row.addWidget(self.setup_text, 1)
        self.setup_action = button("", self.setup_next)
        setup_row.addWidget(self.setup_action)
        self.layout.addWidget(self.setup)
        self.cards = self.metrics([("Noch zu erhalten", "Offene Rechnungen", True),
                                   ("Davon überfällig", "Fälligkeit überschritten"),
                                   ("Unser Team", "Aktive Mitarbeiter und Lernende")])
        heading = self.toolbar()
        heading.addWidget(label("Als Nächstes im Blick", "sectionTitle"))
        heading.addStretch()
        heading.addWidget(button("Alle Rechnungen  →", lambda: window.navigate(1)))
        self.table = Table(["Rechnung", "Kunde", "Fällig am", "Noch offen", "Status"])
        self.layout.addWidget(self.table, 1)
        row, self.hint = selection_bar(self.layout, "Wähle eine Rechnung, um eine Zahlung zu erfassen.")
        self.payment = button("Zahlung erfassen", self.pay, True)
        row.addWidget(self.payment)
        self.table.itemSelectionChanged.connect(lambda: self.payment.setEnabled(self.table.selected_id() is not None))
        self.table.cellDoubleClicked.connect(self.pay)

    def refresh(self):
        outstanding = [r for r in self.db.invoices() if r["open"] > 0]
        self.cards[0].set(chf(sum(r["open"] for r in outstanding)))
        self.cards[1].set(chf(sum(r["open"] for r in outstanding if r["status"] == "Überfällig")))
        self.cards[2].set(sum(e["active"] for e in self.db.employees()))
        rows = sorted(outstanding, key=lambda r: r["due"])[:6]
        self.table.populate([[r["number"], r["customer"], display_date(r["due"]), chf(r["open"]), r["status"]] for r in rows], [r["id"] for r in rows], [3])
        self.payment.setEnabled(False)
        self.hint.setText("Wähle eine Rechnung, um eine Zahlung zu erfassen." if rows else "Alles erledigt: Es sind keine offenen Rechnungen vorhanden.")
        self.setup_step = 0 if not self.db.settings().get("company") else 1 if not self.db.employees() else 2
        self.setup.setVisible(self.setup_step < 2)
        self.setup_text.setText("Einmal einrichten: Deine Firmendaten werden für Lohnausweise übernommen." if self.setup_step == 0 else "Lege dein Team an. Jede Person wird nur einmal erfasst.")
        self.setup_action.setText("Firma einrichten  →" if self.setup_step == 0 else "Erste Person erfassen  →")

    def setup_next(self):
        if self.setup_step == 0:
            self.window.navigate(4)
            self.window.pages[4].tabs.setCurrentIndex(2)
        else:
            self.window.navigate(2)
            self.window.pages[2].new_person()

    def new_invoice(self):
        if InvoiceDialog(self, self.db).exec(): self.refresh()

    def new_salary(self):
        self.window.navigate(3)
        self.window.pages[3].new()

    def quick_time(self):
        self.window.navigate(2)
        team = self.window.pages[2]
        if not self.db.employees():
            team.new_person()
        else:
            team.show_overview()
            team.hint.setText("Wähle die Person aus und klicke auf «Zeit erfassen».")

    def pay(self):
        from .dialogs import PaymentDialog
        r = next((r for r in self.db.invoices() if r["id"] == self.table.selected_id()), None)
        if r:
            PaymentDialog(self, self.db, r).exec()
            self.refresh()


class Invoices(Receivables):
    def __init__(self, db):
        Page.__init__(self, "Debitoren", "Rechnungen und Zahlungseingänge zentral bearbeiten.")
        self.db, self.filtered = db, []
        self.header.addWidget(button("+ Neue Rechnung", self.new, True))
        self.header.addWidget(button("Excel importieren", self.import_excel))
        self.cards = self.metrics([("Rechnungsbetrag", "In der Auswahl"), ("Bereits bezahlt", "In der Auswahl"), ("Noch offen", "In der Auswahl", True)])
        row = self.toolbar()
        self.status = combo([(v, v) for v in ("Alle offenen", "Bezahlt", "Alle Status")])
        self.status.hide()
        self.status.setParent(self)
        self.segment_group = segments(row, [("Offen", "Alle offenen"), ("Bezahlt", "Bezahlt"), ("Alle", "Alle Status")], self.set_status)
        row.addStretch()
        self.search = line(placeholder="Rechnung oder Kunde suchen …")
        row.addWidget(self.search, 1)
        filters = Disclosure("Zeitraum eingrenzen")
        self.year = combo([("Alle Jahre", None)])
        self.quarter = combo([("Alle Quartale", None)] + [(f"Quartal {q}", q) for q in range(1, 5)])
        filters.form.addRow("Rechnungsjahr", self.year)
        filters.form.addRow("Quartal", self.quarter)
        self.layout.addWidget(filters)
        self.table = Table(["Rechnung", "Kunde", "Fällig am", "Betrag CHF", "Offen CHF", "Mahnstufe", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.table, 1)
        row, self.selection_hint = selection_bar(self.layout, "Bitte eine Rechnung auswählen.")
        self.edit_btn = button("Details bearbeiten", self.edit)
        self.pay_btn = button("Zahlung erfassen", self.pay, True)
        self.reminder_btn = button("Mahnstufe", self.reminder)
        row.addWidget(self.edit_btn)
        row.addWidget(self.pay_btn)
        row.addWidget(self.reminder_btn)
        more, actions = menu_button("Weitere Aktionen", [("Auswahl als PDF / Drucken", self.export_pdf), ("Auswahl als CSV exportieren", self.export_csv), ("Rechnung löschen …", self.remove)])
        self.delete_btn = actions[-1]
        self.header.addWidget(more)
        self.summary = label("", "muted")
        self.layout.addWidget(self.summary)
        self.search.textChanged.connect(self.filter_rows)
        for w in (self.status, self.year, self.quarter): w.currentIndexChanged.connect(self.filter_rows)
        self.table.itemSelectionChanged.connect(self.selection)
        self.table.cellDoubleClicked.connect(self.pay)
        self.selection()

    def set_status(self, value):
        self.status.setCurrentIndex(self.status.findData(value))

    def filter_rows(self):
        if not hasattr(self, "summary"): return
        q, status = self.search.text().casefold(), self.status.currentData()
        year, quarter = self.year.currentData(), self.quarter.currentData()
        self.filtered = [r for r in self.db.invoices()
            if (not q or q in (r["number"] + " " + r["customer"] + " " + r["note"]).casefold())
            and (not year or int(r["issued"][:4]) == year)
            and (not quarter or (int(r["issued"][5:7]) - 1) // 3 + 1 == quarter)
            and (status == "Alle Status" or status == "Alle offenen" and r["open"] > 0 or r["status"] == status)]
        self.table.populate([[r["number"], r["customer"], display_date(r["due"]), number(r["amount"]), number(r["open"]), self.reminder_text(r), r["status"]] for r in self.filtered], [r["id"] for r in self.filtered], [3, 4])
        for c, key in zip(self.cards, ("amount", "paid", "open")): c.set(chf(sum(r[key] for r in self.filtered)))
        self.summary.setText(f"{len(self.filtered)} Rechnungen · {self.year.currentText()} · {self.quarter.currentText()}" if self.filtered else "Keine Rechnungen in dieser Auswahl. Erstelle eine Rechnung oder ändere den Filter.")
        self.selection()

    def selection(self):
        super().selection()
        r = self.selected()
        self.selection_hint.setText(f"{r['number']} · {r['customer']}" if r else "Bitte eine Rechnung auswählen.")
        self.pay_btn.setText("Zahlung erfassen" if not r or r["open"] > 0 else "Zahlungen ansehen")


class TimeWorkspace(Page):
    def __init__(self, db, back, manage_team):
        super().__init__("Stundennachweis", "Arbeitszeiten und Abwesenheiten einfach erfassen und in die Excel-Vorlage exportieren.")
        self.db, self.employee, self.current_records = db, None, []
        self.layout.insertWidget(0, button("← Personenübersicht", back))
        self.entry_btn = button("+ Arbeitstag erfassen", self.new_entry, True)
        self.header.addWidget(self.entry_btn)
        self.header.addWidget(button("Zeitraum erfassen", self.bulk_entry))
        self.header.addWidget(button("Person bearbeiten", manage_team))
        row = self.toolbar()
        row.addWidget(label("Kalenderjahr", "muted"))
        current = date.today().year
        self.year = combo([(str(y), y) for y in range(current + 2, current - 7, -1)], current)
        row.addWidget(self.year)
        row.addStretch()
        self.export_btn = button("Excel-Liste exportieren", self.export_excel, True)
        row.addWidget(button("Excel importieren", self.import_excel))
        row.addWidget(self.export_btn)
        self.cards = self.metrics([("Arbeitszeit", "Summe der erfassten Zeiten", True),
                                   ("Arbeitstage", "Tage mit Kommt-/Geht-Zeit"),
                                   ("Abwesenheiten", "Tage mit einem Code")])
        self.table = Table(["Datum", "Wochentag", "Arbeitsblock 1", "Arbeitsblock 2", "Pause", "Art", "Total", "Bemerkung"])
        self.layout.addWidget(self.table, 1)
        row, self.selection_hint = selection_bar(self.layout, "Wähle einen Tag aus oder erfasse einen neuen.")
        self.edit_btn = button("Tag bearbeiten", self.edit_entry)
        self.delete_btn = button("Tag löschen", self.remove_entry)
        row.addWidget(self.edit_btn)
        row.addWidget(self.delete_btn)
        self.hint = label("Die Excel-Datei enthält weiterhin alle Formeln, Monatsblätter, Auswertungen und Makros der Originalvorlage.", "muted")
        self.hint.setWordWrap(True)
        self.layout.addWidget(self.hint)
        self.year.currentIndexChanged.connect(self.refresh)
        self.table.itemSelectionChanged.connect(self.selection)
        self.table.cellDoubleClicked.connect(self.edit_entry)
        self.selection()

    @staticmethod
    def _clock(minutes):
        return "–" if minutes is None else f"{minutes // 60:02d}:{minutes % 60:02d}"

    @staticmethod
    def _worked(record):
        total = 0
        for start, end in ((record["start_1"], record["end_1"]), (record["start_2"], record["end_2"])):
            if start is not None and end is not None:
                total += (end - start) % 1440
        return max(0, total - record["break_minutes"])

    @staticmethod
    def _duration(minutes):
        return f"{minutes // 60}:{minutes % 60:02d} h" if minutes else "–"

    def show_person(self, key):
        self.employee = self.db.employee(key)
        if not self.employee:
            return
        self.title_label.setText(self.employee["first_name"] + " " + self.employee["last_name"])
        self.subtitle_label.setText("Stundennachweis · Personal-Nr. " + self.employee["code"])
        years = {int(r["day"][:4]) for r in self.db.time_records(key)} | {date.today().year}
        selected = self.year.currentData()
        self.year.blockSignals(True)
        self.year.clear()
        for year in sorted(years | set(range(date.today().year - 2, date.today().year + 2)), reverse=True):
            self.year.addItem(str(year), year)
        self.year.setCurrentIndex(max(0, self.year.findData(selected)))
        self.year.blockSignals(False)
        self.refresh()

    def refresh(self):
        if not self.employee:
            return
        year = self.year.currentData()
        self.current_records = self.db.time_records(self.employee["id"], year)
        rows = []
        total = 0
        workdays = 0
        absences = 0
        weekdays = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag")
        for record in self.current_records:
            day_value = date.fromisoformat(record["day"])
            worked = self._worked(record)
            total += worked
            workdays += int(record["start_1"] is not None)
            absences += int(bool(record["code"]))
            block1 = f"{self._clock(record['start_1'])} – {self._clock(record['end_1'])}" if record["start_1"] is not None else "–"
            block2 = f"{self._clock(record['start_2'])} – {self._clock(record['end_2'])}" if record["start_2"] is not None else "–"
            rows.append([display_date(record["day"]), weekdays[day_value.weekday()], block1, block2,
                         f"{record['break_minutes']} min" if record["break_minutes"] else "–",
                         TIME_CODES.get(record["code"], record["code"]), self._duration(worked), record["note"]])
        self.table.populate(rows, [record["id"] for record in self.current_records], [6])
        self.cards[0].set(self._duration(total))
        self.cards[1].set(str(workdays))
        self.cards[2].set(str(absences))
        self.export_btn.setEnabled(bool(self.employee))
        self.selection()

    def selection(self):
        enabled = self.table.selected_id() is not None
        self.edit_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        self.selection_hint.setText("Ausgewählten Tag bearbeiten oder löschen." if enabled else "Wähle einen Tag aus oder erfasse einen neuen.")

    def new_entry(self):
        if self.employee and TimeRecordDialog(self, self.db, self.employee).exec():
            self.refresh()

    def bulk_entry(self):
        if not self.employee:
            return
        dialog = BulkTimeDialog(self, self.db, self.employee, self.year.currentData())
        if dialog.exec():
            self.refresh()
            result = dialog.result_counts
            QMessageBox.information(self, "Zeitraum erfasst",
                                    f"{result['created']} Tage neu erfasst, {result['updated']} überschrieben, "
                                    f"{result['skipped']} bestehende Tage ausgelassen.")

    def edit_entry(self):
        record = next((r for r in self.current_records if r["id"] == self.table.selected_id()), None)
        if record and TimeRecordDialog(self, self.db, self.employee, record).exec():
            self.refresh()

    @guarded
    def remove_entry(self):
        key = self.table.selected_id()
        if key and confirm(self, "Diesen erfassten Tag löschen?"):
            self.db.delete("time_records", key)
            self.refresh()

    @guarded
    def export_excel(self):
        if not self.employee:
            return
        year = self.year.currentData()
        path = save_path(self, "Stundennachweis als Excel-Datei", f"Stundennachweis-{self.employee['last_name']}-{year}.xlsm", "xlsm")
        if path:
            result = export_timesheet(path, self.employee, year, self.current_records, self.db.settings().get("company", ""))
            QMessageBox.information(self, "Excel-Liste erstellt", "Die Originalvorlage wurde vollständig befüllt.\n\n" + str(result))

    @guarded
    def import_excel(self):
        if not self.employee:
            return
        path, _ = QFileDialog.getOpenFileName(self, "Zeiterfassung aus Excel importieren", "",
                                              "Excel-Zeiterfassung (*.xlsm *.xlsx)")
        if not path:
            return
        answer = QMessageBox.question(
            self, "Bestehende Tage",
            "Sollen bereits erfasste Tage mit den Werten aus Excel überschrieben werden?\n\n"
            "Ja = überschreiben · Nein = bestehende Tage behalten",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return
        result = import_timesheet(self.db, path, self.employee["id"], answer == QMessageBox.StandardButton.Yes)
        self.show_person(self.employee["id"])
        index = self.year.findData(result["year"])
        if index >= 0:
            self.year.setCurrentIndex(index)
        QMessageBox.information(self, "Excel-Import abgeschlossen",
                                f"{result['created']} Tage neu importiert, {result['updated']} überschrieben, "
                                f"{result['skipped']} bestehende Tage ausgelassen.")


class Team(QWidget):
    def __init__(self, db, window):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.window = window
        self.overview = Page("Stundennachweis", "Person auswählen, Arbeitstage erfassen und die vollständige Excel-Liste exportieren.")
        self.overview.header.addWidget(button("Team in Einstellungen verwalten", self.manage_team))
        row = self.overview.toolbar()
        self.kind = None
        self.group = segments(row, [("Alle", None), ("Mitarbeiter", "employee"), ("Lernende", "apprentice")], self.set_kind)
        row.addStretch()
        self.search = line(placeholder="Person suchen …")
        row.addWidget(self.search, 1)
        self.table = Table(["Personal-Nr.", "Name", "Bereich", "Einträge dieses Jahr", "Letzter Eintrag", "Status"])
        self.overview.layout.addWidget(self.table, 1)
        row, self.hint = selection_bar(self.overview.layout, "Wähle eine Person aus der Liste.")
        self.open_btn = button("Stundennachweis öffnen", self.open_person)
        self.time_btn = button("Arbeitstag erfassen", self.quick_entry, True)
        row.addWidget(self.open_btn)
        row.addWidget(self.time_btn)
        self.stack.addWidget(self.overview)
        self.workspace = TimeWorkspace(db, self.show_overview, self.manage_selected)
        self.stack.addWidget(self.workspace)
        self.table.itemSelectionChanged.connect(self.selection)
        self.table.cellDoubleClicked.connect(self.open_person)
        self.search.textChanged.connect(self.refresh_overview)
        self.selection()

    def set_kind(self, value):
        self.kind = value
        self.refresh_overview()

    def refresh(self):
        self.refresh_overview()
        if self.stack.currentIndex() == 1:
            if self.workspace.employee:
                self.workspace.show_person(self.workspace.employee["id"])

    def refresh_overview(self):
        q = self.search.text().casefold()
        people = [e for e in self.db.employees(self.kind) if q in (e["first_name"] + " " + e["last_name"] + " " + e["code"]).casefold()]
        rows = []
        for e in people:
            records = self.db.time_records(e["id"], date.today().year)
            rows.append([e["code"], e["first_name"] + " " + e["last_name"], "Lernende" if e["kind"] == "apprentice" else "Mitarbeiter",
                         len(records), display_date(records[0]["day"]) if records else "–", "Aktiv" if e["active"] else "Inaktiv"])
        self.table.populate(rows, [e["id"] for e in people], [3])
        self.selection()
        if not rows: self.hint.setText("Keine Person gefunden. Das Team wird unter Einstellungen verwaltet.")

    def selection(self):
        e = self.db.employee(self.table.selected_id())
        self.open_btn.setEnabled(bool(e))
        self.time_btn.setEnabled(bool(e))
        self.hint.setText(e["first_name"] + " " + e["last_name"] if e else "Wähle eine Person aus der Liste.")

    def show_overview(self):
        self.stack.setCurrentIndex(0)
        self.refresh_overview()

    def open_person(self):
        key = self.table.selected_id()
        if key:
            self.workspace.show_person(key)
            self.stack.setCurrentIndex(1)

    def quick_entry(self):
        self.open_person()
        self.workspace.new_entry()

    def new_person(self):
        self.window.navigate_settings_team(True)

    def manage_team(self):
        self.window.navigate_settings_team()

    def manage_selected(self):
        self.window.navigate_settings_team(employee_id=self.workspace.employee["id"] if self.workspace.employee else None)


class Settings(SettingsPage):
    def __init__(self, db, controller):
        super().__init__(db)
        self.title_label.setText("Einstellungen")
        self.subtitle_label.setText("Team, Firma, Kunden, Datensicherung und Programm-Updates zentral verwalten.")
        self.tabs.setTabText(0, "Team")
        company = self.tabs.widget(2)
        self.tabs.setTabText(2, "Meine Firma")
        self.tabs.setCurrentIndex(0)
        self.update_settings = UpdateSettings(db, controller)
        self.tabs.addTab(self.update_settings, "Updates")
        self.company_status = label("Firmendaten werden beim Verlassen eines Feldes gespeichert.", "muted")
        company.layout().insertWidget(0, self.company_status)
        self.refresh()
        for w in self.company_fields.values(): w.editingFinished.connect(self.persist_company)

    @guarded
    def persist_company(self):
        values = {k: w.text().strip() for k, w in self.company_fields.items()}
        if any(self.db.settings().get(k, "") != v for k, v in values.items()):
            self.db.save_settings(values)
            self.company_status.setText("Firmendaten gespeichert.")

    def refresh(self):
        super().refresh()
        self.update_settings.refresh()

    def open_team(self, employee_id=None, create=False):
        self.tabs.setCurrentIndex(0)
        self.refresh()
        if create:
            self.new_person()
            return
        if employee_id:
            for row in range(self.people.rowCount()):
                if self.people.item(row, 0).data(Qt.ItemDataRole.UserRole) == employee_id:
                    self.people.selectRow(row)
                    break
            person = self.db.employee(employee_id)
            if person and EmployeeDialog(self, self.db, person).exec():
                self.refresh()


class Salaries(SalaryPage):
    def __init__(self, db):
        super().__init__(db)
        self.subtitle_label.setText("In vier Schritten zum Ausweis. Gespeicherte Ausweise kannst du jederzeit bearbeiten und als PDF ausgeben.")
        self.preview_btn.setText("PDF ansehen")
        self.export_btn.setText("PDF speichern")

    def new(self):
        if not self.db.employees():
            dialog = EmployeeDialog(self, self.db)
            if not dialog.exec(): return
        super().new()
