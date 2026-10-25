# dbt layer

Imported 5 October 2026 from the parallel `capstone-loadshift` working copy,
which is now retired. **This repository is the single source of truth.**

## What is here

As of 25 October 2026:

| Layer | Files | What it does |
|---|---|---|
| `models/staging/` | 4 models, `_sources.yml`, `_models.yml` | 1:1 with the sources: rename, cast, resolve `position` to a timestamp. No business logic, per RUNBOOK Stage 6, except the one filter that cannot wait: `stg_entsoe__prices` keeps one of the two A44 curves (trap 5). `stg_entsoe__load` and `stg_entsoe__flows` are disabled until A65 and A11 are pulled. |
| `models/intermediate/` | 6 models, `_models.yml` | Traps 1, 2 and 4, where the lineage graph can show them: A03 carry-forward with A01 left empty, for generation and for prices; the direction split as a full outer join; MW to MWh. The steps a missing series leaves partial, the twin of `validate.incomplete_steps`. And `int_intensity_interval`, a Python model: each step's 5th, 50th and 95th percentile under the shared factor draws. |
| `models/marts/` | 4 dimensions, 3 facts, `_models.yml` | `dim_zone` and `dim_production_type` read `config/` in place. `dim_date` is a generated calendar holding the length of every local day (trap 3). `dim_factor_draw`, a Python model, holds the Monte Carlo draws of every priced factor that every step shares. `fact_generation` holds exactly the parser's rows with energy and emissions, `fact_intensity` the intensity of every generation step, the twin of Checkpoint 5, with its 90% interval, and `fact_price` one day-ahead price per step. Every fact row carries `source_sha256`, its retrieval's key in `raw/manifest.csv`. |
| `tests/` | 11 singular tests, plus 35 generic ones in the `_models.yml` files | Each encodes an error that yields a *plausible number* rather than a crash. |

## Checked against the Python parser

`src/transform/test_dbt_models.py` lands fixture payloads with
`xml_to_parquet.py`, builds every enabled model on them and compares the SQL
with `entsoe_parse.parse()` step by step: carry-forward, both transition days
(92 steps at PT15M, 25 at PT60M), a pump-only series, a series published only
while a unit runs, and both A44 curves; since 18 October 2026 also a series
stated net, one leg per hour, a day that changes resolution, and a series
exempt inside a window only. Since 25 October 2026 the facts too:
`fact_generation` must hold exactly the parsed rows, `fact_intensity` must
pass `check_stage5_intensity`, and `fact_price` must equal `parse_prices()`
expanded; `dim_factor_draw` must hold `intensity.shared_factor_draws` for
the project's seed, every reported interval must be its mix under those
draws (`check_stage6_marts`), and a point moved out of its interval must
fail `assert_deterministic_within_mc_interval`. A second build deletes one day, leaves one A01 position empty and
one retrieval out of the manifest, and the coverage test, the `not_null`
tests on `mw` and the manifest test must fail. CI runs it in the dbt job.
Until 17 October 2026 the only check was a manual one against the
five-point B15 series of the `test_parse.py` fixture, which had been
described as the real DE-LU series.

On the real 2021–2025 A75 and A44 pulls for DE-LU and France, `dbt build` is
green: 23 nodes, every test passing (18 October 2026, and again on 19 October
after lignite and hard coal took Itten et al.'s values); 53 with the facts on
25 October 2026, when `check_stage6_marts` found them equal to the parser and
to Checkpoint 5 in all ten zone-years (RUNBOOK Checkpoint 6), and 61 with the
interval the same day, the point inside it at every reported step.
The SQL coverage test and the Python `check_stage3_coverage` agree exactly:
with `config/source_gaps.csv` emptied, both report the same 101 short
day-series, and none with it.

## What deliberately did not come across

- **`monte_carlo.py`.** `src/transform/intensity.py` supersedes it. That module
  samples every factor from a two-piece lognormal that keeps the published
  median and keeps every draw inside the published band (method 2.0.0,
  17 October 2026). The imported module sampled a triangular for everything,
  which over the hydro range (1 / 24 / 2200) is not defensible. Sampling stays
  in one place, in Python.
- **The facts.** RUNBOOK Stage 6 specifies three facts; the import had one.
  The marts facts were left to that design rather than pre-empted, and built
  to it on 25 October 2026.
- **A seed copy of the factor table.** `dim_production_type` reads
  `config/ipcc_ar5_factors.csv` directly via `read_csv_auto`. One copy, in
  the same file `intensity.py` reads, so the SQL join and the Python interval
  cannot drift apart. `dim_zone` and the coverage test read `config/` the same
  way.
- **`sql/01_schema.sql`.** The T-SQL schema of the Azure excursion. Archived
  on 17 October 2026 in `archive/azure-excursion/`, with the excursion it was
  written for: DuckDB cannot run it.

## Two Python models

`dim_factor_draw` and `int_intensity_interval` run in Python inside
dbt-duckdb, because the sampling and the percentiles belong to
`src/transform/intensity.py` and nowhere else. They load that file by its
path under `GRID_ROOT`, as the SQL models read `config/`, and add nothing to
`sys.path`, since the repository root holds a folder named `dbt`. The draw
count and the seed are the project vars `mc_draws` (10,000, fixed by the rule
in RUNBOOK Stage 6) and `mc_seed`. The interval takes about a minute of a
build on the 2021–2025 data.

`tests/assert_deterministic_within_mc_interval.sql` was disabled until
25 October 2026, when `fact_intensity` came to carry both the point and the
band. Until 17 October 2026 it was a `where false` guard, which dbt reported
as a passing test although it tested nothing.

## Disabled

- `stg_entsoe__load` and `stg_entsoe__flows`, until `raw/parquet/a65.parquet`
  and `a11.parquet` exist. A view over a missing file fails when it is
  created, so `dbt build` could not go green on the data that does exist.

## Running it

Every path the models read (`raw/parquet/`, `config/`, `warehouse/`, and
`src/transform/intensity.py` for the two Python models) hangs off
the environment variable `GRID_ROOT`, the repository root. Its default, `..`,
is that root seen from `dbt/`. Until 17 October 2026 the paths were fixed
relative to `dbt/`, and a build from the root failed with "Cannot open file
…/warehouse/grid.duckdb".

```bash
pip install -r requirements.txt                 # from the repository root
python -m src.transform.xml_to_parquet          # lands raw/ into raw/parquet/
cp dbt/profiles.example.yml dbt/profiles.yml
mkdir -p warehouse

GRID_ROOT=. dbt build --project-dir dbt --profiles-dir dbt     # from the repository root
# PowerShell:  $env:GRID_ROOT = "."; dbt build --project-dir dbt --profiles-dir dbt
# or from dbt/, where GRID_ROOT defaults to "..":  dbt build --profiles-dir .
```

No `dbt deps`: the project uses no packages. `dbt_utils` was declared and
never used, so CI depended on hub.getdbt.com for nothing.

From a clean clone, without `raw/`, run
`python -m pytest src/transform/test_dbt_models.py`: it lands fixtures and
builds every model on them, as CI does.
