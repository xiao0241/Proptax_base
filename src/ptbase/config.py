from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
START_YEAR = 2000
END_YEAR = 2022
YEARS = list(range(START_YEAR, END_YEAR + 1))

VALUE_COLUMNS = [
    "market_or_full_value",
    "assessed_value",
    "net_assessed_value",
    "county_taxable_value",
    "school_taxable_value",
]

GROWTH_COLUMNS = [f"{col}_growth_since_2000" for col in VALUE_COLUMNS]
INDEX_COLUMNS = [f"{col}_index_2000_100" for col in VALUE_COLUMNS]

FINAL_COLUMNS = [
    "state",
    "state_fips",
    "county_name",
    "county_fips",
    "year",
    *VALUE_COLUMNS,
    *GROWTH_COLUMNS,
    *INDEX_COLUMNS,
]

BANNED_FINAL_COLUMNS = {
    "source_url",
    "source_title",
    "source_agency",
    "source_id",
    "data_status",
    "quality_flag",
    "source_note",
    "notes",
    "selected_value_for_analysis",
    "selected_value_type",
    "log_selected_value",
    "valuation_growth_since_2000",
    "valuation_index_2000_100",
    "population",
    "race",
    "income",
    "age",
    "education",
}

EXPECTED_COUNTIES = {"AZ": 15, "CA": 58, "FL": 67, "GA": 159, "MN": 87, "TX": 254, "WA": 39, "WI": 72}
