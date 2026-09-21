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
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from .domain import KINDS, chf, number, display_date, salary_totals


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


def salary_pdf(fields, destination, template=None):
    source = Path(template) if template else resource_path("templates/Vorlage_Lohnausweis.pdf")
    reader = PdfReader(source)
    writer = PdfWriter()
    writer.clone_document_from_reader(reader)
    definitions = writer.get_fields() or {}
    # Each original widget is in the canonical field tree (verified in tests).
    # Reset ALL original sample values, including hidden values and checkboxes.
    values = {name: "/Off" if field.get("/FT") == "/Btn" else ""
              for name, field in definitions.items() if field.get("/FT")}
    unknown = set(fields) - set(values)
    if unknown:
        raise ValueError("Unbekannte PDF-Felder: " + ", ".join(sorted(unknown)))
    values.update({k: str(v) for k, v in fields.items()})
    values.update(salary_totals(values))
    # Python owns calculations. Remove legacy Acrobat scripts, whose recalculation
    # otherwise depends on the viewer; totals stay read-only in the exported form.
    form = writer.root_object["/AcroForm"]
    form.pop(NameObject("/CO"), None)
    for page in writer.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            widget.pop(NameObject("/AA"), None)
            if field_name(widget) in ("8", "11", "abzuege"):
                widget[NameObject("/Ff")] = NumberObject(int(widget.get("/Ff", 0)) | 1)
    formatted = dict(values)
    for page in writer.pages:
        for ref in page.get("/Annots", []):
            widget = ref.get_object()
            name = field_name(widget)
            if name in values and widget.get("/FT") == "/Tx" and values[name]:
                width = float(widget["/Rect"][2]) - float(widget["/Rect"][0]) - 5
                size = min(10.0, 10 * width / max(stringWidth(values[name], "Helvetica", 10), 1))
                if size < 6:
                    raise ValueError(f"Text für PDF-Feld {name} ist zu lang. Bitte kürzen oder auf Fortsetzungszeilen verteilen.")
                formatted[name] = (values[name], "/Arial", size)
    writer.update_page_form_field_values(None, formatted, auto_regenerate=False)
    writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        writer.write(output)
    validate_salary_pdf(destination, values)
    return destination


def validate_salary_pdf(path, expected):
    reader = PdfReader(path)
    fields = reader.get_fields() or {}
    for name, value in expected.items():
        if name not in fields or str(fields[name].get("/V", "")) != str(value):
            raise ValueError(f"PDF-Feld konnte nicht korrekt geschrieben werden: {name}")
    seen = set()
    for page in reader.pages:
        for ref in page.get("/Annots", []):
            obj = ref.get_object()
            if obj.get("/Subtype") != "/Widget":
                continue
            name = field_name(obj)
            seen.add(name)
            value = obj.get("/V")
            if value is None and obj.get("/Parent"):
                value = obj["/Parent"].get("/V")
            if name in expected and str(value if value is not None else "") != str(expected[name]):
                raise ValueError(f"PDF-Anzeige und Feldinhalt weichen ab: {name}")
            if name in expected and not obj.get("/AP", {}).get("/N"):
                raise ValueError(f"PDF-Feld ohne Darstellung: {name}")
    if set(expected) - seen:
        raise ValueError("Die PDF-Vorlage enthält Felder ohne sichtbare Zuordnung.")


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
