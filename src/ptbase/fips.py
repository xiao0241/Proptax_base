from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import ROOT

COUNTY_FIPS_PATH = ROOT / "metadata" / "shared" / "county_fips.csv"


def _key(name: str) -> str:
    cleaned = str(name).strip()
    cleaned = re.sub(r"\bcounty\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.replace("&", " and ")
    cleaned = re.sub(r"[^A-Za-z0-9]+", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().upper()


@lru_cache(maxsize=1)
def load_counties() -> pd.DataFrame:
    df = pd.read_csv(COUNTY_FIPS_PATH, dtype=str)
    return df.sort_values(["state", "county_fips"]).reset_index(drop=True)


@lru_cache(maxsize=None)
def county_lookup(state: str) -> dict[str, tuple[str, str]]:
    state = state.upper()
    df = load_counties().query("state == @state")
    lookup: dict[str, tuple[str, str]] = {}
    for row in df.itertuples(index=False):
        lookup[_key(row.county_name)] = (row.county_name, row.county_fips)

    if state == "FL":
        lookup[_key("Dade")] = ("Miami-Dade", "12086")
        lookup[_key("Dade County")] = ("Miami-Dade", "12086")
        lookup[_key("Miami Dade")] = ("Miami-Dade", "12086")
        lookup[_key("Miami-Dade County")] = ("Miami-Dade", "12086")
        lookup[_key("Saint Johns")] = ("St. Johns", "12109")
        lookup[_key("Saint Lucie")] = ("St. Lucie", "12111")

    return lookup


def normalize_county_name(name: str, state: str) -> tuple[str | None, str | None, str | None]:
    """Return canonical county name, FIPS, and alias note if an alias was used."""
    raw = str(name).strip()
    lookup = county_lookup(state)
    found = lookup.get(_key(raw))
    if found is None:
        return None, None, None

    canonical, county_fips = found
    alias_note = None
    if _key(raw) != _key(canonical):
        alias_note = f"{raw} -> {canonical} ({county_fips})"
    return canonical, county_fips, alias_note


def state_counties(state: str) -> pd.DataFrame:
    return load_counties().query("state == @state").copy().reset_index(drop=True)

