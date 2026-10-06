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
from urllib.parse import unquote, urlsplit

from PySide6.QtCore import Qt, QUrl, QTimer, QObject, QThread, Signal, Slot, QSize
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QDialogButtonBox,
                               QCheckBox, QPlainTextEdit, QListWidget, QListWidgetItem, QFileDialog,
                               QMessageBox, QHeaderView, QLineEdit, QFrame, QWidget, QScrollArea,
                               QGridLayout)

from .widgets import Page, Table, button, combo, label, line, guarded, confirm
from .secrets import protect_secret, unprotect_secret
from .export_paths import initial_path


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
SUITABILITY = {"": "Noch nicht beurteilt", "unsuitable": "Nicht geeignet", "possible": "Eventuell", "suitable": "Geeignet"}
SUITABILITY_COLORS = {"": "#edf2f5", "unsuitable": "#fce3e3", "possible": "#fff3cd", "suitable": "#dff3e8"}
SUITABILITY_SELECTION_COLORS = {"": "#dce8ed", "unsuitable": "#f2bfc2", "possible": "#f3dda0", "suitable": "#bfe2ce"}
DEFAULT_FTP_HOST = "lp2qfs.ftp.infomaniak.com"
DEFAULT_FTP_USER = "lp2qfs_admin"
DEFAULT_FTP_ROOT = "/sites/ast-elektro.ch/uploads"
MAX_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_DOCUMENT_BYTES = 50 * 1024 * 1024
FTP_ERRORS = ftplib.all_errors + (ssl.SSLError,)


def normalize_ftp_root(value):
    """Accept a server path or the complete FTP URL shown by FTP clients."""
    raw = str(value or "").strip().replace("\\", "/")
    if raw.casefold().startswith(("ftp://", "ftps://")):
        raw = unquote(urlsplit(raw).path)
    root = "/" + raw.strip("/")
    if posixpath.normpath(root) != root or not root.startswith("/sites/"):
        raise ValueError("Der FTP-Uploadpfad muss auf einen gültigen Ordner unter /sites verweisen.")
    return root


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


def trial_dates_text(value):
    values = value if isinstance(value, list) else re.split(r"[,;\n]+", str(value or ""))
    result = []
    for item in values:
        raw = str(item).strip()
        if not raw:
            continue
        try:
            raw = datetime.fromisoformat(raw).strftime("%d.%m.%Y")
        except ValueError:
            pass
        if raw not in result:
            result.append(raw)
    return "\n".join(result)


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
              "trial_dates": trial_dates_text(payload.get("trial_dates", [])),
              "message": payload.get("message", ""), "notes": existing["notes"] if existing else "",
              "suitability": existing["suitability"] if existing else "",
              "server_deleted": existing["server_deleted"] if existing else 0,
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
    allowed_root = root.resolve()
    created = updated = files_copied = 0
    for manifest_path in sorted(root.rglob("*.json")):
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
    host = str(host).strip(); user = str(user).strip(); remote_root = normalize_ftp_root(remote_root)
    if not host or any(char in host for char in "/:@ ") or not user or not password:
        raise ValueError("Bitte den FTP-Serverzugang vollständig angeben.")
    ftp = ftp_factory(context=ssl.create_default_context(), timeout=30)
    created = updated = files_copied = 0
    try:
        ftp.connect(host, 21)
        ftp.auth(); ftp.login(user, password); ftp.prot_p()
        ftp.cwd(remote_root)
        manifests = []
        for name in ftp.nlst():
            base = posixpath.basename(str(name).rstrip("/"))
            if base in ("", ".", ".."):
                continue
            remote = posixpath.normpath(posixpath.join(remote_root, base))
            if base.lower().endswith(".json"):
                manifests.append(remote)
                continue
            try:
                ftp.cwd(remote)
                manifests.extend(posixpath.normpath(posixpath.join(remote, posixpath.basename(child)))
                                 for child in ftp.nlst()
                                 if posixpath.basename(str(child)).lower().endswith(".json"))
            except ftplib.error_perm:
                pass
            finally:
                ftp.cwd(remote_root)
        for name in sorted(set(manifests)):
            buffer = io.BytesIO()
            ftp.retrbinary("RETR " + name, buffer.write)
            if buffer.tell() > MAX_MANIFEST_BYTES:
                raise ValueError(f"Die Bewerbungsdatei {posixpath.basename(name)} ist zu gross.")
            try:
                payload = json.loads(buffer.getvalue().decode("utf-8"))
            except (UnicodeDecodeError, ValueError) as exc:
                raise ValueError(f"Die Bewerbungsdatei {posixpath.basename(name)} ist ungültig.") from exc

            def load_remote(source_ref):
                remote = posixpath.normpath(posixpath.join(posixpath.dirname(name), str(source_ref)))
                if posixpath.commonpath((remote, remote_root)) != remote_root:
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


