"""Searchable, maintainable in-app help based on implemented AST workflows."""
from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QListWidget, QListWidgetItem, QTextBrowser, QVBoxLayout, QWidget

from .widgets import Page, line, label


HELP_TOPICS = [
    {
        "id": "overview", "title": "Übersicht und erste Schritte",
        "keywords": "start beginnen einrichten dashboard offene rechnungen",
        "summary": "Die Übersicht zeigt die wichtigsten offenen Aufgaben und führt direkt zu häufigen Arbeiten.",
        "steps": [
            "Hinterlege zuerst unter «Einstellungen» die Firmendaten.",
            "Erfasse anschliessend mindestens eine Person im Team.",
            "Nutze die drei Direktaktionen für Rechnungen, Arbeitszeit oder Lohnausweise.",
            "Offene und überfällige Rechnungen erscheinen darunter zur direkten Bearbeitung.",
        ],
        "notes": "Wenn noch Stammdaten fehlen, zeigt die Übersicht den nächsten Einrichtungsschritt an.",
    },
    {
        "id": "debtors", "title": "Debitoren und Zahlungen",
        "keywords": "rechnung kunde zahlung teilzahlung offen bezahlt csv pdf excel import",
        "summary": "Hier werden Rechnungen, Fälligkeiten, Teilzahlungen und offene Beträge verwaltet.",
        "steps": [
            "Erstelle mit «Neue Rechnung» eine Rechnung oder importiere eine bestehende Excel-Liste.",
            "Wähle eine Tabellenzeile aus. Mit Strg oder Umschalt kannst du mehrere Zeilen markieren.",
            "Erfasse Zahlungseingänge über «Zahlung erfassen» oder ändere die Rechnungsdetails.",
            "Nutze «Weitere Aktionen» für PDF, Druck, CSV oder das Löschen markierter Rechnungen.",
        ],
        "notes": "Status- und Zeitraumfilter verändern nur die Anzeige. Gespeicherte Daten bleiben erhalten.",
    },
    {
        "id": "reminders", "title": "Mahnungen",
        "keywords": "mahnung mahnstufe betreibung erinnerung brief text platzhalter",
        "summary": "Mahnungen erzeugen druckfertige Briefe aus offenen Forderungen oder manuellen Angaben.",
        "steps": [
            "Wähle eine offene Rechnung oder erstelle eine manuelle Mahnung.",
            "Lege die Mahnstufe und die neue Zahlungsfrist fest.",
            "Prüfe den Brieftext. Platzhalter werden mit den Rechnungs- und Kundendaten ersetzt.",
            "Erstelle den Mahnbrief als PDF und speichere danach bei Bedarf die Mahnstufe.",
        ],
        "notes": "Firmendaten und Logo stammen aus den Einstellungen. Fehlende Pflichtangaben werden vor dem Export gemeldet.",
    },
    {
        "id": "timesheet", "title": "Stundennachweis",
        "keywords": "stunden arbeitszeit ferien krankheit unfall minderzeit rapport zeitraum excel eintritt",
        "summary": "Arbeitszeiten und Abwesenheiten werden pro Person erfasst und in die Jahresvorlage exportiert.",
        "steps": [
            "Wähle eine Person und öffne ihren Stundennachweis.",
            "Nutze «Arbeitstag erfassen» für einen einzelnen Tag oder «Zeitraum erfassen» für mehrere Tage.",
            "Wähle bei Abweichungen Ferien, Krankheit, Unfall, Feiertag oder andere begründete Minderzeit.",
            "Aktiviere die Berücksichtigung des Eintritts, damit frühere Tage sowie Sollzeit und Ferienanspruch korrekt abgegrenzt werden.",
            "Speichere den Jahresnachweis als Excel-Datei oder erstelle die PDF-Ausgabe.",
        ],
        "notes": "Montag bis Donnerstag gelten 8.75 Stunden, Freitag 8.25 Stunden. Rapportnummern bleiben in AST und werden nicht nach Excel übertragen.",
    },
    {
        "id": "payroll", "title": "Lohnbuch",
        "keywords": "lohn monatslohn netto brutto abzug bvg ahv alv import excel verlauf diagramm",
        "summary": "Das Lohnbuch berechnet den Nettolohn aus Monatslohn, Zulagen und den erfassten Abzügen.",
        "steps": [
            "Wähle Person und Jahr und erfasse den Monatslohn.",
            "Lege beim BVG fest, ob der Abzug prozentual oder als fixer Betrag berechnet wird.",
            "Importiere bei Bedarf mehrere bestehende AST-Lohnbücher gleichzeitig.",
            "Prüfe Monatswerte und Nettolohn und speichere das Jahr als Excel-Datei.",
            "Im Register «Lohnverlauf» vergleichst du Monat, Jahr, fünf Jahre oder den gesamten Zeitraum.",
        ],
        "notes": "Der Import ist für das von AST erzeugte Layout ausgelegt. Prüfe nach einem Import Person, Jahr und Monatswerte.",
    },
    {
        "id": "references", "title": "Zeugnisse",
        "keywords": "arbeitszeugnis zwischenzeugnis lehrzeugnis bewertung pdf",
        "summary": "Ein geführter Assistent erstellt Arbeits-, Zwischen- und Lehrzeugnisse aus Stammdaten und Bewertungen.",
        "steps": [
            "Starte ein neues Zeugnis und wähle Person, Zeugnisart und Stichtag.",
            "Ergänze Tätigkeiten und beantworte die angezeigten Beurteilungsfragen.",
            "Prüfe den erzeugten, schreibgeschützten Zeugnistext.",
            "Speichere das Zeugnis und kontrolliere die PDF-Vorschau vor dem Export.",
        ],
        "notes": "Nicht beantwortete Fragen werden nicht in den Text aufgenommen. Personendaten stammen aus den Stammdaten.",
    },
    {
        "id": "applications", "title": "Bewerbungen",
        "keywords": "bewerbung dossier beurteilung webserver ftp dokument notiz geeignet",
        "summary": "Bewerbungsdossiers können manuell oder über den eingerichteten Webserver übernommen und intern beurteilt werden.",
        "steps": [
            "Lies neue Dossiers vom Webserver ein oder erfasse eine Bewerbung manuell.",
            "Öffne «Beurteilung & Dossier», um Angaben und Dokumente zu prüfen.",
            "Speichere interne Notizen und wähle Nicht geeignet, Eventuell oder Geeignet.",
            "Öffne Anhänge direkt oder speichere eine lokale Kopie.",
        ],
        "notes": "Bei «Nicht geeignet» ist eine Bestätigung nötig. Erst danach werden verifizierte Serverdateien gelöscht; die lokale Dokumentation bleibt bestehen.",
    },
    {
        "id": "salary", "title": "Lohnausweise",
        "keywords": "lohnausweis lohn abzug pdf steuer jahr formular",
        "summary": "Der Assistent führt durch Person, Lohnangaben, Zusatzangaben und Schlusskontrolle des Lohnausweises.",
        "steps": [
            "Erstelle einen neuen Lohnausweis und übernimm die aktuellen Stammdaten.",
            "Erfasse Lohn, Abzüge und die tatsächlich benötigten Zusatzangaben.",
            "Wechsle mit «Nächster Schritt» bis zur Schlusskontrolle.",
            "Speichere den Ausweis und prüfe ihn über «PDF ansehen», bevor du ihn exportierst.",
        ],
        "notes": "Netto- und Summenfelder werden aus den erfassten Beträgen berechnet. Änderungen erfolgen in AST und werden danach neu exportiert.",
    },
    {
        "id": "settings", "title": "Einstellungen und Datensicherung",
        "keywords": "einstellungen team person firma kunde logo backup sicherung update exportpfad excel web synchronisation",
        "summary": "Hier werden Team, Kunden, Firmendaten, Exportordner, Sicherungen, Darstellung und Updates zentral verwaltet.",
        "steps": [
            "Pflege Personen und Kunden nur einmal in den jeweiligen Registern.",
            "Kontrolliere Firmendaten und Logo, da sie in Dokumente übernommen werden.",
            "Lege Exportordner fest und richte bei Bedarf den vertrauenswürdigen Excel-Zugriff ein.",
            "Erstelle regelmässig Sicherungen und prüfe den externen Sicherungsordner.",
            "Installiere verfügbare Aktualisierungen im Updatebereich.",
        ],
        "notes": "Eine Wiederherstellung ersetzt den aktuellen Datenstand und verlangt deshalb eine Bestätigung. Vorher wird automatisch eine Sicherung angelegt.",
    },
    {
        "id": "tables", "title": "Tabellen bedienen",
        "keywords": "tabelle zeile spalte markieren mehrfach sortieren ausblenden strg umschalt",
        "summary": "Alle zentralen Listen besitzen dieselbe Auswahl- und Anpassungslogik.",
        "steps": [
            "Klicke eine Zeile an, um sie auszuwählen.",
            "Halte Strg für einzelne zusätzliche Zeilen oder Umschalt für einen zusammenhängenden Bereich gedrückt.",
            "Ziehe Spalten- oder Zeilenköpfe, um die Reihenfolge zu ändern.",
            "Klicke einen Kopf mit der rechten Maustaste an, um Einträge aus- oder wieder einzublenden.",
        ],
        "notes": "Reihenfolge und Sichtbarkeit werden gespeichert. Mit «Spalten zurücksetzen» beziehungsweise «Zeilenreihenfolge zurücksetzen» kehrst du zur Vorgabe zurück.",
    },
]


class HelpPage(Page):
    def __init__(self):
        super().__init__("Hilfe & Anleitungen", "Funktionen finden und Schritt für Schritt sicher bedienen.", help_topic=None)
        self.search = line(placeholder="Funktion oder Frage suchen …")
        self.search.setAccessibleName("Hilfe durchsuchen")
        self.search.setClearButtonEnabled(True)
        self.layout.addWidget(self.search)

        content = QHBoxLayout()
        content.setSpacing(16)
        self.topics = QListWidget()
        self.topics.setObjectName("helpTopics")
        self.topics.setMinimumWidth(270)
        self.topics.setMaximumWidth(350)
        self.article = QTextBrowser()
        self.article.setObjectName("helpArticle")
        self.article.setOpenExternalLinks(True)
        self.article.document().setDefaultStyleSheet(
            "body{font-family:'Segoe UI';font-size:10pt;color:#183342;}"
            "h1{font-size:22pt;color:#163443;margin:0 0 12px 0;}"
            "h2{font-size:13pt;color:#163443;margin-top:22px;}"
            ".lead{font-size:11pt;color:#486574;margin-bottom:18px;}"
            "li{margin:7px 0;} .note{background:#e8f4f0;border-left:4px solid #2d9b83;padding:12px;}"
        )
        content.addWidget(self.topics)
        content.addWidget(self.article, 1)
        self.layout.addLayout(content, 1)
        self.no_results = label("Keine passende Anleitung gefunden. Versuche einen einfacheren Begriff.", "emptyState")
        self.no_results.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_results.hide()
        self.layout.addWidget(self.no_results)

        self.search.textChanged.connect(self._filter)
        self.topics.currentItemChanged.connect(self._show_current)
        self._filter("")

    def refresh(self):
        pass

    def open_topic(self, topic_id: str | None):
        self.search.clear()
        for index in range(self.topics.count()):
            item = self.topics.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == topic_id:
                self.topics.setCurrentItem(item)
                self.topics.scrollToItem(item)
                return
        if self.topics.count():
            self.topics.setCurrentRow(0)

    def _filter(self, value: str):
        query = " ".join(value.lower().split())
        current_id = self.topics.currentItem().data(Qt.ItemDataRole.UserRole) if self.topics.currentItem() else None
        self.topics.clear()
        for topic in HELP_TOPICS:
            haystack = " ".join((topic["title"], topic["keywords"], topic["summary"], *topic["steps"], topic["notes"])).lower()
            if not query or all(word in haystack for word in query.split()):
                item = QListWidgetItem(topic["title"])
                item.setData(Qt.ItemDataRole.UserRole, topic["id"])
                self.topics.addItem(item)
                if topic["id"] == current_id:
                    self.topics.setCurrentItem(item)
        has_results = self.topics.count() > 0
        self.topics.setVisible(has_results)
        self.article.setVisible(has_results)
        self.no_results.setVisible(not has_results)
        if has_results and self.topics.currentRow() < 0:
            self.topics.setCurrentRow(0)

    def _show_current(self, item, _previous=None):
        if item is None:
            return
        topic_id = item.data(Qt.ItemDataRole.UserRole)
        topic = next(topic for topic in HELP_TOPICS if topic["id"] == topic_id)
        steps = "".join(f"<li>{html.escape(step)}</li>" for step in topic["steps"])
        self.article.setHtml(
            f"<h1>{html.escape(topic['title'])}</h1>"
            f"<p class='lead'>{html.escape(topic['summary'])}</p>"
            f"<h2>So gehst du vor</h2><ol>{steps}</ol>"
            f"<h2>Gut zu wissen</h2><div class='note'>{html.escape(topic['notes'])}</div>"
        )
