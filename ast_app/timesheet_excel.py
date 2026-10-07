"""Fill the supplied macro workbook without rebuilding its OOXML package.

Only the intended input cells and the direct-hours presentation/formulas are
changed. VBA, controls, drawings, printer settings, validation and the
remaining ZIP members stay byte-for-byte identical.
"""
from __future__ import annotations

from datetime import date
from hashlib import sha256
from html import escape
from pathlib import Path
from copy import deepcopy
import os
import re
import tempfile
import zipfile
from xml.etree import ElementTree as ET

from .documents import resource_path
from .domain import scheduled_work_minutes, worked_minutes


MONTH_SHEETS = {month: f"xl/worksheets/sheet{month + 5}.xml" for month in range(1, 13)}
MONTH_NAMES = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
               "August", "September", "Oktober", "November", "Dezember")
INPUT_COLUMNS = ("D", "E", "F", "G", "H", "J", "O")
TIME_FORMAT_ID = "176"       # #,##0.00 "h"; red negative values
SIGNED_TIME_FORMAT_ID = "176"
BALANCE_FORMAT_ID = "176"


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


def _cell_style(xml: str, reference: str) -> int:
    match = _cell_pattern(reference).search(xml)
    if not match:
        raise ValueError(f"Excel-Vorlage: Zelle {reference} wurde nicht gefunden.")
    style = re.search(r'\bs="(\d+)"', match.group("attrs") or "")
    return int(style.group(1)) if style else 0


def _replace_cell_style(xml: str, reference: str, style_id: int) -> str:
    pattern = _cell_pattern(reference)
    match = pattern.search(xml)
    if not match:
        raise ValueError(f"Excel-Vorlage: Zelle {reference} wurde nicht gefunden.")
    cell_xml = match.group(0)
    if re.search(r'\bs="\d+"', cell_xml.split(">", 1)[0]):
        cell_xml = re.sub(r'\bs="\d+"', f's="{style_id}"', cell_xml, count=1)
    else:
        cell_xml = cell_xml.replace("<c", f'<c s="{style_id}"', 1)
    return xml[:match.start()] + cell_xml + xml[match.end():]


def _replace_formula(xml: str, reference: str, formula_text: str) -> str:
    """Replace only a formula's text and retain shared-formula metadata/style."""
    match = _cell_pattern(reference).search(xml)
    if not match:
        raise ValueError(f"Excel-Vorlage: Zelle {reference} wurde nicht gefunden.")
    cell_xml = match.group(0)
    formula = re.search(r'(<f(?:\s[^>]*)?>).*?(</f>)', cell_xml, re.DOTALL)
    if not formula:
        raise ValueError(f"Excel-Vorlage: Formel in {reference} wurde nicht gefunden.")
    replacement = formula.group(1) + escape(formula_text, quote=False) + formula.group(2)
    cell_xml = cell_xml[:formula.start()] + replacement + cell_xml[formula.end():]
    return xml[:match.start()] + cell_xml + xml[match.end():]


def _replace_formula_cell(xml: str, reference: str, formula_text: str, cached_value,
                          result_kind="number") -> str:
    """Write a formula and its cached result while retaining the cell style."""
    pattern = _cell_pattern(reference)
    match = pattern.search(xml)
    if not match:
        raise ValueError(f"Excel-Vorlage: Zelle {reference} wurde nicht gefunden.")
    attrs = match.group("attrs") or ""
    kept = []
    for name, content in re.findall(r'([\w:]+)="([^"]*)"', attrs):
        if name != "t":
            kept.append(f'{name}="{content}"')
    if result_kind == "string":
        kept.append('t="str"')
    attributes = (" " + " ".join(kept)) if kept else ""
    formula = escape(formula_text, quote=False)
    value = escape(str(cached_value), quote=False)
    replacement = f"<c{attributes}><f>{formula}</f><v>{value}</v></c>"
    return xml[:match.start()] + replacement + xml[match.end():]


