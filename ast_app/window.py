from datetime import date
from PySide6.QtCore import Qt, QSize, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QStackedWidget,
                               QButtonGroup, QFrame, QScrollArea, QApplication, QStyle)

from .widgets import label, button, Table
from .experience import Start, Invoices, Reminders, Team, Salaries, Settings
from .references import ReferencesPage
from .applications import ApplicationsPage
from .update_ui import UpdateController
from . import __version__
from .documents import resource_path


class BackgroundWatermark(QWidget):
    """Subtle, click-through company logo above the working area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("backgroundWatermark")
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._logo = QPixmap(str(resource_path("assets/logo_ast_black.png")))

    def paintEvent(self, event):
        if self._logo.isNull():
            return
        maximum = QSize(max(1, int(self.width() * 0.64)),
                        max(1, int(self.height() * 0.46)))
        logo = self._logo.scaled(
            maximum, Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation
        )
        x = (self.width() - logo.width()) // 2
        y = (self.height() - logo.height()) // 2
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(0.035)
        painter.drawPixmap(x, y, logo)


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
        root.setObjectName("appRoot")
        self.root = root
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.sidebar = QWidget()
        self.sidebar.setObjectName("sidebar")
        self.nav = QVBoxLayout(self.sidebar)
        self.nav.setContentsMargins(20, 20, 20, 22)
        self.nav.setSpacing(8)
        brand_row = QHBoxLayout()
        self.brand_label = label("AST", "brand")
        brand_row.addWidget(self.brand_label, 1)
        self.sidebar_toggle = button("‹", self.toggle_sidebar)
        self.sidebar_toggle.setObjectName("sidebarToggle")
        self.sidebar_toggle.setFixedSize(36, 36)
        brand_row.addWidget(self.sidebar_toggle)
        self.nav.addLayout(brand_row)
        self.brand_caption = label("VERWALTUNG", "brandCaption")
        self.nav.addWidget(self.brand_caption)
        self.nav.addSpacing(22)
        self.nav_section = label("ARBEITSBEREICHE", "navSection")
        self.nav.addWidget(self.nav_section)
        self.nav.addSpacing(4)
        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.buttons = [None] * 8
        self.nav_items = {}
        for page_index, name, child, icon in [
            (0, "Übersicht", False, QStyle.StandardPixmap.SP_DesktopIcon),
            (1, "Debitoren", False, QStyle.StandardPixmap.SP_FileDialogDetailedView),
            (5, "Mahnungen", True, QStyle.StandardPixmap.SP_MessageBoxWarning),
            (2, "Stundennachweis", False, QStyle.StandardPixmap.SP_FileDialogListView),
            (6, "Zeugnisse", False, QStyle.StandardPixmap.SP_FileDialogContentsView),
            (7, "Bewerbungen", False, QStyle.StandardPixmap.SP_DirHomeIcon),
            (3, "Lohnausweise", False, QStyle.StandardPixmap.SP_FileIcon),
            (4, "Einstellungen", False, QStyle.StandardPixmap.SP_ComputerIcon),
        ]:
            b = button(name, lambda index=page_index: self.navigate(index))
            b.setObjectName("navSubButton" if child else "navButton")
            b.setCheckable(True)
            b.setMinimumHeight(38 if child else 46)
            b.setIcon(self.style().standardIcon(icon))
            b.setIconSize(QSize(20, 20))
            b.setToolTip(name)
            self.nav_group.addButton(b, page_index)
            self.nav.addWidget(b)
            self.buttons[page_index] = b
            self.nav_items[page_index] = (name, child)
        self.nav.addStretch()
        self.storage_label = label("DEMODATEN" if demo else "LOKAL GESPEICHERT", "brandCaption")
        self.nav.addWidget(self.storage_label)
        self.bottom_label = label("Separate Testumgebung\nFrei ausprobieren" if demo else "Deine Verwaltung.\nAlles an einem Ort.")
        self.nav.addWidget(self.bottom_label)
        self.nav.addSpacing(10)
        self.version_label = label("Version " + __version__)
        self.nav.addWidget(self.version_label)
        layout.addWidget(self.sidebar)
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)
        self.updates = UpdateController(self, db, demo)
        self.pages = [Start(db, self), Invoices(db), Team(db, self), Salaries(db),
                      Settings(db, self.updates), Reminders(db, self), ReferencesPage(db),
                      ApplicationsPage(db)]
        for page in self.pages:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        for page_index, page in enumerate(self.pages):
            for table_index, table in enumerate(page.findChildren(Table)):
                table.bind_layout(db, f"page_{page_index}_{table_index}")
        self.watermark = BackgroundWatermark(self.root)
        self.stack.currentChanged.connect(self._position_watermark)
        QTimer.singleShot(0, self._position_watermark)
        self.statusBar().showMessage(("DEMO · Fiktive Beispieldaten · " if demo else "") + "Bereit · Änderungen werden beim Speichern übernommen")
        self.navigate(0)
        QApplication.instance().aboutToQuit.connect(self.prepare_shutdown)
        self.refresh_shortcut = QShortcut(QKeySequence("F5"), self)
        self.refresh_shortcut.activated.connect(lambda: self.pages[self.stack.currentIndex()].refresh())
        self.set_sidebar_collapsed(self.db.settings().get("sidebar_collapsed", "0") == "1", save=False)

    def _position_watermark(self, *_):
        self.watermark.setGeometry(self.stack.geometry())
        self.watermark.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "watermark"):
            self._position_watermark()

    def toggle_sidebar(self):
        self.set_sidebar_collapsed(not self.sidebar_collapsed)

    def set_sidebar_collapsed(self, collapsed, save=True):
        self.sidebar_collapsed = bool(collapsed)
        self.sidebar.setFixedWidth(78 if collapsed else 250)
        self.nav.setContentsMargins(10 if collapsed else 20, 20, 10 if collapsed else 20, 22)
        self.brand_label.setText("A" if collapsed else "AST")
        self.brand_label.setAlignment(Qt.AlignmentFlag.AlignCenter if collapsed else Qt.AlignmentFlag.AlignLeft)
        self.sidebar_toggle.setText("›" if collapsed else "‹")
        self.sidebar_toggle.setToolTip("Menü ausklappen" if collapsed else "Menü einklappen")
        for widget in (self.brand_caption, self.nav_section, self.storage_label, self.bottom_label, self.version_label):
            widget.setVisible(not collapsed)
        for page_index, (name, child) in self.nav_items.items():
            nav_button = self.buttons[page_index]
            nav_button.setText("" if collapsed else name)
            nav_button.setProperty("collapsed", collapsed)
            nav_button.style().unpolish(nav_button)
            nav_button.style().polish(nav_button)
        if save:
            self.db.save_settings({"sidebar_collapsed": "1" if collapsed else "0"})
        if hasattr(self, "watermark"):
            QTimer.singleShot(0, self._position_watermark)

    def navigate(self, index):
        if not hasattr(self, "pages"):
            return
        if self.stack.currentIndex() == 4:
            self.pages[4].persist_company()
        self.pages[index].refresh()
        self.stack.setCurrentIndex(index)
        self.buttons[index].setChecked(True)

    def navigate_settings_team(self, create=False, employee_id=None):
        self.navigate(4)
        self.pages[4].open_team(employee_id=employee_id, create=create)

    def prepare_shutdown(self):
        if self._closing: return
        self._closing = True
        self.pages[4].persist_company()
        for field in self.pages[4].company_fields.values():
            field.editingFinished.disconnect(self.pages[4].persist_company)
        self.updates.stopped = True
        if self.updates.job: self.updates.job.cancel.set()
        self.updates.timer.stop()
        self.pages[7].stop_sync()

    def closeEvent(self, event):
        self.prepare_shutdown()
        super().closeEvent(event)
