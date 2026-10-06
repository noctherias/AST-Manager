from __future__ import annotations

import os
import re
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
    ("references_work_pdf", "Arbeitszeugnisse", "Fertige Arbeitszeugnisse als PDF"),
    ("references_interim_pdf", "Zwischenzeugnisse", "Fertige Zwischenzeugnisse als PDF"),
    ("references_apprentice_pdf", "Lehrzeugnisse", "Fertige Lehrzeugnisse als PDF"),
    ("applications_documents", "Bewerbungsunterlagen", "Manuell gespeicherte Dokumentkopien"),
    ("backup_manual", "Manuelle Datensicherungen", "Manuell erstellte AST-Sicherungen"),
)

DEFAULT_EXPORT_ROOT = Path(r"S:\Neue Umgebung\07_IT_Infrastruktur\Software_Installer\SQLITE_AST_Verwaltung")
DEFAULT_EXPORT_FOLDERS = {
    "debtors_pdf": "Debitoren",
    "debtors_csv": "Debitoren",
    "reminders_pdf": "Mahnungen",
    "timesheets_excel": "Stundennachweise",
    "timesheets_pdf": "Stundennachweise",
    "timesheets_csv": "Stundennachweise",
    "salary_pdf": "Lohnausweise",
    "references_work_pdf": "Arbeitszeugnisse",
    "references_interim_pdf": "Zwischenzeugnisse",
    "references_apprentice_pdf": "Lehrzeugnisse",
    "applications_documents": "Bewerbungen",
    "backup_manual": "Datensicherungen",
}


def setting_key(export_key: str) -> str:
    return f"export_directory_{export_key}"


def default_directory(export_key: str = "") -> Path:
    if os.name == "nt" and export_key in DEFAULT_EXPORT_FOLDERS:
        server_folder = DEFAULT_EXPORT_ROOT / DEFAULT_EXPORT_FOLDERS[export_key]
        if server_folder.is_dir():
            return server_folder
    documents = Path.home() / "Documents"
    return documents if documents.exists() else Path.home()


def configured_directory(db, export_key: str) -> Path:
    value = str(db.settings().get(setting_key(export_key), "") or "").strip() if db else ""
    if not value and export_key.startswith("references_") and db:
        # Existing installations used one common setting for all certificates.
        value = str(db.settings().get(setting_key("references_pdf"), "") or "").strip()
    return Path(value) if value else default_directory(export_key)


def safe_folder_name(value) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "").strip())
    name = re.sub(r"[\s_]+", "_", name).strip(" ._")
    return name or "Unbekannt"


def employee_year_folders(employee, year) -> tuple[str, str]:
    employee_name = f"{employee.get('last_name', '')}_{employee.get('first_name', '')}"
    return safe_folder_name(employee_name), safe_folder_name(year)


def initial_path(parent, filename: str, export_key: str, subfolders=()) -> str:
    db = getattr(parent, "db", None)
    folder = configured_directory(db, export_key)
    if subfolders:
        folder = folder.joinpath(*(safe_folder_name(part) for part in subfolders))
        folder.mkdir(parents=True, exist_ok=True)
    return str(folder / filename)


def choose_export_file(parent, title: str, filename: str, extension: str, export_key: str,
                       subfolders=()) -> str:
    path, _ = QFileDialog.getSaveFileName(
        parent,
        title,
        initial_path(parent, filename, export_key, subfolders),
        f"{extension.upper()} (*.{extension})",
    )
    if path and not path.lower().endswith("." + extension.lower()):
        path += "." + extension
    return path
