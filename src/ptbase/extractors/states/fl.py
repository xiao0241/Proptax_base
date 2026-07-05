from __future__ import annotations

import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests

from ...config import ROOT, YEARS
from ...fips import county_lookup, normalize_county_name
from ..base import ExtractionDiagnostics, reject_non_county_source

SHAREPOINT_API = "https://floridarevenue.com/property/dataportal/_api/web"
HOST = "https://floridarevenue.com"
HISTORICAL_ROOT = "/property/dataportal/Documents/PTO Data Portal/Databook Historical Data"
RAW_ROOT = ROOT / "data" / "raw" / "FL"

EXCEL_MEASURES = {
    "market_or_full_value": {
        "tokens": ("just_value", "just value"),
        "sheet_tokens": ("just value all property",),
        "header_tokens": ("total", "just value"),
        "source_id": "fl_dor_data_book_just_value",
    },
    "assessed_value": {
        "tokens": ("assessed_value", "assessed value"),
        "sheet_tokens": ("assessed value all property",),
        "header_tokens": ("total", "assessed value"),
        "source_id": "fl_dor_data_book_assessed_value",
    },
    "county_taxable_value": {
        "tokens": ("taxable_value", "taxable value"),
        "sheet_tokens": ("taxable value all property",),
        "header_tokens": ("total", "taxable value"),
        "source_id": "fl_dor_data_book_county_taxable_value",
    },
    "school_taxable_value": {
        "tokens": ("school_report", "school report"),
        "sheet_tokens": ("school taxable value",),
        "header_tokens": ("school taxable value",),
        "source_id": "fl_dor_data_book_school_taxable_value",
    },
}

PDF_TABLES = {
    "market_or_full_value": "4",
    "county_taxable_value": "27",
    "school_taxable_value": "28",
}


def extract_fl() -> tuple[pd.DataFrame, ExtractionDiagnostics]:
    reject_non_county_source("county_aggregate")
    diagnostics = ExtractionDiagnostics(state="FL")
    frames: list[pd.DataFrame] = []

    for year in YEARS:
        if year <= 2009:
            frame = _extract_pdf_year(year, diagnostics)
        else:
            frame = _extract_excel_year(year, diagnostics)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        diagnostics.missing_sources.append("No FL source files could be parsed.")
        return _empty_fl(), diagnostics

    out = pd.concat(frames, ignore_index=True, sort=False)
    value_cols = list(EXCEL_MEASURES)
    out = out.groupby(["state", "county_name", "year"], as_index=False)[value_cols].first()
    return out, diagnostics


def _extract_pdf_year(year: int, diagnostics: ExtractionDiagnostics) -> pd.DataFrame:
    yy = str(year)[2:]
    file_name = f"{yy}FLpropdata.pdf"
    server_path = f"{HISTORICAL_ROOT}/2000-2009DataBookFiles/{file_name}"
    local_path = RAW_ROOT / str(year) / file_name
    path = _download_or_reuse(server_path, local_path, diagnostics)
    if path is None:
        diagnostics.missing_sources.append(f"FL {year}: missing official historical PDF {file_name}")
        return _empty_fl()

    try:
        text = _pdf_text(path)
        return parse_pdf_text(text, year, diagnostics)
    except Exception as exc:
        diagnostics.missing_sources.append(f"FL {year}: failed to parse official PDF {file_name}: {exc}")
        return _empty_fl()


def _extract_excel_year(year: int, diagnostics: ExtractionDiagnostics) -> pd.DataFrame:
    files = _list_year_files(year, diagnostics)
    year_rows: dict[str, dict[str, object]] = {}

    for measure, spec in EXCEL_MEASURES.items():
        server_path = _select_measure_file(files, spec["tokens"])
        if server_path is None:
            diagnostics.missing_sources.append(f"FL {year}: missing {measure} official county-level workbook")
            continue

        local_path = RAW_ROOT / str(year) / Path(server_path).name
        path = _download_or_reuse(server_path, local_path, diagnostics)
        if path is None:
            diagnostics.missing_sources.append(f"FL {year}: could not download or reuse {Path(server_path).name}")
            continue

        try:
            parsed = parse_excel_report(path, year, measure)
        except Exception as exc:
            diagnostics.missing_sources.append(f"FL {year}: failed to parse {measure} from {Path(path).name}: {exc}")
            continue

        for county_name, value in parsed.items():
            row = year_rows.setdefault(county_name, {"state": "FL", "county_name": county_name, "year": year})
            row[measure] = value

    return pd.DataFrame(year_rows.values()) if year_rows else _empty_fl()