def _hide_rows(xml: str, first_row: int, last_row: int) -> str:
    for row in range(first_row, last_row + 1):
        pattern = re.compile(rf'<row\b(?=[^>]*\br="{row}")(?P<attrs>[^>]*)>')
        match = pattern.search(xml)
        if not match:
            continue
        tag = match.group(0)
        if re.search(r'\bhidden="[^"]*"', tag):
            tag = re.sub(r'\bhidden="[^"]*"', 'hidden="1"', tag, count=1)
        else:
            tag = tag[:-1] + ' hidden="1">'
        xml = xml[:match.start()] + tag + xml[match.end():]
    return xml


def _remove_calc_chain(members: dict[str, bytes]) -> None:
    """Remove the stale formula cache index so Excel rebuilds it on open."""
    if "xl/calcChain.xml" not in members:
        return
    members.pop("xl/calcChain.xml")
    content_types = members["[Content_Types].xml"].decode("utf-8")
    content_types = re.sub(
        r'<Override\b[^>]*\bPartName="/xl/calcChain\.xml"[^>]*/>', "", content_types
    )
    members["[Content_Types].xml"] = content_types.encode("utf-8")
    relationships = members["xl/_rels/workbook.xml.rels"].decode("utf-8")
    relationships = re.sub(
        r'<Relationship\b[^>]*\bTarget="calcChain\.xml"[^>]*/>', "", relationships
    )
    members["xl/_rels/workbook.xml.rels"] = relationships.encode("utf-8")


def _simplify_time_columns(xml: str) -> str:
    """Expose one direct-hours column and hide the obsolete clock columns."""
    xml = _replace_cell(xml, "D3", "Arbeitszeit (h)", "string")

    def adjust(match):
        tag = match.group(0)
        minimum = int(re.search(r'\bmin="(\d+)"', tag).group(1))
        maximum = int(re.search(r'\bmax="(\d+)"', tag).group(1))
        if 5 <= minimum and maximum <= 9:
            if ' hidden=' in tag:
                tag = re.sub(r'\bhidden="[^"]*"', 'hidden="1"', tag)
            else:
                tag = tag[:-2] + ' hidden="1"/>'
        if minimum == maximum == 4:
            tag = re.sub(r'\bwidth="[^"]*"', 'width="12"', tag)
        if minimum == maximum == 10:
            tag = re.sub(r'\bwidth="[^"]*"', 'width="7"', tag)
        return tag

    return re.sub(r'<col\b[^>]*/>', adjust, xml)


def _use_direct_hours_formula(xml: str) -> str:
    # K4 is a standalone formula; K5 is the shared master for K5:K34.
    xml = _replace_formula(xml, "K4", 'IF(A4="",0,IF(D4="",0,D4))')
    return _replace_formula(xml, "K5", 'IF(A5="",0,IF(D5="",0,D5))')


def _ignore_unrecorded_day_formula(xml: str, reference: str) -> str:
    """Keep days without an app record out of the running time balance."""
    match = _cell_pattern(reference).search(xml)
    if not match:
        raise ValueError(f"Excel-Vorlage: Zelle {reference} wurde nicht gefunden.")
    cell_xml = match.group(0)
    formula = re.search(r'<f(?:\s[^>]*)?>(.*?)</f>', cell_xml, re.DOTALL)
    if not formula:
        raise ValueError(f"Excel-Vorlage: Saldoformel in {reference} wurde nicht gefunden.")
    original = formula.group(1)
    corrected = f'IF(AND(D4="",E4="",F4="",G4="",J4=""),0,{original})'
    cell_xml = cell_xml[:formula.start(1)] + corrected + cell_xml[formula.end(1):]
    return xml[:match.start()] + cell_xml + xml[match.end():]


