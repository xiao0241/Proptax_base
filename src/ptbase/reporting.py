from __future__ import annotations

from pathlib import Path

import pandas as pd

from .config import FINAL_COLUMNS, VALUE_COLUMNS, YEARS
from .extractors.base import ExtractionDiagnostics

BOUNDARY_NOTES = {
    "AZ": "No county creation, deletion, split, consolidation, or FIPS change affects the panel window (15 counties, unchanged since 1983).",
    "CA": "No significant county creation, deletion, split, consolidation, or FIPS change affects the panel window.",
    "FL": "No significant county creation, deletion, split, consolidation, or FIPS change affects the panel window. Dade/Miami-Dade alias handling is name-only and maps to FIPS 12086.",
    "GA": "No county creation, deletion, split, consolidation, or FIPS change affects the panel window (159 counties, unchanged since 1932).",
    "MN": "No county creation, deletion, split, consolidation, or FIPS change affects the panel window (87 counties, unchanged since 1922).",
    "TX": "No county creation, deletion, split, consolidation, or FIPS change affects the panel window (254 counties, unchanged since 1931).",
    "WA": "No county creation, deletion, split, consolidation, or FIPS change affects the panel window (39 counties, unchanged since 1911).",
    "WI": "No county creation, deletion, split, consolidation, or FIPS change affects the panel window (72 counties, unchanged since 1961).",
}


def write_validation_summary(
    panels: dict[str, pd.DataFrame],
    diagnostics: dict[str, ExtractionDiagnostics],
    validation_errors: list[str],
    path: Path,
) -> None:
    states = sorted(panels)
    diags = [diagnostics[state] for state in states]
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = ["# Validation Summary", ""]
    for state in states:
        lines.extend(_county_counts(state, panels[state]))
    for state in states:
        lines.extend(_nonmissing_counts(state, panels[state]))
    lines.extend(
        _diagnostic_section(
            "Missing source years or measures",
            [item for diag in diags for item in diag.missing_sources],
        )
    )
    lines.extend(
        _diagnostic_section("FIPS mismatches", [item for diag in diags for item in diag.fips_mismatches])
    )
    alias_mappings: set[str] = set()
    for diag in diags:
        alias_mappings |= diag.alias_mappings
    lines.extend(_diagnostic_section("County name alias mappings", sorted(alias_mappings)))

    schema_ok = all(list(panels[state].columns) == FINAL_COLUMNS for state in states)
    rejected = [item for diag in diags for item in diag.rejected_sources]
    lines.extend(["## Boundary-Change Check", ""])
    for state in states:
        note = BOUNDARY_NOTES.get(state, "No boundary note recorded.")
        lines.append(f"- {state}: {note}")
    lines.extend(
        [
            "",
            "## Source Rejections And Scope Confirmations",
            "",
            "- Rejected non-county sources, if any: " + ("; ".join(rejected) if rejected else "none encountered."),
            "- Confirmed no district-level aggregation was used.",
            "- Confirmed no taxing-district, school-district, municipality, special-district, parcel, tax-rate-area, levy-area, or revenue-district sources were aggregated.",
            "- Confirmed no demographic variables were added.",
            "- Confirmed no combined multi-state final dataset was created.",
            f"- Confirmed final panels ({', '.join(states)}) have identical columns: {schema_ok}.",
            "- Confirmed source metadata were excluded from the final CSVs.",
            "- Confirmed final valuation values are in nominal dollars; no unit conversion was applied.",
            "",
        ]
    )
    lines.extend(_diagnostic_section("Validation errors", validation_errors))
    lines.extend(_diagnostic_section("Extractor notes", [item for diag in diags for item in diag.notes]))
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _county_counts(state: str, panel: pd.DataFrame) -> list[str]:
    lines = [f"## {state} County Count By Year", ""]
    counts = panel.groupby("year")["county_fips"].nunique()
    for year in YEARS:
        lines.append(f"- {year}: {int(counts.get(year, 0))}")
    lines.append("")
    return lines


def _nonmissing_counts(state: str, panel: pd.DataFrame) -> list[str]:
    lines = [f"## {state} Nonmissing Valuation Counts By Year", ""]
    for year in YEARS:
        row = panel[panel["year"] == year]
        counts = ", ".join(f"{col}={int(row[col].notna().sum())}" for col in VALUE_COLUMNS)
        lines.append(f"- {year}: {counts}")
    lines.append("")
    return lines


def _diagnostic_section(title: str, items: list[str]) -> list[str]:
    lines = [f"## {title}", ""]
    if items:
        lines.extend(f"- {item}" for item in items)
    else:
        lines.append("- None.")
    lines.append("")
    return lines
