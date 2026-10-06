from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import QFileDialog


# One independently configurable destination for every kind of file the program
# creates.  The stable keys are stored in the settings table.
EXPORT_DESTINATIONS = (
    ("debtors_pdf", "Debitoren · PDF", "PDF-Listen der Debitoren"),
    ("debtors_csv", "Debitoren · CSV", "CSV-Listen zur Weiterverarbeitung"),
    ("reminders_pdf", "Mahnungen", "Zahlungserinnerungen und Mahnbriefe"),
    ("timesheets_excel", "Stundennachweise · Excel", "Ausgefüllte Excel-Vorlagen"),
    ("timesheets_pdf", "Stundennachweise · PDF", "PDF-Auswertungen der Arbeitszeiten"),
    ("timesheets_csv", "Stundennachweise · CSV", "CSV-Auswertungen der Arbeitszeiten"),
    ("salary_pdf", "Lohnausweise", "Ausgefüllte Lohnausweise als PDF"),
    ("references_pdf", "Arbeits- und Lehrzeugnisse", "Fertige Zeugnisse als PDF"),
    ("applications_documents", "Bewerbungsunterlagen", "Manuell gespeicherte Dokumentkopien"),
    ("backup_manual", "Manuelle Datensicherungen", "Manuell erstellte AST-Sicherungen"),
)


def setting_key(export_key: str) -> str:
    return f"export_directory_{export_key}"


def default_directory() -> Path:
    documents = Path.home() / "Documents"
    return documents if documents.exists() else Path.home()


def configured_directory(db, export_key: str) -> Path:
    value = str(db.settings().get(setting_key(export_key), "") or "").strip() if db else ""
    return Path(value) if value else default_directory()


def initial_path(parent, filename: str, export_key: str) -> str:
    db = getattr(parent, "db", None)
    return str(configured_directory(db, export_key) / filename)


def choose_export_file(parent, title: str, filename: str, extension: str, export_key: str) -> str:
    path, _ = QFileDialog.getSaveFileName(
        parent,
        title,
        initial_path(parent, filename, export_key),
        f"{extension.upper()} (*.{extension})",
    )
    if path and not path.lower().endswith("." + extension.lower()):
        path += "." + extension
    return path
