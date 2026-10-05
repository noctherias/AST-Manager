# Vollständige Vorlagenanalyse und Umsetzung

Analysiert wurden die vier Originaldateien aus der referenzierten Unterhaltung sowie die später ergänzte `Zeiterfassung_Vorlage.xlsm`. Die vier ursprünglichen Vorlagen liegen unverändert in `templates/`; die makrofähige Zeiterfassung wurde vor dem Einchecken von Mitarbeiterdaten und lokalen Speicherpfaden bereinigt. Die Analyse ist mit `python tools/analyze_templates.py` beziehungsweise `python tools/analyze_zeiterfassung.py` reproduzierbar. Die App benötigt weder eine Excel-Installation noch openpyxl; die makrofähige Vorlage wird als Programmressource gezielt befüllt.

## Inventar

| Datei / Blatt | Benutzter Bereich | Rechenformeln | Ferien-Eingabe | Ausgabe Ferienrest |
|---|---|---:|---|---|
| Debitoren / Tabelle1 | A2:Q590 | 1 | – | – |
| Stundennachweis / Name Vorname (L1 20xx-xx) | A2:O66 | 8 | B4:B65 | B66 |
| Stundennachweis / Name Vorname (L2 20xx-xx) | A2:Q66 | 10 | B4:B65 | B66 |
| Stundennachweis / Name Vorname (L3 20xx-xx) | A2:Q79 | 10 | B4:B78 | B79 |
| Lehrling / Nathalie Lehmann (L1 20XX-XX) | A2:O39 | 5 | B4:B21 | B22 |
| Lehrling / Nathalie Lehmann (L2 20XX-XX) mit abschliessendem Leerzeichen im Blattnamen | A2:Q39 | 6 | B4:B21 | B22 |

Insgesamt sechs sichtbare Arbeitsblätter und 40 Zellformeln. Keine weiteren versteckten Blätter. In allen drei Dateien: keine Datenvalidierungen, keine Dropdowns, keine benannten Bereiche, keine festgelegten Druckbereiche, keine Drucktitel, keine externen Arbeitsmappenverknüpfungen, keine Tabellenobjekte, keine Diagramme und keine VBA-Projekte. Vorhandene Formatierungen und bedingte Formatierungsregeln sind im JSON dokumentiert; Arbeitsmappen- und Styles-XML sind ebenfalls enthalten. Es sind keine Rechnungstransaktionen oder Stundenbuchungen vorbelegt. Die Personennamen in Blattnamen werden als Vorlagenbeschriftung behandelt.

## Debitoren

Titel B2: «Debitoren 2026 Quartal 1». Spaltenüberschriften B13:G13: Rechnungsdatum, Rechnungsnummer, Name, Valutadatum, Rechnungsbetrag, bezahlter Betrag. K13 berechnet `=SUM(G:G)`. Dabei werden Textwerte wie «offen» oder «ok» von Excel nicht summiert.

Zwei bedingte Formatierungen suchen die Texte «offen» und «ok» in `G15:H22 G24:H328`. Die App ersetzt diese manuelle Textmarkierung durch berechnete Status «Offen», «Teilbezahlt», «Überfällig», «Bezahlt». Bezahlt bedeutet vollständiger Zahlungseingang. Überfälligkeit wird bei noch offenem Betrag und überschrittener Fälligkeit angezeigt, auch nach Teilzahlung. Der gezahlte Betrag bleibt dabei sichtbar.

Die Vorlage erklärt die Bedeutung des Valutadatums nicht näher. Im MVP ist es das Datum der Zahlung; bei mehreren Zahlungen zeigt die Rechnungsübersicht das jüngste Valutadatum. **Fälligkeit ist ein zusätzliches, gesondertes Feld**, keine Umbenennung des Valutadatums. Neue Rechnungen starten mit heute + 30 Tagen als frei editierbarer Fälligkeit. Jahr und Quartal filtern nach Rechnungsdatum. Die Dashboard-Kachel «Bezahlt [Jahr]» aggregiert nach Zahlungsdatum.

K13 entspricht der Summe aller Zahlungen. Geld wird als ganze Rappen gespeichert, damit Teilzahlungen exakt aufgehen. Überzahlungen und Rechnungsbeträge unter bereits gebuchten Zahlungen werden abgewiesen. Rechnung und Zahlungen sind separate, verknüpfte Datensätze.

## Stundenlogik beider Vorlagen

Alle fünf Stundenblätter enthalten den unverknüpften Eingabewert B3 = **216.25 Stunden**. Aus den Vorlagen lässt sich keine Formel «Ferientage × Stunden pro Tag × Pensum» ableiten. Deshalb übernimmt die App den Stundenanspruch direkt. Sie berechnet keine zusätzliche Kürzung nach Pensum, Eintrittsdatum oder Periodendauer.

