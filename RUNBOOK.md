# Project A — Build Runbook

**Grid Carbon Intensity & Load-Shift Optimiser**
Dr. Adewole Olagoke · started 7 August 2026 · runbook revised 17 October 2026
Gate: Stages 1–6 standing and the first defensible number by **26 November 2026**
Capstone: Stages 7–8 in Modul 10, the final-project block, **01.–11.12.2026**
Target: Stage 10 public during Modul IV, before **6 January 2027**

Ten stages. Each has a **checkpoint** that must pass before the next one starts.
The checkpoints exist because every stage here is one where a silent error
produces plausible-looking numbers rather than a crash.

The stack is defined in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); this
runbook is its instantiation for Project A.

---

## Where this actually stands

*Revised 7 October 2026. The table below used to say no git repository, empty
directories and nothing against the live API. All three were true on
25 September and none is true now. Updated 17 October 2026: the dbt row said
"no" while ten models existed, and the ENTSO-E row did not say that only A44
has been pulled.*

| | Written | Unit-tested | Run against real data |
|---|---|---|---|
| Ingestion client (ENTSO-E) | yes | token redaction, the append-only raw store, local-year windows | **A44 and A75** — A44 06.10.2026; A75 for DE-LU and FR, 2025 on 17.10.2026 and 2021–2024 on 18.10.2026; A65 not yet fetched |
| Ingestion client (SMARD) | yes | — | **yes** — 06.10.2026 |
| Parser, A75 (A03, direction, DST, MAW) | yes | yes; transition days since 17.10. | **yes** — DE-LU and FR 2021–2025, 17. and 18.10.2026 |
| Parser, A44 prices (trap 5) | yes | yes | **yes** — the 2025 DE-LU payload |
| Intensity + uncertainty | yes; method 2.0.0 since 17.10. | yes | the median-factor intensity of the 2021–2025 pulls, under the stage 5 check, 18.10.2026; the Monte Carlo interval and the fact table **not yet** |
| Stage checks (2, 3, 4, 5) | yes; 2 and 5 rewritten 17.10. so they can fail; 3 counts either leg and measures time since 18.10. | yes, each made to fail | **all four** on the 2021–2025 A75 pulls, 18.10.2026 |
| T-SQL schema + DQ views (Azure) | archived 17.10.2026 in `archive/azure-excursion/` | — | never: DuckDB cannot run them |
| dbt models | yes — 10 models (8 enabled), 7 singular tests (1 disabled), 9 generic | built on fixtures in CI and compared with the Python parser | **yes** — the 2021–2025 A75 and 2025 A44 data, 18.10.2026: 23 nodes green |
| CI | yes, `.github/workflows/pipeline.yml` | — | **yes**, green on 3.11 and 3.14 |
| Version control | yes — MIT; public from WE 3, 24./25.10.2026 | — | — |

`raw/` holds the A44 and A75 payloads and one SMARD week, all in `manifest.csv`.
`curated/` is still empty. `docs/` holds ARCHITECTURE.md and RESOURCES.md.

Three of the stage checkpoints could not pass on real data until 7 October:
Stage 2 compared a whole series against one period's step count, Stage 3 merged
zones into one key, and Stage 4 called `.get()` on a dataclass. All three are
fixed and carry regression tests. They are listed here because a checkpoint
that cannot fail is worse than no checkpoint — it sends you debugging a parser
that works.

---

## Pre-flight — already done

**RESTful API access was granted on 7 August 2026** (ticket #9465462,
transparency@entsoe.eu). Nothing is waiting on ENTSO-E.

One step remains and it takes minutes: log in to
<https://transparency.entsoe.eu/> → **My Account** → generate the security
token. Paste it into `.env`.

> The token goes into `.env` on your own machine and nowhere else. Never into
> the Greenbootcamps training environment, never into a shared lab, never into
> git. A token in git history is not removed by deleting the file.

**Published rate limit: 400 requests/minute per token.** Exceeding it returns
429 and a temporary ban that auto-clears in about 10 minutes. `SLEEP_SECONDS`
defaults to 1.5s — that is 40/minute, ten times under the limit. Leave it alone.

## Stack at a glance

