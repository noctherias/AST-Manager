"""Business rules translated from the supplied cells; no Excel runtime."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

KINDS = {"vacation": "Ferien", "overtime": "Überzeit", "sick": "Krankheit", "accident": "Unfall"}
TIME_CODES = {
    "": "Normaler Arbeitstag", "U": "Ferien · ganzer Tag", "UH": "Ferien · halber Tag",
    "K": "Krank · ganzer Tag", "KR": "Krank · Restzeit", "G": "Gleittag",
    "H": "Homeoffice", "F": "Feiertag", "KU": "Kurzarbeit · ganzer Tag",
    "KA": "Kurzarbeit · Restzeit", "B": "Bereitschaft",
}
SALARY_AMOUNTS = [
    ("1", "1 · Lohn / Rente"),
    ("2-1", "2.1 · Verpflegung und Unterkunft"),
    ("2-2", "2.2 · Privatanteil Geschäftswagen"),
    ("2-3-2", "2.3 · Andere Gehaltsnebenleistungen"),
    ("3-2", "3 · Unregelmässige Leistungen"),
    ("4-2", "4 · Kapitalleistungen"),
    ("5", "5 · Beteiligungsrechte"),
    ("6", "6 · Verwaltungsratsentschädigungen"),
    ("7-1-2", "7 · Andere Leistungen"),
    ("9", "9 · AHV / IV / EO / ALV / NBUV"),
    ("10-1", "10.1 · Ordentliche BVG-Beiträge"),
    ("10-2", "10.2 · BVG-Einkauf"),
    ("12", "12 · Quellensteuer"),
    ("13-1-1-2", "13.1.1 · Reise, Verpflegung, Übernachtung"),
    ("13-1-2-2", "13.1.2 · Übrige effektive Spesen"),
    ("13-2-1-2", "13.2.1 · Repräsentationsspesen"),
    ("13-2-2-2", "13.2.2 · Autospesen"),
    ("13-2-3-2", "13.2.3 · Übrige Pauschalspesen"),
    ("13-3", "13.3 · Weiterbildung"),
]
SALARY_TEXT = [
    ("2-3-1", "2.3 · Art der Nebenleistung"), ("3-1", "3 · Art der unregelmässigen Leistung"),
    ("4-1", "4 · Art der Kapitalleistung"), ("7-1", "7 · Art der anderen Leistung"),
    ("13-1-2-1", "13.1.2 · Art der übrigen Spesen"), ("13-2-3-1", "13.2.3 · Art der Pauschalspesen"),
    ("14-1", "14 · Weitere Gehaltsnebenleistungen"), ("14-2", "14 · Fortsetzung"),
    ("15-1", "15 · Bemerkungen"), ("15-2", "15 · Fortsetzung"),
]
SALARY_FLAGS = [("F", "Unentgeltliche Beförderung zum Arbeitsort"),
                ("G", "Kantinenverpflegung / Lunch-Checks"),
                ("13-1-1-1", "13.1.1 · Spesen nach Vorgaben der Wegleitung (Kreuz)")]
GROSS_FIELDS = [n for n, _ in SALARY_AMOUNTS[:9]]
DEDUCTION_FIELDS = ["9", "10-1", "10-2"]


def units(value, scale=100) -> int:
    """Exact cents/hundredths of an hour; reject silent rounding."""
    try:
        d = Decimal(str(value).strip().replace("'", "").replace("’", "").replace(" ", "").replace(",", "."))
        n = d * scale
        if not d.is_finite() or n != n.to_integral_value():
            raise ValueError("Bitte höchstens zwei Nachkommastellen eingeben.")
        return int(n)
    except (InvalidOperation, TypeError):
        raise ValueError("Bitte eine gültige Zahl eingeben.") from None


def number(value: int, suffix="") -> str:
    return f"{value / 100:,.2f}".replace(",", "’") + suffix


def chf(value: int) -> str:
    return "CHF " + number(value)


def iso(value: str) -> str:
    try:
        return date.fromisoformat(value).isoformat()
    except (ValueError, TypeError):
        raise ValueError("Bitte ein gültiges Datum auswählen.") from None


def display_date(value: str | None) -> str:
    return date.fromisoformat(value).strftime("%d.%m.%Y") if value else "–"


def scheduled_work_minutes(value: str | date) -> int:
    """Regular AST working time: Mon–Thu 8.75 h, Fri 8.25 h."""
    workday = date.fromisoformat(value) if isinstance(value, str) else value
    if workday.weekday() < 4:
        return 8 * 60 + 45
    if workday.weekday() == 4:
        return 8 * 60 + 15
    return 0


def worked_minutes(record: dict) -> int:
    """Return direct working minutes, with compatibility for old clock records."""
    direct = record.get("worked_minutes")
    if direct is not None:
        return max(0, int(direct))
    total = 0
    for start, end in ((record.get("start_1"), record.get("end_1")),
                       (record.get("start_2"), record.get("end_2"))):
        if start is not None and end is not None:
            total += (int(end) - int(start)) % 1440
    return max(0, total - int(record.get("break_minutes") or 0))


def invoice_state(amount: int, paid: int, due: str, today=None) -> str:
    if paid >= amount:
        return "Bezahlt"
    if due and due < (today or date.today()).isoformat():
        return "Überfällig"
    return "Teilbezahlt" if paid else "Offen"


def period_balance(allowance, taken, overtime, carry=0, sick=0, accident=0,
                   previous_sick=0, previous_accident=0):
    """B22/B66/B79; E22; G22/I22; L22/N22; O22/Q22 in both workbooks."""
    return {"allowance": allowance, "vacation": taken, "remaining": allowance - taken,
            "overtime": overtime, "carry": carry, "balance": carry + allowance - taken + overtime,
            "sick": sick, "accident": accident,
            "sick_total": previous_sick + sick, "accident_total": previous_accident + accident}


def salary_totals(fields):
    amounts = {}
    for key, _ in SALARY_AMOUNTS:
        raw = fields.get(key, "")
        val = units(raw or 0, 1)
        if val < 0 or val > 999999999:
            raise ValueError("Lohnausweis: Beträge müssen zwischen 0 und 999’999’999 ganzen Franken liegen.")
        amounts[key] = val
    gross = sum(amounts[k] for k in GROSS_FIELDS)
    deductions = sum(amounts[k] for k in DEDUCTION_FIELDS)
    if deductions > gross:
        raise ValueError("Die Abzüge dürfen den Bruttolohn nicht übersteigen.")
    # The original form's calculation scripts display zero gross/net as blank.
    return {"8": str(gross) if gross else "", "abzuege": str(deductions),
            "11": str(gross - deductions) if gross != deductions else ""}
