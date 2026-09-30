"""Original form filling, native reports and Excel-independent CSV exports."""
from __future__ import annotations

import csv
from html import escape
from pathlib import Path
import sys

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .domain import KINDS, chf, number, display_date, salary_totals


OFFICIAL_SALARY_FIELDS = {
    "A": "OptionKreuzOhneRahmen_A", "B": "OptionKreuzOhneRahmen_B",
    "F": "OptionKreuzOhneRahmen_F", "G": "OptionKreuzOhneRahmen_G",
    "13-1-1-1": "OptionKreuzOhneRahmen_13_1_1", "D": "TextLinks_D",
    "E-von": "TextLinks_E-von", "E-bis": "TextLinks_E-bis",
    "2-3-1": "TextLinks_2_3-Art", "3-1": "TextLinks_3-Art",
    "4-1": "TextLinks_4-Art", "7-1": "TextLinks_7-Art",
    "13-1-2-1": "TextLinks_13_1_2-Art", "13-2-3-1": "TextLinks_13_2_3-Art",
    "14-1": "TextLinks_14_1", "14-2": "TextLinks_14_2",
    "15-1": "TextLinks_15_1", "15-2": "TextLinks_15_2",
    "OrtDatum": "TextLinks_I", "1": "DezZahlNull_1", "2-1": "DezZahlNull_2_1",
    "2-2": "DezZahlNull_2_2", "2-3-2": "DezZahlNull_2_3", "3-2": "DezZahlNull_3",
    "4-2": "DezZahlNull_4", "5": "DezZahlNull_5", "6": "DezZahlNull_6",
    "7-1-2": "DezZahlNull_7", "8": "DezZahlNull_8", "9": "DezZahlNull_9",
    "10-1": "DezZahlNull_10_1", "10-2": "DezZahlNull_10_2", "11": "DezZahlNull_11",
    "12": "DezZahlNull_12", "13-1-1-2": "DezZahlNull_13_1_1",
    "13-1-2-2": "DezZahlNull_13_1_2", "13-2-1-2": "DezZahlNull_13_2_1",
    "13-2-2-2": "DezZahlNull_13_2_2", "13-2-3-2": "DezZahlNull_13_2_3",
    "13-3": "DezZahlNull_13_3",
}
LEGACY_SALARY_FIELDS = set(OFFICIAL_SALARY_FIELDS) | {
    "C", "C2", "CGebDatum", "HAnrede", "HName", "HAdresse", "HPostfach", "HWohnort",
    "Unterschrift1.0", "Unterschrift1.1", "Unterschrift1.2", "Unterschrift1.3",
    "Unterschrift1.4", "abzuege",
}


def resource_path(name):
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    return root / name


def field_name(obj):
    names = []
    while obj:
        if "/T" in obj:
            names.append(str(obj["/T"]))
        parent = obj.get("/Parent")
        obj = parent.get_object() if parent else None
    return ".".join(reversed(names))


def _flatten_form_appearances(writer):
    """Paint every widget appearance with a unique page resource name.

    pypdf's built-in flatten loop can reuse an earlier appearance for empty or
    hierarchical fields. Unique XObject names keep all fields in this complex
    Swiss salary certificate visible in Qt PDF, browsers and print output.
    """
    for page_index, page in enumerate(writer.pages):
        widgets = list(page.get("/Annots", []))
        for widget_index, ref in enumerate(widgets):
            widget = ref.get_object()
            if widget.get("/Subtype") != "/Widget":
                continue
            # Respect Invisible, Hidden and NoView annotation flags. The form
            # contains calculation helpers such as ``abzuege`` that must not
            # be painted onto the official document.
            if int(widget.get("/F", 0)) & (1 | 2 | 32):
                continue
            normal = widget.get("/AP", {}).get("/N")
            if normal is None:
                continue
            normal = normal.get_object()
            if hasattr(normal, "get_data"):
                appearance = normal
            else:
                state = widget.get("/AS", "/Off")
                appearance = normal.get(state) if state in normal else normal.get("/Off")
                appearance = appearance.get_object() if appearance is not None else None
            if appearance is None:
                continue
            if widget.get("/FT") == "/Btn" or (widget.get("/Parent") and widget["/Parent"].get("/FT") == "/Btn"):
                appearance.set_data(b"0 G\n1 w\n" + appearance.get_data())
            rect = widget["/Rect"]
            writer._add_apstream_object(
                page, appearance, f"AST_{page_index}_{widget_index}", rect[0], rect[1]
            )


def _official_salary_values(fields, definitions):
    unknown = set(fields) - LEGACY_SALARY_FIELDS
    if unknown:
        raise ValueError("Unbekannte PDF-Felder: " + ", ".join(sorted(unknown)))
    legacy = {key: "" for key in LEGACY_SALARY_FIELDS}
    legacy.update({"A": "/Off", "B": "/Off", "F": "/Off", "G": "/Off", "13-1-1-1": "/Off"})
    legacy.update({key: str(value) for key, value in fields.items()})
    legacy.update(salary_totals(legacy))
    values = {name: "/Off" if definition.get("/FT") == "/Btn" else ""
              for name, definition in definitions.items() if definition.get("/FT")}
    for source, target in OFFICIAL_SALARY_FIELDS.items():
        values[target] = legacy.get(source, "")
    values["AHVLinks_C"] = legacy.get("C2") or legacy.get("C", "")
    values["TextLinks_C-GebDatum"] = legacy.get("CGebDatum", "")
    values["TextMehrzeiligLinks_Empfaenger"] = "\n".join(filter(None, (
        legacy.get("HAnrede"), legacy.get("HName"), legacy.get("HAdresse"),
        legacy.get("HPostfach"), legacy.get("HWohnort"),
    )))
    values["TextMehrzeiligLinks_Bestaetigung"] = "\n".join(filter(None, (
        legacy.get(f"Unterschrift1.{index}", "") for index in range(5)
    )))
    for name, definition in definitions.items():
        if definition.get("/FT") != "/Btn":
            continue
        if values.get(name) == "/Ja":
            values[name] = next((state for state in definition.get("/_States_", []) if state != "/Off"), "/Off")
        else:
            values[name] = "/Off"
    return legacy, values


