from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import shutil
import tempfile

from PySide6.QtCore import Qt, QRectF, QBuffer, QIODevice, QObject, Signal, QThread
from PySide6.QtGui import QColor, QPainter, QFont, QDesktopServices, QPixmap
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QFrame, QTabWidget, QFormLayout,
    QDialog, QFileDialog, QMessageBox, QHeaderView, QScrollArea, QLineEdit, QCheckBox)
from PySide6.QtPdf import QPdfDocument
from PySide6.QtPdfWidgets import QPdfView

from .domain import KINDS, number, chf, display_date
from .widgets import Page, Table, label, button, combo, line, guarded, confirm
from .dialogs import CustomerDialog, EmployeeDialog, InvoiceDialog, PaymentDialog, ReminderDialog, PeriodDialog, EntryDialog, SalaryDialog
from .documents import salary_pdf, csv_export, report_pdf, time_report
from .backups import run_automatic_backups
from .excel_import import import_debtors
from .export_paths import (EXPORT_DESTINATIONS, choose_export_file, default_directory,
                           configured_directory, employee_year_folders, setting_key)
from .excel_trust import ensure_excel_trusted_folder, unblock_excel_file
from .secrets import protect_secret, unprotect_secret
from .web_sync import WebSyncClient, automatic_sync, pull_web, push_desktop


class _AutomaticWebSyncWorker(QObject):
    completed = Signal(str)
    failed = Signal(str)
    finished = Signal()

    def __init__(self, database_path, url, email, password):
        super().__init__()
        self.database_path = database_path
        self.url = url
        self.email = email
        self.password = password

    def run(self):
        from .database import Database
        database = None
        try:
            database = Database(self.database_path)
            message = automatic_sync(database, WebSyncClient(self.url, self.email, self.password, timeout=20))
            self.completed.emit(message)
        except Exception as exc:
            self.failed.emit(str(exc))
        finally:
            if database is not None:
                database.close()
            self.finished.emit()


def save_path(parent, title, name, extension="pdf", export_key="debtors_pdf", subfolders=()):
    return choose_export_file(parent, title, name, extension, export_key, subfolders)


class PdfPreview(QDialog):
    def __init__(self, parent, path):
        super().__init__(parent)
        self.setWindowTitle("PDF-Vorschau")
        self.resize(920, 900)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(label(Path(path).name, "sectionTitle"))
        row.addStretch()
        row.addWidget(button("Im PDF-Programm öffnen", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve())))))
        row.addWidget(button("Schliessen", self.accept))
        layout.addLayout(row)
        self.document = QPdfDocument(self)
        # Keep the preview in memory so Windows does not lock the exported file.
        self.buffer = QBuffer(self)
        self.buffer.setData(Path(path).read_bytes())
        self.buffer.open(QIODevice.OpenModeFlag.ReadOnly)
        self.document.load(self.buffer)
        self.view = QPdfView(self)
        self.view.setDocument(self.document)
        self.view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        self.view.setPageMode(QPdfView.PageMode.MultiPage)
        layout.addWidget(self.view)


