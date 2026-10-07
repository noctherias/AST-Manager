"""Fill the supplied macro workbook without rebuilding its OOXML package.

Only the intended input cells and the direct-hours presentation/formulas are
changed. VBA, controls, drawings, printer settings, validation and the
remaining ZIP members stay byte-for-byte identical.
"""
from __future__ import annotations

from datetime import date, timedelta
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
from .domain import scheduled_work_minutes, vacation_target, worked_minutes


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


def _replace_cached_value(xml: str, reference: str, cached_value) -> str:
    """Update a formula result without changing shared-formula metadata."""
    match = _cell_pattern(reference).search(xml)
    if not match:
        raise ValueError(f"Excel-Vorlage: Zelle {reference} wurde nicht gefunden.")
    cell_xml = match.group(0)
    value = escape(str(cached_value), quote=False)
    cached = re.search(r'<v>.*?</v>', cell_xml, re.DOTALL)
    if cached:
        cell_xml = cell_xml[:cached.start()] + f"<v>{value}</v>" + cell_xml[cached.end():]
    else:
        cell_xml = cell_xml[:-4] + f"<v>{value}</v></c>"
    return xml[:match.start()] + cell_xml + xml[match.end():]


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


def _set_row_heights(xml: str, heights: dict[int, float]) -> str:
    for row, height in heights.items():
        pattern = re.compile(rf'<row\b(?=[^>]*\br="{row}")(?P<attrs>[^>]*)>')
        match = pattern.search(xml)
        if not match:
            continue
        tag = match.group(0)
        tag = re.sub(r'\sht="[^"]*"', "", tag)
        tag = re.sub(r'\scustomHeight="[^"]*"', "", tag)
        tag = tag[:-1] + f' ht="{height:g}" customHeight="1">'
        xml = xml[:match.start()] + tag + xml[match.end():]
    return xml


def _references_in_rows(xml: str, rows: set[int]) -> list[str]:
    references = []
    for reference in re.findall(r'<c\b[^>]*\br="([A-Z]+\d+)"', xml):
        row = int(re.search(r'\d+', reference).group(0))
        if row in rows:
            references.append(reference)
    return references


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
        widths = {1: 14, 2: 5, 3: 19, 4: 14, 10: 9, 11: 12, 12: 12, 13: 10, 15: 34, 16: 12}
        if 5 <= minimum and maximum <= 9:
            if ' hidden=' in tag:
                tag = re.sub(r'\bhidden="[^"]*"', 'hidden="1"', tag)
            else:
                tag = tag[:-2] + ' hidden="1"/>'
        if minimum == maximum and minimum in widths:
            tag = re.sub(r'\bwidth="[^"]*"', f'width="{widths[minimum]}"', tag)
        return tag

    return re.sub(r'<col\b[^>]*/>', adjust, xml)


