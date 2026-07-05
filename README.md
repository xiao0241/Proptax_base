# State-Specific County-Level Official Property Tax Valuation Panels

This repository builds a reproducible Python ETL pipeline for official county-level property tax valuation panels, tax/roll years 2000-2022. Current states: **AZ, CA, FL, GA, MN, WI**. FL and CA carry multi-year coverage; AZ, GA, MN, and WI currently carry the 2002 cross-section (the Brosy & Ferrero-style NAV baseline year), with the panel skeleton in place for later years.

The scope is intentionally narrow. The final deliverables are separate state panels, not a combined multi-state file or national panel:

- `data/states/<ST>/<st>_county_year_valuation_panel_2000_2022.csv` (one per state)

Final CSVs exclude source metadata columns so the analytic county-year panel contains only identifiers and property-tax valuation result variables. Source titles, URLs, sha256 pins, extraction notes, and valuation concordances live in `metadata/` and `reports/validation_summary.md`.

## The county_taxable_value concordance

Every state maps its official **net taxable assessed value (NAV)** concept — the base mill rates actually apply to, after assessment caps and exemptions (Brosy & Ferrero, *Property Taxes and the Great Recession*, Lincoln Institute WP 2025) — into the analytic column `county_taxable_value`, documented per state in `metadata/states/<ST>/value_concordance.yaml`:

