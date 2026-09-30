from __future__ import annotations

from datetime import datetime
import logging
from pathlib import Path
import sys
import threading
import time

from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtWidgets import (QApplication, QDialog, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
                              QProgressBar, QMessageBox, QCheckBox, QWidget)

from . import __version__
from .updates import open_url
from .updates import check_release, download_release, start_installer, configured_repository
from .widgets import label, button, guarded


class Job(QObject):
    success = Signal(object)
    failure = Signal(str)
    progress = Signal(int, int)

    def __init__(self, parent):
        super().__init__(parent)
        self.cancel = threading.Event()
        QApplication.instance().aboutToQuit.connect(self.cancel.set)

    def run(self, operation):
        def task():
            try:
                result = operation()
                if not self.cancel.is_set(): self.success.emit(result)
            except Exception as exc:
                if not self.cancel.is_set(): self.failure.emit(str(exc))
        threading.Thread(target=task, daemon=True, name="AST-Update").start()


class UpdateDialog(QDialog):
    def __init__(self, parent, release, db, demo=False):
        super().__init__(parent)
        self.release, self.db, self.demo = release, db, demo
        self.job = None
        self.setWindowTitle("Eine neue Version ist verfügbar")
        self.resize(610, 500)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 22)
        layout.setSpacing(14)
        layout.addWidget(label("AST wird noch besser", "dialogTitle"))
        layout.addWidget(label(f"Installiert: {__version__}     Neue Version: {release.version}", "muted"))
        notes = QPlainTextEdit()
        notes.setReadOnly(True)
        notes.setPlainText(release.notes)
        layout.addWidget(notes, 1)
        self.status = label("Das Update installiert die neue Programmversion. Deine erfassten Daten bleiben erhalten.", "muted")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        layout.addWidget(self.progress)
        row = QHBoxLayout()
        self.later = button("Später", self.reject)
        self.install = button("Herunterladen & aktualisieren", self.download, True)
        row.addWidget(self.later)
        row.addStretch()
        row.addWidget(self.install)
        layout.addLayout(row)

    def download(self):
        if not getattr(sys, "frozen", False):
            QMessageBox.information(self, "Quellcode-Version", "Diese Funktion aktualisiert die installierte Windows-App. Im Quellcode bitte die neue Version von GitHub übernehmen.")
            return
        self.install.setEnabled(False)
        self.later.setText("Download abbrechen")
        self.status.setText("Die neue Version wird heruntergeladen und geprüft …")
        self.progress.show()
        self.job = Job(self)
        self.job.progress.connect(lambda done, total: self.progress.setValue(round(done * 100 / total)))
        self.job.failure.connect(self.failed)
        self.job.success.connect(self.install_ready)
        job = self.job
        job.run(lambda: download_release(self.release, self.db.path.parent / "updates",
                                         job.progress.emit, job.cancel.is_set, open_url))

    def failed(self, message):
        self.status.setText(message)
        self.install.setEnabled(True)
        self.later.setText("Schliessen")

    @guarded
    def install_ready(self, path):
        try:
            self.db.backup(self.db.path.parent / "backups" / ("vor-update-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".sqlite3"))
            start_installer(path, self.release, self.db.path.parent, self.demo)
        except Exception as exc:
            self.failed(str(exc))
            return
        self.accept()
        QApplication.instance().quit()

    def reject(self):
        if self.job: self.job.cancel.set()
        super().reject()


class UpdateController(QObject):
    state_changed = Signal(str)

    def __init__(self, window, db, demo=False):
        super().__init__(window)
        self.window, self.db, self.demo = window, db, demo
        self.job = None
        self.busy = False
        self.stopped = False
        self.timer = QTimer(self)
        self.timer.setInterval(6 * 60 * 60 * 1000)
        self.timer.timeout.connect(self.automatic_check)

    def start(self):
        QTimer.singleShot(2500, self.automatic_check)
        self.timer.start()

    def automatic_check(self):
        settings = self.db.settings()
        if settings.get("update_auto", "1") != "1": return
        try:
            if time.time() - float(settings.get("update_last_attempt", "0")) < 6 * 60 * 60: return
        except ValueError:
            pass
        self.check(False)

    def check(self, manual=True):
        if self.busy or self.stopped: return
        try:
            repo = configured_repository(self.db.settings())
        except ValueError as exc:
            self.state_changed.emit(str(exc))
            return
        if not repo:
            self.state_changed.emit("Noch kein GitHub-Repository hinterlegt.")
            return
        self.busy = True
        self.state_changed.emit("Neue Version wird gesucht …")
        self.db.save_settings({"update_last_attempt": str(time.time())})
        self.job = Job(self)
        self.job.success.connect(lambda release: self.finished(release, manual))
        self.job.failure.connect(lambda message: self.failed(message, manual))
        self.job.run(lambda: check_release(repo, opener=open_url))

    def failed(self, message, manual):
        self.busy = False
        self.state_changed.emit(message)
        logging.info("Update check: %s", message)
        # Offline starts remain silent; an explicit check gets a visible result.
        if manual: QMessageBox.information(self.window, "Versionsprüfung", message)

    def finished(self, release, manual):
        self.busy = False
        self.state_changed.emit(f"Version {release.version} ist verfügbar." if release else f"Version {__version__} ist aktuell.")
        if not release:
            if manual: QMessageBox.information(self.window, "Du bist auf dem neuesten Stand", f"Version {__version__} ist aktuell.")
            return
        settings = self.db.settings()
        try: snoozed_until = float(settings.get("update_snoozed_until", "0"))
        except ValueError: snoozed_until = 0
        if not manual and settings.get("update_snoozed_version") == release.version and time.time() < snoozed_until:
            return
        def show_when_ready():
            if self.stopped: return
            if QApplication.activeModalWidget():
                QTimer.singleShot(1500, show_when_ready)
                return
            result = UpdateDialog(self.window, release, self.db, self.demo).exec()
            if result != QDialog.DialogCode.Accepted:
                self.db.save_settings({"update_snoozed_version": release.version, "update_snoozed_until": str(time.time() + 86400)})
        show_when_ready()


class UpdateSettings(QWidget):
    def __init__(self, db, controller):
        super().__init__()
        self.db, self.controller = db, controller
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)
        layout.addWidget(label("Programm aktualisieren", "sectionTitle"))
        layout.addWidget(label(f"Installierte Version: {__version__}", "muted"))
        self.state = label("", "muted")
        self.state.setWordWrap(True)
        controller.state_changed.connect(self.state.setText)
        layout.addWidget(self.state)
        layout.addWidget(button("Jetzt nach Updates suchen", lambda: controller.check(True), True))
        self.auto = QCheckBox("Beim Start automatisch nach neuen Versionen suchen")
        self.auto.toggled.connect(self.save_auto)
        layout.addWidget(self.auto)
        help_text = label("Neue Versionen werden automatisch über den fest eingebauten AST-Update-Kanal gefunden. Es sind keine GitHub-Verbindung und keine Zugangsdaten erforderlich.", "muted")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        layout.addStretch()
        self.refresh()

    def refresh(self):
        settings = self.db.settings()
        repo = configured_repository(settings)
        self.state.setText("Automatische Updates sind eingerichtet." if repo else "Der Update-Kanal fehlt in dieser Installation.")
        self.auto.blockSignals(True)
        self.auto.setChecked(settings.get("update_auto", "1") == "1")
        self.auto.blockSignals(False)

    def save_auto(self, checked):
        self.db.save_settings({"update_auto": "1" if checked else "0"})
