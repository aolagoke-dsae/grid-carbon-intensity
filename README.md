# Grid Carbon Intensity

Hourly-and-quarter-hourly carbon intensity for two European bidding zones,
DE-LU and FR, **derived** from the ENTSO-E generation mix using IPCC AR5
lifecycle factors rather than consumed from a vendor — with the published
factor uncertainty propagated through to a 90% interval by Monte Carlo, and a
first-order sensitivity index saying which fuel's factor that interval is
mostly made of.

The eventual purpose is a load-shifting decision model that prices the saving
in tCO2e and euros. That is the question the project exists to answer; it is
not built yet. See **What is not built** below.

> **Status: in build (started 7 August 2026).** See `RUNBOOK.md` for the staged
> plan and current position. Nothing in this repository is presented as
> operational until Stage 10 passes.

## Hypothesis

*Recorded on 10 October 2026, before any generation data was pulled. At this
commit `raw/manifest.csv` lists day-ahead prices (A44) and SMARD rows only —
there is no A75 generation for either zone — so no result yet exists that this
could have been fitted to. The commit timestamp is the record.*

The zone comparison tests a hypothesis rather than asserting one. France's
generation mix barely changes across the day; Germany's (DE-LU) changes a great
deal. For the same plant shifting the same load within the day, therefore:

- the **CO₂ saving should differ sharply between the zones** — larger in DE-LU,
  where the mix moves, than in FR, where it barely does;
- the **cost saving should exist in both**.

Whether that holds is for the data to say. Each saving will be reported per
zone with its Monte Carlo interval. One limitation is stated with it from the
start: the intensity used here is the *average* intensity of the generation
mix, not the *marginal* intensity of the plant that actually responds to a
shift, and the two can differ substantially.

## Stack

Open-access end to end, by design. Python ingestion → immutable raw layer with a
SHA-256 manifest → Parquet → **DuckDB** warehouse → **dbt** (sources, staging,
intermediate, marts, tests, lineage), with **GitHub Actions** for CI and a
**Quarto** report to follow. Uncertainty propagation and the sensitivity index
are plain Python — NumPy, no modelling framework — in
`src/transform/intensity.py`.

The ingestion, parsing, uncertainty and CI layers are written, tested and
running. The dbt models and the report are specified in `RUNBOOK.md` and not
yet built — the Layout and **What is not built** mark which is which.

The acceptance criterion that governs the whole build: **the deterministic
point estimate must fall inside the sampled 90% interval.** The deterministic
point is `deterministic_intensity()` — the energy-weighted mean at each fuel's
median factor, no sampling — and it is a different quantity from the median of
the draws. If it escapes the interval the propagation is skewed, and no figure
is published.

> Corrected 7 October 2026. The test behind this criterion used to compare the
> sampled median against the sampled percentiles, which is true by definition
> and could never fail. The headline control was vacuous for seven weeks.

## What is not built

Named here rather than left for a reader to discover.

| | Status |
|---|---|
| dbt models | **CORRECTION, 08.10.2026, made precise 10.10.2026.** An earlier version of this row said "no models written". That was wrong. The 10 models arrived on 5 October in commit `1c21970` (a second root, merged in `9f60b2f`); today they run to 314 lines, including the 08.10 rewrite of `stg_entsoe__prices.sql`. `stg_entsoe__prices` and its two tests were built and run against the real A44 payload on 10.10.2026. Everything that depends on A75 is unexecuted, because no A75 payload exists yet. |
| `curated/sample/` | **absent**, so `dbt build` from a clean clone does not run |
| Load-shifting decision model | **not started** — the question the project exists to answer |
| Quarto report, GitHub Pages | **not started** |
| Power BI / Azure portability excursion | **not started**; no `.pbix` or `.bacpac` exists |
| Global (Sobol) sensitivity | **not built**. What exists is a first-order index, `variance_contribution()` |
| Cross-border flow (A11) import adjustment | **not built**; intensity is average, not marginal |
| Trap 5, the two competing A44 price curves | **handled** 08.10.2026 — `entsoe_prices_parse.py`, `xml_to_parquet.py` and the curve filter in `stg_entsoe__prices.sql`. What stays open is *which* curve is authoritative: that needs SMARD filter 4169 for the 2025 weeks, which has not been pulled |

What *is* built and running: ingestion with a redacting manifest, the A75
parser with its four traps, the A44 price parser with the fifth, the raw
parquet landing, Monte Carlo uncertainty with the first-order index, the stage
checkpoints, and CI across Python 3.11 and 3.14.

`config/zones.yml` carries five zones; the analysis covers two. The other three
are configuration kept for later, not results.

No subscription, no licence and no free tier is required to run any of it.
`git clone` then `pytest` works today. `dbt build` from a clean clone is the
goal and does not work yet: it needs `curated/sample/`, which is not committed,
and the dbt models, which are not written. Stated here rather than discovered
after cloning.

The architecture is defined once in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
and shared with the Sentinel-2 biomass MRV and German data-role market projects.

## Data provenance

| Source | Used for | Access |
|---|---|---|
| ENTSO-E Transparency Platform | Generation per production type (A75), day-ahead prices (A44), actual load (A65) | REST API, token |
| SMARD (Bundesnetzagentur) | Independent second source for the reconciliation test | REST, no key |
| IPCC AR5 WG3 Annex III | Lifecycle emission factors with published ranges | `config/ipcc_ar5_factors.csv` |

A fetcher exists for each row above and has been run. Cross-border flows (A11),
DWD temperature and EEA verified emissions are candidates for later work and
have no fetcher, so they are not listed as sources.