| Rechenschritt | Originalzellen | Native Umsetzung |
|---|---|---|
| Ferienrest | B22 / B66 / B79 = B3 minus alle Ferienzeilen | Anspruch minus Summe Ferienbuchungen |
| Überzeit | E22 = E4 + … + E21 | Summe Überzeitbuchungen, einschliesslich negativer Korrekturen |
| Guthaben im ersten Jahr | G22 = Ferienrest + E22 | Anspruch − Ferien + Überzeit + optionaler Einstiegssaldo |
| Übertrag Jahr 2 | G22 = erstes Blatt!G22 | Dynamisch berechnetes Guthaben der Vorperiode |
| Guthaben Jahr 2 | I22 = B22/B66 + E22 + G22 | Übertrag + Anspruch − Ferien + Überzeit |
| Übertrag Jahr 3 | G22 = zweites Blatt!I22 | Dynamisch berechnetes Guthaben der Vorperiode |
| Guthaben Jahr 3 | I22 = B79 + E22 + G22 | Übertrag + Anspruch − Ferien + Überzeit |
| Krankheit im ersten Jahr | L22 = L4 + … + L21 | Summe Krankheit in der ersten Periode |
| Unfall im ersten Jahr | O22 = O4 + … + O21 | Summe Unfall in der ersten Periode |
| Krankheit später | N22 = N4 + … + N21 + Vorjahrestotal | Kumulative Krankheit über alle bisherigen Perioden |
| Unfall später | Q22 = Q4 + … + Q21 + Vorjahrestotal | Kumulativer Unfall über alle bisherigen Perioden |

Die detaillierten Berechnungsboxen in `Stundennachweis_Vorlage.xlsx` enthalten G44 = Übertrag (erst ab Jahr 2), G45 = B66/B79, G46 = E22 und G47 = G22/I22. Diese sind zusätzliche Anzeigen derselben Werte und werden nicht doppelt addiert. Die Beschriftung «Total Ferienbezug» bei G45 ist irreführend: die Formel verweist auf den **Rest**, nicht auf den Bezug. Die App bezeichnet Bezug, Rest und Guthaben entsprechend ihrer tatsächlichen Berechnung.

Die Formeln mit `++` in Jahr 2 enthalten ein unäres Plus und sind rechnerisch normale Additionen. Die Ferienformel in Jahr 3 zählt B34/B35/B36 und B52/B53 in ungewohnter Reihenfolge, aber jede benötigte Zeile genau einmal. Diese Reihenfolge verändert die Summe nicht.

Die negativen Werte werden in den Vorlagen mit bedingten Formatierungen hervorgehoben (u. a. G22, I22, G44:G49 und begleitende Beschriftungen). Die App erlaubt negative Salden und negative Überzeit und markiert sie rot. Ferien-, Krankheits- und Unfallbuchungen werden als positive Bezugsstunden validiert; Korrekturen erfolgen über Bearbeiten/Löschen. Das ist eine zusätzliche Eingabeprüfung, da die Originale keine Datenvalidierungen besitzen.

Die ursprünglichen Kapazitäten von 18 Überzeit-/Krankheits-/Unfallbuchungen und 18/62/75 Ferienbuchungen werden durch beliebig viele Datenbankeinträge ersetzt. Es gibt eine chronologische Periodenkette je Person. Die ersten zwei bzw. drei Jahre sind keine fachliche Obergrenze. Perioden dürfen sich nicht überschneiden. Eine zeitliche Lücke erzeugt keinen automatischen Anspruch. Startsalden können ausschliesslich in der ersten Periode erfasst werden und sind in der Berechnung sichtbar.

## Makrofähige Zeiterfassung

`Zeiterfassung_Vorlage.xlsm` enthält 19 Blätter: Voreinstellungen, zwei versteckte Mitarbeiterlisten, Feiertage, Speicherorte, zwölf Monatsblätter, Jahresübersicht und Fahrtkosten. Dazu kommen mehrere tausend Formeln, benannte Bereiche, Datenvalidierungen, geschützte Monatsblätter, 28 Formularsteuerelement-Eigenschaften, VML- und Drawing-Dateien, Druckereinstellungen, eine Berechnungskette und ein VBA-Projekt. In der AST-Ausgabe wird Spalte D als direkte `Arbeitszeit` verwendet; die bisherigen Kommt-/Geht- und Pausenspalten E–I werden ausgeblendet. Code und Bemerkung bleiben in J und O. Die IST-Formeln in K wurden gezielt auf die direkte Arbeitszeit umgestellt; SOLL-Zeit, Tages- und Monatssaldo, Abwesenheitslogik und Jahresübersicht bleiben verknüpft. Die Zeilen 4–34 entsprechen den Kalendertagen 1–31.

Die hinterlegte Regelzeit beträgt Montag bis Donnerstag 8.75 Stunden und Freitag 8.25 Stunden. Sie entspricht 07:00–12:00 mit 0.25 Stunden unbezahlter Vormittagspause sowie 13:00–17:00 beziehungsweise freitags 13:00–16:30. Neue Eingaben speichern nur die effektiven Arbeitsminuten. Beim Öffnen älterer Datenbanken oder Importieren bisheriger Excel-Dateien werden die alten Zeitblöcke einmalig in dieselbe effektive Arbeitszeit umgerechnet.

