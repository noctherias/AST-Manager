from datetime import date
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget, QButtonGroup, QFrame, QScrollArea, QApplication

from .widgets import label, button
from .experience import Start, Invoices, Team, Salaries, Settings
from .update_ui import UpdateController
from . import __version__
from .documents import resource_path


class MainWindow(QMainWindow):
    def __init__(self, db, demo=False):
        super().__init__()
        self.db = db
        self._closing = False
        self.setWindowTitle("AST Verwaltung" + (" · Demomodus" if demo else ""))
        self.setWindowIcon(QIcon(str(resource_path("assets/ast.svg"))))
        self.resize(1380, 880)
        self.setMinimumSize(1120, 720)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(218)
        nav = QVBoxLayout(sidebar)
        nav.setContentsMargins(18, 32, 18, 22)
        nav.setSpacing(9)
        nav.addWidget(label("AST", "brand"))
        nav.addWidget(label("VERWALTUNG", "brandCaption"))
        nav.addSpacing(35)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.buttons = []
        for i, name in enumerate(["Start", "Rechnungen", "Team", "Lohnausweise", "Einstellungen"]):
            b = button(name, lambda index=i: self.navigate(index))
            b.setCheckable(True)
            b.setMinimumHeight(46)
            self.nav_group.addButton(b, i)
            nav.addWidget(b)
            self.buttons.append(b)
        nav.addStretch()
        nav.addWidget(label("DEMODATEN" if demo else "LOKAL GESPEICHERT", "brandCaption"))
        bottom = label("Separate Testumgebung\nFrei ausprobieren" if demo else "Deine Verwaltung.\nAlles an einem Ort.")
        nav.addWidget(bottom)
        nav.addSpacing(10)
        nav.addWidget(label("Version " + __version__))
        layout.addWidget(sidebar)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.updates = UpdateController(self, db, demo)
        self.pages = [Start(db, self), Invoices(db), Team(db), Salaries(db), Settings(db, self.updates)]
        for page in self.pages:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        self.statusBar().showMessage(("DEMO · Fiktive Beispieldaten · " if demo else "") + "Bereit · Änderungen werden beim Speichern übernommen")
        self.navigate(0)
        QApplication.instance().aboutToQuit.connect(self.prepare_shutdown)
        self.refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        self.refresh_shortcut.activated.connect(lambda: self.pages[self.stack.currentIndex()].refresh())

    def navigate(self, index):
        if not hasattr(self, "pages"):
            return
        if self.stack.currentIndex() == 4:
            self.pages[4].persist_company()
        self.pages[index].refresh()
        self.stack.setCurrentIndex(index)
        self.buttons[index].setChecked(True)

    def prepare_shutdown(self):
        if self._closing: return
        self._closing = True
        self.pages[4].persist_company()
        for field in self.pages[4].company_fields.values():
            field.editingFinished.disconnect(self.pages[4].persist_company)
        self.updates.stopped = True
        if self.updates.job: self.updates.job.cancel.set()
        self.updates.timer.stop()

    def closeEvent(self, event):
        self.prepare_shutdown()
        super().closeEvent(event)
