# Grid Carbon Intensity & Load-Shift Optimiser

Hourly-and-quarter-hourly carbon intensity for two European bidding zones,
DE-LU and FR,
**derived** from ENTSO-E generation mix using IPCC AR5 lifecycle factors rather
than consumed from a vendor — with the published factor uncertainty propagated
through to a 90% interval by Monte Carlo and the variance attributed to its
sources by Sobol indices, and a load-shifting optimiser that prices the saving
in tCO2e and euros.

> **Status: in build (started 7 August 2026).** See `RUNBOOK.md` for the staged
> plan and current position. Nothing in this repository is presented as
> operational until Stage 10 passes.

## Stack

Open-access end to end, by design. Python ingestion → immutable raw layer with a
SHA-256 manifest → Parquet → **DuckDB** warehouse → **dbt** (sources, staging,
intermediate, marts, tests, lineage), with **GitHub Actions** for CI and a
**Quarto** report to follow. Uncertainty propagation and global sensitivity
analysis in R (`sensitivity`).

The ingestion, parsing and uncertainty layers are written and tested. The dbt
project, the CI workflows and the report are specified in `RUNBOOK.md` and not
yet built — the Layout below marks which is which.

The acceptance criterion that governs the whole build: **the deterministic point
estimate must fall inside its own 90% interval.** If it does not, the model is
wrong somewhere and no figure is published.

No subscription, no licence and no free tier is required to run any of it:
`git clone` then `dbt build` reproduces the warehouse from scratch. Azure SQL
and Power BI appear once, as a bounded portability excursion (RUNBOOK Stage 6b),
and the artefacts from it — `.pbix` and `.bacpac` — are committed as files.

The architecture is defined once in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
and shared with the Sentinel-2 biomass MRV and German data-role market projects.

## Data provenance

| Source | Used for | Access |
|---|---|---|
| ENTSO-E Transparency Platform | Actual generation per production type (A75), day-ahead prices (A44), actual load (A65), cross-border flows (A11) | REST API, token |
| IPCC AR5 WG3 Annex III | Lifecycle emission factors with published ranges | `config/ipcc_ar5_factors.csv` |
| DWD Open Data | Hourly temperature | Open, no key |
| EEA EU ETS data viewer | Installation-level verified emissions, for benchmarking | Open |

All grid, price and factor data are real and cited. Where a facility load
profile is used in the optimiser it is **illustrative and labelled as such**.

## What is non-obvious in this data

Four things in the real ENTSO-E payload that a naive parser gets wrong, all
handled in `src/transform/entsoe_parse.py` and asserted in `test_parse.py`:

1. **`curveType` A03 omits repeated values.** One DE-LU series states 5 points
   for a 96-step day; the other 91 must be carried forward. A naive loop loses
   95% of that day with no error raised.
2. **`outBiddingZone_Domain` is consumption.** Pumped storage appears twice in
   the same document — once generating, once pumping. Summing both inflates the
   mix and corrupts the intensity denominator.
3. **DE-LU publishes at PT15M.** 96 steps per day, so daylight-saving days have
   **92 and 100** steps, not 23 and 25.
4. **The unit is MAW — power, not energy.** MWh = MW × step_hours, which matters
   as soon as zones at different resolutions are combined.

## The interval is the deliverable

A carbon intensity quoted as a single number is a number nobody can audit.
AR5 publishes a *range* per fuel, so `src/transform/intensity.py` samples each
factor and reports the median with a 90% interval, the share of the hour's
energy that carried a factor at all, and a first-order sensitivity index
saying which fuel the interval is actually made of.

One methodological decision worth stating plainly, because it changes the
answer by a factor of twenty-seven. Three-point information normally implies a
**triangular** distribution, and that is the default here. It is wrong for
hydropower: AR5 gives 1 / 24 / 2200 gCO₂e/kWh, where 2200 comes from a few
tropical reservoir studies. A triangular over that range has its median near
**653** gCO₂e/kWh — dirtier than gas — because the mode sits at the 1st
percentile of the range. So any fuel whose maximum exceeds its median by more
than 10× is instead fitted to a **lognormal** that keeps the published median
and treats the published maximum as the 95th percentile. The heavy tail
survives; the central estimate does not move. `describe_sampling()` reports
which rule fired for which fuel and why.

## Tests

`pytest` — 42 tests, all green.

Four of them are the payload traps above. Six pin the daylight-saving
arithmetic. The rest cover the uncertainty propagation, including the one that
matters most: **the point estimate must fall inside its own interval.** If the
median escapes the distribution it came from, the propagation is wrong and
every downstream figure is decoration.

> **Fixed 2026-09-17.** `validate.expected_steps` returned 24 hours for every
> day of the year, including both transition days. Python subtracts two aware
> datetimes that share a `tzinfo` object by ignoring the offset — "no time
> zone adjustments are done in this case" — so the DST branch was dead code
> that read as correct. It had no test. It does now.

## Layout

```
config/             zones + emission factors, every row carrying a citation
src/ingest/         ENTSO-E client → raw/ + manifest.csv
src/transform/      parser, intensity, uncertainty
src/checks/         stage checkpoint functions, importable and testable
sql/                hand-written schema + DQ views
docs/               ARCHITECTURE.md — the standard shared across projects
raw/                immutable landing, git-ignored (empty until the first pull)
curated/            Parquet outputs, git-ignored
conftest.py         makes `pytest` work from the repo root

planned, not present yet — see RUNBOOK.md:
models/             dbt project: staging / intermediate / marts
report/             Quarto source → GitHub Pages
docs/METHODOLOGY.md assurance write-up
.github/workflows/  ci.yml (pytest + dbt build), refresh.yml (scheduled)
```

## Licence / reuse
Public data, open method. Emission factors are reproduced under fair use with
citation; verify against the source before relying on them.
