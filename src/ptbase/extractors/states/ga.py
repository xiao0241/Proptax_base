from __future__ import annotations

import hashlib

import pandas as pd

from ...config import ROOT
from ..base import ExtractionDiagnostics, reject_non_county_source

# Georgia DOR "County Ad Valorem Tax Digest Consolidated Summaries", tax year 2002
# (hosted by UGA Carl Vinson Institute, georgiadata.org). Long format: one row per
# county x tax district; district id 0 is the countywide county-government M&O
# district. tax-valAmt-mo is the NET M&O digest (40%-assessed value net of state +
# local exemptions, nominal dollars) — the base county M&O mill rates apply to: the
# Brosy & Ferrero NAV concept.
XLSX_PATH = ROOT / "data" / "raw" / "GA" / "2002" / "2002_digest.xlsx"
XLSX_SHA256 = "c9675363d1682c420e3abfe37abac6771ffeef776d6c28d227bc5041c9d0d2dd"
XLSX_URL = "https://georgiadata.org/download/file/fid/146"
SHEET = "2002 digest"
TAX_YEAR = 2002
# Regression pin: sum of the 159 county net M&O digests in the sha256-pinned file.
# Cross-checked against GA DOR FY2003 Statistical Report Table 13 (state digest
# concept; reconciles within 0.06% statewide after motor-vehicle/utility adjustments).
EXPECTED_STATEWIDE_NET_MO = 227_324_419_078


def extract_ga() -> tuple[pd.DataFrame, ExtractionDiagnostics]:
    reject_non_county_source("county_aggregate")
    diagnostics = ExtractionDiagnostics(state="GA")

    if not XLSX_PATH.exists():
        diagnostics.missing_sources.append(
            f"GA 2002: DOR digest workbook missing at {XLSX_PATH} (source: {XLSX_URL})"
        )
        return _empty_ga(), diagnostics

    digest = hashlib.sha256(XLSX_PATH.read_bytes()).hexdigest()
    if digest != XLSX_SHA256:
        raise RuntimeError(f"GA 2002: sha256 mismatch for {XLSX_PATH}: {digest} != pinned {XLSX_SHA256}")
    diagnostics.files_reused.append(str(XLSX_PATH))

    df = pd.read_excel(XLSX_PATH, sheet_name=SHEET)
    years = df["rtn-period-taxYr"].dropna().unique().tolist()
    if years != [TAX_YEAR]:
        raise RuntimeError(f"GA 2002: workbook tax years {years}, expected [{TAX_YEAR}]")

    county = df[df["txpyr-dist-did"] == 0].copy()
    if len(county) != 159 or county["txpyr-name"].nunique() != 159:
        raise RuntimeError(
            f"GA 2002: district-0 rows = {len(county)} over {county['txpyr-name'].nunique()} "
            "counties, expected 159 unique counties"
        )

    net_mo = pd.to_numeric(county["tax-valAmt-mo"], errors="raise")
    exemptions = pd.to_numeric(county["exmp-valAmt-mo"], errors="raise")
    statewide = int(net_mo.sum())
    if statewide != EXPECTED_STATEWIDE_NET_MO:
        raise RuntimeError(
            f"GA 2002: statewide net M&O digest {statewide:,} != pinned {EXPECTED_STATEWIDE_NET_MO:,}"
        )
    diagnostics.notes.append(
        "GA 2002: 159 county-government (district 0) rows from the DOR consolidated digest "
        f"workbook; statewide net M&O digest {statewide:,} (nominal dollars) matches the pinned "
        "total; sha256 verified. Cross-check: GA DOR FY2003 Statistical Report Table 13 "
        "(data/raw/GA/2002/2003_statistical_report.pdf; state digest concept, thousands, excl. "
        "motor vehicles) reconciles within 0.06% statewide. Two district-0 rows carry mislabeled "
        "district names (Crisp, Forsyth) but equal the countywide incorporated+unincorporated "
        "totals exactly."
    )

    out = pd.DataFrame(
        {
            "state": "GA",
            "county_name": county["txpyr-name"].astype(str).str.strip().str.title(),
            "year": TAX_YEAR,
            # gross digest = net M&O + M&O exemptions (identity holds exactly in-source)
            "assessed_value": (net_mo + exemptions).astype("int64").to_numpy(),
            "county_taxable_value": net_mo.astype("int64").to_numpy(),
        }
    )
    return out, diagnostics


def _empty_ga() -> pd.DataFrame:
    return pd.DataFrame(columns=["state", "county_name", "year", "assessed_value", "county_taxable_value"])