All grid, price and factor data are real and cited. Any facility load profile
used later in the decision model will be **illustrative and labelled as such**.

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

Only the second of those two payloads still exists: the second pull overwrote
the first. Since 10 October 2026 that cannot happen. `raw/` is append-only
(`src/ingest/raw_store.py`): every retrieval is a new file named by its
retrieval time and hash, a response that is not data — a non-200 status, an
Acknowledgement, a body that does not parse — goes to a `_failed/` folder, and
the manifest records each document's `revisionNumber`.

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
and is handled as of 8 October 2026 in `src/transform/entsoe_prices_parse.py`,
asserted in `test_prices_parse.py`, and enforced in SQL by the curve filter in
`stg_entsoe__prices.sql` plus two singular dbt tests.

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

   **How it is handled.** `classification_sequence` is emitted by the parser,
   carried through `raw/parquet/a44.parquet`, and filtered once in
   `stg_entsoe__prices.sql` under the dbt var `a44_curve`, default 1. Curve 1
   is chosen for continuity — it is the series that was actually binding at
   each moment, hourly until the 15-minute MTU go-live and 15-minute after —
   **not** because it has been shown to be the authoritative one. That question
   needs SMARD filter 4169 for the 2025 weeks and stays open.

   The arithmetic of ignoring the discriminator, measured: unfiltered, the
   50,044 points carry 15,014 duplicated `(zone, period, position)` keys and a
   median of **91.80 €/MWh** — a figure that belongs to neither curve (90.80
   and 92.41). `dbt/tests/assert_one_price_per_zone_timestamp.sql` fails if a
   timestamp ever appears twice again, and
   `dbt/tests/assert_every_price_period_survives_the_curve_filter.sql` catches
   the opposite mistake: a curve setting that silently deletes delivery periods.
   Curves are counted per zone *and* delivery period, so a zone that publishes
   one curve in one year and two in the next keeps both years.

   One limit worth stating: the staging model carries **stated points only**,
   as the raw layer is meant to. A03 compression means curve 1 is missing 116
   of 15,483 steps (0.75%) and curve 2 is missing 459 of 35,136 (1.31%). The
   carry-forward belongs in an `int_` model that does not exist yet, so a join
   on `ts_utc` today silently drops those intervals.

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

`pytest` — 86 tests, all green: 73 test functions, some parametrised. Four of
them read the real 7.5 MB A44 payload and **skip in CI**, because `raw/*` is
gitignored; CI therefore reports 82 passed, 4 skipped, and a local run with
`raw/` populated reports 86 passed.

Runs on **Python 3.11 and later**. CI proves both ends of that claim —
3.11, the oldest version supported, and 3.14, the version it is developed
on — on every push and once a week. It also runs `dbt parse`, which
resolves every model, source, `ref` and test without touching data, so a
broken reference fails at push time rather than at build time.

| File | Tests | What they pin |
|---|---|---|
| `src/transform/test_parse.py` | 10 | Traps 1–4 in the A75 parser, on fixtures |
| `src/transform/test_prices_parse.py` | 21 | Trap 5 and the A44 parser, including 4 transition-day cases and the 4 real-payload checks |
| `src/transform/test_dst.py` | 13 | Daylight-saving arithmetic of the validation calendar, `validate.expected_steps` |
| `src/transform/test_intensity.py` | 20 | The uncertainty propagation and factor handling |
| `src/checks/test_validate.py` | 6 | The stage checkpoints |
| `src/ingest/test_entsoe_client.py` | 3 | Token redaction in exceptions and the manifest |
| `src/ingest/test_raw_store.py` | 12 | `raw/` is append-only: a failed pull never replaces data, every retrieval is kept, the smoke scripts report the status they actually got |
| `src/transform/test_xml_to_parquet.py` | 1 | The landing reads only the newest accepted retrieval of each year |

The test that matters most: **the deterministic point estimate must fall
inside the Monte Carlo interval built around it.** If it falls outside, the
propagation is wrong and every downstream figure is decoration. It currently
holds for the test mix, which is coal- and gas-heavy, and fails for
nuclear-heavy French mixes, because the triangular sampler takes the published
median as the mode of a right-skewed band. That is the next fix.

Not yet covered: the A75 parser on the transition days themselves. Its fixtures
are 24-hour days, and its step count can be hard-coded to 24 hours without a
single test failing.

> **Fixed 2026-09-17.** `validate.expected_steps` returned 24 hours for every
> day of the year, including both transition days. Python subtracts two aware
> datetimes that share a `tzinfo` object by ignoring the offset — "no time
> zone adjustments are done in this case" — so the DST branch was dead code
> that read as correct. It had no test. It does now.

## Layout

```
config/             zones + emission factors, every row carrying a citation
src/ingest/         ENTSO-E and SMARD clients → raw/ + manifest.csv
src/transform/      A75 parser, A44 price parser, parquet landing, intensity,
                    uncertainty
src/checks/         stage checkpoint functions, importable and testable
sql/                hand-written schema + DQ views
dbt/                10 models and six singular tests, written and parsing;
                    never executed — see What is not built
docs/               ARCHITECTURE.md — the standard shared across projects
.github/workflows/  pipeline.yml — pytest on 3.11 and 3.14, dbt parse, weekly
raw/                append-only landing, git-ignored: one folder per document,
                    zone and year, one file per retrieval, failures in
                    _failed/; manifest.csv is committed
raw/parquet/        stated points per document type, git-ignored, rebuilt with
                    `python -m src.transform.xml_to_parquet`
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
