import pytest

from ptbase.extractors.base import SourceRejectedError, reject_non_county_source


def test_allowed_county_source_granularity():
    reject_non_county_source("county_aggregate")
    reject_non_county_source("statewide_summary_by_county")


@pytest.mark.parametrize(
    "granularity",
    ["parcel", "taxing_district", "school_district", "municipality", "mixed_or_unknown"],
)
def test_rejected_non_county_source_granularity(granularity):
    with pytest.raises(SourceRejectedError):
        reject_non_county_source(granularity)

