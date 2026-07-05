from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yaml

from .config import BANNED_FINAL_COLUMNS, EXPECTED_COUNTIES, FINAL_COLUMNS, VALUE_COLUMNS, YEARS


@dataclass
class ValidationResult:
    state: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def validate_state_panel(panel: pd.DataFrame, state: str) -> ValidationResult:
    result = ValidationResult(state=state)
    if list(panel.columns) != FINAL_COLUMNS:
        result.errors.append(f"{state}: final columns do not match required schema/order")

    banned = sorted(set(panel.columns) & BANNED_FINAL_COLUMNS)
    if banned:
        result.errors.append(f"{state}: final panel contains banned columns: {banned}")

    key_cols = ["state", "county_fips", "year"]
    duplicates = panel.duplicated(key_cols).sum()
    if duplicates:
        result.errors.append(f"{state}: duplicate state/county_fips/year rows: {duplicates}")

    if panel["county_fips"].isna().any():
        result.errors.append(f"{state}: county_fips contains missing values")

    expected_count = EXPECTED_COUNTIES[state]
    counts = panel.groupby("year")["county_fips"].nunique()
    for year in YEARS:
        observed = int(counts.get(year, 0))
        if observed != expected_count:
            result.errors.append(f"{state}: {year} has {observed} counties, expected {expected_count}")

    for col in VALUE_COLUMNS:
        numeric = pd.to_numeric(panel[col], errors="coerce")
        non_missing = panel[col].notna()
        if numeric[non_missing].isna().any():
            result.errors.append(f"{state}: {col} contains nonnumeric nonmissing values")
        if (numeric[non_missing] <= 0).any():
            result.errors.append(f"{state}: {col} contains nonpositive nonmissing values")

    return result


def validate_identical_schema(panels: dict[str, pd.DataFrame]) -> list[str]:
    mismatched = sorted(state for state, panel in panels.items() if list(panel.columns) != FINAL_COLUMNS)
    if mismatched:
        return [f"Final panels do not share the required schema/order: {mismatched}"]
    return []


def validate_value_concordance(panel: pd.DataFrame, state: str, metadata_root: Path) -> list[str]:
    path = metadata_root / "states" / state / "value_concordance.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    mapped = {entry["final_column_name"] for entry in data.get("values", [])}
    errors = []
    for col in VALUE_COLUMNS:
        if panel[col].notna().any() and col not in mapped:
            errors.append(f"{state}: populated valuation column {col} is missing from value_concordance.yaml")
    return errors


def validate_no_combined_final(root: Path) -> list[str]:
    forbidden = [
        root / "data" / "final" / "property_values_long.csv",
        root / "data" / "final" / "source_inventory.csv",
        root / "data" / "final" / "missing_sources.csv",
        root / "data" / "final" / "national_panel.csv",
        root / "data" / "final" / "combined_ca_fl.csv",
    ]
    return [f"Forbidden final deliverable exists: {path}" for path in forbidden if path.exists()]