| Layer | Tool | Cost | Expiry risk |
|---|---|---|---|
| Ingestion | Python + ENTSO-E API | €0 | none |
| Raw landing | local `raw/`, git-ignored; `manifest.csv` committed | €0 | none |
| Curated | Parquet in the repo | €0 | none |
| **Warehouse** | **DuckDB** | €0 | none |
| Transformation | **dbt-duckdb** — sources, staging, marts, tests, docs | €0 | none |
| Orchestration | **GitHub Actions** — free and uncapped on public repos | €0 | none |
| Publication | **Quarto → GitHub Pages** (static, permanent) | €0 | none |
| Uncertainty | **NumPy**, in `src/transform/intensity.py`, tested in CI | €0 | none |
| Environment | **VS Code** + dbt / Quarto extensions; `duckdb -ui` to inspect | €0 | none |
| *Dropped* | Azure SQL (free offer), Stage 6b — see **The gate**; archived in `archive/azure-excursion/`. Power BI is built on the exported Parquet instead | €0 | none |

Defined in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md). Tutorials,
reference repositories and data sources for each
layer are listed in [`docs/RESOURCES.md`](docs/RESOURCES.md), each tagged with
the stage it belongs to.

---

## Stage map

Targets rebased on 17 October 2026 on the running curriculum and the weekend
plan; see **Schedule against the curriculum** below.

| # | Stage | Produces | Cost | Target |
|---|---|---|---|---|
| 0 | Environment, secrets, git | first commit | €0 | done |
| 1 | First raw pull with manifest | `raw/A75/<eic>/2025/` | €0 | done — A44 06.10., A75 17.10.2026 |
| 2 | Parse: A03, direction, DST, MAW | parsed rows in memory | €0 | done — 17.10.2026 |
| 3 | Backfill and coverage | DE-LU and FR × 6 years in `raw/` | €0 | WE 2–3, by 25.10. |
| 4 | Emission factors verified | audited `ipcc_ar5_factors.csv` | €0 | WE 3, 24./25.10. |
| 5 | Deterministic intensity | a defensible number | €0 | WE 4, 31.10./01.11. |
| 6 | DuckDB warehouse + dbt | tested marts, lineage docs | €0 | WE 5–6, by 15.11. |
| 7 | Quality gate | every dbt test green on the backfill | €0 | Modul 10, 01.–11.12. |
| 8 | Monte Carlo and Sobol | 90% interval + drivers | €0 | Modul 10, 01.–11.12. |
| 9 | Orchestration (GitHub Actions) | unattended daily runs | €0 | Modul IV, from 14.12. |
| 10 | Publication (Quarto → Pages) | public URL + methodology | €0 | Modul IV, by 06.01.2027 |
| 6b | *Dropped:* Azure excursion | — | — | archived |

**Stages 0–9 are local and free.** The Azure excursion (Stage 6b) was dropped
in October 2026 and is archived in `archive/azure-excursion/`.

---

## Stage 0 — Environment, secrets, version control

**Needs:** nothing. The token already exists — generate it and paste it in.

```bash
cd grid-carbon-intensity
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # paste the real token when it arrives
git init && git add . && git commit -m "scaffold: ingestion, parser, intensity, checks, schema"
```

**Checkpoint 0**

```bash
python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); \
t=os.getenv('ENTSOE_TOKEN'); print('token loaded:', bool(t), '| length:', len(t or ''))"
git status --porcelain | grep -c '\.env$'    # must print 0
pytest -q                                     # 152 tests (131 functions), all green
                                              # 7 of them build the dbt models on
                                              # fixtures; 4 skip where raw/ is absent
```

- Token loads, and `.env` does **not** appear in git status
- The full suite passes before any live data exists. It should — every test
  runs on fixtures, which is why they were written that way.

**What it unlocks:** a real repository at `github.com/aolagoke-dsae`. Push it.
Since 6 October 2026 the profile holds the public EUDR validator; this
repository joins it at WE 3.

---

## Stage 1 — First raw pull with a manifest

**Needs:** Stage 0. One year, one zone. Nothing clever.

```python
import os
from dotenv import load_dotenv
from src.ingest.entsoe_client import generation_per_type
load_dotenv()
row = generation_per_type("10Y1001A1001A82H", 2025, os.environ["ENTSOE_TOKEN"])
print(row)
```

**Checkpoint 1**

