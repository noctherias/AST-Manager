"""Headless Qt integration tests, using real widgets and clicks."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PySide6.QtCore import Qt, QLocale, QCoreApplication, QEvent
from PySide6.QtGui import QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox, QDialog

from ast_app.database import Database
from ast_app.demo import seed_demo
from ast_app.window import MainWindow
from ast_app.dialogs import EmployeeDialog, CustomerDialog, InvoiceDialog, EntryDialog, PeriodDialog, SalaryDialog, PaymentDialog
from ast_app.theme import STYLE
from ast_app.documents import salary_pdf
from ast_app.pages import PdfPreview

APP = QApplication.instance() or QApplication([])
if os.name == "nt" and os.environ.get("QT_QPA_PLATFORM") == "offscreen":
    # Windows' offscreen plugin does not enumerate the system font registry.
    for font_name in ("segoeui.ttf", "segoeuib.ttf", "seguisb.ttf"):
        font_path = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / font_name
        if font_path.exists(): QFontDatabase.addApplicationFont(str(font_path))
APP.setStyle("Fusion")
APP.setStyleSheet(STYLE)
QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Switzerland))


class UiTests(unittest.TestCase):
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
        for index in range(5):
            QTest.mouseClick(window.buttons[index], Qt.MouseButton.LeftButton)
            for _ in range(4): APP.processEvents()
            self.assertEqual(window.stack.currentIndex(), index)
            if os.environ.get("AST_QA_DIR"):
                folder = Path(os.environ["AST_QA_DIR"])
                folder.mkdir(parents=True, exist_ok=True)
                window.grab().save(str(folder / f"page-{index}.png"))
        window.navigate(2)
        page = window.pages[2]
        self.assertGreater(page.table.rowCount(), 0)
        page.table.selectRow(0)
        self.assertTrue(page.open_btn.isEnabled())
        page.open_person()
        self.assertEqual(page.stack.currentIndex(), 1)
        self.assertIsNotNone(page.workspace.current_balance)
        window.navigate(1)
        page = window.pages[1]
        page.search.setText("2026-nothing")
        self.assertEqual(page.table.rowCount(), 0)
        page.search.clear()
        self.assertEqual(page.table.rowCount(), 4)

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