def _widen_annual_hour_columns(xml: str) -> str:
    """Keep two-decimal hour values readable in every month group."""
    hour_columns = set(range(3, 37, 3))

    def adjust(match):
        tag = match.group(0)
        minimum = int(re.search(r'\bmin="(\d+)"', tag).group(1))
        maximum = int(re.search(r'\bmax="(\d+)"', tag).group(1))
        if minimum == maximum and minimum in hour_columns:
            tag = re.sub(r'\bwidth="[^"]*"', 'width="7.5"', tag)
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
        self._fills_match = re.search(r'<fills\b[^>]*>.*?</fills>', styles_xml, re.DOTALL)
        if not self._fills_match:
            raise ValueError("Excel-Vorlage: Farbdefinitionen wurden nicht gefunden.")
        self._fills_root = ET.fromstring(self._fills_match.group(0))
        self._match = re.search(r'<cellXfs\b[^>]*>.*?</cellXfs>', styles_xml, re.DOTALL)
        if not self._match:
            raise ValueError("Excel-Vorlage: Zellformatvorlagen wurden nicht gefunden.")
        self._root = ET.fromstring(self._match.group(0))
        self._clones: dict[tuple[int, str, int | None], int] = {}

    def fill_id(self, rgb: str) -> int:
        rgb = rgb.upper()
        for index, fill in enumerate(self._fills_root):
            color = fill.find("{*}patternFill/{*}fgColor")
            if color is not None and color.get("rgb", "").upper() == rgb:
                return index
        namespace = (self._fills_root.tag[1:].partition("}")[0]
                     if self._fills_root.tag.startswith("{") else "")
        tag = lambda name: f"{{{namespace}}}{name}" if namespace else name
        fill = ET.Element(tag("fill"))
        pattern = ET.SubElement(fill, tag("patternFill"), {"patternType": "solid"})
        ET.SubElement(pattern, tag("fgColor"), {"rgb": rgb})
        ET.SubElement(pattern, tag("bgColor"), {"indexed": "64"})
        self._fills_root.append(fill)
        return len(self._fills_root) - 1

    def style_for(self, old_style_id: int, number_format_id: str | None,
                  fill_id: int | None = None) -> int:
        if old_style_id < 0 or old_style_id >= len(self._root):
            raise ValueError("Excel-Vorlage: Ungültige Zellformatvorlage.")
        old_style = self._root[old_style_id]
        number_format_id = number_format_id or old_style.get("numFmtId", "0")
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

    def apply_colored(self, sheet_xml: str, references: list[tuple[str, str | None, int]]) -> str:
        for reference, number_format_id, fill_id in references:
            old_style_id = _cell_style(sheet_xml, reference)
            new_style_id = self.style_for(old_style_id, number_format_id, fill_id)
            if new_style_id != old_style_id:
                sheet_xml = _replace_cell_style(sheet_xml, reference, new_style_id)
        return sheet_xml

    def finish(self) -> str:
        self._root.set("count", str(len(self._root)))
        self._fills_root.set("count", str(len(self._fills_root)))
        replacements = (
            (self._match, ET.tostring(self._root, encoding="unicode", short_empty_elements=True)),
            (self._fills_match, ET.tostring(self._fills_root, encoding="unicode", short_empty_elements=True)),
        )
        xml = self.xml
        for match, replacement in sorted(replacements, key=lambda item: item[0].start(), reverse=True):
            xml = xml[:match.start()] + replacement + xml[match.end():]
        return xml


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
    cells.extend((f"P{row}", TIME_FORMAT_ID) for row in range(36, 41))
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
        cells.extend((f"{column}{row}", TIME_FORMAT_ID) for row in range(35, 43))
    cells.extend([
        *[(f"AL{row}", TIME_FORMAT_ID) for row in range(35, 43)],
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


def _easter_sunday(year: int) -> date:
    """Gregorian Easter date, used by the supplied holiday calendar."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def company_holidays(year: int) -> set[date]:
    """Full-day holidays configured by the original AST Excel template."""
    easter = _easter_sunday(int(year))
    return {
        date(year, 1, 1), date(year, 1, 2),
        easter - timedelta(days=2), easter + timedelta(days=1),
        easter + timedelta(days=39), easter + timedelta(days=50),
        date(year, 8, 1), date(year, 12, 25), date(year, 12, 26), date(year, 12, 31),
    }


def monthly_target_minutes(year: int, month: int) -> int:
    """Scheduled full-time hours for one calendar month, excluding holidays."""
    holidays = company_holidays(int(year))
    day = date(int(year), int(month), 1)
    total = 0
    while day.month == int(month):
        if day not in holidays:
            total += scheduled_work_minutes(day)
        day += timedelta(days=1)
    return total


def monthly_summary(records: list[dict], year: int, month: int) -> dict[str, int]:
    """Summarise recorded deviations without treating missing records as absences."""
    result = {"overtime": 0, "vacation": 0, "sick": 0, "accident": 0, "other": 0}
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
        elif code in {"A", "AR"}:
            result["accident"] += shortfall
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
        (39, "Unfall (h)", "accident",
         'SUMPRODUCT(((J4:J34="A")+(J4:J34="AR"))*(N4:N34>K4:K34)*(N4:N34-K4:K34))'),
        (40, "Übrige begründete Minderzeit (h)", "other",
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
    for row in range(41, 48):
        xml = _replace_cell(xml, f"K{row}", None)
        xml = _replace_cell(xml, f"P{row}", None)
    return xml


def _simplify_annual_summary(xml: str, year: int, vacation_hours: float) -> str:
    labels = {
        37: "Überstunden (h)",
        38: "Ferien / Freizeit (h)",
        39: "Krankheit (h)",
        40: "Unfall (h)",
        41: "Übrige Minderzeit (h)",
        42: "Abwesenheit (h)",
        44: "Ferien-Soll (h)",
    }
    for row, title in labels.items():
        xml = _replace_cell(xml, f"A{row}", title, "string")
    summary_columns = ("B", "E", "H", "K", "N", "Q", "T", "W", "Z", "AC", "AF", "AI")
    for month_index, (column, sheet_name) in enumerate(zip(summary_columns, MONTH_NAMES), 1):
        xml = _replace_cached_value(
            xml, f"{column}35", _decimal_hours(monthly_target_minutes(year, month_index))
        )
        for target_row, source_row in ((37, 36), (38, 37), (39, 38), (40, 39), (41, 40)):
            xml = _replace_formula_cell(xml, f"{column}{target_row}",
                                        f"{sheet_name}!P{source_row}", 0)
        xml = _replace_formula_cell(xml, f"{column}42",
                                    f"SUM({column}38:{column}41)", 0)
        vacation_days = (f'COUNTIF({sheet_name}!J4:J34,Voreinstellungen!B25)'
                         f'+COUNTIF({sheet_name}!J4:J34,Voreinstellungen!B26)*Voreinstellungen!C26')
        xml = _replace_formula_cell(xml, f"{column}43", vacation_days, 0)
        xml = _replace_cell(xml, f"{column}44", format(vacation_hours / 12, ".15g"))
    for row in range(37, 43):
        xml = _replace_formula_cell(xml, f"AL{row}", f"SUM(B{row}:AK{row})", 0)
    year_target = sum(monthly_target_minutes(year, month) for month in range(1, 13))
    # AL35 is the master of Excel's shared AL35:AL50 formula group. Replacing
    # the formula itself leaves its dependent cells orphaned and Excel then
    # rejects the workbook. Only refresh its cached result.
    xml = _replace_cached_value(xml, "AL35", _decimal_hours(year_target))
    xml = _replace_formula_cell(xml, "AL43", "SUM(B43:AK43)", 0)
    xml = _replace_formula_cell(xml, "AL44", "SUM(B44:AK44)", format(vacation_hours, ".15g"))
    xml = _hide_rows(xml, 43, 43)
    return _hide_rows(xml, 45, 50)


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
    settings = _replace_cell(settings, "A31", "Unfall · ganzer Tag", "string")
    settings = _replace_cell(settings, "B31", "A", "string")
    settings = _replace_cell(settings, "C31", "REST", "string")
    settings = _replace_cell(settings, "A32", "Unfall · Teil des Tages", "string")
    settings = _replace_cell(settings, "B32", "AR", "string")
    settings = _replace_cell(settings, "C32", "REST", "string")
    settings = re.sub(r'(<dataValidation\b[^>]*>.*?<formula1>).*?(</formula1>)',
                      lambda m: m.group(1) + '"' + escape(full_name, quote=False) + '"' + m.group(2),
                      settings, count=1, flags=re.DOTALL)
    settings = styles.apply(settings, [(reference, TIME_FORMAT_ID) for reference in ("C7", "C8", "C9")])
    members["xl/worksheets/sheet1.xml"] = settings.encode("utf-8")

    by_day = {date.fromisoformat(r["day"]): r for r in records if date.fromisoformat(r["day"]).year == year}
    annual_vacation_hours = vacation_target(employee, year) / 100
    # One restrained palette is used in the month and annual summaries. This
    # prevents the same colour from meaning two different categories.
    fill_overtime = styles.fill_id("FFDDF3E4")
    fill_vacation = styles.fill_id("FFDCEEFF")
    fill_sick = styles.fill_id("FFFFF2CC")
    fill_accident = styles.fill_id("FFF7D6D6")
    fill_other = styles.fill_id("FFFCE4D6")
    fill_total = styles.fill_id("FFE9EEF2")
    fill_header = styles.fill_id("FFDCE6EB")
    category_fills = (
        (36, fill_overtime),
        (37, fill_vacation),
        (38, fill_sick),
        (39, fill_accident),
        (40, fill_other),
    )
    for month, xml_name in MONTH_SHEETS.items():
        xml = members[xml_name].decode("utf-8")
        xml = _simplify_time_columns(xml)
        xml = _use_direct_hours_formula(xml)
        xml = _replace_cell(xml, "J3", "Grund", "string")
        if company:
            xml = _replace_cell(xml, "C1", company, "string")
        # L4, M4 and N4 are masters of their shared formulas down to row 34.
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
        xml = _replace_formula_cell(xml, "F37", "SUM(L4:L34)",
                                    _decimal_hours(monthly_target_minutes(year, month)))
        xml = _remove_legacy_monthly_summary(xml)
        xml = _set_row_heights(xml, {1: 24, 2: 20, 3: 34,
                                     **{row: 20 for row in range(4, 35)},
                                     **{row: 22 for row in range(36, 41)}})
        xml = styles.apply(xml, _monthly_time_cells())
        xml = styles.apply_colored(
            xml,
            [(reference, None, fill_header) for reference in _references_in_rows(xml, {3})],
        )
        xml = styles.apply_colored(
            xml,
            [(f"{column}{row}", TIME_FORMAT_ID, fill_id)
             for row, fill_id in category_fills for column in ("K", "P")],
        )
        xml = styles.apply_colored(
            xml,
            [(f"J{row}", "0", 0) for row in range(36, 48)]
            + [(f"{column}{row}", "0", 0)
               for row in range(41, 48) for column in ("K", "P")],
        )
        members[xml_name] = xml.encode("utf-8")

    annual_name = "xl/worksheets/sheet18.xml"
    annual = members[annual_name].decode("utf-8")
    annual = _simplify_annual_summary(annual, year, annual_vacation_hours)
    annual = _widen_annual_hour_columns(annual)
    annual = _set_row_heights(annual, {1: 24, 2: 20, 3: 24,
                                       **{row: 20 for row in range(4, 35)},
                                       **{row: 22 for row in range(35, 43)}})
    annual = styles.apply(annual, _annual_time_cells())
    annual = styles.apply_colored(
        annual,
        [(reference, None, fill_header) for reference in _references_in_rows(annual, {3})],
    )
    annual_summary_columns = ("B", "E", "H", "K", "N", "Q", "T", "W", "Z", "AC", "AF", "AI", "AL")
    annual_category_fills = tuple((row + 1, fill_id) for row, fill_id in category_fills)
    annual = styles.apply_colored(
        annual,
        [(f"A{row}", "0", fill_id) for row, fill_id in annual_category_fills]
        + [(f"{column}{row}", TIME_FORMAT_ID, fill_id)
           for row, fill_id in annual_category_fills for column in annual_summary_columns]
        + [("A42", "0", fill_total)]
        + [(f"{column}42", TIME_FORMAT_ID, fill_total) for column in annual_summary_columns]
        + [("A44", "0", fill_vacation)]
        + [(f"{column}44", TIME_FORMAT_ID, fill_vacation) for column in annual_summary_columns],
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
