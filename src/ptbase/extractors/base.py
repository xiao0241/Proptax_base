from __future__ import annotations

from dataclasses import dataclass, field


ALLOWED_SOURCE_GRANULARITIES = {"county_aggregate", "statewide_summary_by_county"}
REJECTED_SOURCE_GRANULARITIES = {
    "parcel",
    "taxing_district",
    "special_district",
    "school_district",
    "municipality",
    "city",
    "tax_rate_area",
    "levy_area",
    "revenue_district",
    "mixed_or_unknown",
}


class SourceRejectedError(ValueError):
    pass


def reject_non_county_source(source_granularity: str) -> None:
    if source_granularity in ALLOWED_SOURCE_GRANULARITIES:
        return
    if source_granularity in REJECTED_SOURCE_GRANULARITIES:
        raise SourceRejectedError(f"Rejected non-county source granularity: {source_granularity}")
    raise SourceRejectedError(f"Rejected unknown source granularity: {source_granularity}")


@dataclass
class ExtractionDiagnostics:
    state: str
    files_downloaded: list[str] = field(default_factory=list)
    files_reused: list[str] = field(default_factory=list)
    missing_sources: list[str] = field(default_factory=list)
    rejected_sources: list[str] = field(default_factory=list)
    fips_mismatches: list[str] = field(default_factory=list)
    alias_mappings: set[str] = field(default_factory=set)
    notes: list[str] = field(default_factory=list)

    def merge(self, other: "ExtractionDiagnostics") -> None:
        self.files_downloaded.extend(other.files_downloaded)
        self.files_reused.extend(other.files_reused)
        self.missing_sources.extend(other.missing_sources)
        self.rejected_sources.extend(other.rejected_sources)
        self.fips_mismatches.extend(other.fips_mismatches)
        self.alias_mappings.update(other.alias_mappings)
        self.notes.extend(other.notes)

