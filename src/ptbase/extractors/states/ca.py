from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

import pandas as pd
import requests

from ...config import END_YEAR, ROOT, START_YEAR, YEARS
from ...fips import county_lookup, normalize_county_name
from ..base import ExtractionDiagnostics, reject_non_county_source

CA_API_URL = "https://www.boe.ca.gov/dataportal/api/odata/Net_Assessed_Values_by_County"
RAW_PATH = ROOT / "data" / "raw" / "CA" / "boe_net_assessed_values_by_county.json"

# BOE Annual Report (FY 2001-02), statistical appendix Table 10: net state- and
# county-assessed value on the secured and unsecured rolls, by county, 2002-03 roll
# (lien date Jan 1, 2002). Net of "all other" exemptions; includes the homeowners'
# exemption value (the base the 1% rate applies to) — same Table 10 lineage as the
# BOE OData series above, so the CA series is concept-consistent across years.
PDF_2002_PATH = ROOT / "data" / "raw" / "CA" / "2002" / "table10_02.pdf"
PDF_2002_SHA256 = "095caa356e67b27d8b09bf73e3a44424695a41a2a85e027565560a9c3d4150e3"
PDF_2002_URL = (
    "https://web.archive.org/web/20040720164630if_/http://www.boe.ca.gov/annual/table10_02.pdf"
)
PDF_2002_YEAR = 2002
PDF_2002_UNIT_MULTIPLIER = 1_000  # Table 10 is printed "(In thousands of dollars)"
STATEWIDE_SUM_TOLERANCE = 0.005  # QA gate: county sum vs printed Totals row


def extract_ca() -> tuple[pd.DataFrame, ExtractionDiagnostics]:
    reject_non_county_source("county_aggregate")
    diagnostics = ExtractionDiagnostics(state="CA")
    raw = _load_or_download_ca(diagnostics)
    df = pd.DataFrame(raw)
    if df.empty:
        diagnostics.missing_sources.append("CA BOE OData returned no rows.")
        return _empty_ca(), diagnostics

    df = df[df["AssessmentYearFrom"].isin(YEARS)].copy()
    total_rows = df["County"].astype(str).str.strip().str.casefold().eq("total")
    if total_rows.any():
        diagnostics.notes.append(
            f"CA BOE source included {int(total_rows.sum())} statewide Total rows; these were excluded from the county panel."
        )
        df = df[~total_rows].copy()

    available_years = sorted(pd.to_numeric(df["AssessmentYearFrom"], errors="coerce").dropna().astype(int).unique())
    for year in YEARS:
        if year not in available_years:
            diagnostics.missing_sources.append(
                f"CA {year}: BOE Net Assessed Values by County endpoint has no county-level rows"
            )

    out = pd.DataFrame(
        {
            "state": "CA",
            "county_name": df["County"].astype(str).str.strip(),
            "year": pd.to_numeric(df["AssessmentYearFrom"], errors="coerce").astype("Int64"),
            "net_assessed_value": pd.to_numeric(df["TotalAssessedValue"], errors="coerce"),
        }
    )

    pdf_2002 = _extract_2002_pdf(diagnostics)
    if not pdf_2002.empty:
        out = pd.concat([out, pdf_2002], ignore_index=True, sort=False)

    for idx, row in out.iterrows():
        canonical, _, alias_note = normalize_county_name(row["county_name"], "CA")
        if canonical is None:
            diagnostics.fips_mismatches.append(f"CA unknown county: {row['county_name']}")
        else:
            out.at[idx, "county_name"] = canonical
        if alias_note:
            diagnostics.alias_mappings.add(alias_note)

    # Concordance: CA net assessed value (BOE Table 10) IS the base the 1% rate
    # applies to — the Brosy & Ferrero NAV concept carried as county_taxable_value.
    out["county_taxable_value"] = out["net_assessed_value"]

    return out, diagnostics


