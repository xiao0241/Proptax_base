from __future__ import annotations

import pandas as pd

from .config import FINAL_COLUMNS, GROWTH_COLUMNS, INDEX_COLUMNS, VALUE_COLUMNS, YEARS
from .fips import normalize_county_name, state_counties


def build_state_panel(raw: pd.DataFrame, state: str) -> pd.DataFrame:
    counties = state_counties(state)
    skeleton = (
        counties.assign(_key=1)
        .merge(pd.DataFrame({"year": YEARS, "_key": 1}), on="_key")
        .drop(columns="_key")
        .sort_values(["county_fips", "year"])
        .reset_index(drop=True)
    )

    values = _standardize_raw(raw, state)
    panel = skeleton.merge(values, on=["state", "county_name", "year"], how="left", suffixes=("", "_source"))
    panel = panel.drop(columns=[col for col in panel.columns if col.endswith("_source")])

    for col in VALUE_COLUMNS:
        if col not in panel.columns:
            panel[col] = pd.NA
        panel[col] = pd.to_numeric(panel[col], errors="coerce")

    panel = compute_growth_indexes(panel)
    return panel[FINAL_COLUMNS].sort_values(["county_fips", "year"]).reset_index(drop=True)


def _standardize_raw(raw: pd.DataFrame, state: str) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=["state", "county_name", "year", *VALUE_COLUMNS])

    df = raw.copy()
    df["state"] = state
    normalized_names = []
    for county in df["county_name"]:
        canonical, _, _ = normalize_county_name(county, state)
        normalized_names.append(canonical if canonical is not None else county)
    df["county_name"] = normalized_names
    df["year"] = pd.to_numeric(df["year"], errors="coerce").astype("Int64")
    df = df[df["year"].isin(YEARS)].copy()
    for col in VALUE_COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df[["state", "county_name", "year", *VALUE_COLUMNS]]


def compute_growth_indexes(panel: pd.DataFrame) -> pd.DataFrame:
    out = panel.copy()
    for value_col, growth_col, index_col in zip(VALUE_COLUMNS, GROWTH_COLUMNS, INDEX_COLUMNS, strict=True):
        out[growth_col] = pd.NA
        out[index_col] = pd.NA
        base = out.loc[out["year"] == 2000, ["county_fips", value_col]].rename(columns={value_col: "_base"})
        out = out.merge(base, on="county_fips", how="left")
        valid = out["_base"].notna() & (out["_base"] > 0) & out[value_col].notna()
        out.loc[valid, growth_col] = out.loc[valid, value_col] / out.loc[valid, "_base"] - 1
        out.loc[valid, index_col] = out.loc[valid, value_col] / out.loc[valid, "_base"] * 100
        out = out.drop(columns="_base")
        out[growth_col] = pd.to_numeric(out[growth_col], errors="coerce")
        out[index_col] = pd.to_numeric(out[index_col], errors="coerce")
    return out