def _list_year_files(year: int, diagnostics: ExtractionDiagnostics) -> dict[str, str]:
    folder = f"{HISTORICAL_ROOT}/{year}DataBookFiles"
    url = f"{SHAREPOINT_API}/GetFolderByServerRelativeUrl({folder!r})/Files?$select=Name,ServerRelativeUrl"
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        files = _parse_sharepoint_file_feed(response.content)
        if files:
            return files
    except Exception as exc:
        diagnostics.notes.append(f"FL {year}: SharePoint file listing failed; trying manual raw-file mode: {exc}")

    manual_dir = RAW_ROOT / str(year)
    if not manual_dir.exists():
        return {}
    diagnostics.files_reused.extend(str(path) for path in manual_dir.iterdir() if path.is_file())
    return {path.name: str(path) for path in manual_dir.iterdir() if path.is_file()}


def _parse_sharepoint_file_feed(content: bytes) -> dict[str, str]:
    ns = {"d": "http://schemas.microsoft.com/ado/2007/08/dataservices"}
    root = ET.fromstring(content)
    files: dict[str, str] = {}
    entries = root.findall("{http://www.w3.org/2005/Atom}entry")
    for entry in entries:
        name = entry.find(".//d:Name", ns)
        server_relative = entry.find(".//d:ServerRelativeUrl", ns)
        if name is not None and server_relative is not None and name.text and server_relative.text:
            files[name.text] = server_relative.text
    return files


def _select_measure_file(files: dict[str, str], tokens: tuple[str, ...]) -> str | None:
    for name, path in sorted(files.items()):
        lower = name.lower().replace("-", "_")
        lower_spaced = name.lower().replace("_", " ")
        if any(token in lower or token in lower_spaced for token in tokens):
            if "municipal" not in lower and "parcel" not in lower and "central" not in lower:
                return path
    return None


def _download_or_reuse(server_path: str, local_path: Path, diagnostics: ExtractionDiagnostics) -> Path | None:
    if local_path.exists():
        diagnostics.files_reused.append(str(local_path))
        return local_path

    if str(server_path).startswith("/") and not str(server_path).startswith(str(RAW_ROOT)):
        url = HOST + quote(server_path, safe="/:?=&%")
        try:
            response = requests.get(url, timeout=120)
            response.raise_for_status()
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(response.content)
            diagnostics.files_downloaded.append(str(local_path))
            return local_path
        except Exception as exc:
            diagnostics.notes.append(f"FL download failed for {url}: {exc}")
    else:
        manual_path = Path(server_path)
        if manual_path.exists():
            return manual_path

    return None


def parse_excel_report(path: Path, year: int, measure: str) -> dict[str, float]:
    spec = EXCEL_MEASURES[measure]
    workbook = pd.ExcelFile(path)
    sheet_name = _select_sheet(workbook.sheet_names, spec["sheet_tokens"])
    df = pd.read_excel(path, sheet_name=sheet_name, header=None)
    header_idx = _find_excel_header_row(df)
    headers = [_clean_header(value) for value in df.iloc[header_idx].tolist()]
    county_col = _find_header_index(headers, ("county",))
    value_col = _find_value_column(headers, year, spec["header_tokens"])

    values: dict[str, float] = {}
    for _, row in df.iloc[header_idx + 1 :].iterrows():
        county_raw = row.iloc[county_col]
        if pd.isna(county_raw):
            continue
        county_text = str(county_raw).strip()
        if not county_text or county_text.lower().startswith(("statewide", "data extract")):
            continue
        canonical, _, _ = normalize_county_name(county_text, "FL")
        if canonical is None:
            continue
        value = pd.to_numeric(row.iloc[value_col], errors="coerce")
        if pd.notna(value):
            values[canonical] = float(value)
    return values


def _select_sheet(sheet_names: list[str], tokens: tuple[str, ...]) -> str:
    for sheet in sheet_names:
        lower = sheet.lower()
        if any(token in lower for token in tokens):
            return sheet
    raise ValueError(f"No sheet matched {tokens}; available sheets: {sheet_names}")


def _find_excel_header_row(df: pd.DataFrame) -> int:
    for idx, row in df.iterrows():
        cells = [_clean_header(value) for value in row.tolist()]
        if any(cell == "county" for cell in cells):
            return int(idx)
    raise ValueError("Could not find County header row")


