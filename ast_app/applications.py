"""Applicant dossiers and import from the AST apprenticeship web form."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox,
                               QCheckBox, QPlainTextEdit, QListWidget, QListWidgetItem, QFileDialog,
                               QMessageBox, QHeaderView)

from .widgets import Page, Table, button, combo, label, line, guarded, confirm


CATEGORIES = {
    "trial": "Schnupperlehre",
    "installer": "Elektroinstallateur/in EFZ",
    "assembly": "Montage-Elektriker/in EFZ",
}
STATUSES = {
    "new": "Neu", "review": "In Prüfung", "interview": "Vorstellungsgespräch",
    "trial": "Schnupperlehre", "offer": "Zusage", "rejected": "Absage", "hired": "Angestellt",
}
FILE_CATEGORIES = {"application": "Bewerbung", "cv": "Lebenslauf", "certificates": "Zeugnisse", "other": "Sonstiges"}
DEFAULT_IMPORT_FOLDER = r"\\100.109.95.19\ast-elektro.ch\Website_AST\private_applications"


def category_from_web(value):
    text = str(value or "").casefold()
    if "montage" in text:
        return "assembly"
    if "installateur" in text:
        return "installer"
    return "trial"


def safe_filename(value):
    name = Path(str(value)).name
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name).strip(" .")
    return name or "Dokument"


def sync_manifests(db, folder):
    root = Path(folder)
    if not root.is_dir():
        raise ValueError("Der Bewerbungsordner ist nicht erreichbar. Bitte Netzwerkverbindung und Ordner prüfen.")
    allowed_root = root.parent.resolve()
    created = updated = files_copied = 0
    for manifest_path in sorted(root.glob("*.json")):
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Die Bewerbungsdatei {manifest_path.name} ist ungültig: {exc}") from exc
        source_id = str(payload.get("id") or manifest_path.stem)
        existing = next((row for row in db.applicants() if row["source_id"] == source_id), None)
        values = {"source_id": source_id, "category": category_from_web(payload.get("application_for")),
                  "status": existing["status"] if existing else "new",
                  "first_name": payload.get("first_name", ""), "last_name": payload.get("last_name", ""),
                  "address": payload.get("address", ""), "postcode": payload.get("postcode", ""),
                  "city": payload.get("city", ""), "email": payload.get("email", ""),
                  "phone": payload.get("phone", ""),
                  "vocational_baccalaureate": str(payload.get("vocational_baccalaureate", "")).casefold() in ("1", "true", "ja", "yes"),
                  "message": payload.get("message", ""), "notes": existing["notes"] if existing else "",
                  "submitted_at": payload.get("submitted_at", "")}
        applicant_id = db.save_applicant(values, existing["id"] if existing else None)
        created += not bool(existing); updated += bool(existing)
        current_sources = {row["source_ref"] for row in db.applicant_files(applicant_id)}
        destination = db.path.parent / "applications" / str(applicant_id)
        destination.mkdir(parents=True, exist_ok=True)
        for item in payload.get("files", []):
            source_ref = str(item.get("stored_path", ""))
            if not source_ref or source_ref in current_sources:
                continue
            source = (manifest_path.parent / source_ref).resolve()
            if not source.is_relative_to(allowed_root) or not source.is_file():
                continue
            name = safe_filename(item.get("original_name") or source.name)
            target = destination / name
            counter = 2
            while target.exists():
                target = destination / f"{Path(name).stem}_{counter}{Path(name).suffix}"
                counter += 1
            shutil.copy2(source, target)
            db.save_applicant_file(applicant_id, item.get("category", "other"), name, target, source_ref)
            files_copied += 1
    return {"created": created, "updated": updated, "files": files_copied}


class ApplicantDialog(QDialog):
    def __init__(self, parent, db, row=None):
        super().__init__(parent)
        self.db, self.row, self.pending = db, row or {}, []
        self.setWindowTitle("Bewerbungsdossier" if row else "Bewerbung manuell erfassen")
        self.resize(800, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.addWidget(label(self.windowTitle(), "dialogTitle"))
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.fields = {}
        self.fields["category"] = combo([(title, key) for key, title in CATEGORIES.items()], self.row.get("category", "trial"))
        self.fields["status"] = combo([(title, key) for key, title in STATUSES.items()], self.row.get("status", "new"))
        for key, title in (("first_name", "Vorname *"), ("last_name", "Nachname *"),
                           ("address", "Strasse / Nr."), ("postcode", "PLZ"), ("city", "Ort"),
                           ("email", "E-Mail"), ("phone", "Telefon / Mobile")):
            self.fields[key] = line(self.row.get(key, ""))
        form.addRow("Bewerbung für", self.fields["category"])
        form.addRow("Status", self.fields["status"])
        for key, title in (("first_name", "Vorname *"), ("last_name", "Nachname *"),
                           ("address", "Strasse / Nr."), ("postcode", "PLZ"), ("city", "Ort"),
                           ("email", "E-Mail"), ("phone", "Telefon / Mobile")):
            form.addRow(title, self.fields[key])
        self.matura = QCheckBox("Berufsmatura parallel zur Lehre gewünscht")
        self.matura.setChecked(bool(self.row.get("vocational_baccalaureate", 0)))
        form.addRow("Zusatz", self.matura)
        self.message = QPlainTextEdit(self.row.get("message", "")); self.message.setMaximumHeight(95)
        self.notes = QPlainTextEdit(self.row.get("notes", "")); self.notes.setMaximumHeight(95)
        form.addRow("Nachricht", self.message); form.addRow("Interne Notizen", self.notes)
        layout.addLayout(form)
        layout.addWidget(label("Unterlagen", "sectionTitle"))
        self.files = QListWidget()
        self.files.setMinimumHeight(130)
        self.files.itemDoubleClicked.connect(lambda *_: self.open_file())
        layout.addWidget(self.files, 1)
        file_buttons = QHBoxLayout()
        file_buttons.addWidget(button("Dokument hinzufügen", self.add_file))
        file_buttons.addWidget(button("Öffnen", self.open_file))
        file_buttons.addWidget(button("Kopie speichern", self.save_copy))
        file_buttons.addStretch()
        layout.addLayout(file_buttons)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Dossier speichern")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.refresh_files()

    def refresh_files(self):
        self.files.clear()
        if self.row.get("id"):
            for record in self.db.applicant_files(self.row["id"]):
                item = QListWidgetItem(f"{FILE_CATEGORIES.get(record['category'], 'Dokument')} · {record['original_name']}")
                item.setData(Qt.ItemDataRole.UserRole, record["local_path"])
                self.files.addItem(item)
        for category, path in self.pending:
            item = QListWidgetItem(f"{FILE_CATEGORIES.get(category, 'Dokument')} · {path.name} · neu")
            item.setData(Qt.ItemDataRole.UserRole, str(path))
            self.files.addItem(item)

    def add_file(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Bewerbungsunterlagen auswählen", "",
                                                "Dokumente (*.pdf *.png *.jpg *.jpeg *.doc *.docx);;Alle Dateien (*)")
        if not paths:
            return
        category = "other"
        for path in paths:
            self.pending.append((category, Path(path)))
        self.refresh_files()

    def selected_path(self):
        item = self.files.currentItem()
        return Path(item.data(Qt.ItemDataRole.UserRole)) if item else None

    def open_file(self):
        path = self.selected_path()
        if path and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def save_copy(self):
        source = self.selected_path()
        if not source or not source.is_file():
            return
        target, _ = QFileDialog.getSaveFileName(self, "Dokument speichern", source.name)
        if target:
            shutil.copy2(source, target)

    @guarded
    def submit(self):
        values = {key: field.currentData() if key in ("category", "status") else field.text()
                  for key, field in self.fields.items()}
        values.update({"source_id": self.row.get("source_id", ""), "vocational_baccalaureate": self.matura.isChecked(),
                       "message": self.message.toPlainText(), "notes": self.notes.toPlainText(),
                       "submitted_at": self.row.get("submitted_at", "")})
        self.saved_id = self.db.save_applicant(values, self.row.get("id"))
        destination = self.db.path.parent / "applications" / str(self.saved_id)
        destination.mkdir(parents=True, exist_ok=True)
        for category, source in self.pending:
            if not source.is_file():
                continue
            name = safe_filename(source.name)
            target = destination / name
            counter = 2
            while target.exists():
                target = destination / f"{Path(name).stem}_{counter}{Path(name).suffix}"
                counter += 1
            shutil.copy2(source, target)
            self.db.save_applicant_file(self.saved_id, category, target.name, target, f"manual:{target.name}")
        self.accept()


class ApplicationsPage(Page):
    def __init__(self, db):
        super().__init__("Bewerbungen", "Jede Bewerbung als eigenes Dossier mit Status, Kontaktdaten und Unterlagen verwalten.")
        self.db, self.rows = db, []
        self.header.addWidget(button("Vom Webserver einlesen", self.sync, True))
        self.header.addWidget(button("Importordner", self.choose_folder))
        self.header.addWidget(button("+ Manuell erfassen", self.new))
        filters = QHBoxLayout()
        self.search = line(placeholder="Name, Ort, E-Mail oder Telefon suchen …")
        self.category = combo([("Alle Bewerbungsarten", ""), *[(title, key) for key, title in CATEGORIES.items()]])
        self.status = combo([("Alle Status", ""), *[(title, key) for key, title in STATUSES.items()]])
        filters.addWidget(self.search, 1); filters.addWidget(self.category); filters.addWidget(self.status)
        self.layout.addLayout(filters)
        self.table = Table(["Eingang", "Name", "Bewerbung für", "Status", "Ort", "Kontakt", "Dokumente"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.hint = label("Bitte eine Bewerbung auswählen.", "muted")
        actions.addWidget(self.hint, 1)
        self.open_button = button("Dossier öffnen", self.open, True)
        self.delete_button = button("Löschen", self.remove)
        actions.addWidget(self.open_button); actions.addWidget(self.delete_button)
        self.layout.addLayout(actions)
        self.search.textChanged.connect(self.filter_rows)
        self.category.currentIndexChanged.connect(self.filter_rows)
        self.status.currentIndexChanged.connect(self.filter_rows)
        self.table.itemSelectionChanged.connect(self.selection)
        self.table.cellDoubleClicked.connect(self.open)

    def refresh(self):
        self.all_rows = self.db.applicants()
        self.filter_rows()

    def filter_rows(self, *_):
        query = self.search.text().strip().casefold()
        category = self.category.currentData(); status = self.status.currentData()
        self.rows = [row for row in getattr(self, "all_rows", [])
                     if (not category or row["category"] == category)
                     and (not status or row["status"] == status)
                     and (not query or query in " ".join(str(row.get(key, "")) for key in
                                                         ("first_name", "last_name", "city", "email", "phone")).casefold())]
        self.table.populate([[row["submitted_at"][:10], f"{row['first_name']} {row['last_name']}",
                              CATEGORIES[row["category"]], STATUSES[row["status"]], row["city"],
                              " · ".join(filter(None, [row["email"], row["phone"]])),
                              len(self.db.applicant_files(row["id"]))] for row in self.rows],
                            [row["id"] for row in self.rows], [6])
        self.selection()

    def selected(self):
        key = self.table.selected_id()
        return next((row for row in self.rows if row["id"] == key), None)

    def selection(self):
        row = self.selected(); enabled = bool(row)
        self.open_button.setEnabled(enabled); self.delete_button.setEnabled(enabled)
        self.hint.setText(f"{row['first_name']} {row['last_name']} · {STATUSES[row['status']]}" if row else "Bitte eine Bewerbung auswählen.")

    def new(self):
        if ApplicantDialog(self, self.db).exec():
            self.refresh()

    def open(self, *_):
        row = self.selected()
        if row and ApplicantDialog(self, self.db, row).exec():
            self.refresh()

    def choose_folder(self):
        current = self.db.settings().get("applications_import_folder", DEFAULT_IMPORT_FOLDER)
        folder = QFileDialog.getExistingDirectory(self, "Ordner mit Website-Bewerbungen", current)
        if folder:
            self.db.save_settings({"applications_import_folder": folder})

    @guarded
    def sync(self):
        folder = self.db.settings().get("applications_import_folder", DEFAULT_IMPORT_FOLDER)
        result = sync_manifests(self.db, folder)
        self.refresh()
        QMessageBox.information(self, "Bewerbungen eingelesen",
                                f"Neu: {result['created']}\nAktualisiert: {result['updated']}\nDokumente kopiert: {result['files']}")

    @guarded
    def remove(self):
        row = self.selected()
        if row and confirm(self, "Bewerbung löschen", "Soll dieses Bewerbungsdossier wirklich gelöscht werden?\nDie lokale Dokumentkopie bleibt als Datei erhalten."):
            self.db.delete("applicants", row["id"])
            self.refresh()
