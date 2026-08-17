from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from ...config import ROOT
from ...fips import state_counties
from ..base import ExtractionDiagnostics, reject_non_county_source

# TX Comptroller of Public Accounts, "Annual Property Tax Report - Tax Year 2002",
# Appendix C: County Local Self Report Data. For each county (CAD number 001-254,
# alphabetical) the "Total Values" row is the total APPRAISED value of all property
# categories (A-S) on the county's tax roll. Texas appraises taxable property at
# 100% of market value (Tax Code 23.01), so this is the county's full-market-value
# base -> market_or_full_value. See metadata/states/TX/value_concordance.yaml.
# Whole dollars. The county's *taxable* value (after homestead exemptions and 1-d-1
# productivity valuation) is fund-specific (General Fund vs Farm-to-Market) and is
# not published as a single county figure; deriving it from levy/rate is disallowed
# by repo policy (no valuation inferred from levy/millage), so county_taxable_value
# is not carried for TX.
PDF_PATH = ROOT / "data" / "raw" / "TX" / "2002" / "appc_county_2002.pdf"
PDF_SHA256 = "0909866ee84d005d94743b7f19f258c7f7a00e4b72ddf09fd4b3421531b3f8d0"
PDF_URL = (
    "https://web.archive.org/web/20071122000751id_/"
    "http://www.window.state.tx.us/taxinfo/proptax/02annual/appc.pdf"
)
ASSESSMENT_YEAR = 2002
EXPECTED_CADS = 254
STATEWIDE_SUM_TOLERANCE = 0.005
NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")
# A block header line is 1-5 three-digit CAD numbers (e.g. "001 002 003 004 005").
CAD_ROW_RE = re.compile(r"^\d{3}(?:\s\d{3}){0,4}$")


def extract_tx() -> tuple[pd.DataFrame, ExtractionDiagnostics]:
    reject_non_county_source("statewide_summary_by_county")
    diagnostics = ExtractionDiagnostics(state="TX")

    if not PDF_PATH.exists():
        diagnostics.missing_sources.append(
            f"TX 2002: Comptroller Annual Report (Tax Year 2002) Appendix C missing at {PDF_PATH} "
            f"(source: {PDF_URL})"
        )
        return _empty_tx(), diagnostics

    digest = hashlib.sha256(PDF_PATH.read_bytes()).hexdigest()
    if digest != PDF_SHA256:
        raise RuntimeError(f"TX 2002: sha256 mismatch for {PDF_PATH}: {digest} != pinned {PDF_SHA256}")
    diagnostics.files_reused.append(str(PDF_PATH))

    cad_values, statewide = parse_appendix_c(_pdf_text(PDF_PATH))

    missing = [n for n in range(1, EXPECTED_CADS + 1) if n not in cad_values]
    if missing:
        raise RuntimeError(
            f"TX 2002: parsed {len(cad_values)} counties, expected {EXPECTED_CADS}; "
            f"missing CAD numbers {missing[:5]} ({len(missing)} total)"
        )
    if statewide is None:
        raise RuntimeError("TX 2002: statewide 'Total Appraised Value' total not found")
    county_sum = sum(cad_values.values())
    rel = abs(county_sum - statewide) / statewide
    if rel > STATEWIDE_SUM_TOLERANCE:
        raise RuntimeError(
            f"TX 2002: county sum {county_sum:,} vs printed statewide {statewide:,} "
            f"differs by {rel:.4%} (> {STATEWIDE_SUM_TOLERANCE:.1%})"
        )

    counties = state_counties("TX").sort_values("county_fips").reset_index(drop=True)
    if len(counties) != EXPECTED_CADS:
        raise RuntimeError(
            f"TX 2002: county_fips.csv has {len(counties)} TX counties, expected {EXPECTED_CADS}"
        )
    # CAD number 001-254 is assigned in alphabetical county order, which equals
    # ascending county_fips order (48001 Anderson … 48507 Zavala).
    names = counties["county_name"].tolist()

    out = pd.DataFrame(
        {
            "state": "TX",
            "county_name": [names[cad - 1] for cad in range(1, EXPECTED_CADS + 1)],
            "year": ASSESSMENT_YEAR,
            "market_or_full_value": [cad_values[cad] for cad in range(1, EXPECTED_CADS + 1)],
        }
    )
    diagnostics.notes.append(
        f"TX 2002: Appendix C county total appraised (market) value, tax year 2002; "
        f"{EXPECTED_CADS} counties, sum {county_sum:,} vs printed statewide Total Values "
        f"{statewide:,} (rel diff {rel:.6%}); whole dollars; sha256 verified. CAD number 001-254 "
        f"mapped to counties in ascending-FIPS (alphabetical) order. Cross-check: Appendix A "
        f"appraisal-district Total Value (independent CAD-level totals)."
    )
    return out, diagnostics


def parse_appendix_c(text: str) -> tuple[dict[int, int], int | None]:
    """Parse Appendix C text -> ({CAD number -> total appraised dollars}, statewide dollars).

    Each block prints a header row of up to five CAD numbers, then category rows, then
    a "Total Values" row with the matching appraised totals. The final block is the
    statewide recap, introduced by a "Total Appraised Value" header, whose "Total
    Values" line is the statewide total used as the sum QA gate.
    """
    current: list[int] = []
    statewide_mode = False
    cad_values: dict[int, int] = {}
    statewide: int | None = None
    for line in text.splitlines():
        stripped = re.sub(r"\s+", " ", line).strip()
        if not stripped:
            continue
        if stripped.startswith("Total Appraised Value"):
            statewide_mode = True
            continue
        if CAD_ROW_RE.match(stripped):
            current = [int(token) for token in stripped.split()]
            continue
        if stripped.startswith("Total Values"):
            amounts = [int(token.replace(",", "")) for token in NUMBER_RE.findall(stripped)]
            if statewide_mode:
                statewide = amounts[-1] if amounts else statewide
            elif current and len(amounts) == len(current):
                for cad, amount in zip(current, amounts):
                    cad_values.setdefault(cad, amount)
    return cad_values, statewide


def _pdf_text(path: Path) -> str:
    if shutil.which("pdftotext"):
        return subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        ).stdout

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _empty_tx() -> pd.DataFrame:
    return pd.DataFrame(columns=["state", "county_name", "year", "market_or_full_value"])
