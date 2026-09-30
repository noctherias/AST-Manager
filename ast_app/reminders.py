"""Editable reminder levels and printable A4 reminder letters."""
from __future__ import annotations

from datetime import date, timedelta
from html import escape
from pathlib import Path
from string import Formatter

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.utils import ImageReader

from .domain import chf, display_date


REMINDER_LEVELS = {
    1: "Zahlungserinnerung",
    2: "Mahnung 1",
    3: "Mahnung 2",
    4: "Betreibung",
}

DEFAULT_REMINDER_TEXTS = {
    1: ("Bei unserer Kontrolle haben wir festgestellt, dass die Rechnung {rechnungsnummer} "
        "noch nicht vollständig beglichen wurde. Vermutlich ist die Zahlung Ihrer Aufmerksamkeit entgangen.\n\n"
        "Bitte überweisen Sie den offenen Betrag von {betrag} bis spätestens {frist}."),
    2: ("Trotz unserer Zahlungserinnerung ist die Rechnung {rechnungsnummer} weiterhin offen.\n\n"
        "Wir bitten Sie, den ausstehenden Betrag von {betrag} bis spätestens {frist} zu begleichen."),
    3: ("Leider konnten wir für die Rechnung {rechnungsnummer} weiterhin keinen vollständigen Zahlungseingang feststellen.\n\n"
        "Bitte überweisen Sie den offenen Betrag von {betrag} bis spätestens {frist}."),
    4: ("Die Forderung aus der Rechnung {rechnungsnummer} ist trotz unserer bisherigen Mahnungen weiterhin offen.\n\n"
        "Wir setzen Ihnen eine letzte Zahlungsfrist bis {frist}. Nach unbenutztem Ablauf werden wir die Betreibung einleiten."),
}

PLACEHOLDERS = ("{kunde}", "{rechnungsnummer}", "{rechnungsdatum}", "{faelligkeit}",
                "{betrag}", "{frist}", "{firma}", "{mahnstufe}")
PLACEHOLDER_NAMES = {value[1:-1] for value in PLACEHOLDERS}


def reminder_text(settings, level):
    return settings.get(f"reminder_text_{int(level)}", "").strip() or DEFAULT_REMINDER_TEXTS[int(level)]


def validate_template(template):
    if not str(template).strip():
        raise ValueError("Der Mahntext darf nicht leer sein.")
    try:
        fields = {name for _, name, _, _ in Formatter().parse(template) if name}
    except ValueError as exc:
        raise ValueError("Der Mahntext enthält ungültige geschweifte Klammern.") from exc
    unknown = fields - PLACEHOLDER_NAMES
    if unknown:
        raise ValueError("Unbekannte Platzhalter: " + ", ".join("{" + name + "}" for name in sorted(unknown)))
    return str(template).strip()


def _values(invoice, settings, level, created):
    deadlines = {1: 10, 2: 7, 3: 7, 4: 5}
    return {
        "kunde": invoice["customer"],
        "rechnungsnummer": invoice["number"],
        "rechnungsdatum": display_date(invoice["issued"]),
        "faelligkeit": display_date(invoice["due"]),
        "betrag": chf(invoice["open"]),
        "frist": (created + timedelta(days=deadlines[int(level)])).strftime("%d.%m.%Y"),
        "firma": settings.get("company", ""),
        "mahnstufe": REMINDER_LEVELS[int(level)],
    }


def format_reminder_text(template, invoice, settings, level, created=None):
    try:
        return template.format_map(_values(invoice, settings, level, created or date.today()))
    except KeyError as exc:
        raise ValueError(f"Unbekannter Platzhalter im Mahntext: {{{exc.args[0]}}}") from None
    except ValueError as exc:
        raise ValueError("Der Mahntext enthält ungültige geschweifte Klammern.") from exc


def _paragraphs(text, style):
    result = []
    for part in text.replace("\r\n", "\n").split("\n\n"):
        if part.strip():
            result.extend((Paragraph(escape(part.strip()).replace("\n", "<br/>"), style), Spacer(1, 4 * mm)))
    return result


