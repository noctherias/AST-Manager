from __future__ import annotations

from datetime import date
from functools import wraps
import hashlib
import json
import logging

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLineEdit, QComboBox,
    QDoubleSpinBox, QSpinBox, QDateEdit, QMessageBox, QDialog, QDialogButtonBox,
    QFormLayout, QScrollArea, QCheckBox, QMenu)

from .domain import number


def guarded(fn):
    @wraps(fn)
    def wrapped(self, *args, **kwargs):
        try:
            return fn(self, *args, **kwargs)
        except (ValueError, OSError) as exc:
            QMessageBox.warning(self, "Bitte prüfen", str(exc))
        except Exception as exc:
            logging.exception("Operation failed")
            QMessageBox.critical(self, "Aktion nicht abgeschlossen", f"Die Aktion konnte nicht abgeschlossen werden.\n{exc}")
    return wrapped


def label(text, name=None):
    w = QLabel(text)
    w.setTextFormat(Qt.TextFormat.PlainText)
    if name:
        w.setObjectName(name)
    return w


def button(text, callback=None, primary=False):
    b = QPushButton(text)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setMinimumHeight(36)
    if primary:
        b.setObjectName("primary")
    if callback:
        b.clicked.connect(lambda checked=False: callback())
    return b


def line(value="", placeholder="", max_length=250):
    w = QLineEdit(str(value or ""))
    w.setPlaceholderText(placeholder)
    w.setMaxLength(max_length)
    w.setMinimumHeight(35)
    return w


def combo(items, value=None):
    w = QComboBox()
    w.setMinimumHeight(35)
    for title, data in items:
        w.addItem(str(title), data)
    idx = w.findData(value)
    if idx >= 0:
        w.setCurrentIndex(idx)
    return w


def numeric(value=0, suffix="", negative=False, integer=False):
    w = QSpinBox() if integer else QDoubleSpinBox()
    w.setRange(-999999999 if negative else 0, 999999999)
    if not integer:
        w.setDecimals(2)
        w.setSingleStep(.25 if suffix == " h" else 1)
    w.setValue(value)
    w.setSuffix(suffix)
    w.setGroupSeparatorShown(True)
    w.setMinimumHeight(35)
    w.setAccelerated(True)
    return w


def day(value=None):
    w = QDateEdit()
    w.setCalendarPopup(True)
    w.setDisplayFormat("dd.MM.yyyy")
    w.setDateRange(QDate(1900, 1, 1), QDate(2200, 12, 31))
    w.setDate(QDate.fromString(value or date.today().isoformat(), "yyyy-MM-dd"))
    w.setMinimumHeight(35)
    return w


def day_value(w):
    return w.date().toString("yyyy-MM-dd")


class Metric(QFrame):
    def __init__(self, title, hint="", accent=False):
        super().__init__()
        self.setObjectName("accentCard" if accent else "card")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(19, 17, 19, 17)
        layout.setSpacing(8)
        layout.addWidget(label(title, "metricTitle"))
        self.value = label("–", "metricValue")
        layout.addWidget(self.value)
        self.hint = label(hint, "metricHint")
        layout.addWidget(self.hint)
        self.setMinimumHeight(120)

    def set(self, value, negative=False):
        self.value.setText(str(value))
        self.value.setStyleSheet("color: #bd3c40" if negative else "")