- The new file in `raw/A75/10Y1001A1001A82H/2025/` is **more than 1 MB**
- Its `raw/manifest.csv` row has `http_status` 200, `rejected` 0 and a `revision`
- The `url` column contains `***REDACTED***` and not your token
- The first step is local midnight: for DE-LU 2025, 2024-12-31 23:00 UTC, and
  the last is 2025-12-31 22:45 UTC. Until 17 October 2026 the client asked for
  a UTC year, which cut the first hour off local 1 January (audit A5); the
  coverage check in Stage 3 flagged it as 92 of 96 steps
- Re-run it. The `sha256` WILL differ, and that is not a defect: ENTSO-E stamps every response with a fresh `mRID` and `createdDateTime`, so the manifest hash identifies the retrieval, not the data. Measured on 06.10.2026: two pulls of the identical query, 7,544,161 bytes both times, different hashes. What must be identical is the byte count and the point count; what signals an upstream revision is `revisionNumber`. See the README's provenance section.

**If it fails:** a row with `rejected` 1 points into the `_failed/` folder, and
nothing earlier in `raw/` was touched. A file of a few KB there is usually an
Acknowledgement document: open it, it states the rejection reason, usually a bad
EIC or an out-of-range period. A 401 means the token was refused.

**What it unlocks:** the first honest past-tense sentence on your CV.

---

## Stage 2 — Parse: A03 expansion and direction split

**Needs:** Stage 1. The parser is already written and handles four traps:

| Trap | What goes wrong without it |
|---|---|
| `curveType` A03 omits repeated values | A B15 series states **5 points for a 96-step day**. A naive loop emits 5 rows and silently loses 95% of the day. |
| `outBiddingZone_Domain` | Pumped-storage **consumption** appears in the same document as generation. Summing everything inflates the mix and corrupts the denominator. |
| `PT15M` | DE-LU is quarter-hourly. 96 steps/day, not 24. |
| Unit `MAW` | Power, not energy. MWh = MW × step_hours. |

```python
from src.transform.entsoe_parse import parse
from src.checks.validate import check_stage2_parse, check_stage2_direction
from pathlib import Path
newest = sorted(Path("raw/A75/10Y1001A1001A82H/2025").glob("*.xml"))[-1]   # latest retrieval
xml = newest.read_text(encoding="utf-8")
rows = parse(xml)
print(check_stage2_parse(rows))
print(check_stage2_direction(rows, xml))
```

**Checkpoint 2**

- Both checks return `True`. The direction check reads the XML a second time
  and compares, per zone, fuel and direction, the steps the elements declare
  with the rows. Expect consumption legs beyond pumped storage: the 2025 pulls
  carry B10, B16 and B19 consumption for DE-LU, and B05, B06, B10, B18, B19 and
  B25 for France. 2021–2024 add B06, B12 and B15 for DE-LU, and B12 for France,
  where RTE's hourly data until 18.12.2024 states pumped storage, reservoir
  hydro and coal net: one leg per hour, never both
- Hand-verify one A03 series: pick a `psr` with few stated points and confirm
  the value holds from its position until the next stated one
- `sum(r["mwh"] for r in rows if r["direction"]=="generation")` for one day
  lands in the low millions for DE-LU. Orders of magnitude out means a units error.

---

## Stage 3 — Backfill and coverage

**Needs:** Stage 2. Two zones (DE-LU and FR) × six years = **12 requests**,
because A75 permits a one-year range. Each request covers one *local* calendar
year, so consecutive years meet at local midnight and no hour arrives twice.

> Do **not** use documentType 16.1.A. That is per generation *unit* and limited
> to one day, which turns 30 requests into roughly 11,000.

```python
import csv, os
from dotenv import load_dotenv
from src.ingest.entsoe_client import generation_per_type
load_dotenv()
with open("config/zones.csv", newline="", encoding="utf-8") as fh:
    zones = [z for z in csv.DictReader(fh) if z["in_analysis"] == "yes"]   # DE_LU and FR
for z in zones:
    for year in range(2021, 2027):
        row = generation_per_type(z["eic"], year, os.environ["ENTSOE_TOKEN"])
        print(z["key"], year, row["http_status"], row["rejected"], row["bytes"])
```

The pauses between calls add 18 seconds; the downloads take most of the time,
since one DE-LU year is about 75 MB. Verify every EIC in
`config/zones.csv` against the Transparency Platform Area List before trusting it.