def reminder_pdf(path, invoice, settings, level, template=None, created=None):
    level = int(level)
    if level not in REMINDER_LEVELS:
        raise ValueError("Bitte eine Mahnstufe zwischen 1 und 4 auswählen.")
    if invoice["open"] <= 0:
        raise ValueError("Für eine bezahlte Rechnung kann kein Mahnbrief erstellt werden.")
    created = created or date.today()
    styles = getSampleStyleSheet()
    body = ParagraphStyle("ASTLetter", parent=styles["Normal"], fontName="Helvetica", fontSize=10.5,
                          leading=15, textColor=colors.HexColor("#172f3d"))
    small = ParagraphStyle("ASTSmall", parent=body, fontSize=8.5, leading=12, textColor=colors.HexColor("#536b79"))
    right = ParagraphStyle("ASTRight", parent=small, alignment=TA_RIGHT)
    subject = ParagraphStyle("ASTSubject", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=17)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    story = []
    logo_path = settings.get("logo_path", "").strip()
    logo = Spacer(45 * mm, 20 * mm)
    if logo_path and Path(logo_path).is_file():
        try:
            width, height = ImageReader(logo_path).getSize()
            scale = min((45 * mm) / width, (22 * mm) / height)
            logo = Image(logo_path, width=width * scale, height=height * scale)
        except Exception as exc:
            raise ValueError("Das gespeicherte Firmenlogo kann nicht gelesen werden.") from exc
    company_lines = [settings.get(key, "") for key in ("company", "address")]
    company_lines.append(" ".join(filter(None, (settings.get("postcode", ""), settings.get("city", "")))))
    company_lines.extend(settings.get(key, "") for key in ("phone", "contact"))
    company = Paragraph("<br/>".join(escape(v) for v in company_lines if v), right)
    header = Table([[logo, company]], colWidths=[92 * mm, 78 * mm], hAlign="LEFT")
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.extend((header, Spacer(1, 18 * mm)))
    recipient = [invoice["customer"], invoice.get("customer_address", ""),
                 " ".join(filter(None, (invoice.get("customer_postcode", ""), invoice.get("customer_city", ""))))]
    story.append(Paragraph("<br/>".join(escape(v) for v in recipient if v), body))
    story.extend((Spacer(1, 15 * mm), Paragraph(f"{escape(settings.get('city', ''))}, {created.strftime('%d.%m.%Y')}", right),
                  Spacer(1, 9 * mm), Paragraph(f"{REMINDER_LEVELS[level]} · Rechnung {escape(invoice['number'])}", subject),
                  Spacer(1, 6 * mm), Paragraph("Sehr geehrte Damen und Herren", body), Spacer(1, 5 * mm)))
    text = format_reminder_text(template or reminder_text(settings, level), invoice, settings, level, created)
    story.extend(_paragraphs(text, body))
    details = [["Rechnung", invoice["number"]], ["Rechnungsdatum", display_date(invoice["issued"])],
               ["Fällig am", display_date(invoice["due"])], ["Offener Betrag", chf(invoice["open"])]]
    table = Table(details, colWidths=[48 * mm, 112 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#edf3f5")),
                               ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                               ("FONTNAME", (1, -1), (1, -1), "Helvetica-Bold"),
                               ("GRID", (0, 0), (-1, -1), .4, colors.HexColor("#cedbe1")),
                               ("PADDING", (0, 0), (-1, -1), 8)]))
    story.extend((table, Spacer(1, 10 * mm), Paragraph("Freundliche Grüsse", body), Spacer(1, 8 * mm),
                  Paragraph(escape(settings.get("company", "")), body)))

    def footer(canvas, document):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#718492"))
        canvas.drawString(22 * mm, 13 * mm, settings.get("company", ""))
        canvas.drawRightString(188 * mm, 13 * mm, f"Seite {document.page}")

    SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=25 * mm, rightMargin=25 * mm,
                      topMargin=20 * mm, bottomMargin=22 * mm, title=f"{REMINDER_LEVELS[level]} {invoice['number']}",
                      author=settings.get("company", "AST Verwaltung")).build(story, onFirstPage=footer, onLaterPages=footer)
    return destination