| State | county_taxable_value concept | Scale caveat |
| --- | --- | --- |
| AZ | Primary net assessed valuation (DOR Annual Report Table 36) | class-ratio-scaled base |
| CA | BOE Table 10 net assessed value (net of "all other" exemptions, incl. homeowners' exemption) | ~full value |
| FL | DOR County Taxable Value (post-Save Our Homes, post-exemptions) | ~full value |
| GA | Net county M&O digest (district 0 of the consolidated digest) | 40%-of-FMV base |
| MN | Taxable net tax capacity (bulletin Table 32 col 5; assessment year = panel year) | classified-rate base, ~1-2% of market value |
| WI | Equalized value excluding TIF (TID-out; county-levy apportionment base) | full market value |

Scales differ by design — NAV is whatever base the state's rates apply to. For market-value-scale comparisons use `market_or_full_value` where populated (FL, MN, WI). Distinct bases are never collapsed: e.g. AZ secondary NAV, GA school/state digests, and FL school taxable value are documented but never substituted.

## Official Sources (per state)

Full provenance (URLs, sha256, units, cross-checks) is in `metadata/states/<ST>/source_inventory.yaml`. Summary:

- **AZ 2002**: DOR 2002 Annual Report Table 36 (TY2002 primary NAV by county); cross-checked against the 2003 Annual Report (identical in every county).
- **CA**: BOE Data Portal OData `Net_Assessed_Values_by_County` (2013-2022) plus the FY 2001-02 Annual Report Table 10 PDF for the 2002-03 roll (via Wayback; **printed in thousands of dollars, converted x1000** — the only unit conversion in the repo). Cross-checked against the FY 2002-03 report's revised statewide figure (+0.008%).
- **FL**: DOR Ad Valorem Valuation and Tax Data Book — county-level Excel workbooks (2010+) and historical Data Book PDFs (2000-2009); Just/Assessed/County Taxable/School Taxable values kept as separate concepts. The 2002 denominator is independently re-verified by `src/ptbase/qa/reconcile_fl_2002.py`.
- **GA 2002**: DOR County Ad Valorem Tax Digest Consolidated Summaries workbook (via georgiadata.org); district-0 net M&O digest; gross-minus-exemptions identity holds exactly; cross-checked against the FY2003 Statistical Report (0.06% on the reconciled state-digest concept).
- **MN 2002**: DOR "Property Taxes Levied in Minnesota, Taxes Payable 2003" bulletin — MN's assessment year 2002 (Jan 2, 2002 valuation): Table 32 net tax capacity concepts and Table 28 taxable market value; all three statewide sums reconcile exactly; cross-checked against the payable-2004 bulletin.
- **WI 2002**: DOR "Town, Village and City Taxes 2002" bulletin county TOTAL rows (TID-in and TID-out equalized values, via Wayback); cross-checked against the DOR Aug 2002 news release (all 72 counties identical) and per-county Bureau of Equalization apportionment reports (exact).

For PDF sources the parsers use Poppler `pdftotext -layout` (fixed-width tables), falling back to `pypdf`. Every PDF/workbook source is sha256-pinned in its extractor; a hash mismatch fails the build.

## Schema And Units

All final CSVs use the same columns in the same order. Valuation amounts are nominal dollars. One source requires a unit conversion — CA 2002 (thousands to dollars, x1000) — documented in the CA metadata and the validation summary extractor notes; all other sources are already in dollars.

The panel year is interpreted as the valuation/assessment year determined in that calendar year:

- AZ: DOR "Tax Year" (2002)
- CA: BOE `AssessmentYearFrom` / roll year (2002-03 roll = 2002)
- FL: official Data Book roll/report year
- GA: digest tax year
- MN: assessment year (Jan 2 valuation; published in the payable-(year+1) bulletin)
- WI: assessment year (Jan 1 valuation)

Growth and index columns are computed within county FIPS using the same measure's positive nonmissing year-2000 value. Missing base values are not interpolated or replaced with state averages (states with only 2002 populated therefore carry no growth/index values).

## Geography And Boundaries

County FIPS is the primary geographic key (`metadata/shared/county_fips.csv`: AZ 15, CA 58, FL 67, GA 159, MN 87, WI 72). Source aliases (FL `Dade` -> Miami-Dade 12086; MN bulletin spellings `Ottertail`/`Watowan`/`Wilken` -> Otter Tail/Watonwan/Wilkin) are normalized and logged in the validation summary. Boundary review found no county creation, deletion, split, consolidation, or FIPS change affecting any of the six states during 2000-2022.

## Non-County Sources

The pipeline only accepts official already-aggregated county-level summaries. It does not use parcel-level data and does not aggregate taxing districts, school districts, special districts, municipalities, tax-rate areas, levy areas, or revenue districts into counties. (GA district-0 digest rows and WI county TOTAL rows are official county aggregates printed in the source, not aggregations performed here.)

No Zillow, ACS housing values, Census housing values, commercial estimates, demographic variables, tax revenue, millage rates, or tax-revenue-imputed valuations are used.

## Run

```bash
python -m pip install -e ".[dev]"
make all    # builds the six state CSVs and reports/validation_summary.md
make test
```

FL 2002 provenance/reconciliation report (sha256 gate, independent Table 27 re-parse, per-county diffs):

```bash
PYTHONPATH=src python3 -m ptbase.qa.reconcile_fl_2002
```

## Manual Raw-File Mode

If an official remote source cannot be downloaded, place the official files under the expected raw folders and rerun the pipeline:

- AZ: `data/raw/AZ/2002/REPORTS_ANNUAL_2002_ASSETS_fy02_annual_report.pdf`
- CA: `data/raw/CA/boe_net_assessed_values_by_county.json` (OData) and `data/raw/CA/2002/table10_02.pdf`
- FL: `data/raw/FL/<year>/` (Data Book PDFs 2000-2009, measure workbooks 2010+)
- GA: `data/raw/GA/2002/2002_digest.xlsx`
- MN: `data/raw/MN/2002/ptbulletin_03.pdf`
- WI: `data/raw/WI/2002/tvc02.pdf`

The pipeline does not fake successful downloads, generate synthetic valuation data, interpolate missing years, or infer valuation from tax revenue or millage rates. The 2002 PDF/workbook sources are sha256-pinned, so substituting a different file version fails loudly.

## Adding Future States (or years)

Add a state extractor under `src/ptbase/extractors/states/` and register it in `src/ptbase/cli.py` `EXTRACTORS`; add county FIPS rows to `metadata/shared/county_fips.csv` and the expected count to `EXPECTED_COUNTIES` in `src/ptbase/config.py`; add source inventory plus value concordance YAML under `metadata/states/<STATE>/`. New sources must be official county-level summaries and must map official valuation concepts into the existing wide schema without collapsing distinct tax bases into a generic valuation column. Every extraction must pass the QA gates: pinned sha256, expected county count, and a statewide-sum check against the printed total (0.5% tolerance), plus an independent second-source cross-check recorded in the source inventory.