Die Anwendung speichert diese Eingaben pro Person und Datum in SQLite. Beim Export wird die Originaldatei als OOXML-ZIP-Paket kopiert und nur in den vorgesehenen Zellen ergänzt. Die übrigen Paketbestandteile bleiben unverändert; der SHA-256-Wert von `xl/vbaProject.bin` wird nach dem Schreiben geprüft. Excel wird beim nächsten Öffnen zur vollständigen Neuberechnung angewiesen. Bereits in der Quelldatei enthaltene Namen, Personalnummern und personenspezifische Speicherpfade werden entfernt, bevor die ausgewählte Person eingesetzt wird.

Codes der Vorlage: `F` Feiertag, `G` Gleittag, `K` krank, `KR` Krank-Restzeit, `KU` Kurzarbeit, `KA` Kurzarbeit-Restzeit, `U` Ferien, `UH` halber Ferientag, `H` Homeoffice und `B` Bereitschaft. Die Vorlagenlogik berechnet daraus IST-/SOLL-Arbeitszeit, Pausenhinweise, Tagessaldo, Monatsübertrag, Ferien- und Abwesenheitswerte sowie die Jahresübersicht.

## Druck- und Darstellungseinstellungen

Alle Arbeitsblätter sind für A4 quer angelegt. Gespeicherte Skalierung: Debitoren 65 %, Lehrling L1/L2 jeweils 64 %, allgemeine Stunden L1 53 %, L2 49 %, L3 36 %. Es gibt keine Print-Area-Definitionen. Kopf-/Fusszeilen, Seitenränder, Zeilen-/Spaltenmasse, Zellformate, verbundene Zellen, Filter, Schutzstatus und Ansichten stehen blattweise im JSON.

Die App verwendet native Tabellen und paginierte A4-Querformatberichte mit wiederholten Tabellenköpfen. Sie übernimmt den Inhalt und die Berechnung, nicht die extrem verkleinerten Excel-Druckraster. CSV und PDF sind ohne Excel exportierbar. Zum Drucken einen Bericht als PDF ausgeben und aus der Vorschau im Standard-PDF-Programm öffnen.

## Lohnausweis-PDF

Die aktuelle offizielle ESTV-Vorlage hat eine Seite und 44 Formularfelder. Die App ordnet ihre verständlichen internen Feldnamen beim Export den offiziellen Feldnamen zu und bettet die erzeugten Darstellungen fest in die PDF-Seite ein.

| Funktion | PDF-Felder |
|---|---|
| Art, AHV, Geburtsdatum, Jahr, Zeitraum | `OptionKreuzOhneRahmen_A/B`, `AHVLinks_C`, `TextLinks_C-GebDatum`, `TextLinks_D`, `TextLinks_E-von/bis` |
| Beförderung / Verpflegung | `OptionKreuzOhneRahmen_F/G` |
| Adresse | `TextMehrzeiligLinks_Empfaenger` |
| Lohn, Abzüge und Spesen | `DezZahlNull_1` bis `DezZahlNull_13_3` sowie die zugehörigen Art-Felder |
| Weitere Angaben | `TextLinks_14_1/14_2/15_1/15_2` |
| Ort, Datum und Aussteller | `TextLinks_I`, `TextMehrzeiligLinks_Bestaetigung` |

Die Summen werden unabhängig vom PDF-Viewer in Python berechnet:

- `8 = 1 + 2-1 + 2-2 + 2-3-2 + 3-2 + 4-2 + 5 + 6 + 7-1-2`.
- `11 = 8 − abzuege`.

Bei Null zeigen Brutto und Netto im Original eine leere Zeichenfolge; diese Darstellung ist übernommen. Die App verwendet ganze Franken, wie auf der Vorlage verlangt. Die JavaScript-Eingabehilfen werden nicht zur Laufzeit ausgeführt: die Masken übernehmen numerische Eingabe und die Berechnungen laufen in Python. Die PDF-Aktionen werden aus der Ausgabe entfernt, damit keine vom Viewer abhängige Neuberechnung entsteht.

Vor jedem Export setzt die App alle tatsächlichen Formularfelder zurück, schreibt den gespeicherten Ausweis und berechnet die Summen neu. Checkbox-Zustände werden direkt aus der jeweiligen offiziellen Felddefinition gelesen. Anschliessend werden die Formularansichten sichtbar in die Seite eingebettet und die interaktiven Widgets entfernt, damit Vorschau, Druck und Archiv dieselben Angaben zeigen.

## Nachweis

Die Tests werten die Originalformeln unabhängig aus und vergleichen alle 40 Formeln mit der nativen Umsetzung. Die 39 Stundenformeln werden über 16 Szenarien (Originalleerstand plus 15 deterministische, befüllte Szenarien) geprüft. Zusätzlich werden die gespeicherten Excel-Ergebnisse verglichen. Die Referenz-Auswertung existiert nur in den Tests und ist kein Excel-Interpreter der Anwendung.

Siehe `TESTPROTOKOLL.md` für Datenbank-, PDF-, UI- und Windows-Build-Prüfungen.
