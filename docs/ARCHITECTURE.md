# Portfolio Architecture Standard

Dr. Adewole Olagoke · 25 September 2026 · revised 17 October 2026

One architecture, three projects. Each project is an **instantiation** of this
standard, not a fresh design. That is deliberate: two projects sharing an
architecture demonstrate a method. Two projects with different architectures
demonstrate two tutorials.

---

## The governing rule

> Every layer must be free at the point of use, open-access, and survive any
> account being closed. Nothing in this portfolio may exist only inside a
> cloud subscription, a training tenant, or a licence someone else renews.

This is not frugality. A portfolio is an artefact that must still work in
March 2027 when a recruiter clicks the link, by which time a bootcamp tenant
has been revoked, a trial has lapsed, and a free tier has expired.

---

## Which document governs

Five documents describe this portfolio and they are not interchangeable.

| Document | Answers | Authority |
|---|---|---|
| `docs/ARCHITECTURE.md` (this file) | What the stack is, what is excluded, what every repository must look like | Governs the **standard**. Shared by A, B and C |
| `<project>/RUNBOOK.md` | What to build next here, and how to know it is right | Governs the **build**. Where a runbook and a plan disagree, the runbook wins |
| `<project>/README.md` | What this project is, for someone arriving from a job application | Governs the **first impression**. Carries no build instructions |
| `docs/RESOURCES.md` | What to read before a given stage | Reference only |
| `Master_Plan_Olagoke.docx` | Dates, decisions, certifications, runway, where to apply | Governs the **plan**, never the build |

Start at the runbook. Come here when a runbook does not say how something should
be shaped. Go to the plan when the question is *when* rather than *what*.

---

## Reference stack

| Layer | Tool | Why this one |
|---|---|---|
| Ingestion | Python (`requests`, `pystac-client`) | Open APIs, no vendor SDK lock |
| Raw landing | local `raw/`, git-ignored | Immutable; bytes as received |
| Provenance | `manifest.csv`, committed | SHA-256 per pull, tokens redacted |
| Curated | Parquet in the repo | Columnar, small, diff-able, portable |
| **Warehouse** | **DuckDB** (`.duckdb` file or Parquet) | Embedded OLAP, no server, ICU timezones, `spatial` core extension |
| Transformation | **dbt-duckdb** | sources → staging → intermediate → marts, generic + singular tests, docs and lineage |
| Code tests | `pytest` | Parser and maths correctness on fixtures |
| Data tests | dbt tests + SQL views | Assertions on data in flight |
| Orchestration | **GitHub Actions** | Free and unlimited on public repos, standard runners |
| Uncertainty | **NumPy** (Project A: `src/transform/intensity.py`) | Monte Carlo and first-order shares, tested in CI with the rest; a project whose analysis lives in R uses `sensitivity` |
| Publication | **Quarto → GitHub Pages** | Static, permanent, no licence, no expiry |
| Secondary front-ends | Power BI `.pbix` (committed), Tableau Public | Evidence for Microsoft-stack employers; a linkable visual |

**Total recurring cost: €0.** No credit card, no tenant, no expiry.

### What this deliberately excludes

Azure Data Factory, Synapse, Fabric, Databricks, Snowflake and AWS. Not because
they are bad, but because none of them is required to demonstrate any skill in
the target job descriptions, and each introduces a clock or a bill. See the
bounded excursion below for how the Microsoft evidence is obtained anyway.

---

## Environment and tooling

One environment for all three repositories: **VS Code**. It is already the
working environment, so this costs no migration. Four extensions, all from the
VS Code Marketplace:

| Extension | ID | Why |
|---|---|---|
| dbt | `dbtLabsInc.dbt` | Official. No extension dependencies, works against dbt v1. Language server, linting, column-level lineage |
| Power User for dbt | `innoverio.vscode-dbt-power-user` | Optional. Model preview, compiled SQL, lineage. Depends on `ms-python.python`, which resolves normally here |
| Quarto | `quarto.quarto` | Published by Posit. `.qmd` authoring and local preview |
| *(none)* | — | Nothing for DuckDB — see warehouse inspection below |

**Notebooks are percent-cell Python, never `.ipynb`.** `notebooks/*.py` with
`# %%` separators gives interactive execution with no JSON wrapper, no stored
outputs and a diff a reviewer can read. Notebooks are exploration only; nothing
in one is load-bearing.

### Inspecting the warehouse

DuckDB ships a local UI. Start it, then attach the warehouse **read-only**:

```bash
duckdb -ui        # embedded HTTP server on localhost:4213, opens in a browser
```