class _StyleNormalizer:
    """Clone existing cell styles with a corrected number format.

    The supplied workbook uses the right borders, fills and protection, but a
    large part of the time cells accidentally uses ``0.00``. Cloning each
    affected style changes only its number format and leaves the layout intact.
    """

    def __init__(self, styles_xml: str):
        self.xml = styles_xml
        self._match = re.search(r'<cellXfs\b[^>]*>.*?</cellXfs>', styles_xml, re.DOTALL)
        if not self._match:
            raise ValueError("Excel-Vorlage: Zellformatvorlagen wurden nicht gefunden.")
        self._root = ET.fromstring(self._match.group(0))
        self._clones: dict[tuple[int, str, int | None], int] = {}

    def style_for(self, old_style_id: int, number_format_id: str, fill_id: int | None = None) -> int:
        if old_style_id < 0 or old_style_id >= len(self._root):
            raise ValueError("Excel-Vorlage: Ungültige Zellformatvorlage.")
        old_style = self._root[old_style_id]
        if (old_style.get("numFmtId", "0") == number_format_id
                and (fill_id is None or old_style.get("fillId", "0") == str(fill_id))):
            return old_style_id
        key = (old_style_id, number_format_id, fill_id)
        if key not in self._clones:
            clone = deepcopy(old_style)
            clone.set("numFmtId", number_format_id)
            if fill_id is not None:
                clone.set("fillId", str(fill_id))
                clone.set("applyFill", "1")
            self._root.append(clone)
            self._clones[key] = len(self._root) - 1
        return self._clones[key]

    def apply(self, sheet_xml: str, references: list[tuple[str, str]]) -> str:
        for reference, number_format_id in references:
            old_style_id = _cell_style(sheet_xml, reference)
            new_style_id = self.style_for(old_style_id, number_format_id)
            if new_style_id != old_style_id:
                sheet_xml = _replace_cell_style(sheet_xml, reference, new_style_id)
        return sheet_xml

    def apply_colored(self, sheet_xml: str, references: list[tuple[str, str, int]]) -> str:
        for reference, number_format_id, fill_id in references:
            old_style_id = _cell_style(sheet_xml, reference)
            new_style_id = self.style_for(old_style_id, number_format_id, fill_id)
            if new_style_id != old_style_id:
                sheet_xml = _replace_cell_style(sheet_xml, reference, new_style_id)
        return sheet_xml

    def finish(self) -> str:
        self._root.set("count", str(len(self._root)))
        replacement = ET.tostring(self._root, encoding="unicode", short_empty_elements=True)
        return self.xml[:self._match.start()] + replacement + self.xml[self._match.end():]


def _monthly_time_cells() -> list[tuple[str, str]]:
    cells = []
    for row in range(4, 35):
        cells.extend((f"{column}{row}", TIME_FORMAT_ID) for column in "DEFGHKLN")
        cells.append((f"M{row}", SIGNED_TIME_FORMAT_ID))
        cells.append((f"P{row}", BALANCE_FORMAT_ID))
    cells.extend([
        ("F36", BALANCE_FORMAT_ID), ("F37", TIME_FORMAT_ID),
        ("F38", TIME_FORMAT_ID), ("F39", TIME_FORMAT_ID),
        ("F40", BALANCE_FORMAT_ID),
    ])
    cells.extend((f"P{row}", TIME_FORMAT_ID) for row in (36, 37, 38, 39, 42, 43, 44, 45, 46, 47))
    return cells


def _annual_time_cells() -> list[tuple[str, str]]:
    cells = []
    # One three-column group per month: day, hours, absence code.
    hour_columns = ("C", "F", "I", "L", "O", "R", "U", "X", "AA", "AD", "AG", "AJ")
    for column in hour_columns:
        cells.extend((f"{column}{row}", TIME_FORMAT_ID) for row in range(4, 35))
    # Monthly summary values live in the first column of every month group.
    summary_columns = ("B", "E", "H", "K", "N", "Q", "T", "W", "Z", "AC", "AF", "AI")
    for column in summary_columns:
        cells.extend((f"{column}{row}", TIME_FORMAT_ID) for row in range(35, 42))
    cells.extend([
        *[(f"AL{row}", TIME_FORMAT_ID) for row in range(35, 42)],
    ])
    return cells


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


def _decimal_hours(minutes: int | None):
    if minutes is None:
        return None
    return format(int(minutes) / 60, ".15g")


