"""Fill the supplied Lohnbuch workbook while preserving its native layout."""
from __future__ import annotations

from datetime import date
from pathlib import Path
import os
import re
import tempfile
import zipfile
from xml.etree import ElementTree as ET

from .documents import resource_path
from .timesheet_excel import _replace_cell, _replace_formula_cell


XML_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
RATE_COLUMNS = dict(zip("FGHIJK", ("ahv_rate", "alv_rate", "nbuv_rate", "ktv_rate", "bvg_rate", "pk_rate")))


def _excel_date(value):
    if not value:
        return None
    parsed = date.fromisoformat(str(value))
    return (parsed - date(1899, 12, 30)).days


def _cell(root, reference):
    return root.find(f".//x:c[@r='{reference}']", XML_NS)


def _number(root, reference):
    item = _cell(root, reference)
    value = item.find("x:v", XML_NS) if item is not None else None
    try:
        return float(value.text) if value is not None and value.text else 0.0
    except ValueError:
        return 0.0


def _formula(root, reference):
    item = _cell(root, reference)
    value = item.find("x:f", XML_NS) if item is not None else None
    return value.text.strip() if value is not None and value.text else ""


def _text(root, reference, shared_strings):
    item = _cell(root, reference)
    if item is None:
        return ""
    inline = item.find("x:is/x:t", XML_NS)
    if inline is not None:
        return inline.text or ""
    value = item.find("x:v", XML_NS)
    if value is None or value.text is None:
        return ""
    if item.get("t") == "s":
        try:
            return shared_strings[int(value.text)]
        except (ValueError, IndexError):
            return ""
    return value.text


def import_payroll_book(source):
    """Read payroll books created from the AST template without executing formulas."""
    source = Path(source)
    if source.suffix.lower() not in (".xlsx", ".xlsm"):
        raise ValueError("Bitte eine Excel-Datei im Format XLSX oder XLSM auswählen.")
    try:
        with zipfile.ZipFile(source, "r") as workbook:
            sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
            shared_strings = []
            if "xl/sharedStrings.xml" in workbook.namelist():
                shared = ET.fromstring(workbook.read("xl/sharedStrings.xml"))
                for item in shared.findall("x:si", XML_NS):
                    shared_strings.append("".join(node.text or "" for node in item.findall(".//x:t", XML_NS)))
    except (KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ValueError("Die Datei ist kein gültiges Lohnbuch im AST-Vorlagenlayout.") from exc
    try:
        year = int(round(_number(sheet, "L3")))
    except (TypeError, ValueError) as exc:
        raise ValueError("Das Jahr konnte im Lohnbuch nicht gelesen werden.") from exc
    if not 1900 <= year <= 2200:
        raise ValueError("Das Jahr im Lohnbuch ist ungültig.")
    header_rates = {column: round(_number(sheet, f"{column}29") * 100000) for column in "FGHIK"}
    records = []
    for month in range(1, 14):
        row = month + 29
        gross = round(_number(sheet, f"C{row}") * 100)
        allowance = round(_number(sheet, f"L{row}") * 100)
        deduction_values = {column: round(_number(sheet, f"{column}{row}") * 100) for column in "FGHIJK"}
        if not gross and not allowance and not any(deduction_values.values()):
            continue
        record = {"month": month, "gross": gross, "allowance": allowance, "note": "Excel-Import"}
        for column in "FGHIK":
            formula = _formula(sheet, f"{column}{row}")
            match = re.search(rf"C{row}\*([0-9]+(?:\.[0-9]+)?)", formula, re.IGNORECASE)
            if match:
                rate = round(float(match.group(1)) * 100000)
            elif re.search(rf"\$?{column}\$?29", formula, re.IGNORECASE):
                rate = header_rates[column]
            elif gross:
                rate = round(deduction_values[column] / gross * 100000)
            else:
                rate = 0
            record[RATE_COLUMNS[column]] = rate
        bvg_formula = _formula(sheet, f"J{row}")
        bvg_percent = re.search(rf"C{row}\*([0-9]+(?:\.[0-9]+)?)", bvg_formula, re.IGNORECASE)
        if bvg_percent or re.search(r"\$?J\$?29", bvg_formula, re.IGNORECASE):
            record["bvg_mode"] = "percent"
            record["bvg_rate"] = (round(float(bvg_percent.group(1)) * 100000)
                                  if bvg_percent else round(_number(sheet, "J29") * 100000))
            record["bvg_amount"] = 0
        else:
            record["bvg_mode"] = "fixed"
            record["bvg_rate"] = 0
            record["bvg_amount"] = deduction_values["J"]
        records.append(record)
    if not records:
        raise ValueError("Im ausgewählten Lohnbuch wurden keine Monatslöhne gefunden.")
    return {"year": year, "employee_name": _text(sheet, "J13", shared_strings), "records": records}


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
    for column, key in RATE_COLUMNS.items():
        if column == "J" and latest.get("bvg_mode") == "fixed":
            xml = _replace_cell(xml, "J29", "fix CHF", "string")
        else:
            xml = _replace_cell(xml, f"{column}29", int(latest.get(key) or 0) / 100000)
    for month in range(1, 14):
        row = month + 29
        record = by_month.get(month, {})
        xml = _replace_cell(xml, f"C{row}", int(record.get("gross") or 0) / 100)
        xml = _replace_cell(xml, f"L{row}", int(record.get("allowance") or 0) / 100)
        for column, key in RATE_COLUMNS.items():
            if column == "J" and record.get("bvg_mode") == "fixed":
                fixed = int(record.get("bvg_amount") or 0)
                xml = _replace_formula_cell(xml, f"J{row}", f"{fixed / 100:.2f}", fixed / 100)
                continue
            rate = int(record.get(key) or 0) / 100000
            deduction = round(round(int(record.get("gross") or 0) * int(record.get(key) or 0) / 100000) / 50) * 50
            xml = _replace_formula_cell(xml, f"{column}{row}",
                                        f"ROUND(C{row}*{rate:.8f}*2,0)/2", deduction / 100)
        percentage_keys = ["ahv_rate", "alv_rate", "nbuv_rate", "ktv_rate", "pk_rate"]
        deductions = sum(
            round(round(int(record.get("gross") or 0) * int(record.get(key) or 0) / 100000) / 50) * 50
            for key in percentage_keys)
        deductions += (int(record.get("bvg_amount") or 0) if record.get("bvg_mode") == "fixed" else
                       round(round(int(record.get("gross") or 0) * int(record.get("bvg_rate") or 0) / 100000) / 50) * 50)
        net = int(record.get("gross") or 0) - deductions + int(record.get("allowance") or 0)
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
