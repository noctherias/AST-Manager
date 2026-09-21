# AST Manager

Funktionsfähiges Windows-Desktop-MVP in Python. Fünf übersichtliche Arbeitsbereiche, zentrale SQLite-Datenbank, native Stundenberechnung und Ausgabe in der bereitgestellten Lohnausweis-PDF. Excel wird weder benötigt noch gestartet.

## Sofort ausprobieren

**Empfohlen:** Im [neuesten Release](https://github.com/manueltuescher/AST-Manager/releases/latest) `AST-Verwaltung-Setup-x64.exe` laden und installieren. Danach AST Manager über das Startmenü öffnen. Updates lassen sich direkt im Programm installieren; für das private Repository einmalig den GitHub-Zugang hinterlegen (siehe [Updates einrichten](docs/UPDATES.md)).

**Portable Windows-Version:** Das komplette Windows-Paket entpacken. `Demo starten.bat` öffnet eine getrennte Demo mit fiktiven Personen, Rechnungen, Stunden und einem Lohnausweis. `AST-Verwaltung.exe` öffnet die zunächst leere produktive Datenbank. Der Ordner `_internal` muss neben der EXE bleiben. Python und Excel sind nicht nötig. Die Datenerfassung funktioniert offline; nur die Update-Suche benötigt Internet.

**Aus dem Quellcode:** Python 3.12, 64 Bit, installieren und `start_demo.bat` doppelklicken. Beim ersten Start werden die Bibliotheken aus `requirements.txt` in eine lokale `.venv` installiert. Dafür ist Internet nötig. Danach startet die App offline. `start.bat` öffnet die produktive Datenbank.

Getestet unter Windows 11 x64 mit Python 3.12.14 und PySide6 6.11.2. Mindestfenstergrösse 1120 × 720 logische Pixel; 1380 × 880 oder grösser empfohlen.

## Bedienung

1. **Start:** Direkteinstieg für Rechnung, Zeit und Lohnausweis. Offene Rechnungen mit Fälligkeit stehen darunter. Bei einem leeren Datenbestand helfen Hinweise beim Einrichten.
2. **Rechnungen:** Die Ansicht startet mit offenen Rechnungen. «Bezahlt» und «Alle» wechseln die Auswahl. Rechnung auswählen, dann **Zahlung erfassen** oder **Details bearbeiten**. Die Zahlung wird gespeichert und der Dialog geschlossen. Bisherige Zahlungen sind im Dialog aufklappbar. Zeitraumfilter und Export liegen bei den weiteren Optionen.
3. **Team:** Mitarbeiter und Lernende stehen in einer gemeinsamen Liste mit Filtern. **Neue Person** schlägt eine Personalnummer vor; ergänzende Personalangaben sind aufklappbar. Nach dem Anlegen wird das erste Jahr eingerichtet. Person auswählen → **Zeit erfassen** oder **Nachweis öffnen**. Im Nachweis bleiben Guthaben und Buchungen sichtbar; Berechnung und Vorjahre lassen sich bei Bedarf aufklappen. **Person & Jahre** enthält Stammdaten und Folgejahre.
4. **Lohnausweise:** Vier Schritte führen durch Person/Zeitraum, Lohn/Abzüge, Zusatzangaben und abschliessende Prüfung. Die häufigen Lohnfelder stehen zuerst. Nach dem Speichern **PDF ansehen** oder **PDF speichern** wählen.
5. **Einstellungen:** Firmendaten, Kunden, Datensicherung und Updates. Firmendaten werden beim Verlassen eines Feldes oder Bereichs gespeichert und für künftige Lohnausweise übernommen. Personen werden zentral im Team gepflegt.

Erfassungsdialoge speichern erst mit **Speichern**. Abbrechen verwirft die Eingaben. `F5` aktualisiert die aktuelle Seite. Listen erklären, welche Auswahl für die nächste Aktion nötig ist. Grössere Formulare und ausgeklappte Details können gescrollt werden.

Ferienanspruch wird in Stunden vereinbart (Vorlagenwert 216.25 h); das Pensum reduziert ihn nicht nochmals automatisch. 1.50 h entsprechen 90 Minuten. Für ein erstes Jahr lassen sich bestehende Guthaben übernehmen, Folgejahre berechnen Überträge automatisch. Personen mit bestehenden Daten können auf inaktiv gesetzt werden.

## Übernommene Vorlagenlogik

- Debitoren: bezahlte Beträge werden wie `SUM(G:G)` summiert. Teilzahlungen, Restbetrag, Fälligkeit und Status ergänzen die einfache Liste.
- Stunden: `Guthaben = Vorperioden-Guthaben + Ferienanspruch − Ferienbezug + Überzeit`. Negative Guthaben sind erlaubt und werden hervorgehoben. Krankheit und Unfall summieren sich separat über die Perioden. Frühere Korrekturen aktualisieren alle späteren Salden.
- Die drei Lehrjahre der allgemeinen Vorlage und die zwei Lehrjahre der Lernenden-Vorlage verwenden denselben Kern. Die App hat keine feste Begrenzung für Jahre oder Buchungszeilen.
- Lohnausweis: Brutto aus den neun Betragsfeldern der Ziffern 1–7; Abzüge aus 9, 10.1 und 10.2; Netto = Brutto − Abzüge. Quellensteuer und Spesen werden wie im Original separat ausgewiesen.

Die vollständige Analyse steht in [docs/VORLAGENANALYSE.md](docs/VORLAGENANALYSE.md), das maschinenlesbare Inventar inklusive jeder Formel, Abhängigkeit, Datenvalidierung, benannter Bereiche, Druckeinstellungen und PDF-Felddefinitionen in [docs/template_inventory.json](docs/template_inventory.json).

## Datenspeicherung

Standard: `%LOCALAPPDATA%\AST-Erfassungstool\`.

- `ast.sqlite3`: produktive Daten.
- `ast-demo.sqlite3`: getrennte Demodaten.
- `backups\`: tägliche Start-Sicherungen und Sicherungen vor einer Wiederherstellung.
- `vorschau\`: erzeugte PDF-Vorschauen.
- `credentials\`: separat mit Windows verschlüsselter GitHub-Zugang.
- `updates\`: heruntergeladene und geprüfte Setups.
- `ast.log`: Fehlermeldungen.

Ein anderer Ordner lässt sich mit `python main.py --data-dir "D:\AST-Daten"` wählen. Eine zweite Instanz derselben Datenbank wird verhindert. Die App ist für einen lokalen Arbeitsplatz gedacht. Die SQLite-Datei ist nicht verschlüsselt; sie übernimmt die Windows-Dateizugriffsrechte. Sicherungen werden nicht automatisch auf ein externes Laufwerk übertragen.

## Projektstruktur

```text
main.py                    Programmstart, Datenpfad, Sperre, tägliche Sicherung
ast_app/
  database.py              Schema, Transaktionen, Stammdaten, CRUD, Sicherungen
  domain.py                Berechnungen und Validierung ohne Excel
  dialogs.py               Eingabemasken
  experience.py            Fünf geführte Arbeitsbereiche
  pages.py                 Gemeinsame Datenaktionen, PDF-Vorschau, Auswertungen
  updates.py / update_ui.py Release-Prüfung, Download und Updatefenster
  credentials.py           Geschützter GitHub-Zugang mit Windows DPAPI
  widgets.py / theme.py     Wiederverwendbare UI und Gestaltung
  window.py                Hauptfenster und Navigation
  documents.py             Original-PDF befüllen, Berichte, CSV
  demo.py                  Fiktive Demo, nur im Demomodus
templates/                 Vier unveränderte Originaldateien
docs/                      Vorlagenanalyse und Testprotokoll
tests/                     Fachlogik, Vorlagenvergleich, Datenbank, PDF, UI
tools/                     Reproduzierbare Analyse und Build-Hilfen
scripts/                   Windows-Start-, Test- und Build-Skripte
assets/                    Anwendungssymbol
requirements*.txt          Fixierte Abhängigkeiten
AST-Verwaltung.spec        Windows-Build-Konfiguration
installer/                 Windows-Setup und Neustart nach Updates
.github/workflows/         Tests und automatische Releases
release_config.json        Mitgelieferte Repository-Verbindung
```

## Tests und eigener Build

`test.bat` installiert zusätzlich die Entwicklungsabhängigkeiten und führt die Tests aus. `build.bat` testet zuerst und erstellt anschliessend `dist\AST-Verwaltung\AST-Verwaltung.exe` samt benötigtem `_internal`-Ordner. `build_setup.bat` erstellt anschliessend das Setup (Inno Setup 6 nötig). Programmänderungen auf `main` erzeugen automatisch ein neues Release; Details stehen in [docs/UPDATES.md](docs/UPDATES.md).

Alternativ mit einer aktivierten Python-Umgebung:

```powershell
python -m pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
python tools/analyze_templates.py
python tools/make_icon.py
python -m PyInstaller --noconfirm AST-Verwaltung.spec
python tools/collect_licenses.py dist/AST-Verwaltung/_internal/licenses
```

## Umfang des MVP

Die App übernimmt die vorhandenen Erfassungs- und Rechenfunktionen. Sie ist keine vollständige Lohnbuchhaltung: Beitragssätze und Quellensteuer werden nicht selbst ermittelt, es gibt keine Bankanbindung oder elektronische Steuerübermittlung. Bestehende ausgefüllte Excel-Dateien werden in diesem MVP nicht importiert; die bereitgestellten Stunden-/Debitorenvorlagen enthalten keine Buchungen. Startsalden lassen sich in der ersten Stundenperiode erfassen.

Der Lohnausweis verwendet ausdrücklich die mitgelieferte Formularfassung «605.040.18N, Form. 11, 12.07». Sie wurde nicht durch ein anderes Formular ersetzt oder auf aktuelle behördliche Anforderungen zertifiziert. Der PDF-Export ist ausfüllbar; die in AST berechneten Summen sind schreibgeschützt. Betragsänderungen deshalb in AST vornehmen und das PDF neu exportieren. Gespeicherte Ausweise enthalten einen nachvollziehbaren Stand der Namen, Adressen und Firmendaten zum Zeitpunkt der Erfassung.

Technische Referenzen: [Qt-PDF-Vorschau](https://doc.qt.io/qtforpython-6/PySide6/QtPdfWidgets/QPdfView.html), [pypdf-Formularbearbeitung](https://pypdf.readthedocs.io/en/stable/user/forms.html). Lizenzhinweise: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