def _clean_header(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _find_header_index(headers: list[str], tokens: tuple[str, ...]) -> int:
    for idx, header in enumerate(headers):
        if all(token in header for token in tokens):
            return idx
    raise ValueError(f"Could not find header containing {tokens}: {headers}")


def _find_value_column(headers: list[str], year: int, tokens: tuple[str, ...]) -> int:
    year_token = str(year)
    candidates = []
    for idx, header in enumerate(headers):
        if year_token in header and all(token in header for token in tokens):
            candidates.append(idx)
    if candidates:
        return candidates[-1]
    raise ValueError(f"Could not find {year} value column with {tokens}: {headers}")


def _pdf_text(path: Path) -> str:
    if shutil.which("pdftotext"):
        result = subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.stdout

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_pdf_text(text: str, year: int, diagnostics: ExtractionDiagnostics | None = None) -> pd.DataFrame:
    records: dict[str, dict[str, object]] = {}
    for measure, table_number in PDF_TABLES.items():
        values = _parse_pdf_table(text, table_number, year)
        for county_name, value in values.items():
            record = records.setdefault(county_name, {"state": "FL", "county_name": county_name, "year": year})
            record[measure] = value

    if diagnostics is not None:
        if any("Dade -> Miami-Dade" in note for note in _pdf_alias_notes(text)):
            diagnostics.alias_mappings.add("Dade -> Miami-Dade (12086)")
        for measure in PDF_TABLES:
            count = sum(1 for row in records.values() if measure in row)
            if count != 67:
                diagnostics.missing_sources.append(
                    f"FL {year}: parsed {count} counties from PDF measure {measure}; expected 67"
                )

    return pd.DataFrame(records.values()) if records else _empty_fl()


def _parse_pdf_table(text: str, table_number: str, year: int) -> dict[str, float]:
    lines = _table_section(text.splitlines(), table_number)
    header_idx, year_positions = _find_pdf_year_positions(lines, year)
    ordered_years = sorted(year_positions, key=lambda item: item[1])
    target_idx = [idx for idx, (found_year, _) in enumerate(ordered_years) if found_year == year][0]
    target_pos = ordered_years[target_idx][1]
    prev_pos = ordered_years[target_idx - 1][1] if target_idx > 0 else None
    next_pos = ordered_years[target_idx + 1][1] if target_idx + 1 < len(ordered_years) else None
    start = 0 if prev_pos is None else (prev_pos + target_pos) // 2
    end = 10_000 if next_pos is None else (target_pos + next_pos) // 2

    values: dict[str, float] = {}
    aliases = _pdf_county_aliases()
    for line in lines[header_idx + 1 :]:
        matched = _match_pdf_county(line, aliases)
        if matched is None:
            continue
        source_name, canonical = matched
        window = line[start:end]
        value = _first_money_value(window)
        if value is not None:
            values[canonical] = float(value)
    return values


def _table_section(lines: list[str], table_number: str) -> list[str]:
    header_re = re.compile(rf"\bTABLE\s+{re.escape(table_number)}\s*(?:,\s*PAGE|\s+PAGE)", re.IGNORECASE)
    any_header_re = re.compile(r"\bTABLE\s+([0-9A-Z]+)\s*(?:,\s*PAGE|\s+PAGE)", re.IGNORECASE)
    start = None
    for idx, line in enumerate(lines):
        if header_re.search(line):
            start = idx
            break
    if start is None:
        raise ValueError(f"Could not find PDF table {table_number}")

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        match = any_header_re.search(lines[idx])
        if match and match.group(1).upper() != table_number.upper():
            end = idx
            break
    return lines[start:end]


def _find_pdf_year_positions(lines: list[str], target_year: int) -> tuple[int, list[tuple[int, int]]]:
    for idx, line in enumerate(lines):
        if "comparative statement" in line.lower():
            continue
        matches = [(int(match.group()), match.start()) for match in re.finditer(r"\b(?:19|20)\d{2}\b", line)]
        unique_years = {year for year, _ in matches}
        if len(unique_years) >= 4 and target_year in unique_years:
            deduped: list[tuple[int, int]] = []
            seen = set()
            for year, pos in matches:
                if year not in seen:
                    deduped.append((year, pos))
                    seen.add(year)
            return idx, deduped
    raise ValueError(f"Could not find PDF column positions for {target_year}")


def _pdf_county_aliases() -> list[tuple[str, str]]:
    aliases: list[tuple[str, str]] = []
    for key, (canonical, _) in county_lookup("FL").items():
        aliases.append((key, canonical))
    aliases.extend(
        [
            ("DADE", "Miami-Dade"),
            ("MIAMI DADE", "Miami-Dade"),
            ("ST JOHNS", "St. Johns"),
            ("SAINT JOHNS", "St. Johns"),
            ("ST LUCIE", "St. Lucie"),
            ("SAINT LUCIE", "St. Lucie"),
            ("DESOTO", "DeSoto"),
        ]
    )
    aliases = sorted(set(aliases), key=lambda item: len(item[0]), reverse=True)
    return aliases


def _match_pdf_county(line: str, aliases: list[tuple[str, str]]) -> tuple[str, str] | None:
    stripped = line.lstrip()
    line_key = re.sub(r"[^A-Za-z0-9]+", " ", stripped).strip().upper()
    for alias_key, canonical in aliases:
        if line_key == alias_key or line_key.startswith(alias_key + " "):
            return alias_key, canonical
    return None


def _first_money_value(text: str) -> int | None:
    match = re.search(r"\d{1,3}(?:,\d{3})+|\d{4,}", text)
    if not match:
        return None
    return int(match.group().replace(",", ""))


def _pdf_alias_notes(text: str) -> list[str]:
    return ["Dade -> Miami-Dade (12086)"] if re.search(r"(?m)^\s*DADE\b", text, re.IGNORECASE) else []


def _empty_fl() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "state",
            "county_name",
            "year",
            "market_or_full_value",
            "assessed_value",
            "county_taxable_value",
            "school_taxable_value",
        ]
    )
