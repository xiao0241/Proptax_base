from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd

from ...config import ROOT
from ...fips import normalize_county_name
from ..base import ExtractionDiagnostics, reject_non_county_source

# WA DOR "Property Tax Statistics" (2003 report), Table 27: "Assessed Value of All
# Taxable Property by County, For Taxes Due in 2002 and 2003 ($000)". The "Due 2003"
# column is the January 1, 2002 assessment roll (taxes payable 2003) = assessment
# year 2002. Washington assesses all taxable property at 100% of true and fair
# (market) value (RCW 84.40.030), so this total taxable assessed value is a
# full-market-value levy base -> county_taxable_value (the Brosy & Ferrero NAV
# analog for WA). See metadata/states/WA/value_concordance.yaml. Values are printed
# in THOUSANDS of dollars and converted x1000 to nominal dollars.
XLS_PATH = ROOT / "data" / "raw" / "WA" / "2002" / "Table27_2003.xls"
XLS_SHA256 = "91338a220b7fcd9f062310466c8f23e9112c7091bbf01d93ee58aa5f2fd7a060"
XLS_URL = "https://dor.wa.gov/sites/default/files/2022-03/Table27.xls"
SHEET_NAME = "Table 27"
ASSESSMENT_YEAR = 2002
DUE_2003_COL = 3  # "Due 2003" = January 1, 2002 assessment roll (taxes payable 2003)
THOUSANDS = 1000
EXPECTED_COUNTIES = 39
STATEWIDE_SUM_TOLERANCE = 0.005


def extract_wa() -> tuple[pd.DataFrame, ExtractionDiagnostics]:
    reject_non_county_source("statewide_summary_by_county")
    diagnostics = ExtractionDiagnostics(state="WA")

    if not XLS_PATH.exists():
        diagnostics.missing_sources.append(
            f"WA 2002: DOR Property Tax Statistics Table 27 missing at {XLS_PATH} (source: {XLS_URL})"
        )
        return _empty_wa(), diagnostics

    digest = hashlib.sha256(XLS_PATH.read_bytes()).hexdigest()
    if digest != XLS_SHA256:
        raise RuntimeError(f"WA 2002: sha256 mismatch for {XLS_PATH}: {digest} != pinned {XLS_SHA256}")
    diagnostics.files_reused.append(str(XLS_PATH))

    values, statewide = parse_table27(XLS_PATH)

    if len(values) != EXPECTED_COUNTIES:
        raise RuntimeError(f"WA 2002: parsed {len(values)} counties, expected {EXPECTED_COUNTIES}")
    if statewide is None:
        raise RuntimeError("WA 2002: statewide TOTAL row not found")
    county_sum = sum(values.values())
    rel = abs(county_sum - statewide) / statewide
    if rel > STATEWIDE_SUM_TOLERANCE:
        raise RuntimeError(
            f"WA 2002: county sum {county_sum:,} vs printed TOTAL {statewide:,} "
            f"differs by {rel:.4%} (> {STATEWIDE_SUM_TOLERANCE:.1%})"
        )
    diagnostics.notes.append(
        f"WA 2002: Table 27 assessed value of all taxable property, assessment year 2002 "
        f"(the 'Due 2003' column = January 1, 2002 roll, taxes payable 2003); {EXPECTED_COUNTIES} "
        f"counties, sum {county_sum:,} vs printed TOTAL {statewide:,} (rel diff {rel:.6%}); "
        f"values x1000 from thousands of dollars; sha256 verified. Cross-checks: the 2003 report "
        f"Table 27 PDF (identical) and the DOR '2002 County Comparison' report; Table 31A reports "
        f"the sales-ratio actual value (real property) for the same counties."
    )

    counties = sorted(values)
    out = pd.DataFrame(
        {
            "state": "WA",
            "county_name": counties,
            "year": ASSESSMENT_YEAR,
            "county_taxable_value": [values[c] for c in counties],
        }
    )
    return out, diagnostics


def parse_table27(path: Path) -> tuple[dict[str, int], int | None]:
    """Parse Table 27 -> ({canonical county name -> nominal dollars}, statewide dollars).

    Reads the 'Due 2003' column (assessment year 2002) and converts the printed
    thousands-of-dollars figures to nominal dollars. Non-numeric header/title rows
    and county names outside county_fips.csv are skipped.
    """
    frame = pd.read_excel(path, sheet_name=SHEET_NAME, header=None)
    values: dict[str, int] = {}
    statewide: int | None = None
    for _, row in frame.iterrows():
        label = row[0]
        raw = row[DUE_2003_COL]
        if not isinstance(label, str) or not isinstance(raw, (int, float)) or pd.isna(raw):
            continue
        dollars = int(round(float(raw) * THOUSANDS))
        if label.strip().upper() == "TOTAL":
            statewide = dollars
            continue
        canonical, _fips, _alias = normalize_county_name(label, "WA")
        if canonical is None:
            continue
        values.setdefault(canonical, dollars)
    return values, statewide


def _empty_wa() -> pd.DataFrame:
    return pd.DataFrame(columns=["state", "county_name", "year", "county_taxable_value"])
