"""Guided employment, interim and apprenticeship certificates."""
from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

from PySide6.QtCore import Qt, QDate
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, QTabWidget,
                               QDialogButtonBox, QPlainTextEdit, QMessageBox, QHeaderView, QWidget,
                               QScrollArea)
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, KeepTogether

from .documents import resource_path
from .domain import display_date
from .pages import save_path, PdfPreview
from .widgets import Page, Table, button, combo, day, day_value, label, line, guarded, confirm


REFERENCE_TYPES = {
    "work": "Arbeitszeugnis",
    "interim": "Zwischenzeugnis",
    "apprentice": "Lehrzeugnis",
}
ANSWER_CHOICES = [("Bitte auswählen …", None), ("Immer", 5), ("Meistens", 4),
                  ("Häufig", 3), ("Teilweise", 2), ("Selten", 1)]
COMMON_GROUPS = [
    ("knowledge", "Fachkenntnisse", ["Wendet die nötigen Fachkenntnisse sicher an.", "Findet auch bei anspruchsvollen Aufgaben fachlich passende Lösungen."]),
    ("quality", "Arbeitsqualität", ["Arbeitet genau, sorgfältig und sauber.", "Die Arbeitsergebnisse sind mängelfrei und vollständig."]),
    ("quantity", "Arbeitsmenge und Termine", ["Erledigt die erwartete Arbeitsmenge.", "Hält Termine auch bei hoher Belastung ein."]),
    ("independence", "Selbständigkeit", ["Plant und erledigt Aufgaben selbständig.", "Erkennt Probleme und entwickelt zweckmässige Lösungen."]),
    ("reliability", "Zuverlässigkeit", ["Hält Abmachungen und Vorgaben zuverlässig ein.", "Übernimmt Verantwortung für die eigenen Arbeitsergebnisse."]),
    ("initiative", "Einsatz und Initiative", ["Erkennt anstehende Arbeiten und handelt von sich aus.", "Zeigt auch in anspruchsvollen Situationen hohen Einsatz."]),
    ("learning", "Auffassung und Entwicklung", ["Erfasst neue Inhalte rasch.", "Setzt Rückmeldungen und neue Kenntnisse in der Praxis um."]),
    ("superiors", "Verhalten gegenüber Vorgesetzten", ["Verhält sich gegenüber Vorgesetzten respektvoll und korrekt."]),
    ("team", "Verhalten im Team", ["Arbeitet konstruktiv und hilfsbereit mit dem Team zusammen."]),
    ("customers", "Verhalten gegenüber Kundschaft", ["Tritt gegenüber Kundinnen und Kunden freundlich und professionell auf."]),
]
APPRENTICE_GROUPS = [
    ("school", "Berufsschule und Praxis", ["Überträgt das Berufsschulwissen sicher in die praktische Arbeit.", "Verknüpft Theorie und Praxis nachvollziehbar."]),
    ("development", "Entwicklung während der Lehre", ["Hat sich während der Lehrzeit fachlich kontinuierlich weiterentwickelt.", "Hat an Selbständigkeit und Verantwortung gewonnen."]),
]
PERFORMANCE_KEYS = ("knowledge", "quality", "quantity", "independence", "reliability", "initiative", "learning")
CONDUCT_KEYS = ("superiors", "team", "customers")


def question_groups(reference_type):
    return COMMON_GROUPS + (APPRENTICE_GROUPS if reference_type == "apprentice" else [])


def _score_dimensions(ratings, reference_type):
    scores = {}
    for key, title, questions in question_groups(reference_type):
        answers = []
        for index, _ in enumerate(questions, 1):
            value = ratings.get(f"{key}_{index}")
            if value is None and key in ratings:  # compatibility with certificates made in 0.11.0
                value = ratings[key]
            if value is None and key in CONDUCT_KEYS and "conduct" in ratings:
                value = ratings["conduct"]
            if value is None:
                raise ValueError(f"Bitte alle Fragen im Bereich «{title}» beantworten.")
            value = int(value)
            if value not in range(1, 6):
                raise ValueError(f"Die Antwort im Bereich «{title}» ist ungültig.")
            answers.append(value)
        scores[key] = int(sum(answers) / len(answers) + 0.5)
    return scores


