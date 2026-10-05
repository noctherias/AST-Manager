"""Applicant dossiers and import from the AST apprenticeship web form."""
from __future__ import annotations

import json
import io
import ftplib
import logging
from datetime import datetime
from pathlib import Path
import posixpath
import re
import shutil
import ssl

from PySide6.QtCore import Qt, QUrl, QTimer, QObject, QThread, Signal, Slot
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox,
                               QCheckBox, QPlainTextEdit, QListWidget, QListWidgetItem, QFileDialog,
                               QMessageBox, QHeaderView, QLineEdit)

from .widgets import Page, Table, button, combo, label, line, guarded, confirm
from .secrets import protect_secret, unprotect_secret


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
DEFAULT_FTP_HOST = "lp2qfs.ftp.infomaniak.com"
DEFAULT_FTP_USER = "lp2qfs_admin"
DEFAULT_FTP_ROOT = "/sites/private_applications"
ALLOWED_UPLOAD_ROOT = "/sites/ast-elektro.ch/uploads"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
FTP_ERRORS = ftplib.all_errors + (ssl.SSLError,)


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


def _save_payload(db, payload, load_file):
    source_id = str(payload.get("id") or "").strip()
    if not source_id or len(source_id) > 180:
        raise ValueError("Eine Bewerbungsdatei enthält keine gültige Kennung.")
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
    current_sources = {row["source_ref"] for row in db.applicant_files(applicant_id)}
    destination = db.path.parent / "applications" / str(applicant_id)
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    for item in payload.get("files", []):
        source_ref = str(item.get("stored_path", ""))
        if not source_ref or source_ref in current_sources:
            continue
        content = load_file(source_ref)
        if content is None:
            continue
        name = safe_filename(item.get("original_name") or Path(source_ref).name)
        target = destination / name
        counter = 2
        while target.exists():
            target = destination / f"{Path(name).stem}_{counter}{Path(name).suffix}"
            counter += 1
        target.write_bytes(content)
        db.save_applicant_file(applicant_id, item.get("category", "other"), name, target, source_ref)
        copied += 1
    return bool(existing), copied


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
        def load_local(source_ref):
            source = (manifest_path.parent / source_ref).resolve()
            if not source.is_relative_to(allowed_root) or not source.is_file():
                return None
            if source.stat().st_size > MAX_DOCUMENT_BYTES:
                raise ValueError(f"Die Bewerbungsdatei {source.name} ist zu gross.")
            return source.read_bytes()
        existed, copied = _save_payload(db, payload, load_local)
        created += not existed; updated += existed; files_copied += copied
    return {"created": created, "updated": updated, "files": files_copied}


