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

# MN DOR "Property Taxes Levied in Minnesota: Summary Tables for Taxes Payable 2003".
# MN timing: assessment year 2002 (valuation date Jan 2, 2002) determines taxes
# payable 2003, so the payable-2003 bulletin is the assessment-year-2002 volume.
# Table 32 ("Taxable Value Determination by County", whole dollars):
#   col 1 Total Net Tax Capacity Value  -> net_assessed_value
#   col 5 Total Taxable Value           -> county_taxable_value
# Col 5 is taxable net tax capacity (after TIF capture, fiscal-disparities
# contribution, and power-line value) — per the bulletin, "used in determining
# initial tax rates for local taxing jurisdictions": the Brosy & Ferrero NAV analog.
# Table 28 Part B ("2002 Taxable Market Value ... Real and Personal", whole dollars)
# REAL & PERSONAL total -> market_or_full_value.
PDF_PATH = ROOT / "data" / "raw" / "MN" / "2002" / "ptbulletin_03.pdf"
PDF_SHA256 = "beca4023a9248b4f21c9060b7618aa8aed4a5ef6f77ce42a59487e7b75d8ae7d"
PDF_URL = "https://www.revenue.state.mn.us/sites/default/files/2011-11/ptbulletin_03.pdf"
ASSESSMENT_YEAR = 2002
T32_MARKER = "TAXABLE VALUE DETERMINATION BY COUNTY"
T28B_MARKER = "TAXABLE MARKET VALUE TOTALS"
STATEWIDE_SUM_TOLERANCE = 0.005

# The bulletin's own county spellings that differ from the census names.
EXTRA_ALIASES = {
    "OTTERTAIL": "Otter Tail",
    "WATOWAN": "Watonwan",
    "WILKEN": "Wilkin",
}

NUMBER_RE = re.compile(r"\d{1,3}(?:,\d{3})+|\d+")


def extract_mn() -> tuple[pd.DataFrame, ExtractionDiagnostics]:
    reject_non_county_source("county_aggregate")
    diagnostics = ExtractionDiagnostics(state="MN")

    if not PDF_PATH.exists():
        diagnostics.missing_sources.append(
            f"MN 2002: DOR payable-2003 bulletin missing at {PDF_PATH} (source: {PDF_URL})"
        )
        return _empty_mn(), diagnostics

    digest = hashlib.sha256(PDF_PATH.read_bytes()).hexdigest()
    if digest != PDF_SHA256:
        raise RuntimeError(f"MN 2002: sha256 mismatch for {PDF_PATH}: {digest} != pinned {PDF_SHA256}")
    diagnostics.files_reused.append(str(PDF_PATH))

    pages = _pdf_text(PDF_PATH).split("\f")
    aliases = _aliases(diagnostics)

    t32, t32_statewide = _parse_table(
        pages, T32_MARKER, aliases, n_fields=7, picks={"total_ntc": 0, "taxable_ntc": 4}
    )
    t28, t28_statewide = _parse_table(
        pages, T28B_MARKER, aliases, n_fields=3, picks={"market": 2}
    )

    _gate(diagnostics, "Table 32 total net tax capacity", t32, "total_ntc", t32_statewide)
    _gate(diagnostics, "Table 32 taxable value", t32, "taxable_ntc", t32_statewide)
    _gate(diagnostics, "Table 28B real & personal market value", t28, "market", t28_statewide)

    diagnostics.notes.append(
        "MN 2002: values are for ASSESSMENT YEAR 2002 (taxes payable 2003 bulletin) — MN's "
        "Jan 2, 2002 valuation, matching the calendar-2002 valuation convention used for the "
        "other states. county_taxable_value is taxable net tax capacity (a classified-rate "
        "base, roughly 1-2% of market value — not a market-value-scale concept); "
        "market_or_full_value carries the 2002 taxable market value. Whole dollars; sha256 "
        "verified. Cross-check: the payable-2004 bulletin Table 26 Part C reprints the "
        "payable-2003 county total net tax capacity figures exactly."
    )

    counties = sorted(t32)
    out = pd.DataFrame(
        {
            "state": "MN",
            "county_name": counties,
            "year": ASSESSMENT_YEAR,
            "market_or_full_value": [t28[c]["market"] for c in counties],
            "net_assessed_value": [t32[c]["total_ntc"] for c in counties],
            "county_taxable_value": [t32[c]["taxable_ntc"] for c in counties],
        }
    )
    return out, diagnostics


def _aliases(diagnostics: ExtractionDiagnostics) -> list[tuple[str, str]]:
    aliases = {key: canonical for key, (canonical, _) in county_lookup("MN").items()}
    for key, canonical in EXTRA_ALIASES.items():
        aliases[key] = canonical
        diagnostics.alias_mappings.add(f"{key.title()} -> {canonical}")
    return sorted(aliases.items(), key=lambda item: len(item[0]), reverse=True)


def _parse_table(
    pages: list[str],
    marker: str,
    aliases: list[tuple[str, str]],
    n_fields: int,
    picks: dict[str, int],
) -> tuple[dict[str, dict[str, int]], dict[str, int] | None]:
    table_pages = [page for page in pages if marker in page]
    if not table_pages:
        raise RuntimeError(f"MN 2002: no pages matched table marker {marker!r}")

    values: dict[str, dict[str, int]] = {}
    statewide: dict[str, int] | None = None
    for page in table_pages:
        for line in page.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            money = NUMBER_RE.findall(stripped)
            if len(money) < n_fields:
                continue
            label = re.split(r"\d", stripped, 1)[0]
            label_key = re.sub(r"[^A-Za-z0-9]+", " ", label).strip().upper()
            if not label_key:
                continue
            fields = [int(m.replace(",", "")) for m in money[:n_fields]]
            picked = {name: fields[idx] for name, idx in picks.items()}
            if label_key in ("STATEWIDE", "STATEWIDE TOTAL"):
                if statewide is None:
                    statewide = picked
                continue
            for alias_key, canonical in aliases:
                if label_key == alias_key:
                    if canonical not in values:
                        values[canonical] = picked
                    break

    if len(values) != 87:
        raise RuntimeError(f"MN 2002: parsed {len(values)} counties for {marker!r}, expected 87")
    return values, statewide


def _gate(
    diagnostics: ExtractionDiagnostics,
    label: str,
    values: dict[str, dict[str, int]],
    field: str,
    statewide: dict[str, int] | None,
) -> None:
    if statewide is None:
        raise RuntimeError(f"MN 2002: statewide row not found for {label}")
    county_sum = sum(v[field] for v in values.values())
    printed = statewide[field]
    rel = abs(county_sum - printed) / printed
    if rel > STATEWIDE_SUM_TOLERANCE:
        raise RuntimeError(
            f"MN 2002: {label}: county sum {county_sum:,} vs printed statewide {printed:,} "
            f"differs by {rel:.4%} (> {STATEWIDE_SUM_TOLERANCE:.1%})"
        )
    diagnostics.notes.append(
        f"MN 2002: {label}: 87 counties, sum {county_sum:,} vs printed statewide {printed:,} "
        f"(rel diff {rel:.6%})."
    )


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
    return "\f".join(page.extract_text() or "" for page in reader.pages)


def _empty_mn() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "state",
            "county_name",
            "year",
            "market_or_full_value",
            "net_assessed_value",
            "county_taxable_value",
        ]
    )
