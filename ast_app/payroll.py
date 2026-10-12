"""Monthly payroll book and salary trend view."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import re
from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QMessageBox, QFileDialog

from .widgets import Page, FormDialog, Table, label, button, combo, numeric, line, selection_bar, guarded, confirm
from .domain import chf
from .pages import save_path
from .export_paths import employee_year_folders
from .payroll_excel import export_payroll_book, import_payroll_book


MONTHS = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember", "13. Monatslohn")
RATE_FIELDS = (("ahv_rate", "AHV"), ("alv_rate", "ALV"), ("nbuv_rate", "NBUV"),
               ("ktv_rate", "KTV"), ("bvg_rate", "BVG"), ("pk_rate", "PK"))


class PayrollDialog(FormDialog):
    def __init__(self, parent, db, employee, year, row=None, defaults=None):
        super().__init__(parent, "Monatslohn bearbeiten" if row else "Monatslohn erfassen",
                         f"{employee['first_name']} {employee['last_name']} · {year}", 660)
        self.db, self.employee, self.year, self.row = db, employee, int(year), row or {}
        source = {**(defaults or {}), **self.row}
        self.add("month", "Monat", combo([(title, index) for index, title in enumerate(MONTHS, 1)],
                                           source.get("month", min(date.today().month, 12))))
        self.add("gross", "Bruttolohn", numeric(int(source.get("gross") or 0) / 100, " CHF"))
        self.add("allowance", "Zulagen / Gutschriften", numeric(int(source.get("allowance") or 0) / 100, " CHF"))
        self.form.addRow(label("Lohnabzüge", "sectionTitle"))
        defaults_rates = {"ahv_rate": 5300, "alv_rate": 1100, "nbuv_rate": 1670,
                          "ktv_rate": 1855, "bvg_rate": 0, "pk_rate": 0}
        for key, title in RATE_FIELDS:
            if key == "bvg_rate":
                mode = source.get("bvg_mode") or "percent"
                self.add("bvg_mode", "BVG Berechnung", combo([
                    ("Prozent des Bruttolohns", "percent"), ("Fester Betrag in CHF", "fixed")], mode))
                amount = (int(source.get("bvg_amount") or 0) / 100 if mode == "fixed"
                          else int(source.get("bvg_rate") or 0) / 1000)
                self.bvg_value = numeric(amount, " CHF" if mode == "fixed" else " %")
                self.bvg_value.setRange(0, 999999999 if mode == "fixed" else 100)
                self.bvg_value.setDecimals(2 if mode == "fixed" else 3)
                self.add("bvg_value", "BVG Wert", self.bvg_value)
                self.fields["bvg_mode"].currentIndexChanged.connect(self._bvg_mode_changed)
                continue
            rate = int(source.get(key) if source.get(key) is not None else defaults_rates[key]) / 1000
            field = numeric(rate, " %")
            field.setRange(0, 100)
            field.setDecimals(3)
            field.setSingleStep(0.1)
            self.add(key, title, field)
        self.add("note", "Bemerkung", line(source.get("note", ""), "optional"))
        self._bvg_mode_changed()
        note = label("Prozentuale Abzüge werden auf CHF 0.50 gerundet; ein fixer BVG-Betrag wird exakt übernommen. "
                     "Nettolohn = Bruttolohn - Abzüge + Zulagen.", "muted")
        note.setWordWrap(True)
        self.form.addRow("", note)

    def _bvg_mode_changed(self):
        fixed = self.fields["bvg_mode"].currentData() == "fixed"
        self.bvg_value.setSuffix(" CHF" if fixed else " %")
        self.bvg_value.setDecimals(2 if fixed else 3)
        self.bvg_value.setRange(0, 999999999 if fixed else 100)
        self.bvg_value.setToolTip("Festen monatlichen BVG-Abzug in CHF eingeben." if fixed else
                                  "BVG-Abzug in Prozent des Bruttolohns eingeben.")

    @guarded
    def submit(self):
        values = self.values()
        values["employee_id"], values["year"] = self.employee["id"], self.year
        values["gross"] = round(values["gross"] * 100)
        values["allowance"] = round(values["allowance"] * 100)
        for key, _ in RATE_FIELDS:
            if key == "bvg_rate":
                continue
            values[key] = round(values[key] * 1000)
        bvg_value = values.pop("bvg_value")
        if values["bvg_mode"] == "fixed":
            values["bvg_amount"], values["bvg_rate"] = round(bvg_value * 100), 0
        else:
            values["bvg_rate"], values["bvg_amount"] = round(bvg_value * 1000), 0
        if values["gross"] <= 0:
            raise ValueError("Bitte einen positiven Bruttolohn eingeben.")
        self.saved_id = self.db.save_payroll_record(values, self.row.get("id"))
        self.accept()


class SalaryTrend(QWidget):
    def __init__(self):
        super().__init__()
        self.labels, self.gross, self.net = [], [], []
        self.setMinimumHeight(360)

    def set_data(self, labels, gross, net):
        self.labels, self.gross, self.net = labels, gross, net
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#ffffff"))
        left, top, right, bottom = 78, 32, 28, 58
        width, height = max(1, self.width() - left - right), max(1, self.height() - top - bottom)
        maximum = max(self.gross + self.net + [1]) if self.labels else 1
        for step in range(5):
            y = top + height * step / 4
            painter.setPen(QPen(QColor("#d8e1e5"), 1))
            painter.drawLine(left, int(y), left + width, int(y))
            value = maximum * (1 - step / 4) / 100
            title = (f"CHF {value:,.0f}").replace(",", "’")
            painter.setPen(QColor("#607985"))
            painter.drawText(0, int(y - 10), left - 10, 20, Qt.AlignmentFlag.AlignRight, title)
        if not self.labels:
            painter.setPen(QColor("#607985"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Noch keine Lohndaten vorhanden")
            return
        def points(values):
            count = max(1, len(values) - 1)
            return [QPointF(left + width * index / count, top + height * (1 - value / maximum))
                    for index, value in enumerate(values)]
        for values, colour in ((self.gross, "#0d3441"), (self.net, "#009879")):
            pts = points(values)
            painter.setPen(QPen(QColor(colour), 3))
            for first, second in zip(pts, pts[1:]):
                painter.drawLine(first, second)
            painter.setBrush(QColor(colour))
            for point in pts:
                painter.drawEllipse(point, 3.5, 3.5)
        painter.setPen(QColor("#49636f"))
        stride = max(1, (len(self.labels) + 7) // 8)
        for index, title in enumerate(self.labels):
            if index % stride and index != len(self.labels) - 1:
                continue
            x = left + width * index / max(1, len(self.labels) - 1)
            painter.drawText(int(x - 42), top + height + 12, 84, 28,
                             Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop, title)
        painter.setPen(QPen(QColor("#0d3441"), 3)); painter.drawLine(left, 14, left + 24, 14)
        painter.setPen(QColor("#0d3441")); painter.drawText(left + 30, 5, 85, 20,
                                                            Qt.AlignmentFlag.AlignLeft, "Bruttolohn")
        painter.setPen(QPen(QColor("#009879"), 3)); painter.drawLine(left + 120, 14, left + 144, 14)
        painter.setPen(QColor("#009879")); painter.drawText(left + 150, 5, 85, 20,
                                                            Qt.AlignmentFlag.AlignLeft, "Nettolohn")


class PayrollPage(Page):
    def __init__(self, db):
        super().__init__("Lohnbuch", "Monatslöhne, prozentuale oder feste Abzüge, Nettolohn und Lohnverlauf.")
        self.db, self.records = db, []
        self.header.addWidget(button("+ Monatslohn erfassen", self.new, True))
        controls = self.toolbar()
        controls.addWidget(label("Mitarbeiter", "muted"))
        self.person = combo([])
        controls.addWidget(self.person, 1)
        controls.addWidget(label("Jahr", "muted"))
        current = date.today().year
        self.year = combo([(str(year), year) for year in range(current + 1, current - 10, -1)], current)
        controls.addWidget(self.year)
        controls.addStretch()
        controls.addWidget(button("Excel-Dateien importieren", self.import_excel))
        controls.addWidget(button("Excel speichern", self.export_excel, True))
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs, 1)
        monthly = QWidget(); monthly_layout = QVBoxLayout(monthly); monthly_layout.setContentsMargins(0, 16, 0, 0)
        self.table = Table(["Monat", "Bruttolohn", "BVG-Art", "BVG-Abzug", "Abzüge total",
                            "Zulagen", "Nettolohn", "Bemerkung"])
        monthly_layout.addWidget(self.table, 1)
        row, self.selection_hint = selection_bar(monthly_layout, "Wähle einen Monatslohn aus oder erfasse einen neuen.")
        self.edit_btn = button("Bearbeiten", self.edit); self.delete_btn = button("Löschen", self.remove)
        row.addWidget(self.edit_btn); row.addWidget(self.delete_btn)
        self.tabs.addTab(monthly, "Monatslöhne")
        trend = QWidget(); trend_layout = QVBoxLayout(trend); trend_layout.setContentsMargins(0, 16, 0, 0)
        trend_controls = QHBoxLayout(); trend_controls.addWidget(label("Zeitraum", "muted"))
        self.range = combo([("Monat", "month"), ("Jahr", "year"), ("5 Jahre", "five"), ("Maximum", "all")], "year")
        trend_controls.addWidget(self.range); trend_controls.addStretch(); trend_layout.addLayout(trend_controls)
        self.chart = SalaryTrend(); trend_layout.addWidget(self.chart, 1)
        self.trend_table = Table(["Zeitraum", "Bruttolohn", "Nettolohn", "Differenz"])
        self.trend_table.setMaximumHeight(240); trend_layout.addWidget(self.trend_table)
        self.tabs.addTab(trend, "Lohnverlauf")
        self.person.currentIndexChanged.connect(self.refresh)
        self.year.currentIndexChanged.connect(self.refresh)
        self.range.currentIndexChanged.connect(self.refresh_trend)
        self.table.itemSelectionChanged.connect(self.selection)
        self.table.cellDoubleClicked.connect(self.edit)
        self.refresh_people()

    def refresh_people(self):
        selected = self.person.currentData()
        self.person.blockSignals(True); self.person.clear()
        for employee in self.db.employees():
            self.person.addItem(f"{employee['last_name']} {employee['first_name']} · {employee['code']}", employee["id"])
        if selected is not None and self.person.findData(selected) >= 0:
            self.person.setCurrentIndex(self.person.findData(selected))
        self.person.blockSignals(False)
        self.refresh()

    def refresh(self):
        if not hasattr(self, "person"):
            return
        employees = self.db.employees()
        current_ids = [self.person.itemData(index) for index in range(self.person.count())]
        wanted_ids = [employee["id"] for employee in employees]
        if current_ids != wanted_ids:
            selected = self.person.currentData()
            self.person.blockSignals(True); self.person.clear()
            for employee in employees:
                self.person.addItem(f"{employee['last_name']} {employee['first_name']} · {employee['code']}", employee["id"])
            if selected in wanted_ids:
                self.person.setCurrentIndex(self.person.findData(selected))
            self.person.blockSignals(False)
        employee_id, year = self.person.currentData(), self.year.currentData()
        self.records = self.db.payroll_records(employee_id, year) if employee_id else []
        self.table.populate([[
            MONTHS[r["month"] - 1], chf(r["gross"]),
            "Fixbetrag" if r.get("bvg_mode") == "fixed" else f"{int(r.get('bvg_rate') or 0) / 1000:.3f} %",
            chf(r["bvg"]), chf(r["deductions"]), chf(r["allowance"]), chf(r["net"]), r["note"]
        ] for r in self.records], [r["id"] for r in self.records], [1, 3, 4, 5, 6])
        self.selection(); self.refresh_trend()

    def selected(self):
        return next((record for record in self.records if record["id"] == self.table.selected_id()), None)

    def selection(self):
        enabled = self.selected() is not None
        self.edit_btn.setEnabled(enabled); self.delete_btn.setEnabled(enabled)

    def defaults(self):
        all_records = self.db.payroll_records(self.person.currentData()) if self.person.currentData() else []
        return all_records[-1] if all_records else None

    def new(self):
        employee = self.db.employee(self.person.currentData()) if self.person.currentData() else None
        if not employee:
            QMessageBox.information(self, "Mitarbeiter fehlt", "Bitte zuerst einen Mitarbeiter erfassen.")
            return
        if PayrollDialog(self, self.db, employee, self.year.currentData(), defaults=self.defaults()).exec():
            self.refresh()

    def edit(self):
        record = self.selected(); employee = self.db.employee(self.person.currentData())
        if record and PayrollDialog(self, self.db, employee, self.year.currentData(), record).exec():
            self.refresh()

    @guarded
    def remove(self):
        record = self.selected()
        if record and confirm(self, f"Den Monatslohn {MONTHS[record['month'] - 1]} {record['year']} löschen?"):
            self.db.delete("payroll_records", record["id"]); self.refresh()

    def refresh_trend(self):
        employee_id = self.person.currentData() if hasattr(self, "person") else None
        if not employee_id:
            self.chart.set_data([], [], []); self.trend_table.populate([], []); return
        records = self.db.payroll_records(employee_id)
        mode, selected_year = self.range.currentData(), int(self.year.currentData())
        points = []
        if mode in ("month", "year"):
            chosen = records[-12:] if mode == "month" else [r for r in records if r["year"] == selected_year]
            points = [(f"{MONTHS[r['month'] - 1][:3]} {str(r['year'])[-2:]}", r["gross"], r["net"]) for r in chosen]
        else:
            totals = {}
            for record in records:
                gross, net = totals.get(record["year"], (0, 0))
                totals[record["year"]] = (gross + record["gross"], net + record["net"])
            years = sorted(totals)
            if mode == "five": years = years[-5:]
            points = [(str(year), *totals[year]) for year in years]
        self.chart.set_data([p[0] for p in points], [p[1] for p in points], [p[2] for p in points])
        self.trend_table.populate([[title, chf(gross), chf(net), chf(gross - net)]
                                   for title, gross, net in reversed(points)], list(range(len(points))), [1, 2, 3])

    @guarded
    def import_excel(self):
        employee = self.db.employee(self.person.currentData()) if self.person.currentData() else None
        if not employee:
            QMessageBox.information(self, "Mitarbeiter fehlt", "Bitte zuerst einen Mitarbeiter auswählen.")
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Lohnbücher für ausgewählten Mitarbeiter importieren", "",
            "Excel-Dateien (*.xlsx *.xlsm)")
        if not paths:
            return

        def normal_name(value):
            return re.sub(r"[^\w]+", "", str(value or "").casefold())

        expected_names = {
            normal_name(f"{employee['first_name']} {employee['last_name']}"),
            normal_name(f"{employee['last_name']} {employee['first_name']}"),
        }
        parsed_files = []
        imported_keys = set()
        for path in paths:
            parsed = import_payroll_book(path)
            source_name = parsed.get("employee_name") or ""
            if source_name and normal_name(source_name) not in expected_names:
                raise ValueError(
                    f"{Path(path).name} gehört gemäss Excel zu «{source_name}» und nicht zum "
                    f"ausgewählten Mitarbeiter {employee['first_name']} {employee['last_name']}.")
            year = int(parsed["year"])
            for record in parsed["records"]:
                key = (year, int(record["month"]))
                if key in imported_keys:
                    raise ValueError(
                        f"Der Monat {MONTHS[key[1] - 1]} {year} ist in mehreren ausgewählten Dateien enthalten.")
                imported_keys.add(key)
            parsed_files.append((path, parsed))

        created = updated = 0
        imported_years = sorted({int(parsed["year"]) for _, parsed in parsed_files})
        for year in imported_years:
            if self.year.findData(year) < 0:
                self.year.addItem(str(year), year)
        for _, parsed in parsed_files:
            year = int(parsed["year"])
            existing = {record["month"]: record for record in self.db.payroll_records(employee["id"], year)}
            for record in parsed["records"]:
                previous = existing.get(record["month"])
                values = {**record, "employee_id": employee["id"], "year": year}
                self.db.save_payroll_record(values, previous.get("id") if previous else None)
                updated += int(previous is not None)
                created += int(previous is None)
        latest_year = max(imported_years)
        self.year.setCurrentIndex(self.year.findData(latest_year))
        self.refresh()
        QMessageBox.information(
            self, "Excel-Import abgeschlossen",
            f"{len(parsed_files)} Dateien mit {len(imported_keys)} Monatslöhnen wurden für "
            f"{employee['first_name']} {employee['last_name']} importiert.\n"
            f"Jahre: {', '.join(map(str, imported_years))}\n"
            f"{created} Monate neu angelegt, {updated} bestehende Monate aktualisiert.")

    @guarded
    def export_excel(self):
        employee = self.db.employee(self.person.currentData()) if self.person.currentData() else None
        if not employee:
            return
        year = int(self.year.currentData())
        folders = employee_year_folders(employee, year)
        name = f"Lohnbuch_{year}_{employee['last_name']}_{employee['first_name']}.xlsx"
        path = save_path(self, "Lohnbuch als Excel-Datei", name, "xlsx", "payroll_excel", folders)
        if path:
            result = export_payroll_book(path, employee, year, self.db.payroll_records(employee["id"], year),
                                         self.db.settings())
            QMessageBox.information(self, "Excel-Datei erstellt", "Das Lohnbuch wurde mit Formeln gespeichert.\n\n" + str(result))