def _person_words(employee):
    female = str(employee.get("salutation", "")).casefold().startswith("frau")
    male = str(employee.get("salutation", "")).casefold().startswith("herr")
    if female:
        return "Frau", "sie", "ihr", "Mitarbeiterin", "Lernende"
    if male:
        return "Herr", "er", "sein", "Mitarbeiter", "Lernender"
    return "", "die Person", "ihr", "Mitarbeitende Person", "lernende Person"


def generate_reference_text(employee, reference_type, issue_date, end_date, reason, tasks, ratings):
    """Create a truthful, benevolent certificate from the selected assessments."""
    if reference_type not in REFERENCE_TYPES:
        raise ValueError("Unbekannte Zeugnisart.")
    scores = _score_dimensions(ratings, reference_type)
    title, pronoun, possessive, role_word, apprentice_word = _person_words(employee)
    subject = pronoun[:1].upper() + pronoun[1:]
    name = f"{employee['first_name']} {employee['last_name']}"
    person = f"{title} {name}".strip()
    if not employee.get("job"):
        raise ValueError("Bitte zuerst die Funktion der Person unter Einstellungen erfassen.")
    if not title:
        raise ValueError("Bitte zuerst die Anrede der Person unter Einstellungen erfassen.")
    job = employee["job"]
    hired = display_date(employee.get("hired"))
    until = display_date(end_date) if end_date else "heute"
    birth = f", geboren am {display_date(employee['birth_date'])}," if employee.get("birth_date") else ""

    if reference_type == "apprentice":
        opening = (f"{person}{birth} absolvierte vom {hired} bis {until} in unserem Unternehmen die berufliche "
                   f"Grundbildung als {job}.")
    elif reference_type == "work":
        opening = f"{person}{birth} war vom {hired} bis {until} als {job} in unserem Unternehmen tätig."
    else:
        opening = f"{person}{birth} ist seit dem {hired} als {job} in unserem Unternehmen tätig."

    task_items = [part.strip(" •-\t") for part in str(tasks).replace(";", "\n").splitlines() if part.strip(" •-\t")]
    if not task_items:
        raise ValueError("Bitte die wichtigsten Funktionen und Tätigkeiten sachlich erfassen.")
    task_text = ""
    if task_items:
        task_text = "Zu den wesentlichen Aufgaben gehören insbesondere " + ", ".join(task_items[:-1])
        if len(task_items) > 1:
            task_text += " sowie " + task_items[-1]
        else:
            task_text += task_items[0]
        task_text += "."

    phrases = {
        "knowledge": [
            f"{person} setzte sich im Rahmen der übertragenen Aufgaben mit den erforderlichen Fachthemen auseinander.",
            f"{person} verfügt über grundlegende Fachkenntnisse und setzt diese unter Anleitung ein.",
            f"{person} verfügt über gute Fachkenntnisse und setzt diese sicher ein.",
            f"{person} verfügt über sehr gute und vielseitige Fachkenntnisse, die {pronoun} erfolgreich einsetzt.",
            f"{person} verfügt über ausserordentlich umfassende Fachkenntnisse und setzt diese jederzeit souverän ein.",
        ],
        "quality": [f"{person} bearbeitete die übertragenen Aufgaben mit Aufmerksamkeit.", "Die Arbeitsergebnisse waren insgesamt zweckmässig.", "Die Arbeitsergebnisse sind sorgfältig und von guter Qualität.", "Die Arbeitsergebnisse sind stets sehr sorgfältig und von hoher Qualität.", "Die Arbeitsergebnisse sind jederzeit hervorragend, präzise und von höchster Qualität."],
        "quantity": [f"{person} erledigte die übertragenen Aufgaben im vereinbarten Rahmen.", f"{person} bewältigte den üblichen Arbeitsanfall.", f"Auch bei höherer Belastung arbeitet {pronoun} effizient und zuverlässig.", f"Auch bei hoher Belastung arbeitet {pronoun} stets effizient und sicher.", f"Auch unter anspruchsvollsten Bedingungen arbeitet {pronoun} ausserordentlich effizient, belastbar und sicher."],
        "independence": [f"{person} führte die übertragenen Aufgaben nach Anleitung aus.", "Aufgaben werden mit Unterstützung ausgeführt.", "Aufgaben werden selbständig und zweckmässig ausgeführt.", "Aufgaben werden stets selbständig, vorausschauend und lösungsorientiert ausgeführt.", "Aufgaben werden jederzeit ausserordentlich selbständig, vorausschauend und mit ausgezeichnetem Urteilsvermögen ausgeführt."],
        "reliability": [f"{person} richtete die Arbeitsweise an den vereinbarten Vorgaben aus.", "Abmachungen und Termine werden im Wesentlichen eingehalten.", "Abmachungen und Termine werden zuverlässig eingehalten.", "Abmachungen und Termine werden stets sehr zuverlässig eingehalten.", "Auf {person} ist jederzeit uneingeschränkt Verlass; Abmachungen und Termine werden vorbildlich eingehalten.".format(person=person)],
        "initiative": [f"{subject} widmet sich den übertragenen Aufgaben.", f"{subject} zeigt den erwarteten Einsatz.", f"{subject} zeigt guten Einsatz und angemessene Eigeninitiative.", f"{subject} zeigt stets grossen Einsatz und viel Eigeninitiative.", f"{subject} überzeugt jederzeit durch ausserordentlichen Einsatz, Verantwortungsbewusstsein und Initiative."],
        "learning": [f"{person} setzte sich mit neuen Inhalten auseinander und nahm Hinweise auf.", "Neue Inhalte werden mit Unterstützung aufgenommen und umgesetzt.", "Neue Inhalte werden rasch verstanden und gut umgesetzt.", "Neue Inhalte werden sehr rasch verstanden, verknüpft und sicher umgesetzt.", "Die aussergewöhnlich schnelle Auffassungsgabe ermöglicht jederzeit eine ausgezeichnete Umsetzung selbst komplexer Inhalte."],
        "school": [f"{person} bezog Inhalte aus der Berufsschule in die praktische Arbeit ein.", "Das Berufsschulwissen wird mit Unterstützung praktisch angewendet.", "Das Berufsschulwissen wird gut und sicher in die Praxis übertragen.", "Das Berufsschulwissen wird sehr sicher und vernetzt in der Praxis eingesetzt.", "Theorie und Praxis werden jederzeit auf ausserordentlich hohem Niveau miteinander verbunden."],
        "development": [f"{person} sammelte während der Lehrzeit weitere fachliche und persönliche Erfahrungen.", f"Während der Lehrzeit entwickelte {person} die vorhandenen Kenntnisse weiter.", f"Während der Lehrzeit hat sich {person} gut und kontinuierlich entwickelt.", f"Während der Lehrzeit hat sich {person} sehr erfreulich und zielgerichtet entwickelt.", "Die Entwicklung während der gesamten Lehrzeit war ausserordentlich positiv und vorbildlich."],
        "superiors": ["Das Verhalten gegenüber Vorgesetzten war sachlich.", "Das Verhalten gegenüber Vorgesetzten war korrekt.", "Das Verhalten gegenüber Vorgesetzten war korrekt und respektvoll.", "Das Verhalten gegenüber Vorgesetzten war stets einwandfrei.", "Das Verhalten gegenüber Vorgesetzten war jederzeit vorbildlich."],
        "team": [f"{person} arbeitete im Rahmen der übertragenen Aufgaben mit dem Team zusammen.", "Die Zusammenarbeit im Team war korrekt.", "Die Zusammenarbeit im Team war gut.", "Die Zusammenarbeit im Team war stets sehr gut und hilfsbereit.", "Die Zusammenarbeit im Team war jederzeit vorbildlich, konstruktiv und sehr geschätzt."],
        "customers": ["Das Auftreten gegenüber der Kundschaft war sachlich.", "Das Verhalten gegenüber der Kundschaft war korrekt.", "Das Verhalten gegenüber der Kundschaft war freundlich und korrekt.", "Das Verhalten gegenüber der Kundschaft war stets freundlich, sicher und professionell.", "Das Verhalten gegenüber der Kundschaft war jederzeit ausgesprochen professionell und vorbildlich."],
    }
    assessed_keys = list(PERFORMANCE_KEYS) + (["school", "development"] if reference_type == "apprentice" else [])
    assessment = [phrases[key][scores[key] - 1] for key in assessed_keys]
    overall = int(sum(scores[key] for key in PERFORMANCE_KEYS) / len(PERFORMANCE_KEYS) + 0.5)
    performance = {
        5: f"Die Gesamtleistung von {person} ist ausgezeichnet und übertrifft die Anforderungen deutlich.",
        4: f"Die Gesamtleistung von {person} ist sehr gut und übertrifft die Anforderungen in mehreren Bereichen.",
        3: f"Die Gesamtleistung von {person} ist gut und erfüllt die Anforderungen.",
        2: f"Die Gesamtleistung von {person} entsprach den grundlegenden Anforderungen.",
        1: f"{person} erfüllte die übertragenen Aufgaben im Rahmen der Vorgaben.",
    }[overall]
    conduct_text = " ".join(phrases[key][scores[key] - 1] for key in CONDUCT_KEYS)

    if reference_type == "interim":
        cause = reason.strip() or "auf Wunsch"
        wording = cause if cause.casefold().startswith(("auf ", "wegen ", "anlässlich ")) else "aus " + cause
        close = (f"Dieses Zwischenzeugnis wird {wording} ausgestellt. "
                 f"Wir danken {person} für den bisherigen Einsatz und freuen uns auf die weitere Zusammenarbeit.")
    else:
        if reference_type == "work":
            close = f"{person} verlässt unser Unternehmen per {until}"
            close += (f" {reason.strip()}." if reason.strip() else ".")
        else:
            close = f"Das Lehrverhältnis endet per {until}."
            if reason.strip():
                close += f" {reason.strip().rstrip('.')}."
        close += (f" Wir danken {person} für {possessive} Engagement und wünschen für die berufliche und "
                  "persönliche Zukunft alles Gute.")

    paragraphs = [opening]
    if task_text:
        paragraphs.append(task_text)
    paragraphs.extend([" ".join(assessment), performance, conduct_text, close])
    return "\n\n".join(paragraphs)