class PaymentChart(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName("card")
        self.setMinimumHeight(200)
        self.amounts = [0] * 12

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QColor("#244553"))
        painter.setFont(QFont("Segoe UI", 11, QFont.Weight.DemiBold))
        painter.drawText(22, 30, f"Zahlungseingänge {date.today().year}")
        painter.setFont(QFont("Segoe UI", 8))
        painter.setPen(QColor("#70838f"))
        painter.drawText(22, 50, "CHF je Valutamonat")
        left, top, height = 22, 77, self.height() - 112
        step = (self.width() - 44) / 12
        maximum = max(max(self.amounts), 1)
        painter.setPen(Qt.PenStyle.NoPen)
        for idx, amount in enumerate(self.amounts):
            x = left + idx * step
            painter.setBrush(QColor("#eaf0f3"))
            painter.drawRoundedRect(QRectF(x + 5, top, step - 10, height), 4, 4)
            filled = max(3, height * amount / maximum) if amount else 0
            painter.setBrush(QColor("#0b8b70"))
            if filled:
                painter.drawRoundedRect(QRectF(x + 5, top + height - filled, step - 10, filled), 4, 4)
            painter.setPen(QColor("#667e8c"))
            painter.drawText(QRectF(x, self.height() - 27, step, 16), Qt.AlignmentFlag.AlignCenter,
                             ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"][idx])
            painter.setPen(Qt.PenStyle.NoPen)
        painter.end()


class Dashboard(Page):
    def __init__(self, db, navigate):
        super().__init__("Alles im Blick", "Finanzen, Team und Zeitguthaben an einem Ort.")
        self.db, self.navigate = db, navigate
        self.header.addWidget(button("+ Neue Rechnung", self.new_invoice, True))
        self.cards = self.metrics([("Offene Debitoren", "Alle offenen Rechnungsbeträge", True),
                                   ("Davon überfällig", "Fälligkeit überschritten"),
                                   (f"Bezahlt {date.today().year}", "Nach Valutadatum"),
                                   ("Aktive Personen", "Mitarbeiter und Lernende")])
        middle = QHBoxLayout()
        middle.setSpacing(18)
        self.chart = PaymentChart()
        middle.addWidget(self.chart, 3)
        actions = QFrame()
        actions.setObjectName("card")
        al = QVBoxLayout(actions)
        al.setContentsMargins(22, 18, 22, 18)
        al.addWidget(label("Direkt erledigen", "sectionTitle"))
        al.addWidget(button("Stunden erfassen  →", lambda: navigate(2)))
        al.addWidget(button("Lohnausweis erstellen  →", lambda: navigate(4)))
        al.addWidget(button("Stammdaten verwalten  →", lambda: navigate(5)))
        middle.addWidget(actions, 2)
        self.layout.addLayout(middle)
        title_row = QHBoxLayout()
        title_row.addWidget(label("Offene Rechnungen", "sectionTitle"))
        title_row.addStretch()
        title_row.addWidget(button("Alle Debitoren  →", lambda: navigate(1)))
        self.layout.addLayout(title_row)
        self.table = Table(["Rechnung", "Kunde", "Fällig am", "Offen", "Status"])
        self.table.cellDoubleClicked.connect(self.open_invoice)
        self.layout.addWidget(self.table, 1)
        self.empty = label("", "muted")
        self.layout.addWidget(self.empty)

    def refresh(self):
        invoices = self.db.invoices()
        outstanding = [r for r in invoices if r["open"] > 0]
        overdue = [r for r in outstanding if r["status"] == "Überfällig"]
        payments = self.db.rows("SELECT substr(day,6,2) AS month,SUM(amount) AS total FROM payments WHERE substr(day,1,4)=? GROUP BY month", (str(date.today().year),))
        self.cards[0].set(chf(sum(r["open"] for r in outstanding)))
        self.cards[1].set(chf(sum(r["open"] for r in overdue)))
        self.cards[2].set(chf(sum(r["total"] for r in payments)))
        people = self.db.employees()
        self.cards[3].set(str(sum(e["active"] for e in people)))
        self.cards[3].hint.setText(f"{sum(e['active'] for e in people if e['kind']=='apprentice')} Lernende")
        self.chart.amounts = [0] * 12
        for r in payments:
            self.chart.amounts[int(r["month"]) - 1] = r["total"]
        self.chart.update()
        selected = sorted(outstanding, key=lambda r: r["due"])[:8]
        self.table.populate([[r["number"], r["customer"], display_date(r["due"]), chf(r["open"]), r["status"]] for r in selected], [r["id"] for r in selected], [3])
        self.empty.setText(f"{len(outstanding)} offene Rechnungen · Stand {date.today().strftime('%d.%m.%Y')}" if invoices else "Willkommen. Lege zuerst Personen und Kunden an oder erfasse direkt deine erste Rechnung.")

    def new_invoice(self):
        if InvoiceDialog(self, self.db).exec():
            self.refresh()

    def open_invoice(self):
        key = self.table.selected_id()
        r = next((r for r in self.db.invoices() if r["id"] == key), None)
        if r:
            PaymentDialog(self, self.db, r).exec()
            self.refresh()


class Receivables(Page):
    def __init__(self, db):
        super().__init__("Debitoren", "Rechnungen, Teilzahlungen und offene Beträge.")
        self.db = db
        self.header.addWidget(button("+ Neue Rechnung", self.new, True))
        self.header.addWidget(button("Excel importieren", self.import_excel))
        self.cards = self.metrics([("Rechnungsbetrag", "Aktuelle Auswahl"), ("Bezahlt", "Summe der Zahlungen"), ("Offen", "Rechnung minus bezahlt", True)])
        row = self.toolbar()
        self.search = line(placeholder="Rechnung oder Kunde suchen …")
        row.addWidget(self.search, 2)
        self.status = combo([(v, v) for v in ["Alle Status", "Alle offenen", "Offen", "Teilbezahlt", "Überfällig", "Bezahlt"]])
        row.addWidget(self.status)
        self.year = combo([("Alle Jahre", None)])
        row.addWidget(self.year)
        self.quarter = combo([("Alle Quartale", None)] + [(f"Quartal {q}", q) for q in range(1, 5)])
        row.addWidget(self.quarter)
        for w in (self.status, self.year, self.quarter):
            w.currentIndexChanged.connect(self.filter_rows)
        self.search.textChanged.connect(self.filter_rows)
        self.table = Table(["Rechnung", "Kunde", "Datum", "Fällig", "Valuta", "Betrag CHF", "Bezahlt CHF", "Offen CHF", "Mahnstufe", "Status"])
        self.table.horizontalHeader().setMinimumSectionSize(65)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(self.edit)
        self.table.itemSelectionChanged.connect(self.selection)
        self.layout.addWidget(self.table, 1)
        row = self.toolbar()
        self.edit_btn = button("Bearbeiten", self.edit)
        self.pay_btn = button("Zahlungen", self.pay, True)
        self.reminder_btn = button("Mahnstufe", self.reminder)
        self.delete_btn = button("Löschen", self.remove)
        for b in (self.edit_btn, self.pay_btn, self.reminder_btn, self.delete_btn): row.addWidget(b)
        row.addStretch()
        row.addWidget(button("CSV exportieren", self.export_csv))
        row.addWidget(button("PDF / Drucken", self.export_pdf))
        self.summary = label("", "muted")
        self.layout.addWidget(self.summary)
        self.filtered = []
        self.selection()

    def refresh(self):
        old = self.year.currentData()
        self.year.blockSignals(True)
        self.year.clear()
        self.year.addItem("Alle Jahre", None)
        for year in sorted({int(r["issued"][:4]) for r in self.db.invoices()}, reverse=True): self.year.addItem(str(year), year)
        self.year.setCurrentIndex(max(0, self.year.findData(old)))
        self.year.blockSignals(False)
        self.filter_rows()

    def filter_rows(self):
        if not hasattr(self, "summary"):
            return
        q, status, year, quarter = self.search.text().casefold(), self.status.currentData(), self.year.currentData(), self.quarter.currentData()
        rows = []
        for r in self.db.invoices():
            if q and q not in (r["number"] + " " + r["customer"] + " " + r["note"]).casefold(): continue
            if year and int(r["issued"][:4]) != year: continue
            if quarter and (int(r["issued"][5:7]) - 1) // 3 + 1 != quarter: continue
            if status == "Alle offenen" and r["open"] <= 0: continue
            if status not in ("Alle Status", "Alle offenen") and r["status"] != status: continue
            rows.append(r)
        self.filtered = rows
        self.table.populate([[r["number"], r["customer"], display_date(r["issued"]), display_date(r["due"]), display_date(r["valuta"]), number(r["amount"]), number(r["paid"]), number(r["open"]), self.reminder_text(r), r["status"]] for r in rows], [r["id"] for r in rows], [5, 6, 7])
        for card, key in zip(self.cards, ("amount", "paid", "open")):
            card.set(chf(sum(r[key] for r in rows)))
        self.summary.setText(f"{len(rows)} Rechnungen · Zeitraumfilter nach Rechnungsdatum · Valuta = letzte Zahlung" if rows else "Keine Rechnungen für diese Auswahl. Mit «Neue Rechnung» starten.")
        self.selection()

    def selection(self):
        enabled = self.table.selected_id() is not None
        for b in (self.edit_btn, self.pay_btn, self.reminder_btn, self.delete_btn): b.setEnabled(enabled)

    def selected(self):
        return next((r for r in self.filtered if r["id"] == self.table.selected_id()), None)

    def new(self):
        if InvoiceDialog(self, self.db).exec(): self.refresh()

    @guarded
    def import_excel(self):
        path, _ = QFileDialog.getOpenFileName(self, "Debitoren aus Excel importieren", "",
                                              "Excel-Dateien (*.xlsx *.xlsm)")
        if not path:
            return
        result = import_debtors(self.db, path)
        self.refresh()
        details = f"{result['imported']} Rechnungen und {result['payments']} Zahlungen importiert. {result['skipped']} Duplikate ausgelassen."
        if result["errors"]:
            details += f"\n{len(result['errors'])} Zeilen konnten nicht übernommen werden.\n" + "\n".join(result["errors"][:3])
        QMessageBox.information(self, "Excel-Import abgeschlossen", details)

    def edit(self):
        r = self.selected()
        if r and InvoiceDialog(self, self.db, r).exec(): self.refresh()

    def pay(self):
        r = self.selected()
        if r:
            PaymentDialog(self, self.db, r).exec()
            self.refresh()

    @staticmethod
    def reminder_text(invoice):
        level = invoice.get("reminder_level", 0)
        return "–" if not level else f"Stufe {level} · {display_date(invoice.get('reminder_date'))}"

    def reminder(self):
        invoice = self.selected()
        if invoice and ReminderDialog(self, self.db, invoice).exec():
            self.refresh()

    @guarded
    def remove(self):
        r = self.selected()
        if r and confirm(self, f"Rechnung {r['number']} löschen? Rechnungen mit Zahlungen müssen zuerst bereinigt werden."):
            self.db.delete("invoices", r["id"])
            self.refresh()

    def export_rows(self):
        return [[r["number"], r["customer"], display_date(r["issued"]), display_date(r["due"]), display_date(r["valuta"]), number(r["amount"]), number(r["paid"]), number(r["open"]), self.reminder_text(r), r["status"]] for r in self.filtered]

    @guarded
    def export_csv(self):
        path = save_path(self, "Debitoren exportieren", "Debitoren.csv", "csv", "debtors_csv")
        if path:
            csv_export(path, ["Rechnung", "Kunde", "Rechnungsdatum", "Fällig", "Valuta", "Betrag CHF", "Bezahlt CHF", "Offen CHF", "Mahnstufe", "Status"], self.export_rows())
            QMessageBox.information(self, "Export gespeichert", path)

    @guarded
    def export_pdf(self):
        path = save_path(self, "Debitoren als PDF", "Debitoren.pdf", "pdf", "debtors_pdf")
        if path:
            report_pdf(path, "Debitoren", f"{self.year.currentText()} · {self.quarter.currentText()} · {self.status.currentText()} · Suche: {self.search.text() or '–'}",
                       ["Rechnung", "Kunde", "Datum", "Fällig", "Valuta", "Betrag CHF", "Bezahlt CHF", "Offen CHF", "Mahnstufe", "Status"], self.export_rows(),
                       f"Rechnungsbetrag {chf(sum(r['amount'] for r in self.filtered))} · Bezahlt {chf(sum(r['paid'] for r in self.filtered))} · Offen {chf(sum(r['open'] for r in self.filtered))}",
                       [58, 115, 52, 52, 52, 62, 62, 62, 80, 60])
            PdfPreview(self, path).exec()


class TimePage(Page):
    def __init__(self, db, kind):
        super().__init__("Lernende" if kind == "apprentice" else "Mitarbeiter",
                         "Stundennachweise mit Ferien, Überzeit, Krankheit und Unfall.")
        self.db, self.kind = db, kind
        self.header.addWidget(button("+ Neue Person", self.new_person))
        self.entry_btn = button("+ Stunden erfassen", self.new_entry, True)
        self.header.addWidget(self.entry_btn)
        row = self.toolbar()
        self.person = combo([])
        self.person.setMinimumWidth(220)
        self.period = combo([])
        row.addWidget(self.person, 2)
        row.addWidget(self.period, 2)
        self.person_btn = button("Person bearbeiten", self.edit_person)
        self.new_period_btn = button("+ Periode", self.new_period)
        self.edit_period_btn = button("Periode bearbeiten", self.edit_period)
        row.addWidget(self.person_btn)
        row.addWidget(self.new_period_btn)
        row.addWidget(self.edit_period_btn)
        self.person.currentIndexChanged.connect(lambda _: self.refresh_periods())
        self.period.currentIndexChanged.connect(self.refresh_entries)
        self.cards = self.metrics([("Guthaben", "Ferien inklusive Überzeit", True), ("Ferien bezogen", "In dieser Periode"),
                                   ("Überzeit", "In dieser Periode"), ("Übertrag", "Aus der Vorperiode")])
        self.balance_hint = label("", "muted")
        self.balance_hint.setWordWrap(True)
        self.layout.addWidget(self.balance_hint)
        tabs = QTabWidget()
        self.layout.addWidget(tabs, 1)
        entry_pane = QWidget()
        ep = QVBoxLayout(entry_pane)
        ep.setContentsMargins(12, 12, 12, 12)
        self.table = Table(["Datum", "Kategorie", "Stunden", "Bemerkung"])
        self.table.cellDoubleClicked.connect(self.edit_entry)
        self.table.itemSelectionChanged.connect(self.selection)
        ep.addWidget(self.table)
        tabs.addTab(entry_pane, "Buchungen")
        self.history = Table(["Periode", "Anspruch h", "Übertrag h", "Ferien h", "Überzeit h", "Guthaben h", "Krank kum. h", "Unfall kum. h"])
        tabs.addTab(self.history, "Alle Perioden && Überträge")
        row = self.toolbar()
        self.edit_btn = button("Buchung bearbeiten", self.edit_entry)
        self.delete_btn = button("Buchung löschen", self.remove_entry)
        row.addWidget(self.edit_btn)
        row.addWidget(self.delete_btn)
        row.addStretch()
        self.csv_btn = button("CSV exportieren", self.export_csv)
        self.pdf_btn = button("Nachweis als PDF", self.export_pdf)
        row.addWidget(self.csv_btn)
        row.addWidget(self.pdf_btn)
        self.hint = label("", "muted")
        self.layout.addWidget(self.hint)
        self.current_balance = None
        self.selection()

    def refresh(self, selected=None):
        old = selected or self.person.currentData()
        self.person.blockSignals(True)
        self.person.clear()
        for p in self.db.employees(self.kind):
            self.person.addItem(f"{p['first_name']} {p['last_name']} · {p['code']}" + (" (inaktiv)" if not p["active"] else ""), p["id"])
        self.person.setCurrentIndex(max(0, self.person.findData(old)))
        self.person.blockSignals(False)
        self.refresh_periods()

    def refresh_periods(self, selected=None):
        if not hasattr(self, "hint"):
            return
        old = selected if isinstance(selected, int) and selected > 0 else self.period.currentData()
        self.period.blockSignals(True)
        self.period.clear()
        periods = self.db.periods(self.person.currentData())
        for p in periods:
            self.period.addItem(f"{p['label']} · {display_date(p['start'])} – {display_date(p['end'])}", p["id"])
        idx = self.period.findData(old)
        if idx < 0:
            current = next((p for p in periods if p["start"] <= date.today().isoformat() <= p["end"]), periods[-1] if periods else None)
            idx = self.period.findData(current["id"]) if current else -1
        self.period.setCurrentIndex(idx)
        self.period.blockSignals(False)
        self.refresh_entries()

    def refresh_entries(self):
        if not hasattr(self, "hint"):
            return
        balances = self.db.balances(self.person.currentData())
        b = next((b for b in balances if b["id"] == self.period.currentData()), None)
        self.current_balance = b
        self.current_entries = self.db.entries(b["id"]) if b else []
        self.table.populate([[display_date(e["day"]), KINDS[e["kind"]], number(e["hours"]), e["note"]] for e in self.current_entries], [e["id"] for e in self.current_entries], [2])
        self.history.populate([[p["label"], *[number(p[k]) for k in ("allowance", "carry", "vacation", "overtime", "balance", "sick_total", "accident_total")]] for p in balances], [p["id"] for p in balances], range(1, 8))
        for row, p in enumerate(balances):
            for col, k in [(2, "carry"), (4, "overtime"), (5, "balance")]:
                if p[k] < 0: self.history.item(row, col).setForeground(QColor("#bd3c40"))
        for c, key in zip(self.cards, ("balance", "vacation", "overtime", "carry")):
            c.set(number(b[key], " h") if b else "–", bool(b and b[key] < 0))
        if b:
            self.balance_hint.setText(f"Anspruch {number(b['allowance'])} h − Ferien {number(b['vacation'])} h + Überzeit {number(b['overtime'])} h + Übertrag {number(b['carry'])} h = {number(b['balance'])} h\nKrankheit: {number(b['sick'])} h, kumuliert {number(b['sick_total'])} h     ·     Unfall: {number(b['accident'])} h, kumuliert {number(b['accident_total'])} h")
            self.hint.setText(f"{len(self.current_entries)} Buchungen · Änderungen früherer Perioden aktualisieren alle Folgeperioden.")
        else:
            self.balance_hint.setText("Lege eine Person und ihre erste Periode an, um Stunden zu erfassen.")
            self.hint.setText("Keine Periode ausgewählt.")
        person = self.person.currentData() is not None
        self.person_btn.setEnabled(person)
        self.new_period_btn.setEnabled(person)
        for widget in (self.entry_btn, self.edit_period_btn, self.csv_btn, self.pdf_btn): widget.setEnabled(bool(b))
        self.selection()

    def selection(self):
        enabled = self.table.selected_id() is not None
        self.edit_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)

    def new_person(self):
        d = EmployeeDialog(self, self.db, kind=self.kind)
        if d.exec():
            self.refresh(d.saved_id)
            self.new_period()

    def edit_person(self):
        e = self.db.employee(self.person.currentData())
        if e and EmployeeDialog(self, self.db, e).exec(): self.refresh()

    def new_period(self):
        e = self.db.employee(self.person.currentData())
        if e:
            d = PeriodDialog(self, self.db, e)
            if d.exec(): self.refresh_periods(d.saved_id)

    def edit_period(self):
        b = self.current_balance
        if b and PeriodDialog(self, self.db, self.db.employee(b["employee_id"]), b).exec(): self.refresh_periods(b["id"])

    def new_entry(self):
        if self.current_balance and EntryDialog(self, self.db, self.current_balance).exec(): self.refresh_entries()

    def edit_entry(self):
        row = next((e for e in self.current_entries if e["id"] == self.table.selected_id()), None)
        if row and EntryDialog(self, self.db, self.current_balance, row).exec(): self.refresh_entries()

    @guarded
    def remove_entry(self):
        key = self.table.selected_id()
        if key and confirm(self, "Diese Buchung löschen? Guthaben und Überträge werden neu berechnet."):
            self.db.delete("entries", key)
            self.refresh_entries()

    @guarded
    def export_csv(self):
        if not self.current_balance:
            return
        employee = self.db.employee(self.person.currentData())
        folders = employee_year_folders(employee, self.current_balance["start"][:4])
        path = save_path(self, "Stunden exportieren", "Stundennachweis.csv", "csv",
                         "timesheets_csv", folders)
        if path:
            csv_export(path, ["Datum", "Kategorie", "Stunden", "Bemerkung"], [[display_date(e["day"]), KINDS[e["kind"]], number(e["hours"]), e["note"]] for e in self.current_entries])
            QMessageBox.information(self, "Export gespeichert", path)

    @guarded
    def export_pdf(self):
        if not self.current_balance:
            return
        employee = self.db.employee(self.person.currentData())
        folders = employee_year_folders(employee, self.current_balance["start"][:4])
        path = save_path(self, "Stundennachweis als PDF", "Stundennachweis.pdf", "pdf",
                         "timesheets_pdf", folders)
        if path:
            time_report(path, self.db.employee(self.person.currentData()), self.current_balance, self.current_entries)
            PdfPreview(self, path).exec()