**Prices for the same years.** Decided 18.10.2026: the cost analysis covers the
years the intensity covers, so day-ahead prices (A44) are backfilled for both
zones as well. DE-LU 2025 is in since 06.10.2026; the rest is nine requests:

```python
from src.ingest.entsoe_client import day_ahead_prices
for z in zones:
    for year in range(2021, 2026):
        if z["key"] == "DE_LU" and year == 2025:
            continue                                   # pulled 06.10.2026
        row = day_ahead_prices(z["eic"], year, os.environ["ENTSOE_TOKEN"])
        print(z["key"], year, row["http_status"], row["rejected"], row["bytes"])
```

Land them with the A75 files (`python -m src.transform.xml_to_parquet`).
Whether the earlier years carry one price curve or two, as 2025 does (trap 5),
shows when they land: the curve filter in `stg_entsoe__prices.sql` counts the
curves per delivery period, and its two tests fail on anything it cannot place.

**Checkpoint 3**

```python
from src.checks.validate import check_stage3_coverage, load_coverage_policy
sparse, known = load_coverage_policy()
print(check_stage3_coverage(rows, "Europe/Berlin", sparse, known))
```

- Returns `True`. Every series is checked on every day, so a day with no rows
  at all is a gap too. A step counts if either leg reports it, and coverage is
  measured in time, so the day France moved from hourly to quarter-hour data
  (19.12.2024) is complete. A gap passes only if `config/sparse_series.csv`
  exempts its series on that day — on every day for French coal and battery
  storage, reported only while running; inside a window for German nuclear
  after 15.04.2023, German coal-derived gas before 2023 and French offshore
  wind before June 2023 — or if `config/source_gaps.csv` records it with the
  same size. The register holds 101 gaps for 2021–2025: DE-LU 3 in 2024 and 11
  in 2025; France 10 in 2022, 55 in 2023 (412 of their 454 hours in offshore
  wind's first weeks) and 22 in 2025, publication outages for the rest. A new gap, or a
  recorded one that changed size, fails: inspect it, then update the register
  in a commit of its own.
- The message names the DST days and shows them as **92 and 100 steps**, not as failures
- Every year present in `manifest.csv` with `rejected` 0

This is the checkpoint most worth getting right. Being able to say in an
interview that your pipeline distinguishes a 92-step spring-forward day from a
day with four missing quarter-hours is describing production experience rather
than a tutorial.

> `validate.expected_steps` returned 24 hours for every day of the year,
> including both transition days, until 17 September 2026. Python subtracts two
> aware datetimes sharing a `tzinfo` object by ignoring the offset, so the DST
> branch was dead code that read as correct. It had no test. It does now
> (`test_dst.py`, 6 tests). Do not remove them.

**What it unlocks:** real data for the Tableau module in October. Build that
dashboard on this data. A supplied training set produces a screenshot nobody clicks.

---

## Stage 4 — Emission factors and coverage

**Needs:** Stage 3. `config/ipcc_ar5_factors.csv` carries median, min, max, a
confidence flag and a citation per `psrType`. Six rows are deliberately
**unpriced**: B10 and B25 (pumped and battery storage, not generation), B15 and
B20 (composition undisclosed by ENTSO-E), B17 (waste, contested biogenic/fossil
split) and B06 (oil: AR5 has no oil row, and until 17 October 2026 it was
priced from a placeholder). B25 joined on 17 October 2026, when the first French
A75 pull reported battery storage and the stage 4 check failed on a fuel with
no row. Two priced rows are proxies, marked `low`: B03 (coal-derived gas) and
B02 (lignite), both on AR5's single coal row. Lignite plants generally emit
more per kWh than hard-coal plants, so the B02 proxy probably understates
DE-LU, where lignite was 15.3% of 2025 generation. `load_factors` refuses a
priced row whose source is a placeholder.

> **This is the stage that carries the whole project's credibility.** Open IPCC
> AR5 WG3 Annex III Table A.III.2 and verify every number in that CSV against
> the source. The values were populated from recall to get the code moving.
> Correct any that differ and update the `source` column. This is a checkpoint,
> not a suggestion.

**Checkpoint 4**

```python
from src.checks.validate import check_stage4_factors
print(check_stage4_factors(rows, factors))
```

- Returns `True` — every `psrType` in the data has a row, priced or explicitly flagged
- You have **personally** verified each published figure against Table A.III.2
- Priced share: unpriced fuels under **2%** of DE-LU energy. Higher means the
  unpriced categories are material and you must say so wherever intensity appears.
  Measured on the 2025 pulls (17.10.2026): **4.8% unpriced in DE-LU** (pumped
  storage 2.3, waste 1.3, oil 0.6, other 0.4, other renewable 0.2) and 2.3% in
  France. On 2021–2024 (18.10.2026) DE-LU is 4.4–5.1% in every year and France
  1.6–1.9%. The bar is not met in any year; from 2022 pumped storage alone
  exceeds it.
- **Decided 18.10.2026: accepted, and stated.** The bar stays the standard and
  stays unmet. Every intensity figure, in this repository, the report and the
  dashboard, carries the priced share of generation it rests on: DE-LU
  94.9–95.6% and France 97.7–98.5% across 2021–2025.

**What it unlocks:** the single strongest line for an MRV or assurance
audience — every factor traced by hand to a named table in a named annex.

---

## Stage 5 — Deterministic intensity

**Needs:** Stage 4. Energy-weighted, generation only, priced fuels only:

```
intensity(t) = Σ(mwh_f × ef_median_f) / Σ(mwh_f)     for priced f, direction='generation'
```

Import adjustment using cross-border physical flows (A11) can defer to v2 — but
say so in the README rather than leaving it implied.

**Checkpoint 5**

```python
from src.checks.validate import check_stage5_intensity, incomplete_steps, load_coverage_policy
from src.transform.intensity import deterministic_intensity, energy_by_fuel, load_factors
factors = load_factors("config/ipcc_ar5_factors.csv")
sparse, _ = load_coverage_policy()
partial = incomplete_steps(rows, sparse)        # a series missing: withhold the step
values = {k: None if k in partial else deterministic_intensity(mix, factors)
          for k, mix in energy_by_fuel(rows).items()}
print(check_stage5_intensity(rows, factors, values, sparse))
```

- Returns `True`. The check recomputes every step from the rows and the median
  factors, so MWh on one side of the ratio and MW on the other fails, and so
  does a value reported from a partial mix. Its predecessor bounded the values
  to 0–1000, which no units error leaves
- Range roughly **50–700 gCO2e/kWh** for DE-LU across a year
- Plot one week and look at it. Sunny summer midday low, still winter evening
  high. An inverted shape means a join error.
- Cross-check a handful of hours against an independent published series
  (Electricity Maps free tier). Expect a difference, but not from lifecycle
  versus combustion factors: Electricity Maps' default figures are life-cycle
  intensities too, of the consumed, flow-traced mix. The difference comes from
  imports and from the factor sets. **Document the difference and explain it.**
  That explanation is the single most impressive paragraph in the methodology
  document.
- Measured on the 2021–2025 pulls (18.10.2026), at median factors: DE-LU
  83–622 gCO2e/kWh per quarter-hour, yearly medians 356, 378, 315, 310 and 309;
  France 15–117 per step, medians 47, 70, 41, 28 and 27. Withheld, each at a
  recorded source gap: 10 and 31 quarter-hours in DE-LU in 2024 and 2025, and
  413 hours in France in 2023, most in offshore wind's first weeks. (The
  322 French quarter-hours withheld in 2025 until 18.10. were steps with a
  consumption leg only, counted as partial.) These figures cover the priced
  share of generation only, DE-LU 94.9–95.6% and France 97.7–98.5%
  (Checkpoint 4).

