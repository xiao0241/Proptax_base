from ptbase.extractors.states.tx import parse_appendix_c
from ptbase.fips import state_counties


def test_tx_appendix_c_parses_blocks_and_statewide_total():
    text = """
                  Category             Appraised Value       Appraised Value
                                      001                       002
                                    Anderson                 Andrews
 A. Single-Family Residential     $         100         $         200
 Total Values                     $       1,000         $       2,000
 General Fund Levy                $           5         $           6
 Total County Levy                $           5         $           6
                                      003
                                    Angelina
 A. Single-Family Residential     $         300
 Total Values                     $       3,000
 Total County Levy                $           9
                       Total Appraised Value
 A. Single-Family Residential             $         600
 Total Values                             $       6,000
"""
    cad_values, statewide = parse_appendix_c(text)

    # CAD number -> total appraised value; levy rows are ignored.
    assert cad_values == {1: 1000, 2: 2000, 3: 3000}
    assert statewide == 6000


def test_tx_cad_number_maps_to_alphabetical_fips_order():
    # The extractor assigns CAD number N to the Nth TX county in ascending-FIPS order.
    counties = state_counties("TX").sort_values("county_fips").reset_index(drop=True)
    assert len(counties) == 254
    assert counties.iloc[0]["county_name"] == "Anderson"
    assert counties.iloc[0]["county_fips"] == "48001"
    assert counties.iloc[-1]["county_name"] == "Zavala"
    assert counties.iloc[-1]["county_fips"] == "48507"