def reference_pdf(path, reference, employee, settings):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontName="Helvetica", fontSize=10.5,
                          leading=15, spaceAfter=10, textColor=colors.HexColor("#172f3d"))
    title_style = ParagraphStyle("Title", parent=styles["Title"], fontName="Helvetica-Bold",
                                 fontSize=18, leading=22, alignment=TA_CENTER, textColor=colors.black,
                                 spaceAfter=16)
    small = ParagraphStyle("Small", parent=body, fontSize=8.5, leading=11, textColor=colors.HexColor("#536b79"))

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#b9c9cf"))
        canvas.line(22 * mm, 17 * mm, 188 * mm, 17 * mm)
        canvas.setFont("Helvetica", 7.2)
        canvas.setFillColor(colors.HexColor("#536b79"))
        company = settings.get("company", "AST Elektro Tüscher AG")
        address = " · ".join(filter(None, [settings.get("address", ""),
                                             (settings.get("postcode", "") + " " + settings.get("city", "")).strip()]))
        canvas.drawString(22 * mm, 11 * mm, company)
        canvas.drawCentredString(105 * mm, 11 * mm, address)
        canvas.drawRightString(188 * mm, 11 * mm, settings.get("phone", ""))
        online = " · ".join(filter(None, [settings.get("email", ""), settings.get("website", "")]))
        canvas.drawRightString(188 * mm, 7.5 * mm, online)
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, rightMargin=22 * mm, leftMargin=22 * mm,
                            topMargin=20 * mm, bottomMargin=24 * mm,
                            title=REFERENCE_TYPES[reference["reference_type"]], author=settings.get("company", "AST"))
    story = []
    logo_path = Path(settings.get("logo_path", ""))
    if not logo_path.is_file():
        logo_path = resource_path("assets/logo_ast_black.png")
    if logo_path.is_file():
        logo = Image(str(logo_path), width=70 * mm, height=36 * mm, kind="proportional")
        logo.hAlign = "LEFT"
        story.extend([logo, Spacer(1, 8 * mm)])
    story.append(Paragraph(REFERENCE_TYPES[reference["reference_type"]], title_style))
    story.append(Paragraph(f"<b>{escape(employee['first_name'] + ' ' + employee['last_name'])}</b>", body))
    story.append(Spacer(1, 4 * mm))
    for paragraph in reference["text"].split("\n\n"):
        if paragraph.strip():
            story.append(Paragraph(escape(paragraph.strip()).replace("\n", "<br/>"), body))
    place = settings.get("city", "Aarburg")
    issued = display_date(reference["issue_date"])
    company = escape(settings.get("company", "AST Elektro Tüscher AG"))
    contact = escape(settings.get("contact", ""))
    story.extend([Spacer(1, 10 * mm), Paragraph(f"{escape(place)}, {issued}", body), Spacer(1, 14 * mm),
                  KeepTogether([Paragraph(f"<b>{company}</b>", body), Spacer(1, 8 * mm),
                                Paragraph("__________________________________", small),
                                Paragraph(contact or "Unterschrift", small)])])
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return path


