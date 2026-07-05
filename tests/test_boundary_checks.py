import yaml

from ptbase.config import ROOT


def test_boundary_check_documented_for_ca_fl():
    data = yaml.safe_load((ROOT / "metadata" / "shared" / "geography_issues.yaml").read_text())
    assert "No significant county" in data["boundary_change_check"]["CA"]["finding"]
    assert "No significant county" in data["boundary_change_check"]["FL"]["finding"]
    assert data["aliases"]["FL"]["Dade"] == "Miami-Dade"

