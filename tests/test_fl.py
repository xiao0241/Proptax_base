from pathlib import Path

import pandas as pd

from ptbase.extractors.states.fl import parse_excel_report, parse_pdf_text


def test_fl_excel_parser_reads_county_total_value(tmp_path: Path):
    path = tmp_path / "just_value.xlsx"
    df = pd.DataFrame(
        [
            ["Just Value All Property Types", None, None],
            [2020, None, None],
            [None, None, None],
            ["County", "Status", "2020 Total\n Just Value"],
            ["Alachua", "R-Final", 1000],
            ["Saint Johns", "R-Final", 2000],
            ["Statewide", None, 3000],
        ]
    )
    with pd.ExcelWriter(path) as writer:
        df.to_excel(writer, sheet_name="Just Value All Property Types", header=False, index=False)

    values = parse_excel_report(path, 2020, "market_or_full_value")
    assert values == {"Alachua": 1000.0, "St. Johns": 2000.0}


def test_fl_pdf_parser_reads_tables_and_dade_alias():
    text = """
==== TABLE   4    PAGE ONE.    COMPARATIVE STATEMENT OF   2001, 2000, 1999 AND 1998 TAX ROLLS ====
                             2001 VALUE                  2000 VALUE                  1999 VALUE       1998 VALUE
County        Status
ALACHUA      : PRELIMINARY : 1,111,111     1.0 :       999,999      1.0 :       888,888      1.0 :   777,777:
DADE         :             :     N/A       N/A :     2,222,222      N/A :     2,111,111      N/A : 2,000,000:
==== TABLE   5    PAGE ONE. ignore ====
==== TABLE   27    PAGE ONE.    COMPARATIVE STATEMENT OF   2001, 2000, 1999 AND 1998 TAX ROLLS ====
                             2001 VALUE                  2000 VALUE                  1999 VALUE       1998 VALUE
County        Status
ALACHUA      : PRELIMINARY : 3,111,111     1.0 :     3,999,999      1.0 :       888,888      1.0 :   777,777:
DADE         :             :     N/A       N/A :     4,222,222      N/A :     2,111,111      N/A : 2,000,000:
==== TABLE   28    PAGE ONE.    COMPARATIVE STATEMENT OF   2001, 2000, 1999 AND 1998 TAX ROLLS ====
                             2001 VALUE                  2000 VALUE                  1999 VALUE       1998 VALUE
County        Status
ALACHUA      : PRELIMINARY : 5,111,111     1.0 :     5,999,999      1.0 :       888,888      1.0 :   777,777:
DADE         :             :     N/A       N/A :     6,222,222      N/A :     2,111,111      N/A : 2,000,000:
==== TABLE   29    PAGE ONE. ignore ====
"""
    df = parse_pdf_text(text, 2000)
    dade = df[df["county_name"] == "Miami-Dade"].iloc[0]
    assert dade["market_or_full_value"] == 2222222.0
    assert dade["county_taxable_value"] == 4222222.0
    assert dade["school_taxable_value"] == 6222222.0

