# Multi-state expansion plan for the FP measure

This document spans two repos. It lives here in **`Proptax_base`** (the repo that builds
the county property-tax base) but its purpose is the fiscal-pressure (FP) measure built
in the sibling repo **`migration_localtax`**, whose spec of record is
`migration_localtax/docs/empirical/fp_measure.md`. Paths below are prefixed with the repo
name wherever the file is not in `Proptax_base`.

This is the **general goal**: how the FL pilot becomes a multi-state and eventually
national FP panel, what property-tax-base data exists for 2002, and which phase we are in.

Status as of 2026-07-28: **Phase A complete** (FL + CA + WA + WI pooled regression).
Phases 0, B and C below are future work, not started.

---

## 1. Why the denominator is the binding constraint

`FP_{j,2002} = NetSpend_{j,2002} / Base_{j,2002}` where
`NetSpend = 1000 * (total_expenditure - total_ig_rev)` and `Base = county_taxable_value`.

- **Numerator: already national.** `migration_localtax/data/raw/county_year_tax_rev.csv`
  (Government Finance Database) covers 3,141 counties in 2002 and 3,139 in 2022, for the
  Census-of-Governments years {2002, 2007, 2012, 2017, 2022}.
- **Age structure: already national.** `migration_localtax/result/cohort_ssiv_county.csv`
  (3,146 counties, 51 states), `migration_localtax/data/raw/census_2000_county_pop.csv`,
  and `migration_localtax/data/raw/county_decadal_retiree_netmig_2000_2020.csv` all cover
  every state.
- **Denominator: state by state.** County-level taxable/market property value has no
  national source and must be built one state at a time **in this repo**, which emits one
  CSV per state at `data/states/<ST>/<st>_county_year_valuation_panel_2000_2022.csv` in a
  fixed 20-column schema (5 keys, 5 value concepts, 5 growth, 5 index columns; nominal
  dollars).

So expanding the FP measure = adding states to `Proptax_base`.

## 2. What 2002 county-level property-value data exists (survey, 2026-07-27)

**There is no national source.** The 2002 Census of Governments **dropped** the Volume 2
"Taxable Property Values and Assessment-Sales Price Ratios" series; the Census historical
data page lists it as ending in 1987 (a 1992 file exists at
`https://www2.census.gov/programs-surveys/apes/tables/gc92-2-1.pdf`). Every state must be
sourced from its own department of revenue / equalization agency.

### 2.1 Already built in this repo (8 states, all with 2002)

| State | 2002 concept in `county_taxable_value` | Also has | Scale |
| --- | --- | --- | --- |
| FL | Net taxable value after Save Our Homes cap + homestead exemptions (Brosy & Ferrero NAV) | `market_or_full_value` (just value), `school_taxable_value`; **2000–2022 all years** | taxable |
| CA | BOE net assessed value (Prop 13 acquisition value) | `net_assessed_value`; 2002 + 2013–2022 | **not market** |
| WA | Assessed value of all taxable property, 100% true & fair value (RCW 84.40.030) | — ; 2002 only | market |
| WI | Equalized (full) value excluding TIF | `market_or_full_value` (TID-in); 2002 only | market |
| AZ | Primary net assessed valuation (class ratios) | `net_assessed_value`; 2002 only | fractional |
| GA | Net county M&O digest (40% of FMV) | `assessed_value`; 2002 only | fractional |
| MN | Taxable net tax capacity (~1–2% of market value) | `market_or_full_value`, `net_assessed_value`; 2002 only | tax capacity |
| TX | *(none — deliberately)* | `market_or_full_value` only (100% market, Tax Code 23.01); 2002 only | market |

### 2.2 Confirmed 2002 documents located, not yet built

Live URLs verified 2026-07-27. These publish a genuine market/full/true value by county:

| State | Cnty | Agency & publication | Concept | Format |
| --- | --- | --- | --- | --- |
| **OR** | 36 | DOR *Oregon Property Tax Statistics FY 2002-03*, Table A.2 | Real Market Value | digital PDF |
| **NJ** | 21 | Div. of Taxation *Table of Equalized Valuations 2002* | Aggregate true value (real property); **county totals printed** | digital PDF |
| **UT** | 29 | Tax Commission *Annual Report FY2002-03* | Fair market value | PDF |
| **MT** | 56 | DOR *Biennial Report 2000-2002* | Market value | PDF |
| **NE** | 93 | Property Assessment Div. *2002 Annual Report* | Actual value | PDF |
| **KS** | 105 | PVD *2002 Statistical Report of Property Assessment and Taxation* | Appraised (market) value | PDF (scan risk) |
| **VA** | 134 | Dept. of Taxation *2002 Assessment/Sales Ratio Study* | Estimated true value of taxable real estate (agency-computed) | digital PDF |
| CO | 64 | Div. of Property Taxation *32nd Annual Report* | Actual value | 11 MB PDF, likely scanned |