class ReferenceDialog(QDialog):
    def __init__(self, parent, db, row=None):
        super().__init__(parent)
        self.db, self.row = db, row or {}
        self.setWindowTitle("Zeugnis bearbeiten" if row else "Neues Zeugnis")
        self.resize(820, 720)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.addWidget(label(self.windowTitle(), "dialogTitle"))
        self.step_label = label("", "sectionTitle")
        layout.addWidget(self.step_label)
        self.tabs = QTabWidget()
        self.tabs.tabBar().hide()
        layout.addWidget(self.tabs, 1)

        first = QFormLayout()
        first_widget = QWidget()
        first_widget.setLayout(first)
        employees = db.employees()
        self.person = combo([(f"{e['first_name']} {e['last_name']} · {e['code']}", e["id"]) for e in employees], self.row.get("employee_id"))
        self.kind = combo([(title, key) for key, title in REFERENCE_TYPES.items()], self.row.get("reference_type", "work"))
        self.issue = day(self.row.get("issue_date"))
        self.end = day(self.row.get("end_date") or date.today().isoformat())
        self.reason = line(self.row.get("reason", ""), "z. B. auf eigenen Wunsch / Funktionswechsel")
        self.tasks = QPlainTextEdit(self.row.get("tasks", ""))
        self.tasks.setPlaceholderText("Eine Aufgabe pro Zeile, z. B. Installationen in Neu- und Umbauten")
        first.addRow("Person", self.person)
        first.addRow("Zeugnisart", self.kind)
        first.addRow("Ausgestellt am", self.issue)
        first.addRow("Enddatum / Stichtag", self.end)
        first.addRow("Grund / Anlass", self.reason)
        first.addRow("Aufgaben", self.tasks)
        self.tabs.addTab(first_widget, "Grundlagen")

        ratings_widget = QWidget()
        ratings_layout = QVBoxLayout(ratings_widget)
        ratings_hint = label("Beantworte jede Aussage nach dem tatsächlich beobachteten Verhalten. AST leitet daraus die Beurteilung ab und formuliert das vollständige Zeugnis.", "muted")
        ratings_hint.setWordWrap(True)
        ratings_layout.addWidget(ratings_hint)
        common_widget = QWidget(); common_layout = QVBoxLayout(common_widget)
        saved_ratings = self.row.get("ratings", {})
        self.ratings = {}
        for key, title, questions in COMMON_GROUPS:
            common_layout.addWidget(label(title, "sectionTitle"))
            for index, question in enumerate(questions, 1):
                legacy = saved_ratings.get("conduct") if key in CONDUCT_KEYS else None
                value = saved_ratings.get(f"{key}_{index}", saved_ratings.get(key, legacy))
                field = combo(ANSWER_CHOICES, value)
                field.setMinimumWidth(170); field.setMaximumWidth(210)
                row_layout = QHBoxLayout()
                question_label = label(question); question_label.setWordWrap(True)
                row_layout.addWidget(question_label, 1); row_layout.addWidget(field)
                common_layout.addLayout(row_layout)
                self.ratings[f"{key}_{index}"] = field
        ratings_layout.addWidget(common_widget)
        self.apprentice_box = QWidget(); apprentice_layout = QVBoxLayout(self.apprentice_box)
        apprentice_layout.addWidget(label("Zusätzliche Fragen für Lehrzeugnisse", "sectionTitle"))
        for key, title, questions in APPRENTICE_GROUPS:
            apprentice_layout.addWidget(label(title, "sectionTitle"))
            for index, question in enumerate(questions, 1):
                value = saved_ratings.get(f"{key}_{index}", saved_ratings.get(key))
                field = combo(ANSWER_CHOICES, value)
                field.setMinimumWidth(170); field.setMaximumWidth(210)
                row_layout = QHBoxLayout()
                question_label = label(question); question_label.setWordWrap(True)
                row_layout.addWidget(question_label, 1); row_layout.addWidget(field)
                apprentice_layout.addLayout(row_layout)
                self.ratings[f"{key}_{index}"] = field
        ratings_layout.addWidget(self.apprentice_box)
        ratings_layout.addStretch()
        ratings_scroll = QScrollArea(); ratings_scroll.setWidgetResizable(True); ratings_scroll.setWidget(ratings_widget)
        self.tabs.addTab(ratings_scroll, "Beurteilung")

        text_widget = QWidget()
        text_layout = QVBoxLayout(text_widget)
        text_note = label("Automatisch aus den Antworten erstellt. Ändere Antworten über «Zurück»; der Zeugnistext selbst wird nicht manuell verfasst.", "muted")
        text_note.setWordWrap(True)
        text_layout.addWidget(text_note)
        self.text = QPlainTextEdit(self.row.get("text", ""))
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(420)
        text_layout.addWidget(self.text, 1)
        self.tabs.addTab(text_widget, "Text prüfen")

        buttons = QDialogButtonBox()
        buttons.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        self.back = buttons.addButton("Zurück", QDialogButtonBox.ButtonRole.ActionRole)
        self.next = buttons.addButton("Weiter", QDialogButtonBox.ButtonRole.ActionRole)
        self.save = buttons.addButton("Zeugnis speichern", QDialogButtonBox.ButtonRole.AcceptRole)
        self.next.setObjectName("primary"); self.save.setObjectName("primary")
        self.back.clicked.connect(lambda: self.set_step(self.tabs.currentIndex() - 1))
        self.next.clicked.connect(self.next_step)
        buttons.rejected.connect(self.reject); buttons.accepted.connect(self.submit)
        layout.addWidget(buttons)
        self.person.currentIndexChanged.connect(self._person_changed)
        self.kind.currentIndexChanged.connect(self._kind_changed)
        self.set_step(0)
        self._person_changed()
        self._kind_changed()

    def _person_changed(self):
        employee = self.db.employee(self.person.currentData())
        if employee and employee["kind"] == "apprentice" and not self.row:
            self.kind.setCurrentIndex(self.kind.findData("apprentice"))

    def _kind_changed(self):
        self.apprentice_box.setVisible(self.kind.currentData() == "apprentice")

    def active_question_ids(self):
        return [f"{key}_{index}" for key, _, questions in question_groups(self.kind.currentData())
                for index, _ in enumerate(questions, 1)]

    def set_step(self, index):
        index = max(0, min(2, index))
        self.tabs.setCurrentIndex(index)
        self.step_label.setText(f"Schritt {index + 1} von 3 · {['Grundlagen', 'Beurteilung', 'Text prüfen'][index]}")
        self.back.setVisible(index > 0); self.next.setVisible(index < 2); self.save.setVisible(index == 2)

    @guarded
    def next_step(self):
        if not self.person.currentData():
            raise ValueError("Bitte zuerst eine Person auswählen.")
        if self.tabs.currentIndex() == 0 and not self.tasks.toPlainText().strip():
            raise ValueError("Bitte die wichtigsten Funktionen und Tätigkeiten erfassen.")
        if self.tabs.currentIndex() == 1:
            self.generate()
        self.set_step(self.tabs.currentIndex() + 1)

    def values(self):
        return {"employee_id": self.person.currentData(), "reference_type": self.kind.currentData(),
                "issue_date": day_value(self.issue), "end_date": day_value(self.end),
                "reason": self.reason.text(), "tasks": self.tasks.toPlainText(),
                "ratings": {key: self.ratings[key].currentData() for key in self.active_question_ids()},
                "text": self.text.toPlainText()}

    @guarded
    def generate(self):
        values = self.values()
        employee = self.db.employee(values["employee_id"])
        self.text.setPlainText(generate_reference_text(employee, values["reference_type"], values["issue_date"],
                                                       values["end_date"], values["reason"], values["tasks"],
                                                       values["ratings"]))

    @guarded
    def submit(self):
        self.generate()
        self.saved_id = self.db.save_reference(self.values(), self.row.get("id"))
        self.accept()