class Table(QTableWidget):
    def __init__(self, headers):
        super().__init__(0, len(headers))
        self.setHorizontalHeaderLabels(headers)
        self._layout_db = None
        self._layout_key = "table_" + hashlib.sha1("|".join(headers).encode("utf-8")).hexdigest()[:12]
        self._row_keys = []
        self._applying_layout = False
        self.verticalHeader().show()
        self.verticalHeader().setFixedWidth(34)
        self.verticalHeader().setSectionsMovable(True)
        self.verticalHeader().setToolTip("Zeilen ziehen zum Sortieren · Rechtsklick zum Ausblenden")
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(48)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setToolTip("Spalten ziehen zum Sortieren · Rechtsklick zum Ein- oder Ausblenden")
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setMinimumSectionSize(80)
        self.setMinimumHeight(190)
        self.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.verticalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._column_menu)
        self.verticalHeader().customContextMenuRequested.connect(self._row_menu)
        self.horizontalHeader().sectionMoved.connect(self._save_layout)
        self.verticalHeader().sectionMoved.connect(self._save_layout)

    def bind_layout(self, db, key):
        """Persist column and row arrangement in the active AST database."""
        self._layout_db = db
        self._layout_key = "table_layout_" + str(key)
        self._apply_layout()

    def populate(self, rows, ids=None, numeric_columns=()):
        self._applying_layout = True
        try:
            self.setRowCount(0)
            self.setRowCount(len(rows))
            for r, values in enumerate(rows):
                self.setVerticalHeaderItem(r, QTableWidgetItem(str(r + 1)))
                for c, value in enumerate(values):
                    item = QTableWidgetItem(str(value))
                    if c == 0 and ids is not None:
                        item.setData(Qt.ItemDataRole.UserRole, ids[r])
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                    item.setToolTip(str(value))
                    if value in ("Überfällig", "Negativ"):
                        item.setForeground(QColor("#bd3c40"))
                    elif value in ("Bezahlt", "Aktiv"):
                        item.setForeground(QColor("#087a61"))
                    self.setItem(r, c, item)
            self._row_keys = [str(ids[r]) if ids is not None else str(rows[r][0])
                              for r in range(len(rows))]
        finally:
            self._applying_layout = False
        self._apply_layout()

    def selected_id(self):
        row = self.currentRow()
        return self.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 and self.item(row, 0) else None

    def _stored_layout(self):
        if not self._layout_db:
            return {}
        raw = self._layout_db.settings().get(self._layout_key, "")
        try:
            return json.loads(raw) if raw else {}
        except (TypeError, ValueError):
            return {}

    def _apply_layout(self):
        if self._applying_layout:
            return
        self._applying_layout = True
        try:
            saved = self._stored_layout()
            headers = [self.horizontalHeaderItem(i).text() for i in range(self.columnCount())]
            for target, title in enumerate(saved.get("columns", [])):
                if title in headers:
                    logical = headers.index(title)
                    current = self.horizontalHeader().visualIndex(logical)
                    if current >= 0 and current != target:
                        self.horizontalHeader().moveSection(current, target)
            hidden_columns = set(saved.get("hidden_columns", []))
            for logical, title in enumerate(headers):
                self.setColumnHidden(logical, title in hidden_columns)
            for row in range(self.rowCount()):
                self.setRowHidden(row, False)
            for target, key in enumerate(saved.get("rows", [])):
                if key in self._row_keys:
                    logical = self._row_keys.index(key)
                    current = self.verticalHeader().visualIndex(logical)
                    if current >= 0 and current != target:
                        self.verticalHeader().moveSection(current, target)
            hidden_rows = set(saved.get("hidden_rows", []))
            for logical, key in enumerate(self._row_keys):
                self.setRowHidden(logical, key in hidden_rows)
        finally:
            self._applying_layout = False

    def _save_layout(self, *_):
        if self._applying_layout or not self._layout_db:
            return
        headers = [self.horizontalHeaderItem(i).text() for i in range(self.columnCount())]
        columns = [headers[self.horizontalHeader().logicalIndex(visual)]
                   for visual in range(self.columnCount())]
        rows = [self._row_keys[self.verticalHeader().logicalIndex(visual)]
                for visual in range(self.rowCount()) if self.verticalHeader().logicalIndex(visual) < len(self._row_keys)]
        data = {"columns": columns,
                "hidden_columns": [title for i, title in enumerate(headers) if self.isColumnHidden(i)],
                "rows": rows,
                "hidden_rows": [key for i, key in enumerate(self._row_keys) if self.isRowHidden(i)]}
        self._layout_db.save_settings({self._layout_key: json.dumps(data, ensure_ascii=False)})

    def _column_menu(self, position):
        menu = QMenu(self)
        for logical in range(self.columnCount()):
            title = self.horizontalHeaderItem(logical).text()
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(not self.isColumnHidden(logical))
            action.triggered.connect(lambda checked=False, col=logical: self._set_column_visible(col, checked))
        menu.addSeparator()
        menu.addAction("Spalten zurücksetzen", self._reset_columns)
        menu.exec(self.horizontalHeader().mapToGlobal(position))

    def _set_column_visible(self, logical, visible):
        self.setColumnHidden(logical, not visible)
        self._save_layout()

    def _reset_columns(self):
        self._applying_layout = True
        try:
            for logical in range(self.columnCount()):
                self.setColumnHidden(logical, False)
                current = self.horizontalHeader().visualIndex(logical)
                if current != logical:
                    self.horizontalHeader().moveSection(current, logical)
        finally:
            self._applying_layout = False
        self._save_layout()

    def _row_menu(self, position):
        menu = QMenu(self)
        logical = self.verticalHeader().logicalIndexAt(position)
        if 0 <= logical < self.rowCount():
            title = self.item(logical, 0).text() if self.item(logical, 0) else str(logical + 1)
            menu.addAction(f"Zeile ausblenden · {title}", lambda: self._set_row_visible(logical, False))
        hidden = [row for row in range(self.rowCount()) if self.isRowHidden(row)]
        if hidden:
            menu.addSeparator()
            for row in hidden:
                title = self.item(row, 0).text() if self.item(row, 0) else str(row + 1)
                menu.addAction(f"Einblenden · {title}", lambda checked=False, row=row: self._set_row_visible(row, True))
            menu.addAction("Alle Zeilen einblenden", self._show_all_rows)
        menu.addSeparator()
        menu.addAction("Zeilenreihenfolge zurücksetzen", self._reset_rows)
        menu.exec(self.verticalHeader().mapToGlobal(position))

    def _set_row_visible(self, logical, visible):
        self.setRowHidden(logical, not visible)
        self._save_layout()

    def _show_all_rows(self):
        for row in range(self.rowCount()):
            self.setRowHidden(row, False)
        self._save_layout()

    def _reset_rows(self):
        self._applying_layout = True
        try:
            for logical in range(self.rowCount()):
                self.setRowHidden(logical, False)
                current = self.verticalHeader().visualIndex(logical)
                if current != logical:
                    self.verticalHeader().moveSection(current, logical)
        finally:
            self._applying_layout = False
        self._save_layout()