def _extract_2002_pdf(diagnostics: ExtractionDiagnostics) -> pd.DataFrame:
    if not PDF_2002_PATH.exists():
        diagnostics.missing_sources.append(
            f"CA 2002: BOE Table 10 PDF missing at {PDF_2002_PATH} (source: {PDF_2002_URL})"
        )
        return pd.DataFrame(columns=["state", "county_name", "year", "net_assessed_value"])

    digest = hashlib.sha256(PDF_2002_PATH.read_bytes()).hexdigest()
    if digest != PDF_2002_SHA256:
        raise RuntimeError(
            f"CA 2002: sha256 mismatch for {PDF_2002_PATH}: {digest} != pinned {PDF_2002_SHA256}"
        )
    diagnostics.files_reused.append(str(PDF_2002_PATH))

    text = _pdf_text(PDF_2002_PATH)
    values: dict[str, int] = {}
    statewide_printed: int | None = None
    aliases = sorted(county_lookup("CA").items(), key=lambda item: len(item[0]), reverse=True)
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        label = re.split(r"\.{2,}", stripped, 1)[0]
        label_key = re.sub(r"[^A-Za-z0-9]+", " ", label).strip().upper()
        money = re.findall(r"\d{1,3}(?:,\d{3})+|\d{4,}", stripped)
        if not money:
            continue
        # column 6 (total assessed value) is the last money figure on the row
        value = int(money[-1].replace(",", ""))
        if label_key == "TOTALS":
            statewide_printed = value
            continue
        for alias_key, (canonical, _) in aliases:
            if label_key == alias_key:
                if canonical not in values:
                    values[canonical] = value
                break

    if len(values) != 58:
        raise RuntimeError(f"CA 2002: parsed {len(values)} counties from Table 10, expected 58")
    if statewide_printed is None:
        raise RuntimeError("CA 2002: Totals row not found in Table 10")
    county_sum = sum(values.values())
    rel = abs(county_sum - statewide_printed) / statewide_printed
    if rel > STATEWIDE_SUM_TOLERANCE:
        raise RuntimeError(
            f"CA 2002: county sum {county_sum:,} vs printed Totals {statewide_printed:,} "
            f"differs by {rel:.4%} (> {STATEWIDE_SUM_TOLERANCE:.1%})"
        )
    diagnostics.notes.append(
        "CA 2002: parsed 58 counties from BOE Table 10 (2002-03 roll); source is in thousands "
        f"of dollars, converted x{PDF_2002_UNIT_MULTIPLIER} to nominal dollars (documented in "
        f"metadata/states/CA/source_inventory.yaml); county sum {county_sum:,} (thousands) vs "
        f"printed Totals {statewide_printed:,} (thousands), rel diff {rel:.6%}; sha256 verified."
    )

    return pd.DataFrame(
        {
            "state": "CA",
            "county_name": list(values),
            "year": PDF_2002_YEAR,
            "net_assessed_value": [v * PDF_2002_UNIT_MULTIPLIER for v in values.values()],
        }
    )


def _pdf_text(path: Path) -> str:
    if shutil.which("pdftotext"):
        return subprocess.run(
            ["pdftotext", "-layout", str(path), "-"],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        ).stdout

    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _load_or_download_ca(diagnostics: ExtractionDiagnostics) -> list[dict]:
    if RAW_PATH.exists():
        diagnostics.files_reused.append(str(RAW_PATH))
        return json.loads(RAW_PATH.read_text(encoding="utf-8")).get("value", [])

    try:
        response = requests.get(
            CA_API_URL,
            params={
                "$filter": f"AssessmentYearFrom ge {START_YEAR} and AssessmentYearFrom le {END_YEAR}",
                "$top": "5000",
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
        rows = data.get("value", [])
        RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
        RAW_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
        diagnostics.files_downloaded.append(str(RAW_PATH))
        return rows
    except Exception as exc:
        diagnostics.notes.append(f"CA remote download failed; attempting manual raw-file mode: {exc}")

    if RAW_PATH.exists():
        diagnostics.files_reused.append(str(RAW_PATH))
        return json.loads(RAW_PATH.read_text(encoding="utf-8")).get("value", [])

    raise RuntimeError(
        "CA BOE source could not be downloaded and no manual raw file exists at "
        f"{RAW_PATH}."
    )


def _empty_ca() -> pd.DataFrame:
    return pd.DataFrame(columns=["state", "county_name", "year", "net_assessed_value"])
