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

PLACEHOLDER_INFO = {
    "{kunde}": "Name oder Firma des Empfängers",
    "{kundennummer}": "Kundennummer des Empfängers",
    "{kundenadresse}": "Strasse des Empfängers",
    "{kunden_plz}": "Postleitzahl des Empfängers",
    "{kunden_ort}": "Ort des Empfängers",
    "{kunden_email}": "E-Mail-Adresse des Empfängers",
    "{rechnungsnummer}": "Rechnungsnummer aus der Eingabemaske",
    "{rechnungsdatum}": "Datum der Rechnung",
    "{faelligkeit}": "Fälligkeitsdatum der Rechnung",
    "{betrag}": "Offener Betrag inklusive CHF",
    "{mahndatum}": "Erstellungsdatum des Mahnbriefs",
    "{frist}": "Automatisch berechnete neue Zahlungsfrist",
    "{frist_tage}": "Anzahl Tage der neuen Zahlungsfrist",
    "{tage_ueberfaellig}": "Tage seit dem Fälligkeitsdatum",
    "{mahnstufe}": "Bezeichnung der ausgewählten Mahnstufe",
    "{firma}": "Eigener Firmenname",
    "{firmenadresse}": "Eigene Firmenstrasse",
    "{firmen_plz}": "Eigene Firmen-PLZ",
    "{firmen_ort}": "Eigener Firmenort",
    "{telefon}": "Eigene Telefonnummer",
    "{kontakt}": "Eigene Kontaktperson",
    "{firmen_email}": "Eigene E-Mail-Adresse",
    "{website}": "Eigene Website",
}
PLACEHOLDERS = tuple(PLACEHOLDER_INFO)
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
    due = date.fromisoformat(invoice["due"])
    deadline_days = deadlines[int(level)]
    return {
        "kunde": invoice["customer"],
        "kundennummer": invoice.get("customer_number", ""),
        "kundenadresse": invoice.get("customer_address", ""),
        "kunden_plz": invoice.get("customer_postcode", ""),
        "kunden_ort": invoice.get("customer_city", ""),
        "kunden_email": invoice.get("customer_email", ""),
        "rechnungsnummer": invoice["number"],
        "rechnungsdatum": display_date(invoice["issued"]),
        "faelligkeit": display_date(invoice["due"]),
        "betrag": chf(invoice["open"]),
        "mahndatum": created.strftime("%d.%m.%Y"),
        "frist": (created + timedelta(days=deadline_days)).strftime("%d.%m.%Y"),
        "frist_tage": str(deadline_days),
        "tage_ueberfaellig": str(max(0, (created - due).days)),
        "firma": settings.get("company", ""),
        "firmenadresse": settings.get("address", ""),
        "firmen_plz": settings.get("postcode", ""),
        "firmen_ort": settings.get("city", ""),
        "telefon": settings.get("phone", ""),
        "kontakt": settings.get("contact", ""),
        "firmen_email": settings.get("email", ""),
        "website": settings.get("website", ""),
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
    body = ParagraphStyle("ASTLetter", parent=styles["Normal"], fontName="Helvetica", fontSize=10,
                          leading=12.5, textColor=colors.black)
    small = ParagraphStyle("ASTSmall", parent=body, fontSize=8, leading=10)
    right = ParagraphStyle("ASTRight", parent=body, alignment=TA_RIGHT)
    footer_right = ParagraphStyle("ASTFooterRight", parent=small, alignment=TA_RIGHT)
    subject = ParagraphStyle("ASTSubject", parent=body, fontName="Helvetica-Bold", fontSize=13, leading=16)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    story = []
    logo_path = settings.get("logo_path", "").strip()
    logo = None
    if logo_path and Path(logo_path).is_file():
        try:
            width, height = ImageReader(logo_path).getSize()
            scale = min((58 * mm) / width, (25 * mm) / height)
            logo = Image(logo_path, width=width * scale, height=height * scale)
        except Exception as exc:
            raise ValueError("Das gespeicherte Firmenlogo kann nicht gelesen werden.") from exc
    company_name = escape(settings.get("company", ""))
    if logo is None:
        logo = Paragraph(f"<b>{company_name}</b>", ParagraphStyle(
            "ASTCompany", parent=body, fontName="Helvetica-Bold", fontSize=18, leading=21))
    company_lines = [settings.get("address", ""),
                     " ".join(filter(None, (settings.get("postcode", ""), settings.get("city", "")))),
                     settings.get("phone", ""), settings.get("email", ""), settings.get("website", "")]
    identity = [logo, Spacer(1, 3 * mm), Paragraph("<br/>".join(escape(v) for v in company_lines if v), small)]
    header = Table([[identity, ""]], colWidths=[82 * mm, 78 * mm], hAlign="LEFT")
    header.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                ("TOPPADDING", (0, 0), (-1, -1), 0),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
    story.extend((header, Spacer(1, 11 * mm)))
    recipient = [invoice["customer"], invoice.get("customer_address", ""),
                 " ".join(filter(None, (invoice.get("customer_postcode", ""), invoice.get("customer_city", ""))))]
    recipient_block = Table([["", Paragraph("<br/>".join(escape(v) for v in recipient if v), body)]],
                            colWidths=[92 * mm, 68 * mm], hAlign="LEFT")
    recipient_block.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                         ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                         ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    customer_number = invoice.get("customer_number", "").strip()
    account_lines = []
    if customer_number:
        account_lines.append(f"Kunden-Nr. {escape(customer_number)}")
    account_lines.append(f"Zahlungen berücksichtigt bis {created.strftime('%d.%m.%Y')}")
    account = Paragraph("<br/><br/>".join(account_lines), body)
    place_date = Paragraph(f"{escape(settings.get('city', ''))}, {created.strftime('%d.%m.%Y')}", right)
    info = Table([[account, place_date]], colWidths=[92 * mm, 68 * mm], hAlign="LEFT")
    info.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                              ("LEFTPADDING", (0, 0), (-1, -1), 0),
                              ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    story.extend((recipient_block, Spacer(1, 17 * mm), info, Spacer(1, 14 * mm),
                  Paragraph(f"{REMINDER_LEVELS[level]} zur Rechnung {escape(invoice['number'])}", subject),
                  Spacer(1, 5 * mm)))
    text = format_reminder_text(template or reminder_text(settings, level), invoice, settings, level, created)
    story.extend(_paragraphs(text, body))
    gross = invoice.get("amount", invoice["open"])
    details = [
        ["Rechnung-Nr.", "Belegdatum", "Verfalldatum", "Art", "Betrag brutto", "Betrag offen", "Stufe"],
        [invoice["number"], display_date(invoice["issued"]), display_date(invoice["due"]), "Faktura",
         chf(gross), chf(invoice["open"]), str(level)],
        ["", "", "", "", "Total  " + chf(gross), chf(invoice["open"]), ""],
    ]
    table = Table(details, colWidths=[24 * mm, 23 * mm, 23 * mm, 17 * mm, 30 * mm, 29 * mm, 14 * mm], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.2),
        ("LEADING", (0, 0), (-1, -1), 10),
        ("LINEBELOW", (0, 0), (-1, 0), .55, colors.black),
        ("LINEBELOW", (0, 1), (-1, 1), .55, colors.black),
        ("ALIGN", (4, 1), (5, -1), "RIGHT"),
        ("ALIGN", (6, 0), (6, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]))
    story.extend((Spacer(1, 7 * mm), table, Spacer(1, 11 * mm),
                  Paragraph("Sollte sich Ihre Zahlung mit diesem Schreiben gekreuzt haben, bitten wir Sie, dieses als gegenstandslos zu betrachten.", body),
                  Spacer(1, 13 * mm), Paragraph("Freundliche Grüsse", body), Spacer(1, 5 * mm),
                  Paragraph(company_name, body)))

    def footer(canvas, document):
        canvas.setStrokeColor(colors.HexColor("#555555"))
        canvas.setLineWidth(.6)
        canvas.line(20 * mm, 27 * mm, 190 * mm, 27 * mm)
        footer_left = [f"<b>{company_name}</b>", escape(settings.get("address", "")),
                       escape(" ".join(filter(None, (settings.get("postcode", ""), settings.get("city", ""))))),
                       escape(settings.get("phone", "")), escape(settings.get("email", ""))]
        footer_middle = ["Es gelten unsere AGB"]
        if settings.get("website", ""):
            footer_middle.append("Mehr Infos auf <b>" + escape(settings["website"]) + "</b>")
        left_paragraph = Paragraph("<br/>".join(value for value in footer_left if value), small)
        middle_paragraph = Paragraph("<br/>".join(footer_middle), small)
        page_paragraph = Paragraph(f"Seite {document.page}", footer_right)
        footer_table = Table([[left_paragraph, middle_paragraph, page_paragraph]],
                             colWidths=[72 * mm, 58 * mm, 40 * mm])
        footer_table.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"),
                                          ("LEFTPADDING", (0, 0), (-1, -1), 0),
                                          ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                                          ("TOPPADDING", (0, 0), (-1, -1), 0),
                                          ("BOTTOMPADDING", (0, 0), (-1, -1), 0)]))
        footer_table.wrapOn(canvas, 170 * mm, 22 * mm)
        footer_table.drawOn(canvas, 20 * mm, 5 * mm)

    SimpleDocTemplate(str(destination), pagesize=A4, leftMargin=20 * mm, rightMargin=30 * mm,
                      topMargin=15 * mm, bottomMargin=39 * mm, title=f"{REMINDER_LEVELS[level]} {invoice['number']}",
                      author=settings.get("company", "AST Verwaltung")).build(story, onFirstPage=footer, onLaterPages=footer)
    return destination
