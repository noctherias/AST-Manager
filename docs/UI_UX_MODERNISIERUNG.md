# UI/UX-Modernisierung

## Ziel

Die Oberfläche bleibt fachlich und technisch mit der bestehenden AST-Verwaltung kompatibel. Die Überarbeitung verbessert Orientierung, Lesbarkeit, Bedienzustände und Hilfe, ohne Datenmodell, Berechnungen oder Exporte zu verändern.

## Bestandsaufnahme

Die Anwendung besass bereits wiederverwendbare Seiten-, Formular-, Tabellen- und Schaltflächenkomponenten. Diese zentrale Struktur wurde beibehalten. Die wichtigsten erkannten Schwächen waren:

- Betriebssystemabhängige Standardsymbole ohne gemeinsame Designsprache.
- Eine lange, wenig gegliederte Navigation.
- Uneinheitlich konkrete Beschriftungen wie «Bearbeiten», «Löschen», «Weiter» und «Öffnen».
- Geringe optische Trennung zwischen Seitenüberschrift und Arbeitsinhalt.
- Kein zentraler oder kontextbezogener Hilfebereich.
- Zu wenig sichtbare Unterscheidung zwischen Haupt-, Neben- und Löschaktionen.

## Umgesetztes Designsystem

- Die bisherige Farbwelt aus Dunkelblau, Grün und hellen neutralen Flächen bleibt erhalten.
- Seitenköpfe, Karten, Tabellen, Register, Formulare und Statusflächen verwenden zentral definierte Abstände, Radien, Rahmen und Fokuszustände.
- Primäraktionen erscheinen grün, Nebenaktionen neutral und Löschaktionen zurückhaltend rot.
- Tastaturfokus ist an Schaltflächen, Eingaben, Registern und Navigation sichtbar.
- Die Informationsdichte bleibt für den täglichen Einsatz kompakt.

## Navigation und Symbole

Die Navigation ist in **Start**, **Finanzen**, **Personal** und **System** gegliedert. Alle zehn Bereiche behalten ihre bisherigen Seitenindizes; vorhandene interne Navigation bleibt dadurch kompatibel.

Die früheren Betriebssystemsymbole wurden durch zehn eigene, skalierbare SVG-Symbole mit identischen Abmessungen, Strichstärken und Farben ersetzt. Es besteht keine Laufzeitabhängigkeit zu einer externen Symbolbibliothek.

## Beschriftungen und Bedienzustände

Unklare Beschriftungen wurden dort konkretisiert, wo der betroffene Datentyp bekannt ist, beispielsweise:

- «Monatslohn bearbeiten»
- «Ausgewählte Monatslöhne löschen»
- «Zeugnis bearbeiten»
- «Ausgewählte Bewerbungen löschen»
- «Zahlungen verwalten»
- «Mahnstufe festlegen»
- «Vorheriger Schritt» und «Nächster Schritt»

Mehrfachauswahl bleibt mit Strg und Umschalt möglich. Gefährliche Aktionen sind zusätzlich zur Farbe durch ihren eindeutigen Text erkennbar.

## Integrierte Hilfe

Der neue Bereich **Hilfe und Anleitungen** enthält eine Volltextsuche sowie Anleitungen für:

- Übersicht und erste Einrichtung
- Debitoren und Zahlungen
- Mahnungen
- Stundennachweis
- Lohnbuch
- Zeugnisse
- Bewerbungen
- Lohnausweise
- Einstellungen und Datensicherung
- Tabellenbedienung und Mehrfachauswahl

Jeder Artikel erklärt Zweck, Arbeitsschritte und wichtige Hinweise in einfachem Deutsch. Suchbegriffe enthalten auch naheliegende Alternativen. Jede Hauptansicht besitzt eine Hilfeschaltfläche, die direkt den passenden Artikel öffnet. **F1** öffnet ebenfalls die Hilfe des aktuellen Bereichs. Die Inhalte liegen strukturiert in `ast_app/help.py` und können ohne Änderungen am Seitenlayout ergänzt werden.

## Qualitätssicherung

Die UI-Integrationstests öffnen alle Ansichten, bedienen reale Dialoge und prüfen Navigation, Tabellen, Exporte, Assistenten und Datenspeicherung. Ergänzt wurden Prüfungen für den Hilfebereich, die Suche und den kontextbezogenen Einstieg. Screenshots werden bei Bedarf über `AST_QA_DIR` für jede Ansicht erzeugt und visuell kontrolliert.