```sql
ATTACH 'warehouse/grid.duckdb' AS grid (READ_ONLY);
```

Read-only is not housekeeping. DuckDB permits **one process read-write, or many
processes read-only**, arbitrated by file locks. A UI holding the file
read-write makes the next `dbt build` fail; a running build locks the UI out.
Attaching read-only lets dbt keep the write lock while you keep a live read
view. `Simple Browser: Show` from the VS Code command palette renders
`http://localhost:4213` in an editor tab if you would rather not leave the
editor.

One setup trap: `pip install duckdb` installs the Python module, not the CLI
binary — they are separate artefacts. Install the CLI, or issue
`CALL start_ui();` from whichever client you already have open.

### dbt engine — v1 through the gate, v2 after it

dbt v2 shipped on 14 September 2026 with a **native Rust DuckDB adapter**: the
driver is downloaded and cached on first run, so `pip install dbt-duckdb`
disappears entirely. The Fusion engine is Apache 2.0 and free for individual
use without restriction.

This standard nonetheless stays on **dbt-core 1.x with `dbt-duckdb`** until the
26 November gate. Three reasons: job descriptions through April 2027 name
dbt-core 1.x, not v2; SQLFluff is not natively compatible with v2; and a
migration inside the gate window is unbudgeted risk against a date chosen
deliberately. The official extension supports v1, so no tooling benefit is
deferred by waiting.

**After the gate**, a `v2-migration` branch is worth building. A written record
of what broke in a port is stronger interview material than a project that only
ever ran on one engine.

### Considered and not taken

| Option | Why not |
|---|---|
| **Positron** | Identical repository work to VS Code, but dbt's extensions are untested there, Pylance is unavailable on Open VSX, and the Data Explorer advantage is covered by `duckdb -ui` from any editor. Worth knowing for the R-heavy research employers; not worth switching environments mid-module |
| **Google Colab** | Ephemeral VM, no interactive shell on the free tier, single-file git, and `.ipynb`-with-outputs is precisely the artefact this standard excludes. One legitimate use: an **Open in Colab** badge over the committed sample data at Stage 10, so a reader runs the analysis without cloning or a token |
| **GitHub Codespaces** | Defensible if laptop independence is wanted, and `devcontainer.json` would itself be reproducibility evidence. 120 core-hours and 15 GB-month on GitHub Free — which is 30 wall-clock hours on a 4-core machine, and storage accrues while the codespace is stopped |

---

## Repository skeleton

Identical across all three projects:

```
config/           zones / study areas / factors, each row carrying a citation
src/ingest/       API clients → raw/ + manifest.csv
src/transform/    parsers, derivations, uncertainty
src/checks/       stage checkpoint functions, importable and testable
models/           dbt project: staging / intermediate / marts
sql/              hand-written DDL and DQ views, only where a second warehouse
                  needs them (Project A's went with the Azure excursion)
raw/              immutable landing, git-ignored
curated/          Parquet outputs, committed when small
docs/             METHODOLOGY.md — the assurance document
report/           Quarto source → GitHub Pages
tests/            pytest
.github/workflows/  scheduled + CI
RUNBOOK.md        staged plan with checkpoints
README.md         opens with a screenshot, states what is real
```

---

## Layer notes

### Ingestion and provenance

Every response is written once, to a new file, hashed and recorded; nothing in
`raw/` is ever overwritten. Each logical item (document type, zone, year) is a
directory with one file per retrieval, and a response that is not data goes to
its `_failed/` folder (`src/ingest/raw_store.py`). `manifest.csv` carries URL
with the token redacted, HTTP status, SHA-256, byte count, timestamp and the
document's `revisionNumber`.

A re-run of a closed historical period must reproduce identical *data*, not an
identical hash: ENTSO-E stamps every response with a fresh `mRID` and
`createdDateTime`, so compare the payloads from the first `<TimeSeries>` on. If
the data differs, the source is non-deterministic or has been revised, and you
need to know that before building on it.

Secrets live in `.env` locally and in repository secrets for Actions. Never in
a training tenant, never in git.

### Warehouse — why DuckDB

It is an embedded engine: a file, not a server. It reads Parquet directly, has
full ICU timezone support (so DST-aware logic ports cleanly), and `dbt-duckdb`
is a first-class adapter.

The decisive property for a portfolio: **a recruiter can clone the repository
and run the whole pipeline with one command.** No account, no credentials, no
licence. That is a stronger artefact than a screenshot of a service they cannot
reach.

