import pandas as pd

from ptbase.extractors.states import ca
from ptbase.transform import build_state_panel


def test_ca_extract_maps_boe_fields(monkeypatch, tmp_path):
    payload = {
        "value": [
            {
                "AssessmentYearFrom": 2000,
                "AssessmentYearTo": 2001,
                "County": "Alameda",
                "TotalAssessedValue": 123,
            }
        ]
    }

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    # Keep the test off the real raw file: extract_ca() persists whatever the
    # (mocked) download returns to RAW_PATH, and reuses RAW_PATH when it exists.
    monkeypatch.setattr(ca, "RAW_PATH", tmp_path / "boe_net_assessed_values_by_county.json")
    monkeypatch.setattr(ca.requests, "get", lambda *args, **kwargs: Response())
    raw, diagnostics = ca.extract_ca()
    assert diagnostics.fips_mismatches == []
    assert raw.loc[0, "county_name"] == "Alameda"
    assert raw.loc[0, "year"] == 2000
    assert raw.loc[0, "net_assessed_value"] == 123


def test_ca_panel_growth_uses_net_assessed_base():
    raw = pd.DataFrame(
        {
            "state": ["CA", "CA"],
            "county_name": ["Alameda", "Alameda"],
            "year": [2000, 2001],
            "net_assessed_value": [100.0, 125.0],
        }
    )
    panel = build_state_panel(raw, "CA")
    alameda_2001 = panel[(panel["county_fips"] == "06001") & (panel["year"] == 2001)].iloc[0]
    assert alameda_2001["net_assessed_value_growth_since_2000"] == 0.25
    assert alameda_2001["net_assessed_value_index_2000_100"] == 125.0