class Page(QWidget):
    def __init__(self, title, subtitle):
        super().__init__()
        self.setObjectName("pageRoot")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(32, 26, 32, 24)
        self.layout.setSpacing(18)
        self.header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(5)
        self.title_label = label(title, "pageTitle")
        self.subtitle_label = label(subtitle, "muted")
        self.subtitle_label.setWordWrap(True)
        titles.addWidget(self.title_label)
        titles.addWidget(self.subtitle_label)
        self.header.addLayout(titles, 1)
        self.layout.addLayout(self.header)

    def toolbar(self):
        row = QHBoxLayout()
        row.setSpacing(10)
        self.layout.addLayout(row)
        return row

    def metrics(self, specs):
        row = QHBoxLayout()
        row.setSpacing(14)
        cards = [Metric(*s) for s in specs]
        for card in cards:
            row.addWidget(card, 1)
        self.layout.addLayout(row)
        return cards

    def refresh(self):
        pass


class FormDialog(QDialog):
    def __init__(self, parent, title, subtitle="", width=610):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(width)
        self.resize(width, 580)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 22, 24, 18)
        self.layout.setSpacing(14)
        self.layout.addWidget(label(title, "dialogTitle"))
        if subtitle:
            sub = label(subtitle, "muted")
            sub.setWordWrap(True)
            self.layout.addWidget(sub)
        scroll = QScrollArea()
        scroll.setObjectName("formScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        content = QWidget()
        content.setObjectName("formContent")
        self.form = QFormLayout(content)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.form.setSpacing(12)
        self.form.setContentsMargins(0, 3, 10, 8)
        scroll.setWidget(content)
        self.layout.addWidget(scroll, 1)
        self.buttons = QDialogButtonBox()
        self.cancel_button = self.buttons.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        self.save_button = self.buttons.addButton("Speichern", QDialogButtonBox.ButtonRole.AcceptRole)
        self.save_button.setObjectName("primary")
        self.buttons.rejected.connect(self.reject)
        self.buttons.accepted.connect(self.submit)
        self.layout.addWidget(self.buttons)
        self.fields = {}
        self.saved_id = None

    def add(self, key, title, widget):
        widget.setAccessibleName(title)
        widget.setObjectName(key)
        self.fields[key] = widget
        self.form.addRow(title, widget)
        return widget

    def values(self):
        values = {}
        for k, w in self.fields.items():
            if isinstance(w, QLineEdit): values[k] = w.text().strip()
            elif isinstance(w, QComboBox): values[k] = w.currentData()
            elif isinstance(w, QDateEdit): values[k] = day_value(w)
            elif isinstance(w, (QDoubleSpinBox, QSpinBox)): values[k] = w.value()
            elif isinstance(w, QCheckBox): values[k] = int(w.isChecked())
        return values

    def submit(self):
        self.accept()


def confirm(parent, title, text=None):
    if text is None:
        text, title = title, "Bitte bestätigen"
    return QMessageBox.question(parent, title, text,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes


class Disclosure(QWidget):
    """Secondary fields stay available without crowding the everyday workflow."""
    def __init__(self, title, expanded=False):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.toggle = button("+ " + title)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(expanded)
        self.toggle.setObjectName("disclosure")
        layout.addWidget(self.toggle)
        self.content = QWidget()
        self.form = QFormLayout(self.content)
        self.form.setContentsMargins(8, 4, 8, 8)
        self.form.setSpacing(12)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addWidget(self.content)
        self.content.setVisible(expanded)
        self.toggle.toggled.connect(self.content.setVisible)
        self.toggle.toggled.connect(lambda checked: self.toggle.setText(("- " if checked else "+ ") + title))


def selection_bar(layout, prompt):
    pane = QFrame()
    pane.setObjectName("selectionBar")
    row = QHBoxLayout(pane)
    row.setContentsMargins(16, 12, 16, 12)
    hint = label(prompt, "muted")
    row.addWidget(hint, 1)
    layout.addWidget(pane)
    return row, hint