class SalaryPage(Page):
    def __init__(self, db):
        super().__init__("Lohnausweise", "Lohn erfassen und in der mitgelieferten PDF-Vorlage ausgeben.")
        self.db = db
        self.header.addWidget(button("+ Neuer Lohnausweis", self.new, True))
        self.cards = self.metrics([("Ausweise", "Aktuelle Auswahl"), ("Bruttolohn", "Summe Ziffer 8"), ("Nettolohn", "Summe Ziffer 11", True)])
        row = self.toolbar()
        self.search = line(placeholder="Person oder Jahr suchen …")
        self.search.textChanged.connect(self.refresh)
        row.addWidget(self.search)
        self.table = Table(["Person", "Jahr", "Zeitraum", "Brutto CHF", "Abzüge CHF", "Netto CHF", "Geändert"])
        self.table.itemSelectionChanged.connect(self.selection)
        self.table.cellDoubleClicked.connect(self.edit)
        self.layout.addWidget(self.table, 1)
        row = self.toolbar()
        self.edit_btn = button("Bearbeiten", self.edit)
        self.preview_btn = button("Vorschau", self.preview)
        self.export_btn = button("PDF exportieren", self.export, True)
        self.delete_btn = button("Löschen", self.remove)
        for b in (self.edit_btn, self.preview_btn, self.export_btn): row.addWidget(b)
        row.addStretch()
        row.addWidget(self.delete_btn)
        note = label("Brutto = Ziffern 1–7. Netto = Brutto − Ziffern 9 und 10. Quellensteuer und Spesen werden separat ausgewiesen.\nDie mitgelieferte Formularfassung bleibt erhalten. Keine Berechnung von Beitragssätzen oder elektronische Steuerübermittlung.", "muted")
        note.setWordWrap(True)
        self.layout.addWidget(note)
        self.filtered = []
        self.selection()

    def refresh(self):
        q = self.search.text().casefold()
        self.filtered = [r for r in self.db.salaries() if q in (r["name"] + " " + str(r["year"])).casefold()]
        self.table.populate([[r["fields"].get("HName", r["name"]), r["year"], display_date(r["start"]) + " – " + display_date(r["end"]),
                              *[number(int(r["fields"][k] or 0)*100) for k in ("8", "abzuege", "11")], display_date(r["updated"][:10])] for r in self.filtered], [r["id"] for r in self.filtered], [3, 4, 5])
        self.cards[0].set(str(len(self.filtered)))
        self.cards[1].set(chf(sum(int(r["fields"]["8"] or 0)*100 for r in self.filtered)))
        self.cards[2].set(chf(sum(int(r["fields"]["11"] or 0)*100 for r in self.filtered)))
        self.selection()

    def selection(self):
        enabled = self.table.selected_id() is not None
        for b in (self.edit_btn, self.preview_btn, self.export_btn, self.delete_btn): b.setEnabled(enabled)

    def selected(self):
        return next((r for r in self.filtered if r["id"] == self.table.selected_id()), None)

    def new(self):
        if not self.db.employees():
            QMessageBox.information(self, "Person fehlt", "Bitte zuerst eine Person unter Mitarbeiter, Lernende oder Stammdaten erfassen.")
            return
        if SalaryDialog(self, self.db).exec(): self.refresh()

    def edit(self):
        r = self.selected()
        if r and SalaryDialog(self, self.db, r).exec(): self.refresh()

    @guarded
    def preview(self):
        r = self.selected()
        if r:
            folder = self.db.path.parent / "vorschau"
            folder.mkdir(exist_ok=True)
            path = folder / f"Lohnausweis-{r['id']}-{datetime.now():%Y%m%d-%H%M%S-%f}.pdf"
            salary_pdf(r["fields"], path)
            preview = PdfPreview(self, path)
            preview.exec()
            preview.document.close()

    @guarded
    def export(self):
        r = self.selected()
        if r:
            employee = self.db.employee(r["employee_id"])
            folders = employee_year_folders(employee, r["year"])
            path = save_path(self, "Lohnausweis speichern", f"Lohnausweis-{r['year']}-{r['employee_id']}.pdf",
                             "pdf", "salary_pdf", folders)
            if path:
                salary_pdf(r["fields"], path)
                PdfPreview(self, path).exec()

    @guarded
    def remove(self):
        r = self.selected()
        if r and confirm(self, f"Gespeicherten Ausweis für {r['name']} ({r['year']}) löschen?"):
            self.db.delete("salaries", r["id"])
            self.refresh()