Assessed/taxable-scale only (repo discipline stores values **as published** and never
divides by a statutory ratio to fabricate market value):

| State | Cnty | Concept | Note |
| --- | --- | --- | --- |
| OH | 88 | Assessed = 35% of true value | 2002 Annual Report, digital PDF |
| MI | 83 | SEV = 50% of true cash value | 83 separate per-county PDFs; the widely-available *Ad Valorem Levy Report* is capped Taxable Value, **not** market |
| NM | 33 | Net taxable = ⅓ of full value minus exemptions | DFA *County Net Taxable Values 1983–present*, **native Excel, all years** — the cheapest state to add |
| NC | 100 | Sales-assessment ratios only | needs pairing with the *Statistical Abstract of NC Taxes* for assessed value |

### 2.3 Likely exists, needs an archive request or a browser session

Each row lists the exact manual step. Files then go into `data/raw/<ST>/2002/` in this
repo (manual raw-file mode is supported) and a normal extractor is written against them.

| State | Cnty | What to get | Manual step |
| --- | --- | --- | --- |
| **PA** | 67 | State Tax Equalization Board (STEB) certified **county market values** — the single best concept match outside FL | Email `ra-stebweb@pa.gov` / DCED Tax Equalization Division for the 2002 certification, or pull PDE's 2002-03 Market Value/Personal Income Aid Ratio file which embeds STEB market values |
| **NY** | 62 | ORPS/ORPTS full value (assessed ÷ equalization rate) | Request the 2002 municipal equalization-rate + taxable full-value file from ORPTS, or check OSC's *Special Report on Municipal Affairs* FY2002 |
| **IL** | 102 | *Illinois Property Tax Statistics* EAV + final equalization factors + median assessment levels | The IDOR statistics page renders via JavaScript; download in a real browser or use the Wayback Machine on `revenue.state.il.us` |
| **AK** | ~27 | *Alaska Taxable 2002* full value determination | The DCRA site 403s automated fetches; download via browser from the Alaska Taxable Database. Boroughs/census areas ≠ counties — needs 2000-vintage FIPS |
| **MD** | 24 | SDAT assessable base (full cash value) | Maryland State Archives / SDAT assessable base reports |
| ME, NH | 16, 10 | State Valuation (ME) / DRA equalization survey (NH) — both states levy county taxes apportioned on equalized valuation, so printed county totals plausibly exist | Check the agency history pages; promote to a build if county rows are printed |
| TN, MO, OK, ID, WY, SD, ND, IA, KY, LA, AL, MS, AR, WV, IN, HI, SC, NV | — | Annual reports / ratio studies with county tables | Agency archive or state library request. Cross-cutting fallback: the Lincoln Institute *Significant Features of the Property Tax* legacy mirror, `lincolninst.edu/app/uploads/legacy-files/gwipp/upload/sources/<State>/<Year>/` |

### 2.4 Not usable as a county market-value base

- **MA, VT, CT, RI**: values are published by municipality/town only (MA DLS Equalized
  Valuations, VT PVR equalized education value, CT Equalized Net Grand List, RI full
  value). This repo rejects non-county sources and never self-aggregates municipalities.
  Only a printed county-total row would qualify (the WI precedent).
- **DE**: no state equalization; counties frozen at 1974/1983/1987 base years.
- **NV** improvements: replacement cost less statutory depreciation, not a market estimate.
- **CA**: Prop 13 acquisition value. Already in the repo but **must not be read as market
  value**; carry it with a state fixed effect and an exclusion robustness check.
- **IN**: 2002 is the transition year to market value-in-use; pre-2002 "true tax value"
  was a cost-schedule construct.

## 3. Phases

### Phase 0 — formal survey document (not started)

Write `data/doc/us_2002_market_value_availability.md` in this repo: all 50 states + DC in
one table (tier, concept, agency/publication, granularity, URL, target column, county
count, effort, blocker), per-state detail paragraphs, the manual-step appendix from §2.3,
and a column-coverage matrix telling `migration_localtax` which states can supply an FP
denominator. Keep it in `data/doc/` alongside this file and **not** in `reports/` —
`make clean` runs `find data/intermediate reports -type f -delete` and would erase it.

### Phase A — pooled regression on states already in hand (**complete**)

FL + CA + WA + WI = 236 counties. Built in
`migration_localtax/code/empirical/multistate/` (`ms_config.py`, `ms_data.py`,
`ms_fp.py`, `ms_fp_regression.py`, plus that folder's `README.md` for results and
run instructions).