class ReferencesPage(Page):
    def __init__(self, db):
        super().__init__("Zeugnisse", "Arbeits-, Zwischen- und Lehrzeugnisse geführt beurteilen, prüfen und als PDF ausgeben.")
        self.db, self.rows = db, []
        self.header.addWidget(button("+ Neues Zeugnis", self.new, True))
        self.table = Table(["Person", "Zeugnisart", "Ausgestellt", "Stichtag", "Zuletzt bearbeitet"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.layout.addWidget(self.table, 1)
        row = QHBoxLayout()
        self.hint = label("Bitte ein Zeugnis auswählen.", "muted")
        row.addWidget(self.hint, 1)
        self.edit_button = button("Bearbeiten", self.edit)
        self.preview_button = button("PDF ansehen", self.preview)
        self.export_button = button("PDF speichern", self.export, True)
        self.delete_button = button("Löschen", self.remove)
        for control in (self.edit_button, self.preview_button, self.export_button, self.delete_button):
            row.addWidget(control)
        self.layout.addLayout(row)
        self.table.itemSelectionChanged.connect(self.selection)
        self.table.cellDoubleClicked.connect(self.edit)

    def refresh(self):
        self.rows = self.db.references()
        self.table.populate([[row["name"], REFERENCE_TYPES[row["reference_type"]], display_date(row["issue_date"]),
                              display_date(row["end_date"]), row["updated"].replace("T", " ")]
                             for row in self.rows], [row["id"] for row in self.rows])
        self.selection()

    def selected(self):
        key = self.table.selected_id()
        return next((row for row in self.rows if row["id"] == key), None)

    def selection(self):
        row = self.selected()
        for control in (self.edit_button, self.preview_button, self.export_button, self.delete_button):
            control.setEnabled(bool(row))
        self.hint.setText(f"{row['name']} · {REFERENCE_TYPES[row['reference_type']]}" if row else "Bitte ein Zeugnis auswählen.")

    def new(self):
        if not self.db.employees():
            QMessageBox.information(self, "Noch keine Person", "Bitte zuerst unter Einstellungen eine Person erfassen.")
            return
        if ReferenceDialog(self, self.db).exec():
            self.refresh()

    def edit(self, *_):
        row = self.selected()
        if row and ReferenceDialog(self, self.db, self.db.reference(row["id"])).exec():
            self.refresh()

    def _make_pdf(self, path):
        row = self.selected()
        if not row:
            return
        reference_pdf(path, row, self.db.employee(row["employee_id"]), self.db.settings())

    @guarded
    def preview(self):
        row = self.selected()
        if not row:
            return
        path = self.db.path.parent / "preview-zeugnis.pdf"
        self._make_pdf(path)
        PdfPreview(self, path).exec()

    @guarded
    def export(self):
        row = self.selected()
        if not row:
            return
        employee = self.db.employee(row["employee_id"])
        filename = f"{REFERENCE_TYPES[row['reference_type']]}_{employee['last_name']}_{employee['first_name']}.pdf".replace(" ", "_")
        path = save_path(self, "Zeugnis als PDF speichern", filename, "pdf", "references_pdf")
        if path:
            self._make_pdf(path)
            QMessageBox.information(self, "Zeugnis gespeichert", path)

    @guarded
    def remove(self):
        row = self.selected()
        if row and confirm(self, "Zeugnis löschen", "Soll dieses Zeugnis wirklich gelöscht werden?"):
            self.db.delete("employment_references", row["id"])
            self.refresh()
