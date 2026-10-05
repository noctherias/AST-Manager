"""Entry point: python main.py [--demo] [--data-dir PATH]."""
from __future__ import annotations

import argparse
from datetime import date
import logging
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description="AST Verwaltung")
    parser.add_argument("--demo", action="store_true", help="Separate Demo-Datenbank mit fiktiven Beispielen")
    parser.add_argument("--data-dir", type=Path, help="Abweichender Speicherordner")
    parser.add_argument("--smoke-test", action="store_true", help="Start, Datenbank und alle Seiten prüfen, dann beenden")
    args = parser.parse_args()
    from PySide6.QtCore import QLocale, QLockFile
    from PySide6.QtWidgets import QApplication, QMessageBox
    from ast_app.database import Database
    from ast_app.backups import run_automatic_backups
    from ast_app.demo import seed_demo
    from ast_app.theme import apply_theme
    from ast_app.window import MainWindow

    root = args.data_dir or Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "AST-Erfassungstool"
    root.mkdir(parents=True, exist_ok=True)
    filename = "ast-demo.sqlite3" if args.demo else "ast.sqlite3"
    logging.basicConfig(filename=root / "ast.log", level=logging.INFO, encoding="utf-8",
                        format="%(asctime)s %(levelname)s %(message)s")
    QLocale.setDefault(QLocale(QLocale.Language.German, QLocale.Country.Switzerland))
    app = QApplication(sys.argv[:1])
    app.setApplicationName("AST Verwaltung")
    app.setStyle("Fusion")
    apply_theme(app)
    lock = QLockFile(str(root / (filename + ".lock")))
    lock.setStaleLockTime(0)
    if not lock.tryLock(100):
        QMessageBox.information(None, "AST ist bereits geöffnet", "Diese Datenbank ist bereits in einem anderen AST-Fenster geöffnet.")
        return 1
    db = None
    try:
        db = Database(root / filename)
        if args.demo:
            seed_demo(db)
        settings = db.settings()
        run_automatic_backups(db, root / "backups",
                              "" if args.demo else settings.get("backup_directory", ""),
                              settings.get("backup_retention_days", "30"))

        def exception_hook(kind, value, trace):
            logging.error("Unhandled exception", exc_info=(kind, value, trace))
            QMessageBox.critical(None, "AST · Fehler", f"Die Aktion konnte nicht abgeschlossen werden.\n{value}\nDetails stehen in ast.log im Datenordner.")

        sys.excepthook = exception_hook
        window = MainWindow(db, args.demo)
        if args.smoke_test:
            window.show()
            for index in range(len(window.pages)):
                window.navigate(index)
                app.processEvents()
            from ast_app.documents import salary_pdf, report_pdf
            from ast_app.timesheet_excel import export_timesheet
            from ast_app.excel_import import import_timesheet
            salary_pdf({"A": "/Ja", "B": "/Off", "HName": "AST Starttest", "1": "1000"}, root / "smoke-lohnausweis.pdf")
            report_pdf(root / "smoke-report.pdf", "AST Starttest", "Test", ["Test", "Wert"], [["PDF", "OK"]], "Test erfolgreich")
            employee = db.employees()[0]
            export_timesheet(root / "smoke-stundennachweis.xlsm", employee, date.today().year,
                             db.time_records(employee["id"], date.today().year), db.settings().get("company", ""))
            import_timesheet(db, root / "smoke-stundennachweis.xlsm", employee["id"], overwrite=True)
            (root / "smoke-test-ok.txt").write_text("Alle acht Bereiche erfolgreich geladen.\n", encoding="utf-8")
            window.close()
            return 0
        window.show()
        window.updates.start()
        return app.exec()
    except Exception as exc:
        logging.exception("Application startup failed")
        QMessageBox.critical(None, "AST konnte nicht starten", str(exc))
        return 1
    finally:
        if db:
            db.close()
        lock.unlock()


if __name__ == "__main__":
    raise SystemExit(main())