For geospatial work, `INSTALL spatial; LOAD spatial;` adds geometry types,
GeoParquet, and GDAL-backed format support — which is what makes Project B fit
this standard rather than needing a separate one.

### Orchestration

GitHub Actions is free with no minute cap on public repositories using standard
runners. Two workflows per project:

- `ci.yml` — on every pull request: `pytest`, then `dbt build`. The green check
  on the repository page is evidence nobody can fabricate.
- `refresh.yml` — scheduled: ingest → validate manifest → transform → `dbt build`
  → render Quarto → publish to Pages.

Two limits to design around. Scheduled workflows in a public repo are disabled
after roughly 60 days of repository inactivity, so commit periodically. And a
single job is capped at 6 hours, which matters for raster work — see Project B.

### Publication

Quarto renders to GitHub Pages: static, permanent, free, and you already know
Quarto from the R work, so it costs no learning hours.

Power BI and Tableau are **secondary artefacts**, not the pipeline output. The
`.pbix` is committed to the repo because the file is yours permanently; a
published workspace report lives only as long as the licence under it. Tableau
Public cannot connect to a live database and publishes everything openly, so it
takes a Parquet extract and is refreshed by hand when the data materially changes.

---

## The bounded Azure excursion

*Dropped from Project A in October 2026 (RUNBOOK, The gate) and archived,
with the T-SQL it would have run, in
[`archive/azure-excursion/`](../archive/azure-excursion/README.md).*

---

## One runbook per repository

This standard is shared. Runbooks are not.

Each project lives in its own repository with its own `RUNBOOK.md`, because the
stages differ structurally: Project A ingests a REST API, Project B searches a
STAC catalogue and processes rasters, Project D polls many small heterogeneous
sources on different schedules.
A combined runbook would be unusable at length and wrong in detail.

A project's runbook *should* be written **when that project starts**, not in
advance, because B's checkpoints ought to inherit what A's checkpoints actually
caught in practice — knowledge that does not exist until A has run.

**That is not what happened.** All three runbooks were written by 26 September
2026, before Project A produced a single artefact. The rule was overridden
deliberately, and the cost is real: B's and C's checkpoints are reasoned from
the domain rather than from experience, so some of them are wrong in ways only a
run will reveal.

| Project | Runbook | State |
|---|---|---|
| A — Grid Carbon Intensity | written | building |
| B — Sentinel-2 Biomass MRV | written in advance | not started |
| D — German Data-Role Market | written in advance | not started |
| ~~C — Scope 3 Value Chain~~ | archived 27.09.2026 | replaced by D — see `_archiv_2026-09/projects/README.md` |

So treat B's and C's runbooks as **specifications to be revised**, not
instructions to be followed. When A's stages surface a class of error those
runbooks do not anticipate, amend them then. The order of work is unchanged: A
to Stage 10 first.

---

## Checkpoint discipline

Every project runbook follows the same shape. Each stage has a **checkpoint**
that must pass before the next begins, because every stage here is one where a
silent error produces plausible-looking numbers rather than a crash.

A checkpoint states the command to run and the pass criteria. A stage is not
complete because the code exists. It is complete because a checkpoint passed and
the evidence is in the repo.

Where a runbook carries an **If it fails** note, it records a failure actually
met on that stage. These accumulate as the project runs. A stage without one has
not failed yet — and writing them in advance would be guessing, which is worse
than nothing because a guessed failure mode sends you to the wrong place.

### A checkpoint passes, then you commit

The commit history is not bookkeeping around the work. For this portfolio it is
part of the evidence: a reviewer can read a sequence of commits, each tied to a
checkpoint, and see a build that proceeded in order. They cannot read that from
one squashed import.

- **One commit per passing checkpoint, minimum.** `stage 4: emission factors
  with per-psrType citations, checkpoint 4 green` beats `updates`.
- **Commit the checkpoint evidence with the code that produced it** — the
  manifest row, the test output, the row count that was asserted.
- **Work on `main`.** Branches buy nothing here: no reviewer, no release train.
  The exception is a deliberate excursion, such as the post-gate
  `v2-migration` branch.
- **Push at the end of every session.** A local-only repository is not evidence
  of anything, and the public commit history is half the argument.
- **Never commit a failed stage as though it passed.** If the code must be
  saved, say so in the message: `wip stage 5: interval still inverted`.

---

## Instantiation