def salary_pdf(fields, destination, template=None):
    source = Path(template) if template else resource_path("templates/Vorlage_Lohnausweis.pdf")
    reader = PdfReader(source)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    definitions = writer.get_fields() or {}
    _legacy_values, values = _official_salary_values(fields, definitions)
    # Python owns calculations. Remove legacy Acrobat scripts, whose recalculation
    # otherwise depends on the viewer; totals stay read-only in the exported form.
    form = writer.root_object["/AcroForm"]
    form.pop(NameObject("/CO"), None)
    for page in writer.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            widget.pop(NameObject("/AA"), None)
            if field_name(widget) in ("DezZahlNull_8", "DezZahlNull_11"):
                widget[NameObject("/Ff")] = NumberObject(int(widget.get("/Ff", 0)) | 1)
    # Qt's PDF renderer (used by the in-app preview) does not paint AcroForm
    # widgets. Paint the generated appearances into the page content so the
    # completed certificate looks identical in the preview, browser, printout
    # and archived PDF.
    writer.update_page_form_field_values(None, values, auto_regenerate=False)
    _flatten_form_appearances(writer)
    writer.remove_annotations(subtypes="/Widget")
    writer.root_object.pop(NameObject("/AcroForm"), None)
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        writer.write(output)
    validate_salary_pdf(destination, values)
    return destination


def validate_salary_pdf(path, expected):
    reader = PdfReader(path)
    if "/AcroForm" in reader.trailer["/Root"]:
        raise ValueError("Der Lohnausweis enthält noch nicht eingebettete Formularfelder.")
    for page in reader.pages:
        for ref in page.get("/Annots", []):
            obj = ref.get_object()
            if obj.get("/Subtype") == "/Widget":
                raise ValueError("Der Lohnausweis enthält noch unsichtbare Formular-Ebenen.")
    visible_values = [str(value) for value in expected.values()
                      if value not in ("", "/Off", "/Ja")]
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    if visible_values and not any(value in extracted for value in visible_values):
        raise ValueError("Die Lohnausweisdaten wurden nicht sichtbar in die PDF-Seite eingebettet.")


def csv_export(path, headers, rows):
    with Path(path).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(headers)
        for row in rows:
            # Prevent formula execution when users later open CSV with a spreadsheet.
            writer.writerow(["'" + v if isinstance(v, str) and v.startswith(("=", "+", "-", "@")) else v for v in row])
    return Path(path)


def report_pdf(path, title, subtitle, headers, rows, summary, widths=None):
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ASTTitle", fontName="Helvetica-Bold", fontSize=22, leading=27, textColor=colors.HexColor("#152b3a")))
    styles.add(ParagraphStyle(name="ASTCell", fontName="Helvetica", fontSize=8, leading=11))
    story = [Paragraph(escape(title), styles["ASTTitle"]), Spacer(1, 4 * mm),
             Paragraph(escape(subtitle), styles["Normal"]), Spacer(1, 6 * mm),
             Paragraph(escape(summary), styles["Normal"]), Spacer(1, 6 * mm)]
    data = [[Paragraph(escape(str(v)), styles["ASTCell"]) for v in headers]]
    data.extend([[Paragraph(escape(str(v)).replace("\n", "<br/>"), styles["ASTCell"]) for v in row] for row in rows])
    if len(data) == 1:
        data.append([Paragraph("Keine Einträge", styles["ASTCell"])] + [""] * (len(headers) - 1))
    table = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2f1ed")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f6f8")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"), ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8), ("LINEBELOW", (0, 0), (-1, 0), .5, colors.HexColor("#bed9d0")),
    ]))
    story.append(table)

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(16 * mm, 10 * mm, "AST Verwaltung")
        canvas.drawRightString(281 * mm, 10 * mm, f"Seite {doc.page}")

    SimpleDocTemplate(str(path), pagesize=landscape(A4), rightMargin=16 * mm, leftMargin=16 * mm,
                      topMargin=15 * mm, bottomMargin=18 * mm, title=title, author="AST Verwaltung").build(story, onFirstPage=footer, onLaterPages=footer)
    return Path(path)


def time_report(path, employee, balance, entries):
    name = employee["first_name"] + " " + employee["last_name"]
    summary = (f"Anspruch {number(balance['allowance'])} h  |  Übertrag {number(balance['carry'])} h  |  "
               f"Ferien {number(balance['vacation'])} h  |  Überzeit {number(balance['overtime'])} h  |  "
               f"Guthaben {number(balance['balance'])} h<br/>")
    summary = summary.replace("<br/>", ". ") + (f"Krankheit kumuliert {number(balance['sick_total'])} h; Unfall kumuliert {number(balance['accident_total'])} h.")
    return report_pdf(path, "Stundennachweis · " + name,
                      f"{balance['label']} · {display_date(balance['start'])} bis {display_date(balance['end'])}",
                      ["Datum", "Kategorie", "Stunden", "Bemerkung"],
                      [[display_date(e["day"]), KINDS[e["kind"]], number(e["hours"]), e["note"]] for e in entries],
                      summary, [90, 120, 75, 465])