def monthly_summary(records: list[dict], year: int, month: int) -> dict[str, int]:
    """Summarise recorded deviations without treating missing records as absences."""
    result = {"overtime": 0, "vacation": 0, "sick": 0, "other": 0}
    for record in records:
        day = date.fromisoformat(record["day"])
        if day.year != year or day.month != month:
            continue
        scheduled = scheduled_work_minutes(day)
        actual = worked_minutes(record)
        code = str(record.get("code") or "").upper()
        if actual > scheduled:
            result["overtime"] += actual - scheduled
        if actual >= scheduled or not scheduled or code == "F":
            continue
        shortfall = scheduled - actual
        if code in {"U", "UH", "G"}:
            result["vacation"] += shortfall
        elif code in {"K", "KR"}:
            result["sick"] += shortfall
        else:
            result["other"] += shortfall
    return result


def _write_monthly_summary(xml: str, summary: dict[str, int]) -> str:
    rows = (
        (36, "Überstunden geleistet (h)", "overtime",
         'SUMPRODUCT((K4:K34>N4:N34)*(K4:K34-N4:N34))'),
        (37, "Ferien / Freizeit bezogen (h)", "vacation",
         'SUMPRODUCT(((J4:J34="U")+(J4:J34="UH")+(J4:J34="G"))*(N4:N34>K4:K34)*(N4:N34-K4:K34))'),
        (38, "Krankheit (h)", "sick",
         'SUMPRODUCT(((J4:J34="K")+(J4:J34="KR"))*(N4:N34>K4:K34)*(N4:N34-K4:K34))'),
        (39, "Übrige begründete Minderzeit (h)", "other",
         'SUMPRODUCT(((J4:J34="KU")+(J4:J34="KA")+(J4:J34="E1"))*(N4:N34>K4:K34)*(N4:N34-K4:K34))'),
    )
    for row, title, key, formula in rows:
        xml = _replace_formula_cell(xml, f"K{row}", f'"{title}"', title, "string")
        xml = _replace_formula_cell(xml, f"P{row}", formula, _decimal_hours(summary[key]))
    return xml


def _remove_legacy_monthly_summary(xml: str) -> str:
    """Remove obsolete visible counters and detail labels from the monthly sheet."""
    for row in range(36, 48):
        xml = _replace_cell(xml, f"J{row}", None)
    for row in range(40, 48):
        xml = _replace_cell(xml, f"K{row}", None)
        xml = _replace_cell(xml, f"P{row}", None)
    return xml