**This is the free/local gate.** Everything to here costs nothing. Nothing
after it should start until this passes.

---

## Stage 6 — DuckDB warehouse and dbt

**Needs:** Stage 5 passed. **Cost: €0.** No account, no provisioning.

The project exists in `dbt/` and needs no `dbt init` (which would scaffold a
second project). Every path its models read hangs off `GRID_ROOT`, the
repository root, which defaults to `..`, the root seen from `dbt/`.

```bash
python -m src.transform.xml_to_parquet          # land raw/ into raw/parquet/
cp dbt/profiles.example.yml dbt/profiles.yml
mkdir -p warehouse
GRID_ROOT=. dbt build --project-dir dbt --profiles-dir dbt     # from the repository root
# PowerShell:  $env:GRID_ROOT = "."; dbt build --project-dir dbt --profiles-dir dbt
# or from dbt/, where GRID_ROOT defaults to "..":  dbt build --profiles-dir .
```

**Inspecting the warehouse.** `duckdb -ui` opens a local UI on
`localhost:4213`. Attach **read-only** —
`ATTACH 'warehouse/grid.duckdb' AS grid (READ_ONLY);` — because DuckDB allows
one process read-write *or* many read-only. A UI holding the file read-write
makes the next `dbt build` fail. Full note in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Four layers: declared sources → 1:1 staging → intermediate models carrying
the business logic (directional split, factor join, DST-aware coverage) →
marts exposing three conformed dimensions and three facts. Every model
documented. Nothing bypasses a source declaration. The sources carry no
freshness block: the landed columns are delivery periods, not load times.