| Layer | **A — Grid Carbon Intensity** | **B — Sentinel-2 Biomass MRV** | **D — German Data-Role Market** |
|---|---|---|---|
| Sources | ENTSO-E Transparency Platform; IPCC AR5 WG3 Annex III | Copernicus Data Space; Planetary Computer STAC; CLMS; Global Forest Change; Copernicus DEM GLO-30 | Bundesagentur Jobbörse (**unofficial** interface); Personio / Recruitee / SmartRecruiters / Greenhouse ATS feeds; Helmholtz, Fraunhofer, Interamt RSS |
| Ingestion | REST + token, 400 req/min | STAC search + signed asset reads | REST + header key at 1 req/s; per-platform ATS adapters; RSS. Daily for fast sources, weekly for institutes |
| Heavy compute | none | xarray / rioxarray / odc-stac, **local** | blocking plus fuzzy matching (RapidFuzz) for vacancy dedupe and employer resolution |
| Curated grain | zone × production type × quarter-hour | district × date × index / biomass | vacancy × source × seen-date, plus vacancy × role cluster |
| Warehouse | DuckDB | DuckDB + `spatial` | DuckDB |
| Uncertainty | AR5 factor ranges → MC → 90% interval + Sobol | six-source error budget → MC → 90% interval + Sobol | **classification uncertainty**: precision and recall on 200 hand labels, reported with Wilson intervals, plus a stated source-coverage figure |
| Compliance layer | — | EUDR plot screening vs 31 Dec 2020 cut-off | robots.txt and ToS honoured; LinkedIn, Indeed and StepStone excluded by their terms; no third-party contact data committed |
| Publication | Quarto → Pages; `.pbix`; Tableau Public | Quarto → Pages with maps | Quarto → Pages, every chart carrying its coverage statement; daily digest to a GitHub Issue |

### Project B — the two things that differ

**Rasters never enter the warehouse.** Scene processing runs locally with
`odc-stac` / `xarray` / `rioxarray` and emits zonal statistics per forest
district per date. Those statistics are a few thousand rows of Parquet. DuckDB
holds the statistics, not the imagery, which is why the standard holds.

**Azure buys nothing here.** Microsoft Planetary Computer retired its hosted
compute Hub in June 2024. The data and STAC APIs remain free, but compute is
yours either way — so running it locally is the same work without the bill.

Actions' 6-hour job cap means the historical backfill is computed locally once
and committed as Parquet; the scheduled workflow only processes new acquisitions.

Study area: **Lahn-Dill-Bergland and Vogelsberg forest districts, Hessen**,
roughly 30 km from Pohlheim, with the 2018–2022 spruce dieback as an
independently verifiable disturbance signal validated against HessenForst's
published mortality figures.

The EUDR module is DuckDB `spatial` work end to end: plot polygons as GeoJSON,
tested against forest loss since the 31 December 2020 cut-off, emitting a
per-plot pass/fail with its full evidence chain.

### Project D — the three things that differ

**Many small sources on different clocks.** A and B each poll one API. D polls
one large source plus a dozen ATS tenants plus a dozen RSS feeds, which move at
different speeds. `config/sources.csv` carries a `poll_frequency` per source and
a failing source must never fail the run — it is logged, reported in the digest,
and flagged if silent for fourteen days. Polling a monthly source daily is noise
that teaches you to ignore the digest.

**The uncertainty layer is classification, not Monte Carlo.** There is no factor
range to propagate. The honest analogue is a measured matcher: 200 hand-labelled
postings, thresholds fitted on one half, precision and recall reported on the
held-out half with Wilson intervals. A point estimate from a hundred labels is
not a number anyone should trust, and saying so is the point.

**One source is unofficial, and that is an engineering requirement.** The
Bundesagentur interface is reverse-engineered and community-documented, with no
published terms and no documented rate limits. So: one request per second, an
identifying User-Agent, graceful degradation when it errors, and no headline
dashboard claim resting on it alone. It is named as unofficial in the README, in
`METHODOLOGY.md` and on the dashboard.

Two ideas transferred from the archived Project C rather than being discarded:
match tier drives stated confidence, exactly as data-quality tier drove interval
width; and value-of-information ranking now ranks employers worth investigating
instead of suppliers worth engaging.

---

## Honesty rules (all projects)

1. The README states what is real and what is not.
2. No CV claims a technology until the checkpoint that proves it has passed.
3. Provenance is a column, not a comment. Citation fields are NOT NULL.
4. If you cannot explain a number, do not publish it.
5. Status labels track the runbook: `written` means the code exists, `run`
   means a checkpoint passed. Nothing is `operational` before publication.
6. Dates in a runbook header are targets. When one slips, update it the same day.
