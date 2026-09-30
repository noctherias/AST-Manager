# GitHub-Releases und Programm-Updates

Update-Kanal: [noctherias/AST-Manager](https://github.com/noctherias/AST-Manager).

Das Repository und seine Release-Dateien müssen öffentlich lesbar sein. Dadurch funktioniert die Update-Suche ohne Konto, Token oder manuell eingetragene Repository-Adresse. Die normale Datenerfassung funktioniert weiterhin ohne Internet.

## Im täglichen Betrieb

Die App prüft beim Start und danach alle sechs Stunden auf neuere stabile Releases. Bei einer neuen Version erscheint ein Fenster mit Änderungen und **Herunterladen & aktualisieren**. **Später** verschiebt den Hinweis für diese Version um einen Tag; eine manuelle Suche ist jederzeit möglich. Offline-Fehler unterbrechen die Arbeit nicht.

Der Installer wird über die öffentliche GitHub-API geladen. Die App prüft Dateigrösse und den von GitHub gelieferten SHA-256-Digest und erstellt vor der Installation eine SQLite-Sicherung. Nach erfolgreichem Start des Setups wird AST geschlossen. Das Setup aktualisiert die Programmdateien und startet AST wieder mit demselben Datenordner und Demo-/Produktivmodus.

Die Installation erfolgt ohne Administratorrechte unter `%LOCALAPPDATA%\Programs\AST-Manager`. Daten bleiben unter `%LOCALAPPDATA%\AST-Erfassungstool` beziehungsweise dem ausdrücklich gewählten Datenordner. Auch eine Deinstallation entfernt diese Daten nicht. Beim Wechsel vom portablen ZIP zur installierten App anschliessend den Startmenü-Eintrag **AST Manager** benutzen. Die Quellcode-Version zeigt verfügbare Updates an, installiert jedoch keinen Ersatz über die Entwicklungsumgebung.

## Änderungen veröffentlichen

Ein Push mit Programmänderungen auf `main` startet **Windows Release**. Reine Änderungen an Markdown-Dateien oder `docs/` erzeugen kein neues Programmrelease. Unter **Actions → Windows Release → Run workflow** kann ein Release manuell gestartet werden. Pull Requests führen die Tests aus.

Der Workflow führt Tests aus, baut die Windows-App, prüft ihren Start und erstellt das Setup. Erst danach wird ein zunächst privater Entwurf mit allen Dateien als fertiges Release veröffentlicht. Ein fehlgeschlagener Build wird nicht angeboten. Die Patch-Version wird automatisch gegenüber bestehenden Versions-Tags erhöht. Für einen neuen Haupt-/Nebenversionszweig kann die Basisversion in `ast_app/__init__.py` erhöht werden.

Der Release-Tag enthält den exakten versionierten Quellstand; die Versionsanpassung wird auf dem Tag gespeichert, ohne zusätzliche Commits auf `main` zu erzwingen. Der Quellcode-ZIP enthält dieselbe Version wie das Setup. Die alte Repository-Historie bleibt erhalten; gebündelte Laufzeit-DLLs werden künftig nur als Release-Dateien verteilt.

Dateien pro Release:

- `AST-Verwaltung-Setup-x64.exe`: empfohlene Installation und automatische Updates.
- `AST-Verwaltung-Windows.zip`: portable Version.
- `AST-Erfassungstool-Quellcode.zip`: vollständiger Quellcode einschliesslich Vorlagen und Build-Skripten.

GitHub Actions benötigt für diesen Workflow `contents: write` (im Workflow gesetzt), aktivierte Actions und verfügbare Windows-Runner-Minuten. Der Update-Kanal und die Release-Dateien müssen öffentlich lesbar bleiben.

## Eigener Setup-Build

`build.bat` erstellt die App. `build_setup.bat` erstellt danach das Setup mit installiertem Inno Setup 6. Ein abweichender Compilerpfad lässt sich an `scripts/installer.ps1 -Compiler "C:\Pfad\ISCC.exe"` übergeben. Der CI-Build prüft den Compilerdownload gegen eine fest hinterlegte SHA-256-Prüfsumme.

Der AST-Installer ist noch nicht mit einem eigenen Codesignatur-Zertifikat signiert; Windows kann deshalb beim ersten manuellen Start eine Herausgeber-Warnung anzeigen. Die Downloadprüfung ersetzt keine Herausgebersignatur. Automatische Schema-Migrationen über Datenbankversion 1 hinaus müssen mit zukünftigen Änderungen ergänzt und getestet werden.

Technische Grundlagen: [GitHub Releases](https://docs.github.com/en/rest/releases/releases#get-the-latest-release), [Release-Assets und Digests](https://docs.github.com/en/rest/releases/assets#get-a-release-asset), [Inno Setup](https://jrsoftware.org/ishelp/).
