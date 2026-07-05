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

# WI DOR "Town, Village and City Taxes 2002" bulletin (county-level, whole dollars,
# valuation date Jan 1, 2002). Per county:
#   2002 Full Value (equalized value, TID-in)        -> market_or_full_value
#   2002 Full Value Excluding TIF (TID-out)          -> county_taxable_value
# TID-out is the equalized value net of tax-incremental-district value increments —
# per the bulletin, the value "used for the apportionment of county and school
# levies": the county-levy base, i.e. the Brosy & Ferrero NAV analog for WI. Note
# WI equalized values are full-market-value concepts (not ratio-scaled assessed
# values); see metadata/states/WI/value_concordance.yaml.
PDF_PATH = ROOT / "data" / "raw" / "WI" / "2002" / "tvc02.pdf"
PDF_SHA256 = "576e006e0b076f0bf490f801e0ea2a3e62bac611935827519a27db672092ae79"
PDF_URL = "http://web.archive.org/web/20050315064933id_/http://www.dor.state.wi.us/pubs/slf/tvc02.pdf"
ASSESSMENT_YEAR = 2002
COUNTY_ROW_RE = re.compile(r"^TOTAL\s+(.+?)\s+COUNTY\b")
# digit required after STATE so summary lines like "TOTAL STATE TAX CREDIT" don't match
STATE_ROW_RE = re.compile(r"^TOTAL\s+STATE\s+\d")
NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")
STATEWIDE_SUM_TOLERANCE = 0.005


def extract_wi() -> tuple[pd.DataFrame, ExtractionDiagnostics]:
    reject_non_county_source("county_aggregate")
    diagnostics = ExtractionDiagnostics(state="WI")

    if not PDF_PATH.exists():
        diagnostics.missing_sources.append(
            f"WI 2002: DOR TVC 2002 bulletin missing at {PDF_PATH} (source: {PDF_URL})"
        )
        return _empty_wi(), diagnostics

    digest = hashlib.sha256(PDF_PATH.read_bytes()).hexdigest()
    if digest != PDF_SHA256:
        raise RuntimeError(f"WI 2002: sha256 mismatch for {PDF_PATH}: {digest} != pinned {PDF_SHA256}")
    diagnostics.files_reused.append(str(PDF_PATH))

    lookup = county_lookup("WI")
    values: dict[str, tuple[int, int]] = {}
    statewide: tuple[int, int] | None = None
    for line in _pdf_text(PDF_PATH).splitlines():
        stripped = line.strip()
        state_match = STATE_ROW_RE.match(stripped)
        county_match = COUNTY_ROW_RE.match(stripped)
        if not state_match and not county_match:
            continue
        money = NUMBER_RE.findall(stripped)
        if len(money) < 3:
            continue
        # fields: population, full value (TID-in), full value excluding TIF (TID-out), ...
        tid_in = int(money[1].replace(",", ""))
        tid_out = int(money[2].replace(",", ""))
        if state_match:
            if statewide is None:
                statewide = (tid_in, tid_out)
            continue
        key = re.sub(r"[^A-Za-z0-9]+", " ", county_match.group(1)).strip().upper()
        found = lookup.get(key)
        if found is None:
            diagnostics.fips_mismatches.append(f"WI unknown county row: {stripped[:60]}")
            continue
        canonical = found[0]
        if canonical not in values:
            values[canonical] = (tid_in, tid_out)

    if len(values) != 72:
        raise RuntimeError(f"WI 2002: parsed {len(values)} county TOTAL rows, expected 72")
    if statewide is None:
        raise RuntimeError("WI 2002: TOTAL STATE row not found")
    for label, idx in (("TID-in equalized value", 0), ("TID-out equalized value", 1)):
        county_sum = sum(v[idx] for v in values.values())
        printed = statewide[idx]
        rel = abs(county_sum - printed) / printed
        if rel > STATEWIDE_SUM_TOLERANCE:
            raise RuntimeError(
                f"WI 2002: {label}: county sum {county_sum:,} vs printed TOTAL STATE {printed:,} "
                f"differs by {rel:.4%} (> {STATEWIDE_SUM_TOLERANCE:.1%})"
            )
        diagnostics.notes.append(
            f"WI 2002: {label}: 72 counties, sum {county_sum:,} vs printed TOTAL STATE "
            f"{printed:,} (rel diff {rel:.6%})."
        )
    diagnostics.notes.append(
        "WI 2002: whole dollars; sha256 verified. Cross-checks: DOR Aug 15, 2002 news release "
        "(data/raw/WI/2002/020815pr.html) lists all 72 counties' TID-in equalized values and the "
        "statewide total identically; per-county Bureau of Equalization apportionment reports "
        "(02eqada.pdf, 02eqmil.pdf) reproduce the TID-out values for Adams and Milwaukee exactly."
    )

    counties = sorted(values)
    out = pd.DataFrame(
        {
            "state": "WI",
            "county_name": counties,
            "year": ASSESSMENT_YEAR,
            "market_or_full_value": [values[c][0] for c in counties],
            "county_taxable_value": [values[c][1] for c in counties],
        }
    )
    return out, diagnostics


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


def _empty_wi() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["state", "county_name", "year", "market_or_full_value", "county_taxable_value"]
    )