class SettingsPage(Page):
    def __init__(self, db):
        super().__init__("Stammdaten & Einstellungen", "Personen und Kunden zentral pflegen. Daten lokal sichern.")
        self.db = db
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs, 1)
        self.people = Table(["Personal-Nr.", "Name", "Bereich", "Funktion", "Pensum", "Status"])
        self.people.cellDoubleClicked.connect(self.edit_person)
        self.customers = Table(["Kunden-Nr.", "Name / Firma", "Strasse", "PLZ", "Ort", "E-Mail"])
        self.customers.cellDoubleClicked.connect(self.edit_customer)
        for title, table, new, edit in [("Personen", self.people, self.new_person, self.edit_person), ("Kunden", self.customers, self.new_customer, self.edit_customer)]:
            pane = QWidget()
            layout = QVBoxLayout(pane)
            layout.setContentsMargins(16, 16, 16, 16)
            row = QHBoxLayout()
            row.addWidget(button("+ Neu erfassen", new, True))
            row.addWidget(button("Auswahl bearbeiten", edit))
            row.addStretch()
            layout.addLayout(row)
            layout.addWidget(table)
            self.tabs.addTab(pane, title)
        company = QWidget()
        company_layout = QVBoxLayout(company)
        form = QFormLayout()
        form.setContentsMargins(18, 20, 18, 15)
        form.setSpacing(16)
        self.company_fields = {}
        for key, title in [("company", "Firma"), ("address", "Strasse"), ("postcode", "PLZ"),
                           ("city", "Ort"), ("phone", "Telefon"), ("email", "E-Mail"),
                           ("website", "Website"), ("contact", "Verantwortliche Person")]:
            self.company_fields[key] = line()
            form.addRow(title, self.company_fields[key])
        self.logo_preview = label("Kein Firmenlogo gewählt", "muted")
        self.logo_preview.setMinimumSize(220, 80)
        self.logo_preview.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        logo_actions = QWidget()
        logo_row = QHBoxLayout(logo_actions)
        logo_row.setContentsMargins(0, 0, 0, 0)
        logo_row.addWidget(button("Logo auswählen …", self.upload_logo))
        logo_row.addWidget(button("Logo entfernen", self.remove_logo))
        logo_row.addStretch()
        form.addRow("Logo für Mahnungen", self.logo_preview)
        form.addRow("", logo_actions)
        form.addRow("", button("Firmendaten speichern", self.save_company, True))
        company_layout.addLayout(form)
        company_layout.addStretch()
        self.tabs.addTab(company, "Firma")
        data = QWidget()
        dl = QVBoxLayout(data)
        dl.setContentsMargins(22, 22, 22, 22)
        dl.addWidget(label("Datensicherung", "sectionTitle"))
        path_label = label("Aktive Datenbank:\n" + str(db.path), "muted")
        path_label.setWordWrap(True)
        path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        dl.addWidget(path_label)
        dl.addWidget(button("Sicherung erstellen …", self.backup, True))
        dl.addWidget(button("Sicherung wiederherstellen …", self.restore))
        dl.addSpacing(16)
        dl.addWidget(label("Automatische externe Sicherung", "sectionTitle"))
        backup_row = QHBoxLayout()
        self.backup_directory = line("", "z. B. E:\\AST-Sicherungen oder ein Netzlaufwerk")
        self.backup_directory.setReadOnly(True)
        backup_row.addWidget(self.backup_directory, 1)
        backup_row.addWidget(button("Ordner wählen …", self.choose_backup_directory))
        backup_row.addWidget(button("Deaktivieren", self.clear_backup_directory))
        dl.addLayout(backup_row)
        retention_row = QHBoxLayout()
        retention_row.addWidget(label("Aufbewahrung in Tagen", "muted"))
        self.backup_retention = line("30")
        self.backup_retention.setMaximumWidth(90)
        retention_row.addWidget(self.backup_retention)
        retention_row.addStretch()
        retention_row.addWidget(button("Einstellungen speichern", self.save_backup_settings))
        retention_row.addWidget(button("Jetzt extern sichern", self.backup_external, True))
        dl.addLayout(retention_row)
        description = label("Beim Programmstart wird täglich eine Sicherung erstellt. Ist ein externer Ordner gewählt, wird die Datenbank zusätzlich dorthin gesichert. Alte automatische externe Sicherungen werden nach der gewählten Frist entfernt.\nVor jeder Wiederherstellung wird der aktuelle Stand automatisch gesichert.", "muted")
        description.setWordWrap(True)
        dl.addWidget(description)
        dl.addStretch()
        self.tabs.addTab(data, "Daten && Sicherung")

        exports = QWidget()
        exports_layout = QVBoxLayout(exports)
        exports_layout.setContentsMargins(22, 22, 22, 22)
        exports_layout.setSpacing(12)
        exports_layout.addWidget(label("Standardordner für Exporte", "sectionTitle"))
        export_hint = label(
            "Lege für jede Ausgabeart einen eigenen Ordner fest. Beim Export wird dieser Ordner "
            "automatisch geöffnet; Dateiname und Ziel können danach weiterhin geändert werden.", "muted")
        export_hint.setWordWrap(True)
        exports_layout.addWidget(export_hint)
        excel_security = QFrame()
        excel_security.setObjectName("card")
        security_layout = QHBoxLayout(excel_security)
        security_layout.setContentsMargins(16, 12, 16, 12)
        security_text = label(
            "Excel-Sicherheit: Der Stundennachweis-Ordner wird auf diesem PC als vertrauenswürdig "
            "eingetragen. Danach funktionieren die Schaltflächen ohne geschützte Ansicht.", "muted")
        security_text.setWordWrap(True)
        security_layout.addWidget(security_text, 1)
        security_layout.addWidget(button("Excel-Zugriff einrichten", self.setup_excel_security, True))
        exports_layout.addWidget(excel_security)
        self.export_directory_fields = {}
        for key, title, description in EXPORT_DESTINATIONS:
            card = QFrame()
            card.setObjectName("card")
            card_layout = QVBoxLayout(card)
            card_layout.setContentsMargins(16, 12, 16, 12)
            card_layout.setSpacing(7)
            heading = QHBoxLayout()
            heading.addWidget(label(title, "sectionTitle"))
            heading.addStretch()
            heading.addWidget(label(description, "muted"))
            card_layout.addLayout(heading)
            path_row = QHBoxLayout()
            field = line()
            field.setReadOnly(True)
            field.setPlaceholderText(str(default_directory(key)) + " (Standard)")
            self.export_directory_fields[key] = field
            path_row.addWidget(field, 1)
            path_row.addWidget(button("Ordner wählen …", lambda value=key: self.choose_export_directory(value)))
            path_row.addWidget(button("Standard", lambda value=key: self.clear_export_directory(value)))
            card_layout.addLayout(path_row)
            exports_layout.addWidget(card)
        exports_layout.addStretch()
        export_scroll = QScrollArea()
        export_scroll.setWidgetResizable(True)
        export_scroll.setFrameShape(QFrame.Shape.NoFrame)
        export_scroll.setWidget(exports)
        self.tabs.addTab(export_scroll, "Exportpfade")

        web = QWidget()
        web_layout = QVBoxLayout(web)
        web_layout.setContentsMargins(22, 22, 22, 22)
        web_layout.setSpacing(14)
        web_layout.addWidget(label("Desktop und Web verbinden", "sectionTitle"))
        web_hint = label(
            "Verbindet diesen PC verschlüsselt mit manager.ast-elektro.ch. Die erste Übertragung wird bewusst "
            "gewählt; danach kann die App Änderungen beider Seiten automatisch erkennen.", "muted")
        web_hint.setWordWrap(True)
        web_layout.addWidget(web_hint)
        web_form = QFormLayout()
        self.web_url = line("https://manager.ast-elektro.ch", "https://manager.ast-elektro.ch")
        self.web_email = line("", "E-Mail des Webkontos")
        self.web_password = line("", "Passwort des Webkontos")
        self.web_password.setEchoMode(QLineEdit.EchoMode.Password)
        web_form.addRow("Webadresse", self.web_url)
        web_form.addRow("E-Mail", self.web_email)
        web_form.addRow("Passwort", self.web_password)
        web_layout.addLayout(web_form)
        self.web_auto = QCheckBox("Nach der ersten Übertragung automatisch synchronisieren")
        web_layout.addWidget(self.web_auto)
        actions = QHBoxLayout()
        actions.addWidget(button("Verbindung prüfen", self.test_web_connection))
        actions.addStretch()
        actions.addWidget(button("Webstand auf diesen PC übernehmen", self.pull_web_data))
        actions.addWidget(button("Desktopstand ins Web übertragen", self.push_web_data, True))
        web_layout.addLayout(actions)
        self.web_status = label("Noch nicht verbunden.", "muted")
        self.web_status.setWordWrap(True)
        web_layout.addWidget(self.web_status)
        web_layout.addStretch()
        self.tabs.addTab(web, "Web-Synchronisation")

    def refresh(self):
        people = self.db.employees()
        self.people.populate([[p["code"], p["first_name"] + " " + p["last_name"], "Lernende" if p["kind"] == "apprentice" else "Mitarbeiter", p["job"], number(p["workload"], " %"), "Aktiv" if p["active"] else "Inaktiv"] for p in people], [p["id"] for p in people])
        customers = self.db.customers()
        self.customers.populate([[c[k] for k in ("customer_number", "name", "address", "postcode", "city", "email")] for c in customers], [c["id"] for c in customers])
        settings = self.db.settings()
        for key, widget in self.company_fields.items(): widget.setText(settings.get(key, ""))
        self._show_logo(settings.get("logo_path", ""))
        self.backup_directory.setText(settings.get("backup_directory", ""))
        self.backup_retention.setText(settings.get("backup_retention_days", "30"))
        for key, field in self.export_directory_fields.items():
            field.setText(settings.get(setting_key(key), ""))
        self.web_url.setText(settings.get("web_sync_url", "https://manager.ast-elektro.ch"))
        self.web_email.setText(settings.get("web_sync_email", ""))
        self.web_auto.setChecked(settings.get("web_sync_enabled", "0") == "1")
        if settings.get("web_sync_password") and not self.web_password.text():
            try:
                self.web_password.setText(unprotect_secret(settings["web_sync_password"]))
            except (ValueError, OSError):
                self.web_status.setText("Das gespeicherte Webpasswort gehört zu einem anderen Windows-Benutzer. Bitte neu eingeben.")
        revision = settings.get("web_sync_revision", "")
        if revision:
            self.web_status.setText(f"Synchronisation eingerichtet · letzter Serverstand {revision}")

    def _web_client(self):
        url = self.web_url.text().strip()
        email = self.web_email.text().strip()
        password = self.web_password.text()
        if not email or not password:
            raise ValueError("Bitte E-Mail und Passwort des Webkontos eingeben.")
        self.db.save_settings({
            "web_sync_url": url,
            "web_sync_email": email,
            "web_sync_password": protect_secret(password),
            "web_sync_enabled": "1" if self.web_auto.isChecked() else "0",
        })
        return WebSyncClient(url, email, password, timeout=20)

    @guarded
    def test_web_connection(self):
        remote = self._web_client().fetch()
        revision = int(remote.get("revision", 0))
        self.web_status.setText(f"Verbindung erfolgreich · Serverstand {revision}")
        QMessageBox.information(self, "Webverbindung", "Die geschützte Verbindung zur Webversion funktioniert.")

    @guarded
    def push_web_data(self):
        if not confirm(self, "Desktopstand übertragen",
                       "Der aktuelle Datenstand dieses PCs ersetzt die Geschäftsdaten der Webversion. Fortfahren?"):
            return
        revision = push_desktop(self.db, self._web_client())
        self.web_status.setText(f"Desktop und Web sind synchron · Serverstand {revision}")
        QMessageBox.information(self, "Synchronisation abgeschlossen", "Der vollständige Desktop-Datenstand wurde ins Web übertragen.")

    @guarded
    def pull_web_data(self):
        if not confirm(self, "Webstand übernehmen",
                       "Der Webdatenstand ersetzt die Geschäftsdaten auf diesem PC. Vorher wird automatisch eine lokale Sicherung erstellt. Fortfahren?"):
            return
        revision = pull_web(self.db, self._web_client())
        self.refresh()
        self.web_status.setText(f"Desktop und Web sind synchron · Serverstand {revision}")
        QMessageBox.information(self, "Synchronisation abgeschlossen", "Der Webdatenstand wurde übernommen. Eine lokale Sicherung wurde erstellt.")

    def run_automatic_web_sync(self):
        settings = self.db.settings()
        if settings.get("web_sync_enabled") != "1" or hasattr(self, "_sync_thread"):
            return
        try:
            password = unprotect_secret(settings.get("web_sync_password", ""))
        except (ValueError, OSError) as exc:
            self.web_status.setText(str(exc))
            return
        if not settings.get("web_sync_email") or not password or not settings.get("web_sync_revision"):
            return
        self.web_status.setText("Synchronisation läuft im Hintergrund …")
        self._sync_thread = QThread(self)
        self._sync_worker = _AutomaticWebSyncWorker(
            self.db.path, settings.get("web_sync_url", "https://manager.ast-elektro.ch"),
            settings["web_sync_email"], password)
        self._sync_worker.moveToThread(self._sync_thread)
        self._sync_thread.started.connect(self._sync_worker.run)
        self._sync_worker.completed.connect(self._automatic_sync_completed)
        self._sync_worker.failed.connect(self._automatic_sync_failed)
        self._sync_worker.finished.connect(self._sync_thread.quit)
        self._sync_worker.finished.connect(self._sync_worker.deleteLater)
        self._sync_thread.finished.connect(self._automatic_sync_finished)
        self._sync_thread.start()

    def _automatic_sync_completed(self, message):
        self.web_status.setText(message)

    def _automatic_sync_failed(self, message):
        self.web_status.setText("Automatische Synchronisation angehalten: " + message)

    def _automatic_sync_finished(self):
        thread = self._sync_thread
        del self._sync_worker
        del self._sync_thread
        thread.deleteLater()

    @guarded
    def choose_export_directory(self, export_key):
        field = self.export_directory_fields[export_key]
        path = QFileDialog.getExistingDirectory(
            self, "Standardordner für diesen Export wählen", field.text() or str(default_directory(export_key)))
        if path:
            self.db.save_settings({setting_key(export_key): path})
            field.setText(path)

    def clear_export_directory(self, export_key):
        self.db.save_settings({setting_key(export_key): ""})
        self.export_directory_fields[export_key].clear()

    @guarded
    def setup_excel_security(self):
        folder = configured_directory(self.db, "timesheets_excel")
        folder.mkdir(parents=True, exist_ok=True)
        error = ensure_excel_trusted_folder(folder)
        if error:
            raise ValueError("Excel konnte den Ordner nicht freigeben: " + error)
        unblocked = 0
        for workbook in folder.rglob("*.xlsm"):
            unblock_excel_file(workbook)
            unblocked += 1
        QMessageBox.information(
            self, "Excel-Zugriff eingerichtet",
            f"Der Stundennachweis-Ordner ist auf diesem PC freigegeben. "
            f"{unblocked} vorhandene Excel-Datei(en) wurden ebenfalls entsperrt.\n\n"
            "Schliesse jetzt einmal alle Excel-Fenster vollständig. Danach die Datei direkt aus dem "
            "eingestellten Stundennachweis-Ordner öffnen. Diese Einrichtung ist pro PC einmal erforderlich."
        )

    def new_person(self):
        if EmployeeDialog(self, self.db).exec(): self.refresh()

    def edit_person(self):
        row = self.db.employee(self.people.selected_id())
        if row and EmployeeDialog(self, self.db, row).exec(): self.refresh()

    def new_customer(self):
        if CustomerDialog(self, self.db).exec(): self.refresh()

    def edit_customer(self):
        row = next((c for c in self.db.customers() if c["id"] == self.customers.selected_id()), None)
        if row and CustomerDialog(self, self.db, row).exec(): self.refresh()

    @guarded
    def save_company(self):
        self.db.save_settings({k: w.text() for k, w in self.company_fields.items()})
        QMessageBox.information(self, "Gespeichert", "Firmendaten wurden gespeichert.")

    def _show_logo(self, path):
        pixmap = QPixmap(path) if path else QPixmap()
        if pixmap.isNull():
            self.logo_preview.setPixmap(QPixmap())
            self.logo_preview.setText("Kein Firmenlogo gewählt")
        else:
            self.logo_preview.setText("")
            self.logo_preview.setPixmap(pixmap.scaled(210, 72, Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation))
            self.logo_preview.setToolTip(str(path))

    @guarded
    def upload_logo(self):
        source, _ = QFileDialog.getOpenFileName(self, "Firmenlogo auswählen", "",
                                                "Bilder (*.png *.jpg *.jpeg)")
        if not source:
            return
        if QPixmap(source).isNull():
            raise ValueError("Die ausgewählte Datei ist kein lesbares PNG- oder JPG-Bild.")
        folder = self.db.path.parent / "branding"
        folder.mkdir(parents=True, exist_ok=True)
        destination = folder / ("firmenlogo" + Path(source).suffix.lower())
        shutil.copy2(source, destination)
        self.db.save_settings({"logo_path": str(destination)})
        self._show_logo(str(destination))

    @guarded
    def remove_logo(self):
        path = Path(self.db.settings().get("logo_path", ""))
        folder = (self.db.path.parent / "branding").resolve()
        if path.is_file() and path.resolve().parent == folder:
            path.unlink()
        self.db.save_settings({"logo_path": ""})
        self._show_logo("")

    @guarded
    def backup(self):
        path = save_path(self, "Sicherung speichern", f"AST-Sicherung-{datetime.now():%Y%m%d-%H%M%S}.sqlite3",
                         "sqlite3", "backup_manual")
        if path:
            self.db.backup(path)
            QMessageBox.information(self, "Sicherung erstellt", path)

    def choose_backup_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Ordner für automatische Sicherungen wählen",
                                                self.backup_directory.text() or str(Path.home()))
        if path:
            self.backup_directory.setText(path)
            self._save_backup_settings()

    def clear_backup_directory(self):
        self.backup_directory.clear()
        self._save_backup_settings()

    def _save_backup_settings(self):
        try:
            retention = int(self.backup_retention.text())
            if not 1 <= retention <= 3650:
                raise ValueError
        except ValueError:
            raise ValueError("Die Aufbewahrung muss zwischen 1 und 3650 Tagen liegen.") from None
        self.db.save_settings({"backup_directory": self.backup_directory.text(),
                               "backup_retention_days": retention})

    @guarded
    def save_backup_settings(self):
        self._save_backup_settings()
        QMessageBox.information(self, "Gespeichert", "Die Einstellungen für automatische Sicherungen wurden gespeichert.")

    @guarded
    def backup_external(self):
        if not self.backup_directory.text():
            raise ValueError("Bitte zuerst einen externen Sicherungsordner wählen.")
        self._save_backup_settings()
        created = run_automatic_backups(self.db, self.db.path.parent / "backups",
                                        self.backup_directory.text(), self.backup_retention.text())
        QMessageBox.information(self, "Sicherung geprüft", "Die externe Tagessicherung ist aktuell.\n" +
                                (str(created[-1]) if created else self.backup_directory.text()))

    @guarded
    def restore(self):
        path, _ = QFileDialog.getOpenFileName(self, "AST-Sicherung wählen", "", "AST-Datenbank (*.sqlite3 *.db)")
        if path and confirm(self, "Die gewählte Sicherung ersetzt alle aktuellen Daten. Zuvor wird der aktuelle Stand gesichert. Fortfahren?"):
            safety = self.db.restore(path)
            self.refresh()
            QMessageBox.information(self, "Wiederhergestellt", "Daten wiederhergestellt.\nDer vorherige Stand liegt unter:\n" + str(safety))
