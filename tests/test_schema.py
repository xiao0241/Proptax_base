import pandas as pd

from ptbase.config import BANNED_FINAL_COLUMNS, FINAL_COLUMNS, ROOT, YEARS
from ptbase.transform import build_state_panel
from ptbase.validate import validate_no_combined_final


def test_final_schema_order_for_state_panel():
    raw = pd.DataFrame(
        {
            "state": ["CA"],
            "county_name": ["Alameda"],
            "year": [2000],
            "net_assessed_value": [100.0],
        }
    )
    panel = build_state_panel(raw, "CA")
    assert list(panel.columns) == FINAL_COLUMNS
    assert not (set(panel.columns) & BANNED_FINAL_COLUMNS)
    assert panel["year"].min() == min(YEARS)
    assert panel["year"].max() == max(YEARS)


def test_no_generic_or_selected_value_columns():
    banned = {
        "selected_value_for_analysis",
        "selected_value_type",
        "log_selected_value",
        "valuation_growth_since_2000",
        "valuation_index_2000_100",
    }
    assert not (set(FINAL_COLUMNS) & banned)


def test_no_combined_final_output_exists():
    assert validate_no_combined_final(ROOT) == []
