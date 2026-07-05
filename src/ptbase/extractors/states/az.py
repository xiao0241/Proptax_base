from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from ...config import ROOT
from ...fips import county_lookup
from ..base import ExtractionDiagnostics, reject_non_county_source

# AZ DOR 2002 Annual Report (transmitted Nov 2002), Table 36: TAX YEAR 2002 PRIMARY
# PROPERTY TAX LEVIES — NET ASSESSED VALUATION by county (whole dollars). Primary NAV
# (limited values, net of exemptions) is the base primary (operating) levies apply to:
# the Brosy & Ferrero NAV concept. Table 37 secondary NAV (full cash values, for
# bonds/overrides) exists in the same source but maps to no schema column; see
# metadata/states/AZ/value_concordance.yaml.
PDF_PATH = ROOT / "data" / "raw" / "AZ" / "2002" / "REPORTS_ANNUAL_2002_ASSETS_fy02_annual_report.pdf"
PDF_SHA256 = "c5cbee162bce01a07ce20725d3a00e80af5045ebb4282eb081f4ef6fde3b43be"
PDF_URL = "https://azdor.gov/sites/default/files/2023-03/REPORTS_ANNUAL_2002_ASSETS_fy02_annual_report.pdf"
TAX_YEAR = 2002
SECTION_START = "TAX YEAR 2002 PRIMARY PROPERTY TAX LEVIES"
SECTION_END = "TAX YEAR 2001"
STATEWIDE_SUM_TOLERANCE = 0.005


def extract_az() -> tuple[pd.DataFrame, ExtractionDiagnostics]:
    reject_non_county_source("county_aggregate")
    diagnostics = ExtractionDiagnostics(state="AZ")

    if not PDF_PATH.exists():
        diagnostics.missing_sources.append(
            f"AZ 2002: DOR 2002 Annual Report PDF missing at {PDF_PATH} (source: {PDF_URL})"
        )
        return _empty_az(), diagnostics

    digest = hashlib.sha256(PDF_PATH.read_bytes()).hexdigest()
    if digest != PDF_SHA256:
        raise RuntimeError(f"AZ 2002: sha256 mismatch for {PDF_PATH}: {digest} != pinned {PDF_SHA256}")
    diagnostics.files_reused.append(str(PDF_PATH))

    values, statewide_printed = _parse_table36(_pdf_text(PDF_PATH))

    if len(values) != 15:
        raise RuntimeError(f"AZ 2002: parsed {len(values)} counties from Table 36, expected 15")
    if statewide_printed is None:
        raise RuntimeError("AZ 2002: TOTAL STATE row not found in Table 36")
    county_sum = sum(values.values())
    rel = abs(county_sum - statewide_printed) / statewide_printed
    if rel > STATEWIDE_SUM_TOLERANCE:
        raise RuntimeError(
            f"AZ 2002: county sum {county_sum:,} vs printed TOTAL STATE {statewide_printed:,} "
            f"differs by {rel:.4%} (> {STATEWIDE_SUM_TOLERANCE:.1%})"
        )
    diagnostics.notes.append(
        "AZ 2002: parsed 15 counties from DOR 2002 Annual Report Table 36 (tax year 2002 primary "
        f"net assessed valuation, whole dollars); county sum {county_sum:,} vs printed TOTAL STATE "
        f"{statewide_printed:,}, rel diff {rel:.6%}; sha256 verified. Cross-check: the 2003 Annual "
        "Report (data/raw/AZ/2002/annual2003.pdf) reprints identical TY2002 figures for every county."
    )

    out = pd.DataFrame(
        {
            "state": "AZ",
            "county_name": list(values),
            "year": TAX_YEAR,
            # Concordance: AZ primary NAV is the Brosy & Ferrero NAV concept.
            "net_assessed_value": list(values.values()),
            "county_taxable_value": list(values.values()),
        }
    )
    return out, diagnostics


def _parse_table36(text: str) -> tuple[dict[str, int], int | None]:
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if SECTION_START in line), None)
    if start is None:
        raise RuntimeError(f"AZ 2002: section header not found: {SECTION_START!r}")
    section: list[str] = []
    for line in lines[start + 1 :]:
        if SECTION_END in line:
            break
        section.append(line)

    aliases = sorted(county_lookup("AZ").items(), key=lambda item: len(item[0]), reverse=True)
    values: dict[str, int] = {}
    statewide: int | None = None
    for line in section:
        stripped = line.strip()
        money = re.findall(r"\d{1,3}(?:,\d{3})+|\d+", stripped)
        if not money:
            continue
        label = re.split(r"[\d$]", stripped, 1)[0]
        label_key = re.sub(r"[^A-Za-z0-9]+", " ", label).strip().upper()
        # NET ASSESSED VALUATION is the first money figure on each row
        value = int(money[0].replace(",", ""))
        if label_key == "TOTAL STATE":
            statewide = value
            continue
        for alias_key, (canonical, _) in aliases:
            if label_key == alias_key:
                if canonical not in values:
                    values[canonical] = value
                break
    return values, statewide


def _pdf_text(path: Path) -> str:
    if shutil.which("pdftotext"):
        return subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _empty_az() -> pd.DataFrame:
    return pd.DataFrame(columns=["state", "county_name", "year", "net_assessed_value", "county_taxable_value"])