def _simplify_annual_summary(xml: str) -> str:
    labels = {
        37: "Überstunden geleistet (h)",
        38: "Ferien / Freizeit bezogen (h)",
        39: "Krankheit (h)",
        40: "Übrige begründete Minderzeit (h)",
        41: "Abwesenheiten gesamt (h)",
    }
    for row, title in labels.items():
        xml = _replace_cell(xml, f"A{row}", title, "string")
    summary_columns = ("B", "E", "H", "K", "N", "Q", "T", "W", "Z", "AC", "AF", "AI")
    for month_index, (column, sheet_name) in enumerate(zip(summary_columns, MONTH_NAMES), 1):
        for target_row, source_row in ((37, 36), (38, 37), (39, 38), (40, 39)):
            xml = _replace_formula_cell(xml, f"{column}{target_row}",
                                        f"{sheet_name}!P{source_row}", 0)
        xml = _replace_formula_cell(xml, f"{column}41",
                                    f"SUM({column}38:{column}40)", 0)
        vacation_days = (f'COUNTIF({sheet_name}!J4:J34,Voreinstellungen!B25)'
                         f'+COUNTIF({sheet_name}!J4:J34,Voreinstellungen!B26)*Voreinstellungen!C26')
        xml = _replace_formula_cell(xml, f"{column}43", vacation_days, 0)
    for row in range(37, 42):
        xml = _replace_formula_cell(xml, f"AL{row}", f"SUM(B{row}:AK{row})", 0)
    xml = _replace_formula_cell(xml, "AL43", "SUM(B43:AK43)", 0)
    return _hide_rows(xml, 42, 50)


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
    required = {"xl/vbaProject.bin", "xl/styles.xml", "xl/worksheets/sheet1.xml",
                "xl/worksheets/sheet2.xml", "xl/worksheets/sheet3.xml",
                "xl/worksheets/sheet18.xml", *MONTH_SHEETS.values()}
    if not required <= set(members):
        raise ValueError("Die mitgelieferte Zeiterfassungsvorlage ist unvollständig.")

    styles = _StyleNormalizer(members["xl/styles.xml"].decode("utf-8"))

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
    settings = _replace_cell(settings, "A29", "Andere begründete Minderzeit", "string")
    settings = re.sub(r'(<dataValidation\b[^>]*>.*?<formula1>).*?(</formula1>)',
                      lambda m: m.group(1) + '"' + escape(full_name, quote=False) + '"' + m.group(2),
                      settings, count=1, flags=re.DOTALL)
    settings = styles.apply(settings, [(reference, TIME_FORMAT_ID) for reference in ("C7", "C8", "C9")])
    members["xl/worksheets/sheet1.xml"] = settings.encode("utf-8")

    by_day = {date.fromisoformat(r["day"]): r for r in records if date.fromisoformat(r["day"]).year == year}
    # Existing template fill IDs: cyan, green, yellow and orange.
    category_fills = ((36, 14), (37, 17), (38, 13), (39, 20))
    for month, xml_name in MONTH_SHEETS.items():
        xml = members[xml_name].decode("utf-8")
        xml = _simplify_time_columns(xml)
        xml = _use_direct_hours_formula(xml)
        xml = _replace_cell(xml, "J3", "Grund", "string")
        if company:
            xml = _replace_cell(xml, "C1", company, "string")
        # L4, M4 and N4 are masters of their shared formulas down to row 34.
        xml = _ignore_unrecorded_day_formula(xml, "L4")
        xml = _ignore_unrecorded_day_formula(xml, "M4")
        for day_number in range(1, 32):
            row = day_number + 3
            for column in INPUT_COLUMNS:
                xml = _replace_cell(xml, f"{column}{row}", None)
            record = by_day.get(date(year, month, day_number)) if day_number <= 28 or _valid_day(year, month, day_number) else None
            if not record:
                continue
            xml = _replace_cell(xml, f"D{row}", _decimal_hours(worked_minutes(record)))
            xml = _replace_cell(xml, f"J{row}", record.get("code", ""), "string")
            xml = _replace_cell(xml, f"O{row}", record.get("note", ""), "string")
        xml = _write_monthly_summary(xml, monthly_summary(records, year, month))
        xml = _remove_legacy_monthly_summary(xml)
        xml = styles.apply(xml, _monthly_time_cells())
        xml = styles.apply_colored(
            xml,
            [(f"{column}{row}", TIME_FORMAT_ID, fill_id)
             for row, fill_id in category_fills for column in ("K", "P")],
        )
        xml = styles.apply_colored(
            xml,
            [(f"J{row}", "0", 0) for row in range(36, 48)]
            + [(f"{column}{row}", "0", 0)
               for row in range(40, 48) for column in ("K", "P")],
        )
        members[xml_name] = xml.encode("utf-8")

    annual_name = "xl/worksheets/sheet18.xml"
    annual = members[annual_name].decode("utf-8")
    annual = _simplify_annual_summary(annual)
    annual = styles.apply(annual, _annual_time_cells())
    annual_summary_columns = ("B", "E", "H", "K", "N", "Q", "T", "W", "Z", "AC", "AF", "AI", "AL")
    annual = styles.apply_colored(
        annual,
        [(f"A{row}", "0", fill_id) for row, fill_id in category_fills]
        + [(f"{column}{row}", TIME_FORMAT_ID, fill_id)
           for row, fill_id in category_fills for column in annual_summary_columns],
    )
    members[annual_name] = annual.encode("utf-8")
    members["xl/styles.xml"] = styles.finish().encode("utf-8")
    _remove_calc_chain(members)

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
                if info.filename in members:
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
