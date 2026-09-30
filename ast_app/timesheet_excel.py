"""Fill the supplied macro workbook without rebuilding its OOXML package.

Only the intended input cells are changed. VBA, controls, drawings, printer
settings, formulas, validation and the remaining ZIP members stay byte-for-byte
identical.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
from html import escape
from pathlib import Path
import os
import re
import tempfile
import zipfile

from .documents import resource_path


MONTH_SHEETS = {month: f"xl/worksheets/sheet{month + 5}.xml" for month in range(1, 13)}
INPUT_COLUMNS = ("D", "E", "F", "G", "H", "J", "O")


def _cell_pattern(reference: str):
    return re.compile(
        rf'<c\b(?=[^>]*\br="{re.escape(reference)}")(?P<attrs>[^>]*?)(?:\s*/>|>(?P<body>.*?)</c>)',
        re.DOTALL,
    )


def _replace_cell(xml: str, reference: str, cell_value, kind="number") -> str:
    pattern = _cell_pattern(reference)
    match = pattern.search(xml)
    if not match:
        raise ValueError(f"Excel-Vorlage: Zelle {reference} wurde nicht gefunden.")
    attrs = match.group("attrs") or ""
    kept = []
    for name, content in re.findall(r'([\w:]+)="([^"]*)"', attrs):
        if name != "t":
            kept.append(f'{name}="{content}"')
    attributes = (" " + " ".join(kept)) if kept else ""
    if cell_value is None or cell_value == "":
        replacement = f"<c{attributes}/>"
    elif kind == "string":
        text = escape(str(cell_value), quote=False)
        replacement = f'<c{attributes} t="inlineStr"><is><t xml:space="preserve">{text}</t></is></c>'
    else:
        replacement = f"<c{attributes}><v>{cell_value}</v></c>"
    return xml[:match.start()] + replacement + xml[match.end():]


def _shared_string_indexes(sheet_xml: str, columns: set[str], first_row=2) -> set[int]:
    indexes = set()
    for match in re.finditer(r'<c\b([^>]*\bt="s"[^>]*)>(.*?)</c>', sheet_xml, re.DOTALL):
        ref = re.search(r'\br="([A-Z]+)(\d+)"', match.group(1))
        val = re.search(r'<v>(\d+)</v>', match.group(2))
        if ref and val and ref.group(1) in columns and int(ref.group(2)) >= first_row:
            indexes.add(int(val.group(1)))
    return indexes


def _scrub_shared_strings(xml: str, indexes: set[int]) -> str:
    items = list(re.finditer(r'<si(?:\s[^>]*)?>.*?</si>', xml, re.DOTALL))
    sensitive = []
    for index in indexes:
        if index < len(items):
            sensitive.extend(re.findall(r'<t(?:\s[^>]*)?>(.*?)</t>', items[index].group(0), re.DOTALL))
    # The workbook also stores one folder path per employee as a separate
    # shared string. Scrub every shared string containing a selected name or
    # personnel number, not only the visible employee-list cells.
    indexes |= {index for index, item in enumerate(items)
                if any(text and text in item.group(0) for text in sensitive)}
    for index in sorted(indexes, reverse=True):
        if index >= len(items):
            continue
        item = items[index]
        xml = xml[:item.start()] + "<si><t></t></si>" + xml[item.end():]
    return xml


def _time_serial(minutes: int | None):
    if minutes is None:
        return None
    return format(int(minutes) / 1440, ".15g")


def _vba_hash(members: dict[str, bytes]) -> str | None:
    value = members.get("xl/vbaProject.bin")
    return sha256(value).hexdigest() if value else None


def export_timesheet(destination, employee: dict, year: int, records: list[dict], company="") -> Path:
    """Export one employee/year into the original macro-enabled template."""
    year = int(year)
    if year < 1900 or year > 2200:
        raise ValueError("Bitte ein gültiges Exportjahr auswählen.")
    destination = Path(destination)
    if destination.suffix.lower() != ".xlsm":
        destination = destination.with_suffix(".xlsm")
    destination.parent.mkdir(parents=True, exist_ok=True)
    template = resource_path("templates/Zeiterfassung_Vorlage.xlsm")
    if not template.exists():
        raise ValueError("Die Excel-Vorlage fehlt in der Programminstallation.")

    with zipfile.ZipFile(template, "r") as source:
        infos = source.infolist()
        members = {info.filename: source.read(info.filename) for info in infos}
    original_vba = _vba_hash(members)
    required = {"xl/vbaProject.bin", "xl/worksheets/sheet1.xml", "xl/worksheets/sheet2.xml",
                "xl/worksheets/sheet3.xml", *MONTH_SHEETS.values()}
    if not required <= set(members):
        raise ValueError("Die mitgelieferte Zeiterfassungsvorlage ist unvollständig.")

    # Remove the personal names and numbers embedded in the supplied source file.
    staff = members["xl/worksheets/sheet2.xml"].decode("utf-8")
    staff_ahv = members["xl/worksheets/sheet3.xml"].decode("utf-8")
    sensitive_indexes = _shared_string_indexes(staff, {"A"}) | _shared_string_indexes(staff_ahv, {"B", "C"})
    shared = members["xl/sharedStrings.xml"].decode("utf-8")
    members["xl/sharedStrings.xml"] = _scrub_shared_strings(shared, sensitive_indexes).encode("utf-8")

    for row in range(2, 101):
        for reference, xml_name in ((f"A{row}", "xl/worksheets/sheet2.xml"),
                                    (f"B{row}", "xl/worksheets/sheet3.xml"),
                                    (f"C{row}", "xl/worksheets/sheet3.xml")):
            xml = members[xml_name].decode("utf-8")
            if _cell_pattern(reference).search(xml):
                members[xml_name] = _replace_cell(xml, reference, None).encode("utf-8")

    full_name = (employee.get("first_name", "") + " " + employee.get("last_name", "")).strip()
    staff = members["xl/worksheets/sheet2.xml"].decode("utf-8")
    staff_ahv = members["xl/worksheets/sheet3.xml"].decode("utf-8")
    members["xl/worksheets/sheet2.xml"] = _replace_cell(staff, "A2", full_name, "string").encode("utf-8")
    staff_ahv = _replace_cell(staff_ahv, "B2", full_name, "string")
    staff_ahv = _replace_cell(staff_ahv, "C2", employee.get("code", ""), "string")
    members["xl/worksheets/sheet3.xml"] = staff_ahv.encode("utf-8")

    settings = members["xl/worksheets/sheet1.xml"].decode("utf-8")
    settings = _replace_cell(settings, "C2", year)
    settings = _replace_cell(settings, "C3", full_name, "string")
    settings = re.sub(r'(<dataValidation\b[^>]*>.*?<formula1>).*?(</formula1>)',
                      lambda m: m.group(1) + '"' + escape(full_name, quote=False) + '"' + m.group(2),
                      settings, count=1, flags=re.DOTALL)
    members["xl/worksheets/sheet1.xml"] = settings.encode("utf-8")

    by_day = {date.fromisoformat(r["day"]): r for r in records if date.fromisoformat(r["day"]).year == year}
    for month, xml_name in MONTH_SHEETS.items():
        xml = members[xml_name].decode("utf-8")
        if company:
            xml = _replace_cell(xml, "C1", company, "string")
        for day_number in range(1, 32):
            row = day_number + 3
            for column in INPUT_COLUMNS:
                xml = _replace_cell(xml, f"{column}{row}", None)
            record = by_day.get(date(year, month, day_number)) if day_number <= 28 or _valid_day(year, month, day_number) else None
            if not record:
                continue
            for column, key in (("D", "start_1"), ("E", "end_1"), ("F", "start_2"), ("G", "end_2")):
                xml = _replace_cell(xml, f"{column}{row}", _time_serial(record.get(key)))
            xml = _replace_cell(xml, f"H{row}", _time_serial(record.get("break_minutes") or None))
            xml = _replace_cell(xml, f"J{row}", record.get("code", ""), "string")
            xml = _replace_cell(xml, f"O{row}", record.get("note", ""), "string")
        members[xml_name] = xml.encode("utf-8")

    workbook = members["xl/workbook.xml"].decode("utf-8")
    workbook = re.sub(r'(<[^>]*absPath\b[^>]*\burl=")[^"]*(")', r'\1\2', workbook, count=1)
    workbook = re.sub(r'<calcPr\b([^>]*)/?>',
                      lambda m: _calc_pr(m.group(1)), workbook, count=1)
    members["xl/workbook.xml"] = workbook.encode("utf-8")
    core = members["docProps/core.xml"].decode("utf-8")
    core = re.sub(r'<cp:lastModifiedBy>.*?</cp:lastModifiedBy>',
                  '<cp:lastModifiedBy>AST Manager</cp:lastModifiedBy>', core, flags=re.DOTALL)
    members["docProps/core.xml"] = core.encode("utf-8")

    handle, temporary = tempfile.mkstemp(prefix="ast-zeiterfassung-", suffix=".xlsm", dir=destination.parent)
    os.close(handle)
    try:
        with zipfile.ZipFile(temporary, "w") as target:
            for info in infos:
                target.writestr(info, members[info.filename])
        with zipfile.ZipFile(temporary, "r") as check:
            written = {name: check.read(name) for name in check.namelist()}
        if set(written) != set(members) or _vba_hash(written) != original_vba:
            raise ValueError("Der Excel-Export konnte die Makros der Vorlage nicht sicher erhalten.")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return destination


def _valid_day(year: int, month: int, day: int) -> bool:
    try:
        date(year, month, day)
        return True
    except ValueError:
        return False


def _calc_pr(attributes: str) -> str:
    values = dict(re.findall(r'([\w:]+)="([^"]*)"', attributes))
    values.update({"calcMode": "auto", "fullCalcOnLoad": "1", "forceFullCalc": "1"})
    return "<calcPr " + " ".join(f'{name}="{value}"' for name, value in values.items()) + "/>"
