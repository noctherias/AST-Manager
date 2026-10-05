# AST Manager

Windows-Desktopanwendung in Python mit acht klaren Arbeitsbereichen, zentraler SQLite-Datenbank, Excel-Stundennachweis und Ausgabe in der bereitgestellten Lohnausweis-PDF. Excel wird zur Erfassung und zum Export nicht benötigt; die exportierte `.xlsm` kann anschliessend in Excel geöffnet, berechnet und gedruckt werden.

## Sofort ausprobieren

**Empfohlen:** Im [neuesten Release](https://github.com/noctherias/AST-Manager/releases/latest) `AST-Verwaltung-Setup-x64.exe` laden und installieren. Danach AST Manager über das Startmenü öffnen. Updates werden automatisch über den fest eingebauten Update-Kanal gefunden und lassen sich direkt im Programm installieren; eine GitHub-Verbindung ist nicht nötig (siehe [Updates einrichten](docs/UPDATES.md)).

**Portable Windows-Version:** Das komplette Windows-Paket entpacken. `Demo starten.bat` öffnet eine getrennte Demo mit fiktiven Personen, Rechnungen, Stunden und einem Lohnausweis. `AST-Verwaltung.exe` öffnet die zunächst leere produktive Datenbank. Der Ordner `_internal` muss neben der EXE bleiben. Python und Excel sind nicht nötig. Die Datenerfassung funktioniert offline; nur die Update-Suche benötigt Internet.

Das AST-Firmenlogo liegt als dezentes, transparentes Wasserzeichen im hellen Arbeitsbereich. Es wird mit dem Programm ausgeliefert und benötigt keinen Zugriff auf das ursprüngliche Netzlaufwerk.

**Aus dem Quellcode:** Python 3.12, 64 Bit, installieren und `start_demo.bat` doppelklicken. Beim ersten Start werden die Bibliotheken aus `requirements.txt` in eine lokale `.venv` installiert. Dafür ist Internet nötig. Danach startet die App offline. `start.bat` öffnet die produktive Datenbank.

Getestet unter Windows 11 x64 mit Python 3.12.14 und PySide6 6.11.2. Mindestfenstergrösse 1120 × 720 logische Pixel; 1380 × 880 oder grösser empfohlen.

## Bedienung

1. **Übersicht:** Direkteinstieg für Debitoren, Arbeitszeit und Lohnausweis. Offene Rechnungen mit Fälligkeit stehen darunter. Bei einem leeren Datenbestand helfen Hinweise beim Einrichten.
2. **Debitoren:** Die Ansicht startet mit offenen Rechnungen. «Bezahlt» und «Alle» wechseln die Auswahl. Rechnung auswählen, dann **Zahlung erfassen**, **Mahnstufe** oder **Details bearbeiten**. Die Tabelle zeigt das Quartal automatisch aus dem Rechnungsdatum und besitzt eine Bemerkungsspalte. Über **Spalten** lassen sich Spalten ein- und ausblenden; ihre Reihenfolge kann direkt an den Überschriften verschoben werden. Beide Einstellungen bleiben nach dem Neustart erhalten. Eine bestehende Debitoren-Datei lässt sich über **Excel importieren** übernehmen. Zeitraumfilter und Export liegen bei den weiteren Optionen. Der eingerückte Unterpunkt **Mahnungen** führt durch Zahlungserinnerung, Mahnung 1, Mahnung 2 und Betreibung. Jede Stufe besitzt einen frei bearbeitbaren Brieftext. Variablen wie `{rechnungsnummer}`, `{betrag}`, `{frist}`, `{kunde}` oder `{tage_ueberfaellig}` lassen sich aus einer Liste in den Text einfügen und werden aus der Rechnung oder der manuellen Eingabemaske ersetzt. Der druckfertige PDF-Brief folgt dem AST-Briefstil mit Logo und Firmendaten links, Empfänger rechts, Zahlungsstand, Rechnungstabelle, Gruss und dreigeteilter Fusszeile. Kunden-Nr., Firmen-E-Mail und Website können in den Stammdaten ergänzt werden. Über **Mahnung manuell** kann derselbe Brief auch ohne zuvor erfasste Debitorenrechnung erstellt werden.
3. **Stundennachweis:** Person auswählen und **Arbeitstag erfassen**. Pro Tag wird nur noch die effektive Arbeitszeit eingegeben. Montag bis Donnerstag werden automatisch mit 8.75 h, Freitag mit 8.25 h vorgeschlagen. **Zeitraum erfassen** setzt diese Regelzeiten automatisch für alle gewählten Tage ein. **Excel importieren** liest neue und bisherige AST-Jahresdateien; **Excel-Liste exportieren** befüllt die zwölf Monatsblätter der Vorlage.
4. **Lohnausweise:** Vier Schritte führen durch Person/Zeitraum, Lohn/Abzüge, Zusatzangaben und abschliessende Prüfung. Die häufigen Lohnfelder stehen zuerst. Nach dem Speichern **PDF ansehen** oder **PDF speichern** wählen.
5. **Zeugnisse:** Ein Assistent erstellt Arbeitszeugnisse, Zwischenzeugnisse und Lehrzeugnisse. Manuell erfasst werden nur sachliche Angaben wie Art, Stichtag, Anlass und Tätigkeiten; Eintritt, Funktion und Personalien stammen aus den Stammdaten. Konkrete Multiple-Choice-Fragen decken Arbeitsqualität und -menge, Fachkenntnisse, Selbständigkeit, Zuverlässigkeit, Initiative, Lernfähigkeit sowie das Verhalten gegenüber Vorgesetzten, Team und Kundschaft ab. Für Lernende kommen Berufsschultransfer und Entwicklung hinzu. AST wertet die Antworten aus und erzeugt den vollständigen, schreibgeschützten Zeugnistext sowie das AST-PDF. Die Formulierungen sind klar und verzichten auf versteckte Zeugniscodes; Grundlage sind die [SECO-Hinweise zum Arbeitszeugnis](https://www.seco.admin.ch/de/faq-arbeitszeugnis).
6. **Bewerbungen:** Jede Bewerbung wird als eigenes Dossier mit Kategorie, Status, Kontaktdaten, Nachricht, Schnupperdaten, internen Notizen und Unterlagen geführt. Unterstützt werden Schnupperlehre, Elektroinstallateur/in EFZ und Montage-Elektriker/in EFZ. Das Webformular legt unter `/sites/ast-elektro.ch/uploads` pro Person einen eigenen Ordner mit Manifest und Anhängen an. AST meldet sich beim Programmstart automatisch per verschlüsseltem FTPS am Webserver an und fragt danach alle fünf Minuten neue Bewerbungen und Uploads ab. **Vom Webserver einlesen** startet zusätzlich jederzeit einen sofortigen Abgleich. Das Passwort wird mit Windows-DPAPI für den aktuellen Windows-Benutzer verschlüsselt gespeichert und gehört nicht zum Quellcode oder Release. Bewerbungen können auch manuell erfasst werden.
7. **Einstellungen:** Das Team wird hier einmalig angelegt und bearbeitet. Daneben liegen Firmendaten, Kunden, Datensicherung und Updates. Firmendaten werden beim Verlassen eines Feldes oder Bereichs gespeichert.

Erfassungsdialoge speichern erst mit **Speichern**. Abbrechen verwirft die Eingaben. `F5` aktualisiert die aktuelle Seite. Listen erklären, welche Auswahl für die nächste Aktion nötig ist. Tabellenüberschriften und Zellinhalte sind einheitlich mittig ausgerichtet. In jeder Tabelle lassen sich Spalten und Zeilen an ihren Überschriften ziehen; per Rechtsklick können sie aus- und wieder eingeblendet oder zurückgesetzt werden. Die Anordnung und Sichtbarkeit bleiben nach einem Neustart erhalten. Die linke Navigation lässt sich über den Pfeil beim AST-Schriftzug einklappen; die gewählte Ansicht bleibt ebenfalls erhalten. Grössere Formulare und ausgeklappte Details können gescrollt werden.

Die Arbeitszeit entspricht der bereits bereinigten Tageszeit: Montag bis Donnerstag 07:00–12:00 abzüglich 0.25 h Pause plus 13:00–17:00 ergibt 8.75 h; Freitag endet der Nachmittag um 16:30 und ergibt 8.25 h. Personen mit bestehenden Daten können in den Einstellungen auf inaktiv gesetzt werden.

Alle Arbeitszeiten werden in Viertelstunden und als Dezimalstunden dargestellt: 15 Minuten = 0.25 h, 30 Minuten = 0.50 h und 45 Minuten = 0.75 h. Excel-Dateien erhalten automatisch den Namen `Stundennachweis_Jahr_Nachname_Vorname.xlsm`; Leerzeichen in Namen werden durch Unterstriche ersetzt.

## Übernommene Vorlagenlogik

- Debitoren: bezahlte Beträge werden wie `SUM(G:G)` summiert. Teilzahlungen, Restbetrag, Fälligkeit und Status ergänzen die einfache Liste.
- Zeiterfassung: Die Excel-Ausgabe zeigt nur noch die direkte Eingabespalte `Arbeitszeit` sowie `Code` und `Bemerkungen`. Die früheren Kommt-/Geht-Spalten werden ausgeblendet. Die angepassten Formeln berechnen daraus weiterhin IST-/SOLL-Zeit, Tages- und Monatssaldo, Ferien, Krankheit, Homeoffice, Kurzarbeit und Jahresübersicht.
- Der Export arbeitet direkt auf dem OOXML-Paket. VBA-Projekt, Formularsteuerelemente, Zeichnungen, Druckereinstellungen, Datenvalidierungen, benannte Bereiche und Formeln werden nicht neu erzeugt. Personendaten, die bereits in der gelieferten Quelldatei standen, werden aus jedem Export entfernt.
- Lohnausweis: Brutto aus den neun Betragsfeldern der Ziffern 1–7; Abzüge aus 9, 10.1 und 10.2; Netto = Brutto − Abzüge. Quellensteuer und Spesen werden wie im Original separat ausgewiesen.

Die vollständige Analyse steht in [docs/VORLAGENANALYSE.md](docs/VORLAGENANALYSE.md), das maschinenlesbare Inventar inklusive jeder Formel, Abhängigkeit, Datenvalidierung, benannter Bereiche, Druckeinstellungen und PDF-Felddefinitionen in [docs/template_inventory.json](docs/template_inventory.json).

## Datenspeicherung

Standard: `%LOCALAPPDATA%\AST-Erfassungstool\`.

- `ast.sqlite3`: produktive Daten.
- `ast-demo.sqlite3`: getrennte Demodaten.
- `backups\`: tägliche Start-Sicherungen und Sicherungen vor einer Wiederherstellung. Unter Einstellungen kann zusätzlich ein externer Ordner mit Aufbewahrungsfrist gewählt werden.
- `vorschau\`: erzeugte PDF-Vorschauen.
- `updates\`: heruntergeladene und geprüfte Setups.
- `applications\`: lokale Kopien der eingelesenen Bewerbungsunterlagen, nach Dossier geordnet.
- `ast.log`: Fehlermeldungen.

Ein anderer Ordner lässt sich mit `python main.py --data-dir "D:\AST-Daten"` wählen. Eine zweite Instanz derselben Datenbank wird verhindert. Die App ist für einen lokalen Arbeitsplatz gedacht. Die SQLite-Datei ist nicht verschlüsselt; sie übernimmt die Windows-Dateizugriffsrechte.

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
  widgets.py / theme.py     Wiederverwendbare UI und Gestaltung
  window.py                Hauptfenster und Navigation
  documents.py             Original-PDF befüllen, Berichte, CSV
  reminders.py             Mahnstufen, Textvorlagen und PDF-Briefe
  references.py            Zeugnisassistent, Textbausteine und PDF-Ausgabe
  applications.py          Bewerbungsdossiers und Website-Import
  timesheet_excel.py       Makrovorlage verlustfrei befüllen und prüfen
  demo.py                  Fiktive Demo, nur im Demomodus
templates/                 Originalvorlagen für Lohnausweis und Zeiterfassung
docs/                      Vorlagenanalyse und Testprotokoll
tests/                     Fachlogik, Vorlagenvergleich, Datenbank, PDF, UI
tools/                     Analyse, Build-Hilfen und reversible Website-Anbindung
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

Der Release-Workflow signiert Anwendung und Installer automatisch, sobald ein Code-Signing-Zertifikat als GitHub-Secrets hinterlegt wurde. Die einmalige Einrichtung ist in [docs/CODE_SIGNING.md](docs/CODE_SIGNING.md) beschrieben.

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

Die App übernimmt die vorhandenen Erfassungs- und Rechenfunktionen. Sie ist keine vollständige Lohnbuchhaltung: Beitragssätze und Quellensteuer werden nicht selbst ermittelt, es gibt keine Bankanbindung oder elektronische Steuerübermittlung. Unterstützt werden der Import der mitgelieferten Debitoren-Struktur und der AST-Zeiterfassung mit zwölf Monatsblättern. Andere frei aufgebaute Arbeitsmappen werden nicht automatisch zugeordnet. Die Berechnung der exportierten Excel-Formeln erfolgt beim Öffnen in Excel.

Der Lohnausweis verwendet die aktuelle offizielle ESTV-Formularfassung «Form. 11 dfi 605.040.18N 01.21» von 2023. Der PDF-Export bettet alle Werte sichtbar in die Seite ein, damit Vorschau, Browser, Druck und Archiv dieselben Daten zeigen. Änderungen werden in AST vorgenommen und anschliessend neu exportiert. Gespeicherte Ausweise enthalten einen nachvollziehbaren Stand der Namen, Adressen und Firmendaten zum Zeitpunkt der Erfassung.

Technische Referenzen: [Qt-PDF-Vorschau](https://doc.qt.io/qtforpython-6/PySide6/QtPdfWidgets/QPdfView.html), [pypdf-Formularbearbeitung](https://pypdf.readthedocs.io/en/stable/user/forms.html). Lizenzhinweise: [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
