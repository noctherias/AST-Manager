"""Fill the supplied Lohnbuch workbook while preserving its native layout."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import os
import re
import tempfile
import zipfile

from .documents import resource_path
from .timesheet_excel import _replace_cell, _replace_formula_cell


def _excel_date(value):
    if not value:
        return None
    parsed = date.fromisoformat(str(value))
    return (parsed - date(1899, 12, 30)).days


def export_payroll_book(destination, employee, year, records, company_settings=None):
    destination = Path(destination).absolute()
    if destination.suffix.lower() != ".xlsx":
        destination = destination.with_suffix(".xlsx")
    destination.parent.mkdir(parents=True, exist_ok=True)
    template = resource_path("templates/Lohnbuch_Vorlage.xlsx")
    if not template.exists():
        raise ValueError("Die Lohnbuch-Vorlage fehlt in der Programminstallation.")
    with zipfile.ZipFile(template, "r") as source:
        infos = source.infolist()
        members = {info.filename: source.read(info.filename) for info in infos}
    sheet_name = "xl/worksheets/sheet1.xml"
    if sheet_name not in members:
        raise ValueError("Die Lohnbuch-Vorlage ist unvollständig.")
    xml = members[sheet_name].decode("utf-8")
    settings = company_settings or {}
    full_name = f"{employee.get('last_name', '')} {employee.get('first_name', '')}".strip()
    xml = _replace_cell(xml, "L3", int(year))
    xml = _replace_cell(xml, "L7", employee.get("ahv", ""), "string")
    xml = _replace_cell(xml, "L9", _excel_date(employee.get("birth_date")))
    xml = _replace_cell(xml, "J13", full_name, "string")
    xml = _replace_cell(xml, "J15", employee.get("address", ""), "string")
    place = " ".join(filter(None, (str(employee.get("postcode", "")).strip(),
                                   str(employee.get("city", "")).strip())))
    xml = _replace_cell(xml, "J17", place, "string")
    xml = _replace_cell(xml, "L26", "Zulagen", "string")
    city = str(settings.get("city") or "Aarburg").strip()
    xml = _replace_cell(xml, "J21", f"{city}, {date.today():%d.%m.%Y}", "string")

    by_month = {int(record["month"]): record for record in records if int(record["year"]) == int(year)}
    latest = by_month[max(by_month)] if by_month else {}
    for column, key in zip("FGHIJK", ("ahv_rate", "alv_rate", "nbuv_rate", "ktv_rate", "bvg_rate", "pk_rate")):
        xml = _replace_cell(xml, f"{column}29", int(latest.get(key) or 0) / 100000)
    for month in range(1, 14):
        row = month + 29
        record = by_month.get(month, {})
        xml = _replace_cell(xml, f"C{row}", int(record.get("gross") or 0) / 100)
        xml = _replace_cell(xml, f"L{row}", int(record.get("allowance") or 0) / 100)
        for column, key in zip("FGHIJK", ("ahv_rate", "alv_rate", "nbuv_rate", "ktv_rate", "bvg_rate", "pk_rate")):
            rate = int(record.get(key) or 0) / 100000
            deduction = round(round(int(record.get("gross") or 0) * int(record.get(key) or 0) / 100000) / 50) * 50
            xml = _replace_formula_cell(xml, f"{column}{row}",
                                        f"ROUND(C{row}*{rate:.8f}*2,0)/2", deduction / 100)
        net = (int(record.get("gross") or 0) - sum(
            round(round(int(record.get("gross") or 0) * int(record.get(key) or 0) / 100000) / 50) * 50
            for key in ("ahv_rate", "alv_rate", "nbuv_rate", "ktv_rate", "bvg_rate", "pk_rate")
        ) + int(record.get("allowance") or 0))
        xml = _replace_formula_cell(xml, f"M{row}", f"C{row}-SUM(F{row}:K{row})+L{row}", net / 100)
    for column in ("C", "F", "G", "H", "I", "J", "K", "L", "M"):
        total = 0
        if column == "C": total = sum(int(r.get("gross") or 0) for r in by_month.values())
        elif column == "L": total = sum(int(r.get("allowance") or 0) for r in by_month.values())
        elif column == "M": total = sum(int(r.get("net") or 0) for r in by_month.values())
        else:
            key = dict(zip("FGHIJK", ("ahv", "alv", "nbuv", "ktv", "bvg", "pk")))[column]
            total = sum(int(r.get(key) or 0) for r in by_month.values())
        xml = _replace_formula_cell(xml, f"{column}45", f"SUM({column}30:{column}43)", total / 100)
    for column in "FGHIJK":
        key = dict(zip("FGHIJK", ("ahv", "alv", "nbuv", "ktv", "bvg", "pk")))[column]
        xml = _replace_formula_cell(xml, f"{column}48", f"SUM({column}30:{column}43)",
                                    sum(int(r.get(key) or 0) for r in by_month.values()) / 100)
    xml = _replace_formula_cell(xml, "M48", "SUM(F48:K48)",
                                sum(int(r.get("deductions") or 0) for r in by_month.values()) / 100)
    members[sheet_name] = xml.encode("utf-8")
    workbook = members.get("xl/workbook.xml", b"").decode("utf-8")
    workbook = re.sub(r'<calcPr\b([^>]*)/?>', '<calcPr calcId="191029" fullCalcOnLoad="1" forceFullCalc="1"/>', workbook, count=1)
    members["xl/workbook.xml"] = workbook.encode("utf-8")
    handle, temporary = tempfile.mkstemp(prefix="ast-lohnbuch-", suffix=".xlsx", dir=destination.parent)
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, "w") as target:
            for info in infos:
                target.writestr(info, members[info.filename])
        with zipfile.ZipFile(temporary, "r") as check:
            if check.testzip() is not None:
                raise ValueError("Die Excel-Datei konnte nicht vollständig erstellt werden.")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination
