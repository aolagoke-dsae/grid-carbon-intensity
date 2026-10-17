# dbt layer

Imported 5 October 2026 from the parallel `capstone-loadshift` working copy,
which is now retired. **This repository is the single source of truth.**

## What came across

| Layer | Files | Why |
|---|---|---|
| `models/staging/` | 4 models + `_sources.yml` | 1:1 with the sources. Rename, cast, resolve `position` to a timestamp. No business logic, per RUNBOOK Stage 6. |
| `models/intermediate/` | 3 models | The four traps, where the lineage graph can show them. |
| `models/marts/` | 3 conformed dimensions | Matches the Stage 6 spec. |
| `tests/` | 4 singular tests | Each encodes an error that yields a *plausible number* rather than a crash. |

`int_generation_gapfilled` was checked in DuckDB after the import against the
five-point B15 series in the `test_parse.py` fixture. That series was lifted
from a DE-LU payload of August 2026; it is not an A75 pull of this repository,
which has none yet. 5 stated points expand to 96 rows, the value holds to
position 18 and changes at 19, and the daily total is 1736.635 MWh, the figure
the Python parser's test asserts.

*Corrected 17 October 2026. This paragraph used to call the fixture "the real
DE-LU B15 series" and to compare 1736.64 with 1736.63, which are two roundings
of the same 1736.635.*

## What deliberately did not come across

- **`monte_carlo.py`.** `src/transform/intensity.py` supersedes it. That module
  samples every factor from a two-piece lognormal that keeps the published
  median and keeps every draw inside the published band (method 2.0.0,
  17 October 2026). The imported module sampled a triangular for everything,
  which over the hydro range (1 / 24 / 2200) is not defensible. Sampling stays
  in one place, in Python.
- **The facts.** RUNBOOK Stage 6 specifies three facts; the import had one.
  The marts facts are left to that design rather than pre-empted.
- **A seed copy of the factor table.** `dim_production_type` reads
  `../config/ipcc_ar5_factors.csv` directly via `read_csv_auto`. One copy, in
  the same file `intensity.py` reads, so the SQL join and the Python interval
  cannot drift apart.
- **`sql/01_schema.sql`.** Untouched. RUNBOOK keeps it as portability evidence
  and the second dbt target at Stage 6b.

## Disabled

`tests/assert_deterministic_within_mc_interval.sql` is disabled with
`config(enabled = false)` until a fact carries both the deterministic value and
the band. Until 17 October 2026 it was a `where false` guard, which dbt
reported as a passing test although it tested nothing. When the fact exists,
point the query at it and remove the config line. The criterion itself is
already tested in Python (`src/transform/test_intensity.py`).

## Running it

Run it from `dbt/`: the models read `../raw/parquet` and `../config`
relative to this folder.

```bash
pip install -r ../requirements.txt
cp profiles.example.yml ~/.dbt/profiles.yml   # edit the path
dbt deps && dbt parse
```

`dbt build` needs landed data. From a clean clone only `dbt parse` succeeds.
With the A44 payload landed, `dbt build --select stg_entsoe__prices` builds
that model and runs its two tests; the rest waits for A75 (see the main README).
