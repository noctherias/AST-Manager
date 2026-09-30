from __future__ import annotations

from datetime import date
from functools import wraps
import logging

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QLineEdit, QComboBox,
    QDoubleSpinBox, QSpinBox, QDateEdit, QMessageBox, QDialog, QDialogButtonBox,
    QFormLayout, QScrollArea, QCheckBox)

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
        self.verticalHeader().hide()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setAlternatingRowColors(False)
        self.setWordWrap(False)
        self.verticalHeader().setDefaultSectionSize(48)
        self.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignCenter)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setMinimumSectionSize(80)
        self.setMinimumHeight(190)

    def populate(self, rows, ids=None, numeric_columns=()):
        self.setRowCount(0)
        self.setRowCount(len(rows))
        for r, values in enumerate(rows):
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

    def selected_id(self):
        row = self.currentRow()
        return self.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 and self.item(row, 0) else None


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


def confirm(parent, text):
    return QMessageBox.question(parent, "Bitte bestätigen", text,
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
