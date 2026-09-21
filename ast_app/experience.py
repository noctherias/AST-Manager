"""Task-focused screens; the shared data and calculation services remain central."""
from datetime import date
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QStackedWidget,
                              QMenu, QButtonGroup, QDialog, QHeaderView)
from .widgets import Page, Table, Metric, Disclosure, label, button, combo, line, selection_bar, guarded
from .pages import Receivables, TimePage, SettingsPage, SalaryPage
from .dialogs import EmployeeDialog, PeriodDialog, EntryDialog, InvoiceDialog
from .domain import chf, number, display_date
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
            self.window.pages[4].tabs.setCurrentIndex(0)
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
        Page.__init__(self, "Rechnungen", "1. Rechnung auswählen    2. Zahlung erfassen oder Details bearbeiten")
        self.db, self.filtered = db, []
        self.header.addWidget(button("+ Neue Rechnung", self.new, True))
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
        self.table = Table(["Rechnung", "Kunde", "Fällig am", "Betrag CHF", "Offen CHF", "Status"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.table, 1)
        row, self.selection_hint = selection_bar(self.layout, "Bitte eine Rechnung auswählen.")
        self.edit_btn = button("Details bearbeiten", self.edit)
        self.pay_btn = button("Zahlung erfassen", self.pay, True)
        row.addWidget(self.edit_btn)
        row.addWidget(self.pay_btn)
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
        self.table.populate([[r["number"], r["customer"], display_date(r["due"]), number(r["amount"]), number(r["open"]), r["status"]] for r in self.filtered], [r["id"] for r in self.filtered], [3, 4])
        for c, key in zip(self.cards, ("amount", "paid", "open")): c.set(chf(sum(r[key] for r in self.filtered)))
        self.summary.setText(f"{len(self.filtered)} Rechnungen · {self.year.currentText()} · {self.quarter.currentText()}" if self.filtered else "Keine Rechnungen in dieser Auswahl. Erstelle eine Rechnung oder ändere den Filter.")
        self.selection()

    def selection(self):
        super().selection()
        r = self.selected()
        self.selection_hint.setText(f"{r['number']} · {r['customer']}" if r else "Bitte eine Rechnung auswählen.")
        self.pay_btn.setText("Zahlung erfassen" if not r or r["open"] > 0 else "Zahlungen ansehen")


class TimeWorkspace(TimePage):
    def __init__(self, db, back):
        Page.__init__(self, "Stundennachweis", "")
        self.db, self.kind = db, "employee"
        self.layout.insertWidget(0, button("← Zurück zum Team", back))
        self.person = combo([])
        self.person.setParent(self)
        self.person.hide()
        self.entry_btn = button("+ Zeit erfassen", self.new_entry, True)
        self.header.addWidget(self.entry_btn)
        more, actions = menu_button("Person & Jahre", [("Person bearbeiten", self.edit_person), ("Nächstes Jahr einrichten", self.new_period), ("Ausgewähltes Jahr bearbeiten", self.edit_period), ("CSV exportieren", self.export_csv)])
        self.person_btn, self.new_period_btn, self.edit_period_btn, self.csv_btn = actions
        self.header.addWidget(more)
        row = self.toolbar()
        row.addWidget(label("Zeitraum", "muted"))
        self.period = combo([])
        row.addWidget(self.period, 1)
        self.pdf_btn = button("Nachweis als PDF", self.export_pdf)
        row.addWidget(self.pdf_btn)
        self.setup_button = button("Erstes Jahr einrichten", self.new_period, True)
        self.layout.addWidget(self.setup_button)
        self.cards = self.metrics([("Verfügbares Guthaben", "Ferien inklusive Überzeit", True), ("Ferien bezogen", "Im gewählten Zeitraum"), ("Überzeit", "Im gewählten Zeitraum")])
        carry = Metric("Übertrag")
        carry.setParent(self)
        carry.hide()
        self.cards.append(carry)
        self.details = Disclosure("Wie setzt sich das Guthaben zusammen?")
        self.balance_hint = label("", "muted")
        self.balance_hint.setWordWrap(True)
        self.details.form.addRow(self.balance_hint)
        self.history = Table(["Jahr", "Anspruch h", "Übertrag h", "Ferien h", "Überzeit h", "Guthaben h", "Krank ges. h", "Unfall ges. h"])
        self.history.setMaximumHeight(210)
        self.details.form.addRow(self.history)
        self.layout.addWidget(self.details)
        self.table = Table(["Datum", "Kategorie", "Stunden", "Bemerkung"])
        self.layout.addWidget(self.table, 1)
        row, self.selection_hint = selection_bar(self.layout, "Wähle eine Buchung, um sie zu ändern.")
        self.edit_btn = button("Buchung bearbeiten", self.edit_entry)
        self.delete_btn = button("Entfernen", self.remove_entry)
        row.addWidget(self.edit_btn)
        row.addWidget(self.delete_btn)
        self.hint = label("", "muted")
        self.layout.addWidget(self.hint)
        self.current_balance = None
        self.person.currentIndexChanged.connect(lambda: self.refresh_periods())
        self.period.currentIndexChanged.connect(self.refresh_entries)
        self.table.itemSelectionChanged.connect(self.selection)
        self.table.cellDoubleClicked.connect(self.edit_entry)
        self.selection()

    def show_person(self, key):
        e = self.db.employee(key)
        if not e: return
        self.kind = e["kind"]
        self.title_label.setText(e["first_name"] + " " + e["last_name"])
        self.subtitle_label.setText(("Lernende" if self.kind == "apprentice" else "Mitarbeiter") + " · Ferien, Überzeit und Abwesenheiten")
        self.refresh(key)

    def refresh_entries(self):
        super().refresh_entries()
        if hasattr(self, "setup_button"):
            self.setup_button.setVisible(self.period.count() == 0)
            if not self.current_balance:
                self.hint.setText("Richte zuerst ein Jahr ein. Danach kannst du Ferien, Stunden und Abwesenheiten erfassen.")
            elif not self.current_entries:
                self.hint.setText("Noch keine Einträge. Mit «Zeit erfassen» die erste Buchung hinzufügen.")

    def edit_person(self):
        key = self.person.currentData()
        e = self.db.employee(key)
        if e and EmployeeDialog(self, self.db, e).exec(): self.show_person(key)


class Team(QWidget):
    def __init__(self, db):
        super().__init__()
        self.db = db
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack)
        self.overview = Page("Unser Team", "1. Person auswählen    2. Zeit erfassen oder den Stundennachweis öffnen")
        self.overview.header.addWidget(button("+ Neue Person", self.new_person, True))
        row = self.overview.toolbar()
        self.kind = None
        self.group = segments(row, [("Alle", None), ("Mitarbeiter", "employee"), ("Lernende", "apprentice")], self.set_kind)
        row.addStretch()
        self.search = line(placeholder="Person suchen …")
        row.addWidget(self.search, 1)
        self.table = Table(["Name", "Bereich", "Jahr / Lehrjahr", "Guthaben", "Status"])
        self.overview.layout.addWidget(self.table, 1)
        row, self.hint = selection_bar(self.overview.layout, "Wähle eine Person aus der Liste.")
        self.open_btn = button("Nachweis öffnen", self.open_person)
        self.time_btn = button("Zeit erfassen", self.quick_entry, True)
        row.addWidget(self.open_btn)
        row.addWidget(self.time_btn)
        self.stack.addWidget(self.overview)
        self.workspace = TimeWorkspace(db, self.show_overview)
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
            self.workspace.show_person(self.workspace.person.currentData())

    def refresh_overview(self):
        q = self.search.text().casefold()
        people = [e for e in self.db.employees(self.kind) if q in (e["first_name"] + " " + e["last_name"] + " " + e["code"]).casefold()]
        rows = []
        for e in people:
            balances = self.db.balances(e["id"])
            current = next((b for b in balances if b["start"] <= date.today().isoformat() <= b["end"]), balances[-1] if balances else None)
            rows.append([e["first_name"] + " " + e["last_name"], "Lernende" if e["kind"] == "apprentice" else "Mitarbeiter", current["label"] if current else "Noch nicht eingerichtet", number(current["balance"], " h") if current else "–", "Aktiv" if e["active"] else "Inaktiv"])
        self.table.populate(rows, [e["id"] for e in people], [3])
        self.selection()
        if not rows: self.hint.setText("Noch keine Person gefunden. Mit «Neue Person» starten oder die Suche ändern.")

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
        if not self.workspace.current_balance: self.workspace.new_period()
        self.workspace.new_entry()

    def new_person(self):
        d = EmployeeDialog(self, self.db, kind=self.kind or "employee")
        if d.exec():
            self.workspace.show_person(d.saved_id)
            self.stack.setCurrentIndex(1)
            self.workspace.new_period()


class Settings(SettingsPage):
    def __init__(self, db, controller):
        super().__init__(db)
        self.title_label.setText("Einstellungen")
        self.subtitle_label.setText("Firma, Kunden, Datensicherung und Programm-Updates.")
        self.tabs.removeTab(0)  # People live exclusively under Team.
        company = self.tabs.widget(1)
        self.tabs.removeTab(1)
        self.tabs.insertTab(0, company, "Meine Firma")
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