Standing on 17 October 2026: staging, the three intermediate models and the
three dimensions, built green on the 2025 data. The facts are this stage's
work. The T-SQL schema written for the Azure excursion is archived in
`archive/azure-excursion/`; DuckDB cannot run it.

**Checkpoint 6**

- `dbt build` green; `dbt docs generate` produces a lineage graph
- Mart row count equals the parsed row count **exactly**
- Every fact row resolves to its retrieval in the ingest manifest: every
  landed row carries `source_sha256`, and the intermediate models pass it on
- `select count(*) from main_marts.dim_production_type where ef_source_citation is null or trim(ef_source_citation) = ''`
  returns 0, and so does
  `select count(*) from main_marts.dim_production_type where is_priced and lower(ef_source_citation) like '%placeholder%'`.
  Until 17 October 2026 the first query named the wrong schema and would have
  passed oil's placeholder anyway
- `git clone` + `dbt build` reproduces the warehouse from scratch on a machine
  that has never seen the project. That is the property the whole standard exists for.

---

## Stage 7 — Quality gate

**Needs:** Stage 6. **Cost: €0.**

Generic tests (`unique`, `not_null`, `relationships`, `accepted_values`) on
every grain, plus four singular tests that encode the domain:

1. Step coverage distinguishing a genuine gap from a 92- or 100-step DST day —
   `assert_step_count_per_local_day`, built
2. The direction split, losing nothing and mixing nothing —
   `assert_no_consumption_in_generation_total`, built
3. Priced-fuel coverage threshold below which a figure is withheld — with the fact
4. The intensity recomputed from the mix, the SQL twin of
   `check_stage5_intensity` — with the fact. Not a plausibility band: no units
   error leaves one

**Checkpoint 7**

- All dbt tests pass
- `assert_step_count_per_local_day` returns no rows, and `dim_date` marks one
  23-hour and one 25-hour day per year per zone (`is_dst_transition`). The test
  reads the same exemptions as `check_stage3_coverage`, and on the 2021–2025
  pulls the two agree exactly: with the register emptied, both report the same
  101 gaps (18.10.2026)
- Unmapped fuels returns only the six deliberately unpriced categories
- **Break one on purpose.** Delete a day from a staging model and confirm the
  coverage test fails loudly. A test you have not seen fail is a test you do
  not know works. Until 17 October 2026 this one would have passed: it
  counted only the days that had rows. `test_dbt_models.py` now deletes a day
  on fixtures in every CI run.

---

## Stage 8 — Monte Carlo and Sobol

**Needs:** Stage 7. **Cost: €0.** 10,000 draws per step, sampling each fuel's
factor across its published range. The propagation and the first-order shares
already exist in NumPy (`src/transform/intensity.py`) and run in CI with
everything else. What this stage adds is the Sobol analysis of the saving
itself, where load, price and intensity interact.

