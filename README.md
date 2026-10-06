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

### What the manifest hash does and does not tell you

`raw/manifest.csv` records a sha256 for every payload. That hash identifies the
**retrieval**, not the data. ENTSO-E stamps each response with a fresh `mRID` and
a `createdDateTime`, so the same query repeated minutes later returns a different
hash. Measured on two pulls of the identical 2025 DE-LU A44 query:

| Retrieved (UTC) | Bytes | sha256 | `mRID` |
| --- | --- | --- | --- |
| 2026-10-06 16:30:47 | 7,544,161 | `d9687790…` | `a87148b1…` |
| 2026-10-06 18:31:50 | 7,544,161 | `9d48b590…` | `1c85b890…` |

Same byte count, same 732 TimeSeries, same 50,044 points, different hash. The
size is unchanged because both differing fields are fixed-width.

The consequence: **a changed manifest hash does not mean the data changed.** It
changes on every fetch. Comparing hashes to answer "has ENTSO-E revised this
series since we pulled it?" returns a false positive every time.

The field that does answer that question is `revisionNumber` in the
`Publication_MarketDocument` — 1 in both pulls above. For a content-level check
independent of the envelope, hash the extracted
`(resolution, classificationSequence, timestamp, value)` tuples instead of the
raw file: that is stable across retrievals and moves only when the numbers do.

The file hash is still worth recording. It answers a different and narrower
question — whether the bytes on this disk are the bytes that arrived — which is
what a provenance record is for.

## What is non-obvious in this data

Five things in the real ENTSO-E payload that a naive parser gets wrong. Traps 1
to 4 are handled in `src/transform/entsoe_parse.py` and asserted in
`test_parse.py`. Trap 5 was found on 6 October 2026 in the first full-year pull
and is **not yet implemented** — it is an open decision, not a solved problem.

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
5. **A44 returns two competing price curves for 2025, and only one field tells
   them apart.** The full-year DE-LU day-ahead pull is 50,044 points — more than
   a year holds at PT15M (35,040). The document carries 732 TimeSeries that are
   identical in `businessType` (A62), `contract_MarketAgreement.type` (A01),
   `auction.type` (A01), domain, currency and unit. The *only* discriminator is
   `classificationSequence_AttributeInstanceComponent.position`:

   | position | resolution | coverage | points | median €/MWh |
   | --- | --- | --- | --- | --- |
   | 1 | PT60M | 2024-12-31 23:00 → 2025-09-30 21:00 | 6,514 | 94.50 |
   | 1 | PT15M | 2025-09-30 22:00 → 2026-01-01 22:15 | 8,853 | 89.67 |
   | 2 | PT15M | 2024-12-31 23:00 → 2026-01-01 22:00 | 34,677 | 92.41 |

   Position 1 is one continuous series that switches resolution at the German
   15-minute MTU go-live, 1 October 2025 local. Position 2 runs at PT15M for the
   whole year. Where they overlap — 8,605 timestamps in Q4 — they **disagree in
   8,602 of them**: median difference +0.41 €/MWh, but the range runs from
   −198.37 to +278.69. The divergence is largest in exactly the scarcity and
   negative-price quarter-hours a load-shift study is about.

   Key on `(resolution, classificationSequence…position, timestamp)`, never on
   timestamp alone. A parser that groups by timestamp silently turns the choice
   of curve into whatever `first()`, `mean()` or `last()` happens to do.

   Two corollaries of trap 1 measured on the same file: the PT60M series declares
   6,551 hours in its `timeInterval` (6,552 minus the 23-hour DST day on
   30 March) and delivers 6,514 — **37 points dropped by A03 compression** that
   must be carried forward. And the hourly price never equals its four
   quarter-hours: 0 agreements in 6,323 comparable hours. They are separate
   market products, not an aggregation.

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

Runs on **Python 3.11 and later**. CI proves both ends of that claim —
3.11, the oldest version supported, and 3.14, the version it is developed
on — on every push and once a week. It also runs `dbt parse`, which
resolves every model, source, `ref` and test without touching data, so a
broken reference fails at push time rather than at build time.

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
src/ingest/         ENTSO-E and SMARD clients → raw/ + manifest.csv
src/transform/      parser, intensity, uncertainty
src/checks/         stage checkpoint functions, importable and testable
sql/                hand-written schema + DQ views
dbt/                staging / intermediate / marts, plus three singular tests
docs/               ARCHITECTURE.md — the standard shared across projects
.github/workflows/  pipeline.yml — pytest on 3.11 and 3.14, dbt parse, weekly
raw/                immutable landing, git-ignored; manifest.csv is committed
curated/            Parquet outputs, git-ignored
conftest.py         makes `pytest` work from the repo root

planned, not present yet — see RUNBOOK.md:
curated/sample/     bounded sample so `git clone && dbt build` runs tokenless
report/             Quarto source → GitHub Pages
docs/METHODOLOGY.md assurance write-up
```

## Licence / reuse

Three different things are licensed three different ways.

**The code is MIT** — see `LICENSE`. Use it, change it, ship it; keep the notice.

**The emission factors** in `config/ipcc_ar5_factors.csv` are reproduced from
IPCC AR5 WG3 Annex III with citation. Verify against the source before relying
on them.

**The ENTSO-E data is not redistributed here.** `raw/` is git-ignored and only
`manifest.csv` — the provenance record, with the token redacted — is committed.
Anyone re-running the ingestion obtains the data themselves, under the ENTSO-E
Transparency Platform's own terms of use, which this repository's licence does
not and cannot grant. The same will apply to `curated/sample/` once it exists:
a sample of ENTSO-E-derived values carries ENTSO-E's terms, not MIT.