def delete_remote_application(host, user, password, source_id, remote_root=DEFAULT_FTP_ROOT,
                              ftp_factory=ftplib.FTP_TLS):
    """Delete exactly one verified website application folder through FTPS."""
    source_id = str(source_id or "").strip()
    remote_root = normalize_ftp_root(remote_root)
    if not source_id or source_id.startswith("manual-") or posixpath.basename(source_id) != source_id or source_id in (".", ".."):
        raise ValueError("Für diese Bewerbung existiert kein löschbarer Serverordner.")
    remote_folder = posixpath.normpath(posixpath.join(remote_root, source_id))
    if posixpath.dirname(remote_folder) != remote_root:
        raise ValueError("Der Bewerbungsordner liegt ausserhalb des erlaubten Uploadpfads.")
    ftp = ftp_factory(context=ssl.create_default_context(), timeout=30)
    try:
        ftp.connect(str(host).strip(), 21)
        ftp.auth(); ftp.login(str(user).strip(), password); ftp.prot_p()
        manifest_data = io.BytesIO()
        ftp.retrbinary("RETR " + remote_folder + "/application.json", manifest_data.write)
        try:
            payload = json.loads(manifest_data.getvalue().decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError("Der Serverordner enthält keine gültige Bewerbungsdatei.") from exc
        if str(payload.get("id", "")).strip() != source_id:
            raise ValueError("Der Serverordner gehört nicht eindeutig zu dieser Bewerbung.")
        ftp.cwd(remote_folder)
        names = [posixpath.basename(str(name).rstrip("/")) for name in ftp.nlst()]
        for name in names:
            if name not in ("", ".", ".."):
                ftp.delete(remote_folder + "/" + name)
        ftp.cwd(remote_root)
        ftp.rmd(remote_folder)
    except FTP_ERRORS as exc:
        raise ValueError(f"Die Serverdateien konnten nicht gelöscht werden: {exc}") from exc
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
                               "applications_ftp_root": normalize_ftp_root(self.root.text()),
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


class FtpDeleteWorker(QObject):
    finished = Signal()
    failed = Signal(str)

    def __init__(self, connection, source_id):
        super().__init__()
        self.connection = connection
        self.source_id = source_id

    @Slot()
    def run(self):
        try:
            host, user, password, remote_root = self.connection
            delete_remote_application(host, user, password, self.source_id, remote_root)
            self.finished.emit()
        except Exception as exc:
            logging.exception("Application FTP deletion failed")
            self.failed.emit(str(exc))


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
        self.matura_label = label("Zusatz")
        form.addRow(self.matura_label, self.matura)
        self.trial_dates = QPlainTextEdit(self.row.get("trial_dates", "")); self.trial_dates.setMaximumHeight(72)
        self.trial_dates.setPlaceholderText("Ein Datum pro Zeile")
        self.trial_dates_label = label("Mögliche Schnuppertage")
        form.addRow(self.trial_dates_label, self.trial_dates)
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
        self.fields["category"].currentIndexChanged.connect(self.update_category_fields)
        self.update_category_fields()
        self.refresh_files()

    def update_category_fields(self, *_):
        is_trial = self.fields["category"].currentData() == "trial"
        self.trial_dates_label.setVisible(is_trial); self.trial_dates.setVisible(is_trial)
        self.matura_label.setVisible(not is_trial); self.matura.setVisible(not is_trial)

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
        target, _ = QFileDialog.getSaveFileName(
            self, "Dokument speichern", initial_path(self, source.name, "applications_documents"))
        if target:
            shutil.copy2(source, target)

    @guarded
    def submit(self):
        values = {key: field.currentData() if key in ("category", "status") else field.text()
                  for key, field in self.fields.items()}
        values.update({"source_id": self.row.get("source_id", ""), "vocational_baccalaureate": self.matura.isChecked(),
                       "trial_dates": self.trial_dates.toPlainText(),
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


def _display(value, fallback="Nicht angegeben"):
    text = str(value or "").strip()
    return text or fallback


def _info_card(title, value):
    card = QFrame(); card.setObjectName("appInfoCard")
    box = QVBoxLayout(card); box.setContentsMargins(18, 15, 18, 15); box.setSpacing(7)
    caption = label(title, "appInfoCaption")
    content = label(_display(value), "appInfoValue")
    content.setWordWrap(True); content.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    box.addWidget(caption); box.addWidget(content); box.addStretch()
    return card


class ApplicantStatusDialog(QDialog):
    """Read-only submitted data with an explicit internal review workspace."""
    def __init__(self, parent, db, row):
        super().__init__(parent)
        self.db, self.row = db, row
        self.delete_thread = self.delete_worker = None
        self.setWindowTitle(f"Beurteilung & Dossier · {row['first_name']} {row['last_name']}")
        self.resize(980, 790)
        outer = QVBoxLayout(self); outer.setContentsMargins(22, 20, 22, 18); outer.setSpacing(14)

        self.hero = QFrame(); hero = QVBoxLayout(self.hero); hero.setContentsMargins(24, 20, 24, 20); hero.setSpacing(10)
        top = QHBoxLayout()
        title_box = QVBoxLayout(); title_box.setSpacing(3)
        self.name = label(f"{row['first_name']} {row['last_name']}", "applicantName")
        self.subtitle = label(f"{CATEGORIES[row['category']]} · Eingang {row['submitted_at'][:10]}", "applicantSubtitle")
        title_box.addWidget(self.name); title_box.addWidget(self.subtitle)
        top.addLayout(title_box, 1)
        self.badge = label("", "applicantBadge"); self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        top.addWidget(self.badge)
        hero.addLayout(top)
        hero.addWidget(label("BEURTEILUNG AUSWÄHLEN", "appInfoCaption"))
        review = QHBoxLayout(); review.setSpacing(10)
        self.review_buttons = {}
        for key, text, object_name in (("unsuitable", "Nicht geeignet", "reviewRed"),
                                       ("possible", "Eventuell", "reviewYellow"),
                                       ("suitable", "Geeignet", "reviewGreen")):
            control = button(text, lambda value=key: self.set_suitability(value))
            control.setObjectName(object_name); control.setCheckable(True)
            self.review_buttons[key] = control; review.addWidget(control)
        hero.addLayout(review)
        outer.addWidget(self.hero)

        note_card = QFrame(); note_card.setObjectName("appReviewCard")
        note_box = QVBoxLayout(note_card); note_box.setContentsMargins(18, 15, 18, 15); note_box.setSpacing(9)
        note_heading = QHBoxLayout()
        note_heading.addWidget(label("Interne Notiz", "sectionTitle")); note_heading.addStretch()
        note_heading.addWidget(label("Nur intern · Bewerbungsdaten bleiben unverändert", "muted"))
        note_box.addLayout(note_heading)
        self.notes = QPlainTextEdit(row.get("notes", ""))
        self.notes.setObjectName("appInternalNotes")
        self.notes.setPlaceholderText("Zum Beispiel Eindruck, Rückfrage, nächster Schritt oder Gesprächsnotiz …")
        self.notes.setMaximumHeight(92)
        note_box.addWidget(self.notes)
        note_actions = QHBoxLayout(); note_actions.addStretch()
        self.save_notes_button = button("Notiz speichern", self.save_notes, True)
        self.notes.textChanged.connect(lambda: self.save_notes_button.setText("Notiz speichern"))
        note_actions.addWidget(self.save_notes_button); note_box.addLayout(note_actions)
        outer.addWidget(note_card)

        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setObjectName("applicantScroll")
        content = QWidget(); content.setObjectName("applicantContent")
        body = QVBoxLayout(content); body.setContentsMargins(2, 2, 2, 2); body.setSpacing(14)

        cards = QGridLayout(); cards.setSpacing(12)
        address = " ".join(filter(None, [row.get("address", ""), row.get("postcode", ""), row.get("city", "")]))
        contact = "\n".join(filter(None, [row.get("email", ""), row.get("phone", "")]))
        details = ("Gewünscht" if row.get("vocational_baccalaureate") else "Nicht gewählt")
        if row["category"] == "trial":
            details = _display(row.get("trial_dates"), "Keine Schnupperdaten angegeben")
        cards.addWidget(_info_card("Kontakt", contact), 0, 0)
        cards.addWidget(_info_card("Adresse", address), 0, 1)
        cards.addWidget(_info_card("Bewerbungsart", CATEGORIES[row["category"]]), 0, 2)
        cards.addWidget(_info_card("Schnupperdaten" if row["category"] == "trial" else "Berufsmatura", details), 1, 0, 1, 2)
        cards.addWidget(_info_card("Bearbeitungsstand", STATUSES[row["status"]]), 1, 2)
        body.addLayout(cards)

        body.addWidget(label("Nachricht der Bewerberin / des Bewerbers", "sectionTitle"))
        message = QFrame(); message.setObjectName("appMessageCard")
        message_box = QVBoxLayout(message); message_box.setContentsMargins(18, 16, 18, 16)
        message_text = label(_display(row.get("message"), "Keine Nachricht übermittelt."), "appMessage")
        message_text.setWordWrap(True); message_text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        message_box.addWidget(message_text); body.addWidget(message)

        body.addWidget(label("Bewerbungsunterlagen", "sectionTitle"))
        self.files = QListWidget(); self.files.setObjectName("appDocuments"); self.files.setMinimumHeight(170)
        self.files.itemDoubleClicked.connect(lambda *_: self.open_file())
        for record in self.db.applicant_files(row["id"]):
            path = Path(record["local_path"])
            size = f"{path.stat().st_size / 1024:.0f} KB" if path.is_file() else "lokale Kopie fehlt"
            item = QListWidgetItem(f"{FILE_CATEGORIES.get(record['category'], 'Dokument')}\n{record['original_name']} · {size}")
            item.setData(Qt.ItemDataRole.UserRole, str(path)); item.setToolTip(str(path))
            item.setSizeHint(QSize(0, 58))
            self.files.addItem(item)
        if not self.files.count():
            item = QListWidgetItem("Keine Unterlagen vorhanden"); item.setFlags(Qt.ItemFlag.NoItemFlags); self.files.addItem(item)
        body.addWidget(self.files)
        file_actions = QHBoxLayout()
        file_actions.addWidget(button("Dokument öffnen", self.open_file, True))
        file_actions.addWidget(button("Kopie speichern", self.save_copy)); file_actions.addStretch()
        body.addLayout(file_actions)

        self.server_note = label("", "muted"); self.server_note.setWordWrap(True); body.addWidget(self.server_note)
        scroll.setWidget(content); outer.addWidget(scroll, 1)

        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText("Schliessen")
        close.rejected.connect(self.reject); outer.addWidget(close)
        self.refresh_status()

    def selected_path(self):
        item = self.files.currentItem()
        return Path(item.data(Qt.ItemDataRole.UserRole)) if item and item.data(Qt.ItemDataRole.UserRole) else None

    def open_file(self):
        path = self.selected_path()
        if path and path.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def save_copy(self):
        source = self.selected_path()
        if not source or not source.is_file():
            return
        target, _ = QFileDialog.getSaveFileName(
            self, "Dokument speichern", initial_path(self, source.name, "applications_documents"))
        if target:
            shutil.copy2(source, target)

    @guarded
    def save_notes(self):
        self.db.set_applicant_notes(self.row["id"], self.notes.toPlainText())
        self.row = self.db.applicant(self.row["id"])
        self.notes.blockSignals(True)
        self.notes.setPlainText(self.row.get("notes", ""))
        self.notes.blockSignals(False)
        self.save_notes_button.setText("Notiz gespeichert")

    def refresh_status(self):
        value = self.row.get("suitability", "")
        self.hero.setObjectName({"unsuitable": "applicantHeroRed", "possible": "applicantHeroYellow",
                                 "suitable": "applicantHeroGreen"}.get(value, "applicantHeroNeutral"))
        self.badge.setText(SUITABILITY[value])
        for key, control in self.review_buttons.items():
            control.setChecked(key == value)
        self.hero.style().unpolish(self.hero); self.hero.style().polish(self.hero)
        if self.row.get("server_deleted"):
            self.server_note.setText("Serverstatus: Die Originaldateien wurden nach der Beurteilung «Nicht geeignet» gelöscht. Die lokale Dossierkopie bleibt erhalten.")
        else:
            self.server_note.setText("Serverstatus: Die Originaldateien bleiben auf dem Bewerbungsserver gespeichert.")

    @guarded
    def set_suitability(self, value):
        if value == self.row.get("suitability"):
            return
        if value != "unsuitable" or self.row.get("server_deleted") or str(self.row.get("source_id", "")).startswith("manual-"):
            self.db.set_applicant_suitability(self.row["id"], value)
            self.row = self.db.applicant(self.row["id"]); self.refresh_status()
            return
        if not confirm(self, "Serverdateien endgültig löschen",
                       "Soll diese Bewerbung als «Nicht geeignet» markiert werden?\n\n"
                       "Alle Originaldateien dieses Bewerbers werden dabei unwiderruflich vom Webserver gelöscht. "
                       "Die bereits eingelesene lokale Dossierkopie bleibt im AST-Programm erhalten."):
            self.refresh_status(); return
        settings = self.db.settings(); encrypted = settings.get("applications_ftp_password", "")
        if not encrypted:
            raise ValueError("Der Serverzugang ist nicht eingerichtet. Die Beurteilung wurde nicht geändert.")
        password = unprotect_secret(encrypted)
        connection = (settings.get("applications_ftp_host", DEFAULT_FTP_HOST),
                      settings.get("applications_ftp_user", DEFAULT_FTP_USER), password,
                      settings.get("applications_ftp_root", DEFAULT_FTP_ROOT))
        for control in self.review_buttons.values(): control.setEnabled(False)
        self.server_note.setText("Serverdateien werden sicher gelöscht …")
        thread = QThread(self); worker = FtpDeleteWorker(connection, self.row["source_id"])
        worker.moveToThread(thread); thread.started.connect(worker.run)
        worker.finished.connect(self._delete_finished); worker.failed.connect(self._delete_failed)
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater); worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater); thread.finished.connect(self._delete_cleanup)
        self.delete_thread, self.delete_worker = thread, worker; thread.start()

    @Slot()
    def _delete_finished(self):
        self.db.set_applicant_suitability(self.row["id"], "unsuitable", True)
        self.row = self.db.applicant(self.row["id"]); self.refresh_status()
        QMessageBox.information(self, "Bewerbung beurteilt", "Die Bewerbung wurde rot markiert und die Originaldateien wurden vom Server gelöscht.")

    @Slot(str)
    def _delete_failed(self, message):
        for control in self.review_buttons.values(): control.setEnabled(True)
        self.refresh_status()
        QMessageBox.warning(self, "Serverdateien nicht gelöscht", message + "\n\nDie Beurteilung wurde nicht geändert.")

    def _delete_cleanup(self):
        self.delete_thread = self.delete_worker = None
        for control in self.review_buttons.values(): control.setEnabled(True)

    def closeEvent(self, event):
        if self.delete_thread and self.delete_thread.isRunning():
            QMessageBox.information(self, "Löschen läuft", "Bitte warte, bis die Serverdateien vollständig gelöscht wurden.")
            event.ignore(); return
        super().closeEvent(event)


class ApplicationsPage(Page):
    def __init__(self, db):
        super().__init__("Bewerbungen", "Bewerbung auswählen und über «Beurteilung & Dossier» bewerten, notieren und prüfen.")
        self.db, self.rows = db, []
        self.sync_thread = self.sync_worker = None
        self.sync_manual = False
        self.header.addWidget(button("Vom Webserver einlesen", self.sync, True))
        self.header.addWidget(button("Serverzugang", self.configure_server))
        self.header.addWidget(button("+ Manuell erfassen", self.new))
        filters = QHBoxLayout()
        self.search = line(placeholder="Name, Ort, E-Mail oder Telefon suchen …")
        self.category = combo([("Alle Bewerbungsarten", ""), *[(title, key) for key, title in CATEGORIES.items()]])
        self.status = combo([("Alle Beurteilungen", ""), *[(title, key) for key, title in SUITABILITY.items() if key]])
        filters.addWidget(self.search, 1); filters.addWidget(self.category); filters.addWidget(self.status)
        self.layout.addLayout(filters)
        self.server_status = label("Serverabgleich wird vorbereitet …", "muted")
        self.layout.addWidget(self.server_status)
        self.table = Table(["Eingang", "Name", "Bewerbung für", "Beurteilung", "Ort", "Kontakt", "Dokumente"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        self.hint = label("Bewerbung auswählen, um Beurteilung und interne Notizen zu öffnen.", "muted")
        actions.addWidget(self.hint, 1)
        self.open_button = button("Beurteilung && Dossier öffnen", self.open, True)
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
        category = self.category.currentData(); suitability = self.status.currentData()
        self.rows = [row for row in getattr(self, "all_rows", [])
                     if (not category or row["category"] == category)
                     and (not suitability or row.get("suitability", "") == suitability)
                     and (not query or query in " ".join(str(row.get(key, "")) for key in
                                                         ("first_name", "last_name", "city", "email", "phone")).casefold())]
        self.table.populate([[row["submitted_at"][:10], f"{row['first_name']} {row['last_name']}",
                              CATEGORIES[row["category"]], SUITABILITY[row.get("suitability", "")], row["city"],
                              " · ".join(filter(None, [row["email"], row["phone"]])),
                              len(self.db.applicant_files(row["id"]))] for row in self.rows],
                            [row["id"] for row in self.rows], [6])
        for index, row in enumerate(self.rows):
            colour = QColor(SUITABILITY_COLORS[row.get("suitability", "")])
            for column in range(self.table.columnCount()):
                if self.table.item(index, column):
                    self.table.item(index, column).setBackground(colour)
        self.selection()

    def selected(self):
        key = self.table.selected_id()
        return next((row for row in self.rows if row["id"] == key), None)

    def selection(self):
        row = self.selected(); enabled = bool(row)
        self.open_button.setEnabled(enabled); self.delete_button.setEnabled(enabled)
        selected_colour = SUITABILITY_SELECTION_COLORS[row.get("suitability", "") if row else ""]
        self.table.setStyleSheet(
            f"QTableWidget::item:selected {{ background: {selected_colour}; color: #183342; }}")
        self.hint.setText(f"{row['first_name']} {row['last_name']} · {SUITABILITY[row.get('suitability', '')]} · jetzt beurteilen oder Notiz erfassen" if row else "Bewerbung auswählen, um Beurteilung und interne Notizen zu öffnen.")

    def new(self):
        if ApplicantDialog(self, self.db).exec():
            self.refresh()

    def open(self, *_):
        row = self.selected()
        if row:
            ApplicantStatusDialog(self, self.db, self.db.applicant(row["id"])).exec()
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
        self.sync_manual = manual
        worker.finished.connect(self._sync_finished)
        worker.failed.connect(self._sync_failed)
        worker.finished.connect(thread.quit); worker.failed.connect(thread.quit)
        worker.finished.connect(worker.deleteLater); worker.failed.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._sync_cleanup)
        self.sync_thread, self.sync_worker = thread, worker
        thread.start()

    def _sync_cleanup(self):
        self.sync_thread = self.sync_worker = None

    @Slot(dict)
    def _sync_finished(self, result):
        manual = self.sync_manual
        self.refresh()
        now = datetime.now().strftime("%H:%M")
        addition = f" · {result['created']} neu · {result['files']} Dokumente" if result["created"] or result["files"] else ""
        self.server_status.setText(f"Automatischer Serverabgleich aktiv · zuletzt {now}{addition}")
        if manual:
            QMessageBox.information(self, "Bewerbungen eingelesen",
                                    f"Neu: {result['created']}\nAktualisiert: {result['updated']}\nDokumente kopiert: {result['files']}")

    @Slot(str)
    def _sync_failed(self, message):
        manual = self.sync_manual
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