The binding limitation found in this phase: **WA and WI have a 2002 base but no 2022
base**, so change-outcomes (`d_fp`, `policy_gap`, `d_log_fp`) are only computable for
FL + CA (125 counties); the other outcomes use all 236. Adding WA 2022 (DOR Property Tax
Statistics, taxes due 2023) and WI 2022 (DOR *Town, Village and City Taxes 2022*) to this
repo is a cheap, high-value follow-up — same agencies, same tables, one more year.

### Phase B — build the 7 confirmed market-value states (not started)

OR, NJ, UT, MT, NE, KS, VA in this repo, in that order (simplest table structure to
hardest geography). Per state, following the TX/WA precedent:

- `src/ptbase/extractors/states/<st>.py` — `extract_<st>()` returning
  `(df, ExtractionDiagnostics)`; must call `reject_non_county_source(...)`, sha256-pin the
  raw file, gate on expected county count and on statewide sum vs the printed total
  (≤0.5%), and degrade to an empty frame plus a `missing_sources` note when the raw file
  is absent. PDFs follow the `tx.py` `pdftotext -layout` block parser; spreadsheets follow
  `wa.py`.
- `metadata/states/<ST>/source_inventory.yaml` and `value_concordance.yaml` (every
  populated value column must appear as a `final_column_name` or validation fails).
- `tests/test_<st>.py` — pure parse-function tests on synthetic input, no network.
- Register in `cli.py` `EXTRACTORS`, `config.py` `EXPECTED_COUNTIES`, `reporting.py`
  `BOUNDARY_NOTES`; append rows to `metadata/shared/county_fips.csv` from
  `https://www2.census.gov/geo/docs/reference/codes/files/st<fips>_<st>_cou.txt`; update
  `README.md`.

State-specific gotchas found during the survey:

- **VA**: 134 county-equivalents = 95 counties + 39 independent cities. The `" city"`
  suffix is load-bearing (Richmond, Roanoke, Fairfax, Franklin, Bedford all exist as both
  a county and a city). Clifton Forge city reverted to a town inside Alleghany County on
  2001-07-01 and must not appear; Bedford city did the same on 2013-07-01, so its
  post-2012 rows stay structurally NaN.
- **CO**: Broomfield (08014) was created 2001-11-15 from parts of Adams, Boulder,
  Jefferson and Weld, so the county count goes 63 → 64 inside the panel window and
  Broomfield can never have a 2000 base (no growth/index values).
- **MT**: consolidated city-counties print as "Anaconda-Deer Lodge" (→ Deer Lodge, 30023)
  and "Butte-Silver Bow" (→ Silver Bow, 30093); add an alias block in
  `fips.county_lookup` following the FL pattern.
- **KS**: the source is served from a ContentDM digital repository with no stable
  filename; check the PDF text layer first — if it is image-only, do not OCR, demote the
  state to survey-only.
- **NE**: agricultural land was assessed at 80% of actual value in 2002 — record the scope
  in the concordance.
- **OR**: FY 2002-03 statistics describe the January 1, 2002 roll, i.e. panel year 2002.

Housekeeping to fix while in this repo: `reporting.py` hardcodes
"no unit conversion was applied" into every validation summary, which is already false
(CA 2002 and WA 2002 are ×1000); the README says `make all` builds "six state CSVs" (it
builds eight); `pyproject.toml` still describes the project as "for California and
Florida"; and `data/final/states/FL/fl_county_year_valuation_panel_2000_2020.csv` is a
stale artifact from an older vintage that nothing in the pipeline reads.

### Phase C — full merge and rerun (not started)

Extend the Phase A state list with whichever Phase B states populate a usable denominator,
then rerun the pipeline. Open design decision at that point: pool on the taxable base
where the concept is market-scale, or use `market_or_full_value` everywhere for
comparability, or report both as robustness. States that carry only `market_or_full_value`
(TX today; NJ and VA if their taxable-value tables are not added) can enter only the
market-value variant. The merged multi-state file lives in
`migration_localtax/data/interim/` — this repo bans combined multi-state files and its
`src/ptbase/validate.py` fails the build if one appears.

## 4. Denominator comparability (read before pooling)

The `county_taxable_value` column is not the same economic object in every state:

| State | What the 2002 base actually is | Comparable to FL? |
| --- | --- | --- |
| FL | Net taxable value after the Save Our Homes cap and homestead exemptions | reference |
| WA | 100% true & fair (market) value, no cap wedge | market-scale, wider base than FL |
| WI | Equalized full value excluding TIF | market-scale, wider base than FL |
| CA | Prop 13 acquisition value; drifts further below market the longer a parcel is held | **not market**; state FE + exclusion robustness |
| AZ, GA, MN | Fractional assessment (class ratios, 40% digest, net tax capacity) | **do not pool** |
| TX | No taxable value published at county level | market-value variant only |

Because the base differs in level, pooled FP levels differ mechanically across states.
Use state fixed effects, report per-state FP distributions, and treat cross-state level
comparisons as descriptive.