def sync_ftp(db, host, user, password, remote_root=DEFAULT_FTP_ROOT, ftp_factory=ftplib.FTP_TLS):
    """Import website manifests and uploads through explicit TLS-protected FTP."""
    host = str(host).strip(); user = str(user).strip(); remote_root = "/" + str(remote_root).strip().strip("/")
    if not host or any(char in host for char in "/:@ ") or not user or not password:
        raise ValueError("Bitte den FTP-Serverzugang vollständig angeben.")
    if posixpath.normpath(remote_root) != remote_root or not remote_root.startswith("/sites/"):
        raise ValueError("Der FTP-Importpfad muss ein gültiger Ordner unter /sites sein.")
    ftp = ftp_factory(context=ssl.create_default_context(), timeout=30)
    created = updated = files_copied = 0
    try:
        ftp.connect(host, 21)
        ftp.auth(); ftp.login(user, password); ftp.prot_p()
        ftp.cwd(remote_root)
        manifests = sorted(name for name in ftp.nlst() if posixpath.basename(name).lower().endswith(".json"))
        for name in manifests:
            buffer = io.BytesIO()
            ftp.retrbinary("RETR " + posixpath.basename(name), buffer.write)
            if buffer.tell() > MAX_MANIFEST_BYTES:
                raise ValueError(f"Die Bewerbungsdatei {posixpath.basename(name)} ist zu gross.")
            try:
                payload = json.loads(buffer.getvalue().decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError(f"Die Bewerbungsdatei {posixpath.basename(name)} ist ungültig.") from exc

            def load_remote(source_ref):
                remote = posixpath.normpath(posixpath.join(remote_root, str(source_ref)))
                if posixpath.commonpath((remote, ALLOWED_UPLOAD_ROOT)) != ALLOWED_UPLOAD_ROOT:
                    return None
                document = io.BytesIO()
                ftp.retrbinary("RETR " + remote, document.write)
                if document.tell() > MAX_DOCUMENT_BYTES:
                    raise ValueError(f"Die Bewerbungsdatei {posixpath.basename(remote)} ist zu gross.")
                return document.getvalue()

            existed, copied = _save_payload(db, payload, load_remote)
            created += not existed; updated += existed; files_copied += copied
        return {"created": created, "updated": updated, "files": files_copied}
    except FTP_ERRORS as exc:
        raise ValueError(f"Der Bewerbungsserver ist nicht erreichbar oder der Zugang wurde abgelehnt: {exc}") from exc
    finally:
        try:
            ftp.quit()
        except Exception:
            ftp.close()


class FtpSettingsDialog(QDialog):
    def __init__(self, parent, db):
        super().__init__(parent)
        self.db = db
        self.setWindowTitle("Bewerbungsserver")
        self.resize(610, 360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.addWidget(label("Bewerbungsserver", "dialogTitle"))
        hint = label("Die Verbindung erfolgt verschlüsselt über FTPS. Das Passwort wird mit deinem Windows-Benutzer verschlüsselt gespeichert.", "muted")
        hint.setWordWrap(True); layout.addWidget(hint)
        settings = db.settings()
        form = QFormLayout()
        self.host = line(settings.get("applications_ftp_host", DEFAULT_FTP_HOST))
        self.user = line(settings.get("applications_ftp_user", DEFAULT_FTP_USER))
        self.root = line(settings.get("applications_ftp_root", DEFAULT_FTP_ROOT))
        self.password = line()
        self.password.setEchoMode(QLineEdit.EchoMode.Password)
        try:
            self.password.setText(unprotect_secret(settings.get("applications_ftp_password", "")))
        except (ValueError, OSError):
            pass
        form.addRow("Server", self.host); form.addRow("Benutzer", self.user)
        form.addRow("Importpfad", self.root); form.addRow("Passwort", self.password)
        layout.addLayout(form); layout.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Zugang speichern")
        buttons.button(QDialogButtonBox.StandardButton.Save).setObjectName("primary")
        buttons.accepted.connect(self.submit); buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    @guarded
    def submit(self):
        if not all((self.host.text().strip(), self.user.text().strip(), self.root.text().strip(), self.password.text())):
            raise ValueError("Bitte alle Angaben zum Bewerbungsserver ausfüllen.")
        self.db.save_settings({"applications_ftp_host": self.host.text(),
                               "applications_ftp_user": self.user.text(),
                               "applications_ftp_root": self.root.text(),
                               "applications_ftp_password": protect_secret(self.password.text())})
        self.accept()


class FtpSyncWorker(QObject):
    finished = Signal(dict)
    failed = Signal(str)

    def __init__(self, database_path, host, user, password, remote_root):
        super().__init__()
        self.database_path = database_path
        self.connection = (host, user, password, remote_root)

    @Slot()
    def run(self):
        from .database import Database
        db = None
        try:
            db = Database(self.database_path)
            self.finished.emit(sync_ftp(db, *self.connection))
        except Exception as exc:
            logging.exception("Application FTP sync failed")
            self.failed.emit(str(exc))
        finally:
            if db:
                db.close()


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
        self.sync_thread = self.sync_worker = None
        self.header.addWidget(button("Vom Webserver einlesen", self.sync, True))
        self.header.addWidget(button("Serverzugang", self.configure_server))
        self.header.addWidget(button("+ Manuell erfassen", self.new))
        filters = QHBoxLayout()
        self.search = line(placeholder="Name, Ort, E-Mail oder Telefon suchen …")
        self.category = combo([("Alle Bewerbungsarten", ""), *[(title, key) for key, title in CATEGORIES.items()]])
        self.status = combo([("Alle Status", ""), *[(title, key) for key, title in STATUSES.items()]])
        filters.addWidget(self.search, 1); filters.addWidget(self.category); filters.addWidget(self.status)
        self.layout.addLayout(filters)
        self.server_status = label("Serverabgleich wird vorbereitet …", "muted")
        self.layout.addWidget(self.server_status)
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
        self.sync_timer = QTimer(self)
        self.sync_timer.setInterval(5 * 60 * 1000)
        self.sync_timer.timeout.connect(self.auto_sync)
        self.sync_timer.start()
        QTimer.singleShot(1500, self.auto_sync)

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

    def configure_server(self):
        if FtpSettingsDialog(self, self.db).exec() == QDialog.DialogCode.Accepted:
            self._start_sync(False)

    def _start_sync(self, manual):
        if self.sync_thread and self.sync_thread.isRunning():
            if manual:
                self.server_status.setText("Serverabgleich läuft bereits …")
            return
        settings = self.db.settings()
        encrypted = settings.get("applications_ftp_password", "")
        if not encrypted:
            if manual and FtpSettingsDialog(self, self.db).exec() == QDialog.DialogCode.Accepted:
                settings = self.db.settings(); encrypted = settings.get("applications_ftp_password", "")
            else:
                self.server_status.setText("Serverzugang noch nicht eingerichtet")
                return
        try:
            password = unprotect_secret(encrypted)
        except (ValueError, OSError) as exc:
            if manual:
                QMessageBox.warning(self, "Serverzugang prüfen", str(exc))
            self.server_status.setText("Serverzugang muss erneut gespeichert werden")
            return
        self.server_status.setText("Serverabgleich läuft …")
        thread = QThread(self)
        worker = FtpSyncWorker(self.db.path, settings.get("applications_ftp_host", DEFAULT_FTP_HOST),
                               settings.get("applications_ftp_user", DEFAULT_FTP_USER), password,
                               settings.get("applications_ftp_root", DEFAULT_FTP_ROOT))
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(lambda result: self._sync_finished(result, manual))
        worker.failed.connect(lambda message: self._sync_failed(message, manual))
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater); worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._sync_cleanup)
        self.sync_thread, self.sync_worker = thread, worker
        thread.start()

    def _sync_cleanup(self):
        self.sync_thread = self.sync_worker = None

    def _sync_finished(self, result, manual):
        self.refresh()
        now = datetime.now().strftime("%H:%M")
        addition = f" · {result['created']} neu · {result['files']} Dokumente" if result["created"] or result["files"] else ""
        self.server_status.setText(f"Automatischer Serverabgleich aktiv · zuletzt {now}{addition}")
        if manual:
            QMessageBox.information(self, "Bewerbungen eingelesen",
                                    f"Neu: {result['created']}\nAktualisiert: {result['updated']}\nDokumente kopiert: {result['files']}")

    def _sync_failed(self, message, manual):
        logging.warning("Automatic application FTP sync failed: %s", message)
        self.server_status.setText("Serverabgleich vorübergehend nicht möglich · nächster Versuch automatisch")
        if manual:
            QMessageBox.warning(self, "Serverabgleich nicht möglich", message)

    def auto_sync(self):
        self._start_sync(False)

    def stop_sync(self):
        self.sync_timer.stop()
        if self.sync_thread and self.sync_thread.isRunning():
            self.sync_thread.quit()
            self.sync_thread.wait(35000)

    def sync(self):
        self._start_sync(True)

    @guarded
    def remove(self):
        row = self.selected()
        if row and confirm(self, "Bewerbung löschen", "Soll dieses Bewerbungsdossier wirklich gelöscht werden?\nDie lokale Dokumentkopie bleibt als Datei erhalten."):
            self.db.delete("applicants", row["id"])
            self.refresh()