The sampling rule is implemented and worth stating in interviews. AR5 gives
min / median / max per fuel, and most bands reach much further above the median
than below it (nuclear 3.7 / 12 / 110, hydropower 1 / 24 / 2200). Each factor
is sampled from a **two-piece lognormal**: the published median stays the
median, min and max sit at the 2.5th and 97.5th percentiles, and every draw
stays inside the band. A triangular with the median as its mode — the default
until 17 October 2026 — moves the median of a skewed band (nuclear's to 37.7)
and pushed the deterministic point outside its interval on nuclear-heavy mixes.
`describe_sampling()` lists the fitted spreads per fuel.

**Checkpoint 8**

- The deterministic point (every fuel at its median factor) falls **inside**
  the resulting 90% interval. If it does not, the sampling is biased.
- Re-run with 20,000 draws: interval bounds move less than 1%. That is
  convergence and you should be able to state it.
- Sobol indices sum to approximately 1 and name a dominant driver. Do not
  expect it to be coal: coal's AR5 band (740–910) is the narrowest of any fuel.
  A fuel's share grows with its energy share squared and with its band's
  spread, so gas, biomass or even a small hydro share can lead. Read the width
  share beside the variance share before naming the driver.

---

## Stage 9 — Orchestration with GitHub Actions

**Needs:** Stage 8. **Cost: €0** — Actions is free with no minute cap on public
repositories using standard runners.

Today `pipeline.yml` runs `pytest` on Python 3.11 and 3.14, parses the dbt
project and builds it on fixtures, on every push and weekly. This stage turns
it into two workflows:

- **`ci.yml`** — on every pull request: `pytest`, then `dbt build`. The green
  check on the repository page is evidence nobody can fabricate.
- **`refresh.yml`** — scheduled 06:00 UTC: ingest → validate manifest →
  transform → `dbt build` → render Quarto → publish. Token from repository
  secrets, never hard-coded.

**Checkpoint 9**

- Two consecutive unattended successful scheduled runs on consecutive days
- CI blocks a pull request that breaks a dbt test — open one deliberately and
  watch it go red
- **Break it on purpose:** revoke the repository secret, confirm the run fails
  **loudly and notifies**, restore it. A pipeline that fails silently is worse
  than no pipeline, and you cannot claim it alerts until you have watched it alert.

> Scheduled workflows in a public repo are disabled after roughly 60 days of
> repository inactivity. Commit something periodically.

---

## Stage 10 — Publication

**Needs:** Stage 9. **Cost: €0.**

**Primary: Quarto → GitHub Pages.** Static, permanent, no licence, no expiry,
and you already know Quarto from the R work so it costs no learning hours. The
site renders from the marts and republishes on every scheduled run.

**Secondary: Tableau Public.** A hand-built dashboard on a Parquet extract.
Tableau Public cannot connect to a live database and publishes everything
openly, which is fine here — the data is open. Build it during the October
Tableau module, on this data rather than a supplied training set.

**Checkpoint 10**

- GitHub Pages URL opens from a signed-out browser
- README opens with a **screenshot**, not a folder tree
- `docs/METHODOLOGY.md` written: sources, factor table with citations, the
  A03/DST/direction handling, the sampling-rule decision, the uncertainty
  method, and the known limitations (no import adjustment yet, six unpriced
  fuel categories, the lignite proxy)
- Once you have 30+ consecutive green scheduled runs, screenshot the Actions
  history and put it near the top of the README. That image is worth more than
  any certificate, because it proves the thing ran without you.

---

## Stage 6b — Azure and Power BI excursion (dropped)

*Dropped from the capstone in October 2026 — see **The gate**. Power BI is
built on the exported Parquet instead.* The procedure, its checkpoint and the
T-SQL it would have run are archived in
[`archive/azure-excursion/`](archive/azure-excursion/README.md). The T-SQL
runs nowhere: DuckDB stops at `CREATE OR ALTER`, and Azure SQL would need
Windows time-zone names.

---

## Schedule against the curriculum

Rebased on 17 October 2026 on the running curriculum and on the weekend plan
decided on 5 October 2026: eight weekends, then Modul 10. Until then this
section followed the Maßnahmebogen, the funding document, which dates the end
of the course differently. Where the two disagree, the curriculum is what is
taught and governs this plan:

| | Maßnahmebogen | Curriculum |
|---|---|---|
| Final project | Abschlussprojekt 27.11.–04.12., 54 UE | Modul 10, 01.–11.12., 9 teaching days, 81 hours |
| Modul II ends | 04.12.2026 | 11.12.2026 |
| Modul IV | 05.12.2026–05.01.2027, 135 UE | 14.12.2026–06.01.2027, 16 teaching days |
| Machine Learning | 29.10.–09.11. | 09.–18.11. |

The right-hand column below is what exists in the repository at the end of
each block.

| When | Course alongside | Runbook work |
|---|---|---|
| WE 2, 17./18.10. | Modul 4a, SQL | **Stage 3.** Backfill DE-LU and FR, coverage checked per year |
| WE 3, 24./25.10. | Modul 4b, Tableau | **Stage 4.** Every factor checked by hand against AR5 Table A.III.2. Repository public |
| WE 4, 31.10./01.11. | Modul 5a, Tableau LOD | **Stage 5.** The deterministic intensity on the backfill; Checkpoint 5 |
| WE 5, 07./08.11. | Power BI; DAX into late November | **Stage 6.** The intensity model and the facts in dbt |
| WE 6, 14./15.11. | Modul 6, Machine Learning | **Stage 6.** The intensity fact with a first Monte Carlo interval: the first defensible number |
| WE 7, 21./22.11. | Modul 7, DAX and APIs | One Power BI page showing that number, read from the `exports/` Parquet; README draft |
| WE 8, 28./29.11. | Modul 9, Green IT | Buffer. The marginal-versus-average intensity section, the limitation an experienced interviewer opens first. A one-page work plan for Modul 10 |
| **01.–11.12.** | **Modul 10, final project** | **Stages 7 and 8.** Every dbt test green on the backfill; the decision model with Monte Carlo and Sobol, reproducible with a fixed seed; the ML part on this data, baseline **first** (seasonal naive, same weekday last week; if the model loses to it, document that), then the price-spread forecast; Power BI pages 2 and 3, measures in DAX rather than precomputed in Power Query; README, lineage screenshot, `BENCHMARKS.md`. Submission |
| 12./13.12. | — | All repositories public; README and lineage checked |
| **14.12.–06.01.** | **Modul IV** — PSM I, Praktikumsgespräche | **Stages 9 and 10** in the margin; PL-300 between 14 and 23 December |

### The gate

**By 26 November: Stages 1–6 standing and the first defensible number.** On
1 December the data must be in, the parser running and the dbt project
standing, so that Modul 10's 81 hours go to analysis rather than setup. Until
17 October 2026 this runbook put Stages 1–8 before 26 November, because the
Maßnahmebogen has no Modul 10 and treats 27.11.–04.12. as consolidation. The
curriculum gives the final project nine teaching days of its own.

**Stages 7 and 8 belong to Modul 10**, and the capstone is submitted at its
end, 11 December.

**Stages 9 and 10 have no course slot.** Orchestration and publication happen
in Modul IV alongside PSM I and the placement interviews, and 21–24 and 28–31
December are teaching days: there is no Christmas window. Budget for that now
rather than discovering it in December.

**DP-600 and the Azure excursion are dropped.** Fabric requires a work or school tenant, and the certification targets platform operations rather than inference. The hours go to the causal module and the GenAI extraction artifact instead.

### Why the gate stays at 26 November

Modul 10 only works if it starts sharp on 1 December. Nine supervised days are
enough to finish an analysis, not to build ingestion. The weekends to
22 November carry the setup, and WE 8 is buffer: if two weekends are lost, the
plan still holds.

The portfolio has to be presentable by mid-December, when Modul IV and the
placement conversations begin. Their exact window is still to be confirmed
against the curriculum.

PL-300 moved to 14–23 December 2026: DAX is taught into late November.

Reliable Power BI path: dbt writes the mart tables to `exports/` as Parquet and
Power BI Desktop reads that folder. The DuckDB ODBC route works but carries a
risk on a submission day that nobody needs.

Build on your own machine and accounts, not the school's: its access ends with
the course.

## Honesty rules for this repo

1. The README states what is real and what is not. Everything here uses real
   ENTSO-E data — say so plainly, and say equally plainly that the facility load
   profile in the optimiser is illustrative.
2. **Do not update the CV to claim Azure or Power BI until Stage 10 passes.**
   All CV variants currently carry these under "in progress" / "Im Aufbau" —
   move them up only when a public URL exists.
3. Provenance is a column. `ef_source_citation` is NOT NULL for a reason.
4. If you cannot explain a number, do not publish it.
5. Status labels in the CV project block track this document. `written` means
   the code exists. `run` means a checkpoint passed. Nothing is described as
   operational before Stage 10.
6. Dates in this header are targets, not claims. When one slips, update it here the same day.
