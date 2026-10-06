"""Headless Qt integration tests, using real widgets and clicks."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QLocale, QCoreApplication, QEvent, QDate
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (QApplication, QMessageBox, QDialog, QLineEdit, QPlainTextEdit,
                               QAbstractSpinBox)

from ast_app.database import Database
from ast_app.demo import seed_demo
from ast_app.window import MainWindow
from ast_app.experience import timesheet_filename
from ast_app.dialogs import (EmployeeDialog, CustomerDialog, InvoiceDialog, EntryDialog, PeriodDialog,
                             SalaryDialog, PaymentDialog, TimeRecordDialog, BulkTimeDialog, ManualReminderDialog)
from ast_app.theme import apply_theme
from ast_app.documents import salary_pdf
from ast_app.pages import PdfPreview
from ast_app.widgets import Table, confirm, numeric, day
from ast_app.export_paths import setting_key
from ast_app.references import ReferenceDialog
from ast_app.applications import ApplicationsPage, ApplicantStatusDialog

APP = QApplication.instance() or QApplication([])
if os.name == "nt" and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    # Windows' offscreen plugin does not enumerate the system font registry.
    for font_name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font_name
        if font_path.exists(): QFontDatabase.addApplicationFont(str(font_path))
APP.setStyle("Fusion")
apply_theme(APP)
QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Switzerland))


class UiTests(unittest.TestCase):
    def test_numbers_use_direct_entry_and_dates_offer_a_clear_calendar(self):
        amount = numeric(8.75, " h")
        self.assertEqual(amount.buttonSymbols(), QAbstractSpinBox.ButtonSymbols.NoButtons)
        self.assertFalse(amount.keyboardTracking())
        self.assertIn("Tastatur", amount.toolTip())
        date_field = day("2026-10-06")
        self.assertTrue(date_field.calendarPopup())
        self.assertTrue(date_field.calendarWidget().isGridVisible())
        self.assertEqual(date_field.calendarWidget().firstDayOfWeek(), Qt.DayOfWeek.Monday)
        self.assertIn("TT.MM.JJJJ", date_field.toolTip())

    def test_timesheet_export_filename_uses_year_last_and_first_name(self):
        employee = {"last_name": "von Muster", "first_name": "Anna Maria"}
        self.assertEqual(timesheet_filename(employee, 2027),
                         "Stundennachweis_2027_von_Muster_Anna_Maria.xlsm")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp.name) / "ui.sqlite3")
        seed_demo(self.db)
        self.messages = []
        self.patchers = [patch.object(QMessageBox, name, side_effect=lambda *a: self.messages.append(a[2])) for name in ("warning", "critical")]
        for p in self.patchers: p.start()

    def tearDown(self):
        for w in list(APP.topLevelWidgets()):
            w.close()
            w.deleteLater()
        APP.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        for p in self.patchers: p.stop()
        self.db.close()
        self.temp.cleanup()
        self.assertEqual(self.messages, [])

    def test_navigation_and_all_pages(self):
        window = MainWindow(self.db, True)
        window.show()
        APP.processEvents()
        self.assertFalse(window.watermark._logo.isNull())
        self.assertFalse(window.watermark.isVisible())
        self.assertEqual(window.watermark.geometry(), window.stack.geometry())
        self.assertTrue(window.watermark.testAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents))
        for index in range(8):
            QTest.mouseClick(window.buttons[index], Qt.MouseButton.LeftButton)
            for _ in range(4): APP.processEvents()
            self.assertEqual(window.stack.currentIndex(), index)
            if os.environ.get("AST_QA_DIR"):
                folder = Path(os.environ["AST_QA_DIR"])
                folder.mkdir(parents=True, exist_ok=True)

                window.grab().save(str(folder / f"page-{index}.png"))
        self.assertEqual(window.buttons[5].objectName(), "navSubButton")
        self.assertGreater(window.pages[5].table.rowCount(), 0)
        self.assertGreater(window.pages[6].table.rowCount(), 0)
        self.assertGreater(window.pages[7].table.rowCount(), 0)
        self.assertTrue(window.pages[7].sync_timer.isActive())
        self.assertEqual(window.pages[7].sync_timer.interval(), 5 * 60 * 1000)
        settings = window.pages[4]
        settings.background_logo.setChecked(True)
        APP.processEvents()
        self.assertTrue(window.watermark.isVisible())
        self.assertEqual(self.db.settings()["background_logo_enabled"], "1")
        settings.background_logo.setChecked(False)
        APP.processEvents()
        self.assertFalse(window.watermark.isVisible())
        reminders = window.pages[5]
        reminders.tabs.setCurrentIndex(1)
        reminders.template_editors[1].clear()
        reminders.placeholder_picker.setCurrentIndex(reminders.placeholder_picker.findData("{rechnungsnummer}"))
        reminders.insert_placeholder()
        self.assertEqual(reminders.template_editors[1].toPlainText(), "{rechnungsnummer}")
        if os.environ.get("AST_QA_DIR"):
            reminders.grab().save(str(Path(os.environ["AST_QA_DIR"]) / "mahntexte-variablen.png"))
        window.navigate(2)
        page = window.pages[2]
        self.assertGreater(page.table.rowCount(), 0)
        page.table.selectRow(0)
        self.assertTrue(page.open_btn.isEnabled())
        page.open_person()
        self.assertEqual(page.stack.currentIndex(), 1)
        self.assertIsNotNone(page.workspace.employee)
        displayed_hours = {page.workspace.table.item(row, 2).text()
                           for row in range(page.workspace.table.rowCount())}
        self.assertIn("8.75 h", displayed_hours)
        self.assertIn("8.25 h", displayed_hours)
        if os.environ.get("AST_QA_DIR"):
            page.grab().save(str(Path(os.environ["AST_QA_DIR"]) / "stundennachweis-detail.png"))
        window.navigate(1)
        page = window.pages[1]
        page.search.setText("2026-nothing")
        self.assertEqual(page.table.rowCount(), 0)
        page.search.clear()
        self.assertEqual(page.table.rowCount(), 4)

    def test_every_export_destination_can_be_configured_separately(self):
        window = MainWindow(self.db, True)
        settings = window.pages[4]
        self.assertIn("debtors_pdf", settings.export_directory_fields)
        self.assertIn("applications_documents", settings.export_directory_fields)
        folder = str(Path(self.temp.name) / "exports")
        Path(folder).mkdir()
        with patch("ast_app.pages.QFileDialog.getExistingDirectory", return_value=folder):
            settings.choose_export_directory("salary_pdf")
        self.assertEqual(self.db.settings()[setting_key("salary_pdf")], folder)
        self.assertEqual(settings.export_directory_fields["salary_pdf"].text(), folder)
        self.assertEqual(self.db.settings().get(setting_key("debtors_pdf"), ""), "")

    def test_applicant_status_is_read_only_and_saves_review_tag(self):
        applicant = self.db.applicants()[0]
        dialog = ApplicantStatusDialog(None, self.db, applicant)
        dialog.show()
        APP.processEvents()
        self.assertEqual(dialog.findChildren(QLineEdit), [])
        self.assertEqual(dialog.findChildren(QPlainTextEdit), [dialog.notes])
        self.assertEqual(set(dialog.review_buttons), {"unsuitable", "possible", "suitable"})
        dialog.set_suitability("possible")
        self.assertEqual(self.db.applicant(applicant["id"])["suitability"], "possible")
        self.assertEqual(dialog.badge.text(), "Eventuell")
        dialog.notes.setPlainText("Telefonisch am 5. Oktober kontaktiert.")
        QTest.mouseClick(dialog.save_notes_button, Qt.MouseButton.LeftButton)
        self.assertEqual(self.db.applicant(applicant["id"])["notes"],
                         "Telefonisch am 5. Oktober kontaktiert.")
        self.db.set_applicant_suitability(applicant["id"], "unsuitable", True)
        page = ApplicationsPage(self.db); page.refresh(); page.table.selectRow(0)
        APP.processEvents()
        self.assertEqual(page.table.item(0, 0).background().color().name(), "#fce3e3")
        self.assertIn("#f2bfc2", page.table.styleSheet())
        if os.environ.get("AST_QA_DIR"):
            folder = Path(os.environ["AST_QA_DIR"]); folder.mkdir(parents=True, exist_ok=True)
            dialog.grab().save(str(folder / "bewerber-status.png"))
            page.resize(1060, 680); page.show(); APP.processEvents()
            page.grab().save(str(folder / "bewerbungen-rot.png"))

    def test_real_form_save_click_and_reopen(self):
        d = CustomerDialog(None, self.db)
        d.fields["name"].setText("GUI Test AG")
        d.fields["city"].setText("Zürich")
        d.show(); APP.processEvents()
        QTest.mouseClick(d.save_button, Qt.MouseButton.LeftButton)
        self.assertEqual(d.result(), QDialog.DialogCode.Accepted)
        invoice = InvoiceDialog(None, self.db)
        invoice.fields["number"].setText("GUI-001")
        invoice.fields["customer_id"].setCurrentIndex(invoice.fields["customer_id"].findData(d.saved_id))
        invoice.fields["amount"].setValue(123.45)
        invoice.show(); APP.processEvents()
        QTest.mouseClick(invoice.save_button, Qt.MouseButton.LeftButton)
        self.assertEqual(invoice.result(), QDialog.DialogCode.Accepted)
        saved = next(r for r in self.db.invoices() if r["id"] == invoice.saved_id)
        payment = PaymentDialog(None, self.db, saved)
        payment.fields["amount"].setValue(23.45)
        payment.show(); APP.processEvents()
        QTest.mouseClick(payment.save_button, Qt.MouseButton.LeftButton)
        saved = next(r for r in self.db.invoices() if r["id"] == invoice.saved_id)
        self.assertEqual(saved["open"], 10000)

    def test_debtor_columns_quarter_note_and_saved_layout(self):
        window = MainWindow(self.db, True)
        page = window.pages[1]
        window.navigate(1)
        page.refresh()
        headers = [page.table.horizontalHeaderItem(i).text() for i in range(page.table.columnCount())]
        self.assertEqual(headers[-1], "Bemerkung")
        self.assertIn("Quartal", headers)
        quarter_column = headers.index("Quartal")
        note_column = headers.index("Bemerkung")
        self.assertRegex(page.table.item(0, quarter_column).text(), r"^Q[1-4] / \d{4}$")
        self.assertEqual(page.table.item(0, note_column).text(), "Demodaten")
        window.show(); APP.processEvents()
        if os.environ.get("AST_QA_DIR"):
            folder = Path(os.environ["AST_QA_DIR"])
            folder.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(folder / "debitoren-spalten.png"))

        page.set_column_visible("status", False)
        header = page.table.horizontalHeader()
        header.moveSection(header.visualIndex(note_column), 0)
        saved = self.db.settings()
        self.assertNotIn("status", json.loads(saved["debtor_columns_visible"]))
        self.assertEqual(json.loads(saved["debtor_columns_order"])[0], "note")

        reopened = MainWindow(self.db, True).pages[1]
        self.assertTrue(reopened.table.isColumnHidden(headers.index("Status")))
        self.assertEqual(reopened.table.horizontalHeader().visualIndex(note_column), 0)

    def test_tables_centered_and_sidebar_collapse_persists(self):
        window = MainWindow(self.db, True)
        window.show(); window.navigate(1); APP.processEvents()
        tables = window.findChildren(Table)
        self.assertGreater(len(tables), 5)
        for table in tables:
            self.assertTrue(table.horizontalHeader().defaultAlignment() & Qt.AlignmentFlag.AlignHCenter)
        first_item = window.pages[1].table.item(0, 0)
        self.assertTrue(first_item.textAlignment() & Qt.AlignmentFlag.AlignHCenter)

        self.assertEqual(window.sidebar.width(), 250)
        QTest.mouseClick(window.sidebar_toggle, Qt.MouseButton.LeftButton)
        APP.processEvents()
        self.assertEqual(window.sidebar.width(), 78)
        self.assertEqual(window.buttons[1].text(), "")
        self.assertEqual(window.buttons[1].toolTip(), "Debitoren")
        self.assertEqual(self.db.settings()["sidebar_collapsed"], "1")
        if os.environ.get("AST_QA_DIR"):
            folder = Path(os.environ["AST_QA_DIR"])
            folder.mkdir(parents=True, exist_ok=True)
            window.grab().save(str(folder / "navigation-eingeklappt.png"))

        reopened = MainWindow(self.db, True)
        self.assertEqual(reopened.sidebar.width(), 78)
        QTest.mouseClick(reopened.sidebar_toggle, Qt.MouseButton.LeftButton)
        self.assertEqual(reopened.sidebar.width(), 250)
        self.assertEqual(reopened.buttons[1].text(), "Debitoren")
        self.assertEqual(self.db.settings()["sidebar_collapsed"], "0")

    def test_table_columns_rows_and_visibility_persist(self):
        window = MainWindow(self.db, True)
        window.show(); window.navigate(7); APP.processEvents()
        table = window.pages[7].table
        self.assertGreater(table.columnCount(), 2)
        self.assertGreater(table.rowCount(), 0)
        table._set_column_visible(4, False)
        table._set_row_visible(0, False)
        last = table.columnCount() - 1
        table.horizontalHeader().moveSection(table.horizontalHeader().visualIndex(last), 0)
        APP.processEvents()

        reopened = MainWindow(self.db, True)
        reopened.navigate(7); APP.processEvents()
        restored = reopened.pages[7].table
        self.assertTrue(restored.isColumnHidden(4))
        self.assertTrue(restored.isRowHidden(0))
        self.assertEqual(restored.horizontalHeader().visualIndex(last), 0)
        restored._reset_columns(); restored._reset_rows()

    def test_reference_is_generated_only_from_answered_questions(self):
        dialog = ReferenceDialog(None, self.db)
        self.assertTrue(dialog.text.isReadOnly())
        dialog.tasks.setPlainText("Elektroinstallationen\nServicearbeiten")
        active = dialog.active_question_ids()
        self.assertTrue(active)
        self.assertTrue(all(dialog.ratings[key].currentData() is None for key in active))
        for key in active:
            dialog.ratings[key].setCurrentIndex(dialog.ratings[key].findData(4))
        dialog.generate()
        self.assertIn("Gesamtleistung", dialog.text.toPlainText())
        self.assertIn("Verhalten gegenüber Vorgesetzten", dialog.text.toPlainText())

    def test_background_application_sync_returns_to_ui_thread(self):
        self.db.save_settings({"applications_ftp_password": "encrypted-test"})
        page = ApplicationsPage(self.db)
        page.show(); APP.processEvents()
        result = {"created": 0, "updated": 0, "files": 0}
        with patch("ast_app.applications.unprotect_secret", return_value="secret"), \
             patch("ast_app.applications.sync_ftp", return_value=result):
            page._start_sync(False)
            for _ in range(100):
                APP.processEvents()
                if page.sync_thread is None:
                    break
                QTest.qWait(10)
        self.assertIsNone(page.sync_thread)
        self.assertIn("Automatischer Serverabgleich aktiv", page.server_status.text())

    def test_confirmation_supports_separate_title_and_message(self):
        with patch("ast_app.widgets.QMessageBox.question", return_value=QMessageBox.StandardButton.Yes) as question:
            self.assertTrue(confirm(None, "Zeugnis löschen", "Soll dieses Zeugnis wirklich gelöscht werden?"))
        self.assertEqual(question.call_args.args[1:3], ("Zeugnis löschen", "Soll dieses Zeugnis wirklich gelöscht werden?"))

    def test_selected_reference_can_be_deleted(self):
        window = MainWindow(self.db, True)
        page = window.pages[6]
        page.refresh()
        before = len(self.db.references())
        self.assertGreater(before, 0)
        page.table.selectRow(0)
        with patch("ast_app.references.confirm", return_value=True):
            page.remove()
        self.assertEqual(len(self.db.references()), before - 1)

    def test_time_and_salary_dialogs(self):
        e = self.db.employees()[0]
        period = self.db.periods(e["id"])[-1]
        d = EntryDialog(None, self.db, period)
        d.fields["hours"].setValue(1.50)
        d.fields["kind"].setCurrentIndex(d.fields["kind"].findData("overtime"))
        d.submit()
        self.assertEqual(d.result(), QDialog.DialogCode.Accepted)
        self.assertTrue(any(r["hours"] == 150 for r in self.db.entries(period["id"])))
        salary = SalaryDialog(None, self.db)
        salary.pdf["1"].setValue(72000)
        salary.pdf["9"].setValue(4800)
        salary.pdf["10-1"].setValue(3600)
        salary.show(); APP.processEvents()
        if os.environ.get("AST_QA_DIR"):
            salary.grab().save(str(Path(os.environ["AST_QA_DIR"]) / "salary-dialog.png"))
        salary.submit()
        self.assertEqual(salary.result(), QDialog.DialogCode.Accepted)
        row = self.db.salaries()[0]
        self.assertEqual(row["fields"]["11"], "63600")
        reopened = SalaryDialog(None, self.db, row)
        self.assertEqual(reopened.pdf["1"].value(), 72000)
        pdf = Path(self.temp.name) / "salary.pdf"
        salary_pdf(row["fields"], pdf)
        preview = PdfPreview(None, pdf)
        preview.show(); APP.processEvents()
        self.assertEqual(preview.document.pageCount(), 1)
        preview.document.close()

    def test_simple_daily_time_dialog(self):
        employee = self.db.employees()[0]
        dialog = TimeRecordDialog(None, self.db, employee)
        dialog.fields["day"].setDate(QDate(2026, 1, 5))
        dialog.fields["note"].setText("Baustelle")
        dialog.show(); APP.processEvents()
        if os.environ.get("AST_QA_DIR"):
            dialog.grab().save(str(Path(os.environ["AST_QA_DIR"]) / "arbeitstag-dialog.png"))
        dialog.submit()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        saved = next(row for row in self.db.time_records(employee["id"]) if row["note"] == "Baustelle")
        self.assertEqual(saved["worked_minutes"], 525)
        self.assertIsNone(saved["start_1"])

    def test_bulk_time_dialog_uses_shorter_friday(self):
        employee = self.db.employees()[0]
        dialog = BulkTimeDialog(None, self.db, employee, 2026)
        dialog.fields["start_day"].setDate(QDate(2026, 1, 5))
        dialog.fields["end_day"].setDate(QDate(2026, 1, 9))
        dialog.submit()
        records = {row["day"]: row["worked_minutes"] for row in self.db.time_records(employee["id"], 2026)}
        self.assertEqual([records[f"2026-01-0{day}"] for day in range(5, 9)], [525, 525, 525, 525])
        self.assertEqual(records["2026-01-09"], 495)

    def test_manual_reminder_dialog_builds_standalone_claim(self):
        dialog = ManualReminderDialog(None, self.db)
        customer = self.db.customers()[0]
        dialog.customer_picker.setCurrentIndex(dialog.customer_picker.findData(customer["id"]))
        dialog.fields["number"].setText("MAN-2026-01")
        dialog.fields["open"].setValue(245.75)
        dialog.fields["level"].setCurrentIndex(dialog.fields["level"].findData(2))
        dialog.show(); APP.processEvents()
        if os.environ.get("AST_QA_DIR"):
            folder = Path(os.environ["AST_QA_DIR"])
            folder.mkdir(parents=True, exist_ok=True)
            dialog.grab().save(str(folder / "manuelle-mahnung.png"))
        dialog.submit()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(dialog.invoice["customer"], customer["name"])
        self.assertEqual(dialog.invoice["open"], 24575)
        self.assertEqual(dialog.level, 2)

    def test_wizard_advances_and_saves_from_review(self):
        salary = SalaryDialog(None, self.db)
        salary.pdf["1"].setValue(12000)
        salary.show(); APP.processEvents()
        self.assertFalse(salary.save_button.isVisible())
        for expected in (1, 2, 3):
            QTest.mouseClick(salary.next_button, Qt.MouseButton.LeftButton)
            APP.processEvents()
            self.assertEqual(salary.tabs.currentIndex(), expected)
        self.assertTrue(salary.save_button.isVisible())
        self.assertIn("12", salary.review_label.text())
        QTest.mouseClick(salary.save_button, Qt.MouseButton.LeftButton)
        self.assertEqual(salary.result(), QDialog.DialogCode.Accepted)

    def test_simplified_person_form_and_company_survive_window_close(self):
        before = self.db.settings()["company"]
        window = MainWindow(self.db, True)
        window.show(); APP.processEvents()
        window.close()
        self.assertEqual(self.db.settings()["company"], before)
        person = EmployeeDialog(None, self.db, kind="apprentice")
        person.fields["first_name"].setText("Test")
        person.fields["last_name"].setText("Person")
        person.submit()
        self.assertEqual(person.result(), QDialog.DialogCode.Accepted)
        saved = self.db.employee(person.saved_id)
        self.assertTrue(saved["code"].startswith("AST-"))
        period = PeriodDialog(None, self.db, saved)
        period.submit()
        self.assertEqual(period.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(self.db.periods(saved["id"])[0]["start"], saved["hired"])
        window = MainWindow(self.db, True)
        window.navigate(4)
        settings = window.pages[4]
        settings.company_fields["company"].setText("Neu gespeichert AG")
        window.navigate(0)
        self.assertEqual(self.db.settings()["company"], "Neu gespeichert AG")

    def test_update_creates_backup_before_install(self):
        from ast_app.update_ui import UpdateDialog
        from ast_app.updates import Release
        dialog = UpdateDialog(None, Release("9.0.0", "Test", "", "", 2, "a" * 64), self.db)
        with patch("ast_app.update_ui.start_installer") as installer, patch.object(APP, "quit"):
            dialog.install_ready(Path(self.temp.name) / "verified-setup.exe")
            self.assertEqual(installer.call_count, 1)
            backups = list((self.db.path.parent / "backups").glob("vor-update-*.sqlite3"))
            self.assertEqual(len(backups), 1)
            check = Database(backups[0])
            self.assertEqual(len(check.employees()), len(self.db.employees()))
            check.close()


if __name__ == "__main__": unittest.main()
