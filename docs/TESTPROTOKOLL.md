# Testprotokoll

Stand: 30.09.2026, Version 0.7.0. Geprüft unter Windows 11 x64 (10.0.26200), Python 3.12.14, PySide6 6.11.2, pypdf 6.10.0, ReportLab 4.4.9 und PyInstaller 6.22.3.

## Automatisierte Tests

`python -m unittest discover -s tests -v`: **41 Tests**. Die fachlichen, Dokument-, Mahnbrief-, Import-, Export-, Datenbank-, Update- und UI-Tests liefen lokal erfolgreich.

| Bereich | Geprüfte Fälle |
|---|---|
| Originalformeln | Alle 40 Formeln. 39 Stundenformeln über 16 Szenarien mit unabhängiger Auswertung der originalen Zellreferenzen; zusätzlich Abgleich gespeicherter Excel-Ergebnisse. Debitoren-Summe über die gesamte ursprüngliche Spalte. |
| Zahlen und Salden | Exakte Rappen und Hundertstelstunden, Schweizer Zahleneingaben, keine stille Rundung, negative Zeitguthaben, Überzeitkorrekturen und kumulative Absenzen. |
| Debitoren | Offen/teilbezahlt/überfällig/bezahlt, Fälligkeit am Stichtag, Teilzahlungen, eindeutige Rechnungsnummern, Ablehnung von Überzahlung und unzulässiger Rechnungsreduktion. |
| Perioden | Drei Jahre mit Übertrag, nachträgliche Änderung im ersten Jahr, kumulative Krankheit/Unfall, Persistenz nach Neustart, Überschneidungen, Grenzen des Buchungsdatums, Schutz vorhandener Startsalden. |
| Zeiterfassung | Eindeutiger Datensatz pro Person/Tag, zwei Arbeitsblöcke, Zusatzpause, Codes und Bemerkung; Jahresfilter und Persistenz. Verlustfreier XLSM-Export mit identischer Paketstruktur und identischem VBA-Hash, korrekte Zielzellen sowie Entfernung vorbestehender Personendaten. |
| Sicherungen | SQLite-Sicherung und Wiederherstellung, automatische Sicherheitssicherung, Integritätsprüfung und gültige Fremdschlüssel nach Wiederherstellung. |
| Lohnausweis | Richtige Brutto-/Abzugs-/Nettosumme, separate Quellensteuer und Spesen, Ganzfrankenbeträge, ein Ausweis pro Person/Jahr, Jahresgrenzen, Erhalt gespeicherter Personalangaben bei späteren Stammdatenänderungen. |
| PDF-Struktur | Vollständige Widget-/Feldbaum-Zuordnung der Quelle, alle Eingabefelder, Checkboxen und fünf Aussteller-Unterfelder; sichtbare Einbettung in die fertige Seite, keine verbleibenden Widgets, entfernte Vorlagenwerte, Ablehnung unbekannter Felder. |
| Berichte/CSV | Mehrseitiger PDF-Bericht, Unicode-CSV, Schutz vor Formelinterpretation beim späteren Öffnen in Tabellenprogrammen. |
| Updates | Fest eingebauter öffentlicher Update-Kanal, Versionsvergleich, stabile Releases, sichere Weiterleitungsziele, Hash-/Grössenprüfung, Abbruchbereinigung, Offline-/Zugriffsfehler, Datenbanksicherung vor Installation, Startparameter und erneute Integritätsprüfung. |
| Oberfläche | Fünf Arbeitsbereiche navigiert, Filter, Auswahlaktionen, reale Qt-Klicks zum Speichern von Kunden, Rechnung, Teilzahlung und Arbeitstag; Lohnausweis speichern/wiederöffnen, integrierte PDF-Vorschau; Teamverwaltung unter Einstellungen und Erhalt der Firmendaten beim Schliessen. Die explizite helle Palette wurde mit Bildausgaben der Seiten und Dialoge geprüft. |

Die Qt-Tests laufen mit dem Offscreen-Plugin. Für die Bildkontrolle wurden die Windows-Schriften explizit geladen. Es wurden zusätzlich die Hauptseiten und der Lohnausweisdialog als Bilder geprüft. Die drei PDF-Arten wurden mit Poppler gerendert und visuell auf Text, Feldpositionen, Summen und Seitenränder kontrolliert.

## Windows-Paket

Der Build enthält Python, die nötigen Qt-Module, PDF- und Excel-Bibliotheken, die offizielle Lohnausweis-PDF und `Zeiterfassung_Vorlage.xlsm`. Der Starttest der gebauten EXE umfasst alle fünf Arbeitsbereiche, SQLite-Datenhaltung, PDF-Berichte und einen echten XLSM-Export. Der Excel-Import wird mit einer erzeugten Debitorendatei sowie einem exportierten und wieder eingelesenen Stundennachweis geprüft.

Beim Pakettest wurde ein Konflikt mit einer vom Build-PATH eingesammelten Poppler-ICU-DLL gefunden. Der Build schliesst diese fremde Bibliothek aus und verwendet die von Qt erwartete Windows-ICU-Schnittstelle. Die Korrektur ist in der mitgelieferten `.spec` verankert.

## Grenzen der Prüfung

Zusätzlich mit Version 0.2.0 geprüft: gebautes Inno-Setup unter eigener Test-Kennung im Arbeitsordner installiert, installierte EXE mit Demo-Datenbank und PDF-Starttest ausgeführt, Setup erneut über dieselbe Installation ausgeführt. Der SHA-256-Hash der Datenbank blieb unverändert. Danach die Testinstallation deinstalliert; die Datenbank blieb bestehen. Der Windows-DPAPI-Test wurde unter dem normalen Windows-Benutzer ausgeführt (das eingeschränkte Sandbox-Konto hat kein verwendbares DPAPI-Profil). Diese Update- und Installer-Tests bleiben unverändert Teil der Release-Pipeline für 0.3.0.

Getestet auf diesem Windows-11-Rechner, nicht auf einem separaten frisch installierten Windows-Rechner. Keine Steuer-/Lohnbuchhaltungs-Zertifizierung, kein Bank- oder Mehrbenutzerbetrieb. Frei aufgebaute Arbeitsmappen ausserhalb der unterstützten Debitoren- und Zeiterfassungsstruktur werden nicht automatisch zugeordnet.
