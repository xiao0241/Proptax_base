from pathlib import Path

import pandas as pd

from ptbase.extractors.states.wa import parse_table27


def test_wa_table27_reads_due_2003_column_and_converts_thousands(tmp_path: Path):
    path = tmp_path / "Table27.xlsx"
    frame = pd.DataFrame(
        [
            ["Table 27", None, None, None, None],
            ["ASSESSED VALUE OF ALL TAXABLE PROPERTY BY COUNTY", None, None, None, None],
            ["For Taxes Due in 2002 and 2003 ($000)", None, None, None, None],
            ["County", "Due 2002", None, "Due 2003", None],
            ["Adams", 1000.0, None, 1100.0, None],
            ["King", 200000.0, None, 223890.0, None],
            ["TOTAL", 201000.0, None, 224990.0, None],
        ]
    )
    with pd.ExcelWriter(path) as writer:
        frame.to_excel(writer, sheet_name="Table 27", header=False, index=False)

    values, statewide = parse_table27(path)

    # 'Due 2003' column (assessment year 2002), converted x1000 from thousands.
    assert values == {"Adams": 1_100_000, "King": 223_890_000}
    assert statewide == 224_990_000
