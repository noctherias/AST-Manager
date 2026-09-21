# AST Verwaltung

Funktionsfähiges Windows-Desktop-MVP in Python. Sechs Module, zentrale SQLite-Datenbank, native Stundenberechnung und Ausgabe in der bereitgestellten Lohnausweis-PDF. Excel wird weder benötigt noch gestartet.

## Sofort ausprobieren

**Fertige Windows-Version:** Das komplette Windows-Paket entpacken. `Demo starten.bat` öffnet eine getrennte Demo mit fiktiven Personen, Rechnungen, Stunden und einem Lohnausweis. `AST-Verwaltung.exe` öffnet die zunächst leere produktive Datenbank. Der Ordner `_internal` muss neben der EXE bleiben. Python und Internet sind für diese Version nicht nötig.

**Aus dem Quellcode:** Python 3.12, 64 Bit, installieren und `start_demo.bat` doppelklicken. Beim ersten Start werden die Bibliotheken aus `requirements.txt` in eine lokale `.venv` installiert. Dafür ist Internet nötig. Danach startet die App offline. `start.bat` öffnet die produktive Datenbank.

Getestet unter Windows 11 x64 mit Python 3.12.14 und PySide6 6.11.2. Mindestfenstergrösse 1180 × 760 logische Pixel; 1440 × 900 oder grösser empfohlen.

## Bedienung

1. Unter **Stammdaten → Firma** die Ausstellerdaten eintragen und speichern.
2. Unter **Mitarbeiter** oder **Lernende** eine Person anlegen. Personalnummer, Name, Pensum und Ferienanspruch werden zentral gespeichert.
3. Für diese Person die erste **Periode** anlegen. Bei Lernenden sind Start und Ende des Lehrjahres frei wählbar. Der Ferienanspruch ist ein Stundenwert; die Vorlage verwendet 216.25 h. Teiljahre oder Teilzeitansprüche werden bewusst als vereinbarter Stundenwert erfasst.
4. **Stunden erfassen**: Ferien, Überzeit, Krankheit oder Unfall mit Datum und Dezimalstunden buchen. 1.50 h entsprechen 90 Minuten. Guthaben und Überträge aktualisieren sich sofort nach dem Speichern. Im Tab «Alle Perioden & Überträge» erscheinen die verbundenen Jahre.
5. Unter **Debitoren** eine Rechnung anlegen. Kunden können direkt im Rechnungsdialog angelegt werden. Eine Rechnung auswählen und **Zahlungen** öffnen, um Teilzahlungen mit Valutadatum zu verbuchen. Such-, Status-, Jahres- und Quartalsfilter wirken auf Tabelle und Auswertung. Doppelklick öffnet die Bearbeitung.
6. Unter **Lohnausweise** einen Ausweis pro Person und Jahr anlegen. Beträge in ganzen CHF eingeben, speichern und **Vorschau** oder **PDF exportieren** wählen. Alle sichtbaren Formularfelder sind abgedeckt, einschliesslich Spesen, Nebenleistungen und Ausstellerzeilen.
7. Unter **Stammdaten → Daten & Sicherung** sichern oder wiederherstellen. Vor der Wiederherstellung wird eine zusätzliche Sicherung angelegt. Beim ersten Programmstart pro Tag wird der aktuelle Stand ebenfalls gesichert.

Eingaben werden mit **Speichern** übernommen. Das Schliessen oder Abbrechen eines Erfassungsdialogs verwirft ungespeicherte Eingaben. Das Firmenformular hat einen eigenen Speicherknopf. `F5` aktualisiert die aktuelle Seite. Personen mit bestehenden Daten können auf inaktiv gesetzt werden.

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
- `ast.log`: Fehlermeldungen.

Ein anderer Ordner lässt sich mit `python main.py --data-dir "D:\AST-Daten"` wählen. Eine zweite Instanz derselben Datenbank wird verhindert. Die App ist für einen lokalen Arbeitsplatz gedacht. Die SQLite-Datei ist nicht verschlüsselt; sie übernimmt die Windows-Dateizugriffsrechte. Sicherungen werden nicht automatisch auf ein externes Laufwerk übertragen.

## Projektstruktur

```text
main.py                    Programmstart, Datenpfad, Sperre, tägliche Sicherung
ast_app/
  database.py              Schema, Transaktionen, Stammdaten, CRUD, Sicherungen
  domain.py                Berechnungen und Validierung ohne Excel
  dialogs.py               Eingabemasken
  pages.py                 Sechs Module, PDF-Vorschau, Auswertungen
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
```

## Tests und eigener Build

`test.bat` installiert zusätzlich die Entwicklungsabhängigkeiten und führt die Tests aus. `build.bat` testet zuerst und erstellt anschliessend `dist\AST-Verwaltung\AST-Verwaltung.exe` samt benötigtem `_internal`-Ordner. Für Änderungen den gesamten Build-Ordner weitergeben.

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
