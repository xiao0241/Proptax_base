from ptbase.fips import normalize_county_name, state_counties


def test_dade_alias_maps_to_miami_dade_fips():
    county, fips, note = normalize_county_name("Dade", "FL")
    assert county == "Miami-Dade"
    assert fips == "12086"
    assert note == "Dade -> Miami-Dade (12086)"


def test_state_county_counts():
    assert len(state_counties("CA")) == 58
    assert len(state_counties("FL")) == 67


def test_saint_aliases_map_to_official_fips_names():
    assert normalize_county_name("Saint Johns", "FL")[:2] == ("St. Johns", "12109")
    assert normalize_county_name("Saint Lucie", "FL")[:2] == ("St. Lucie", "12111")

