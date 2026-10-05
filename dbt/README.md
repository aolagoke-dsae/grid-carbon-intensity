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

`int_generation_gapfilled` was re-validated in DuckDB after the import against
the real DE-LU B15 series: 5 stated points expand to 96 rows, the value holds
to position 18 and changes at 19, daily total 1736.64 MWh against the Python
oracle's 1736.63. The 0.01 is float rounding.

## What deliberately did not come across

- **`monte_carlo.py`.** `src/transform/intensity.py` supersedes it. That module
  fits a **lognormal** where a factor band is strongly right-skewed — hydro at
  1 / 24 / 2200 — and a triangular only where the band is symmetric enough to
  justify one. The imported module sampled triangular for everything, which
  over that hydro range is not defensible. Sampling stays in one place, in Python.
- **The facts.** RUNBOOK Stage 6 specifies three facts; the import had one.
  The marts facts are left to that design rather than pre-empted.
- **A seed copy of the factor table.** `dim_production_type` reads
  `../config/ipcc_ar5_factors.csv` directly via `read_csv_auto`. One copy, in
  the same file `intensity.py` reads, so the SQL join and the Python interval
  cannot drift apart.
- **`sql/01_schema.sql`.** Untouched. RUNBOOK keeps it as portability evidence
  and the second dbt target at Stage 6b.

## Dormant

`tests/assert_deterministic_within_mc_interval.sql` is guarded with
`where false` until a fact carries both the deterministic value and the band.
Point it at that fact and delete the guard.

## Running it

```bash
pip install -r ../requirements.txt
cp profiles.example.yml ~/.dbt/profiles.yml   # edit the path
dbt deps && dbt build && dbt docs generate
```
