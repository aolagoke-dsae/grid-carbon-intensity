# Project A — Build Runbook

**Grid Carbon Intensity & Load-Shift Optimiser**
Dr. Adewole Olagoke · started 7 August 2026 · runbook revised 17 October 2026
Gate: Stages 1–8 complete by **26 November 2026** (Abschlussprojekt opens 27.11.)
Target: Stage 10 public during Modul IV, before **5 January 2027**

Ten stages. Each has a **checkpoint** that must pass before the next one starts.
The checkpoints exist because every stage here is one where a silent error
produces plausible-looking numbers rather than a crash.

The stack is defined once in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
and shared with the Sentinel-2 biomass MRV and the German data-role market
projects. This runbook is its instantiation for Project A.

---

## Where this actually stands

*Revised 7 October 2026. The table below used to say no git repository, empty
directories and nothing against the live API. All three were true on
25 September and none is true now. Updated 17 October 2026: the dbt row said
"no" while ten models existed, and the ENTSO-E row did not say that only A44
has been pulled.*

| | Written | Unit-tested | Run against real data |
|---|---|---|---|
| Ingestion client (ENTSO-E) | yes | token redaction and the append-only raw store, since 10.10. | **A44 only** — two pulls, 06.10.2026; A75 and A65 not yet fetched |
| Ingestion client (SMARD) | yes | — | **yes** — 06.10.2026 |
| Parser, A75 (A03, direction, DST, MAW) | yes | yes; transition days since 17.10. | **not yet** — no A75 payload |
| Parser, A44 prices (trap 5) | yes | yes | **yes** — the 2025 DE-LU payload |
| Intensity + uncertainty | yes; method 2.0.0 since 17.10. | yes | **not yet** — needs A75 |
| Stage checks (2, 3, 4, 5) | yes | yes, since 07.10. | **not yet** |
| SQL schema + DQ views | yes | — | **not yet** |
| dbt models | yes — 10 models, 6 singular tests (1 disabled) | `dbt parse` in CI | `stg_entsoe__prices` and its two tests, 10.10.2026 |
| CI | yes, `.github/workflows/pipeline.yml` | — | **yes**, green on 3.11 and 3.14 |
| Version control | yes — MIT; public from WE 3, 24./25.10.2026 | — | — |

`raw/` holds one ENTSO-E payload and one SMARD week, both in `manifest.csv`.
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
| *Dropped* | Azure SQL (free offer), Stage 6b — see **The gate**. Power BI is built on the exported Parquet instead | €0 | none |

Defined once in [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) and shared with
the Sentinel-2 biomass MRV and the German data-role market projects. Tutorials,
reference repositories and data sources for each
layer are listed in [`docs/RESOURCES.md`](docs/RESOURCES.md), each tagged with
the stage it belongs to.

---

## Stage map

| # | Stage | Produces | Cost | Target |
|---|---|---|---|---|
| 0 | Environment, secrets, git | first commit | €0 | **today** |
| 1 | First raw pull with manifest | `raw/A75/<eic>/2025/` | €0 | **this weekend** |
| 2 | Parse: A03, direction, DST, MAW | parsed rows in memory | €0 | w/c 28 Sept |
| 3 | Backfill and coverage | DE-LU and FR × 6 years in `raw/` | €0 | w/c 5 Oct |
| 4 | Emission factors verified | audited `ipcc_ar5_factors.csv` | €0 | w/c 12–19 Oct |
| 5 | Deterministic intensity | a defensible number | €0 | by 1 Nov |
| 6 | DuckDB warehouse + dbt | tested marts, lineage docs | €0 | w/c 2 Nov |
| 7 | Quality gate | dbt tests + DQ views green | €0 | w/c 16 Nov |
| 8 | Monte Carlo and Sobol | 90% interval + drivers | €0 | w/c 23 Nov |
| 9 | Orchestration (GitHub Actions) | unattended daily runs | €0 | w/c 7 Dec |
| 10 | Publication (Quarto → Pages) | public URL + methodology | €0 | by 19 Dec |
| 6b | *Dropped:* Azure excursion | — | — | see **The gate** |

**Stages 0–9 are local and free.** The Azure excursion (Stage 6b) was dropped
in October 2026; its procedure is kept below for reference.

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
pytest -q                                     # 101 tests (84 functions), all green
                                              # (97 + 4 skipped where raw/ is absent)
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
rows = parse(newest.read_text(encoding="utf-8"))
print(check_stage2_parse(rows))
print(check_stage2_direction(rows))
```

**Checkpoint 2**

- Both checks return `True`
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
import yaml, os
from dotenv import load_dotenv
from src.ingest.entsoe_client import generation_per_type
load_dotenv()
cfg = yaml.safe_load(open("config/zones.yml"))
for z in cfg["zones"]:
    if z["key"] not in ("DE_LU", "FR"):      # the analysis covers two zones
        continue
    for year in range(2021, 2027):
        generation_per_type(z["eic"], year, os.environ["ENTSOE_TOKEN"])
```

The pauses between calls add 18 seconds; the downloads take most of the time,
since one DE-LU year is about 75 MB. Verify every EIC in
`config/zones.yml` against the Transparency Platform Area List before trusting it.

**Checkpoint 3**

```python
from src.checks.validate import check_stage3_coverage
print(check_stage3_coverage(rows, "Europe/Berlin"))
```

- Returns `True`
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
confidence flag and a citation per `psrType`. Five rows are deliberately
**unpriced**: B10 and B25 (pumped and battery storage, not generation), B15 and
B20 (composition undisclosed by ENTSO-E), B17 (waste, contested biogenic/fossil
split). B25 joined on 17 October 2026, when the first French A75 pull reported
battery storage and the stage 4 check failed on a fuel with no row. Two more
— B03 and B06 — are marked `low` because they are proxies rather than published
AR5 rows.

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
from src.checks.validate import check_stage5_plausibility
print(check_stage5_plausibility(values))
```

- Returns `True`; range roughly **50–700 gCO2e/kWh** for DE-LU across a year
- Plot one week and look at it. Sunny summer midday low, still winter evening
  high. An inverted shape means a join error.
- Cross-check a handful of hours against an independent published series
  (Electricity Maps free tier). Expect a few percent difference — you use
  lifecycle factors, some sources use direct combustion only. **Document the
  difference and explain it.** That explanation is the single most impressive
  paragraph in the methodology document.

**This is the free/local gate.** Everything to here costs nothing. Nothing
after it should start until this passes.

---

## Stage 6 — DuckDB warehouse and dbt

**Needs:** Stage 5 passed. **Cost: €0.** No account, no provisioning.

```bash
pip install duckdb dbt-duckdb
dbt init  # profile target: duckdb, path: warehouse/grid.duckdb
dbt build
```

**Inspecting the warehouse.** `duckdb -ui` opens a local UI on
`localhost:4213`. Attach **read-only** —
`ATTACH 'warehouse/grid.duckdb' AS grid (READ_ONLY);` — because DuckDB allows
one process read-write *or* many read-only. A UI holding the file read-write
makes the next `dbt build` fail. Full note in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

Four layers: declared sources with freshness → 1:1 staging → intermediate
models carrying the business logic (directional split, factor join, DST-aware
coverage) → marts exposing three conformed dimensions and three facts. Every
model documented. Nothing bypasses a source declaration.

Keep `sql/01_schema.sql` exactly as it is. It is hand-written T-SQL with
persisted computed columns and CHECK constraints, and it becomes the second
dbt target at Stage 6b. It is the portability evidence.

**Checkpoint 6**

- `dbt build` green; `dbt docs generate` produces a lineage graph
- Mart row count equals the parsed row count **exactly**
- Every fact row resolves to a batch in the ingest manifest
- `select count(*) from dim_production_type where ef_source_citation is null` returns 0
- `git clone` + `dbt build` reproduces the warehouse from scratch on a machine
  that has never seen the project. That is the property the whole standard exists for.

---

## Stage 7 — Quality gate

**Needs:** Stage 6. **Cost: €0.**

Generic tests (`unique`, `not_null`, `relationships`, `accepted_values`) on
every grain, plus four singular tests that encode the domain:

1. Step coverage distinguishing a genuine gap from a 92- or 100-step DST day
2. Pumped-storage double-count detection
3. Priced-fuel coverage threshold below which a figure is withheld
4. Intensity plausibility band

`sql/02_dq_checks.sql` stays as the portable SQL expression of the same logic.

**Checkpoint 7**

- All dbt tests pass
- `OK` dominates the coverage status; `OK_DST_SPRING_FORWARD` and
  `OK_DST_FALL_BACK` appear once per year per zone; `MISSING_STEPS` and
  `DUPLICATE_STEPS` are zero
- Unmapped fuels returns only the five deliberately unpriced categories
- **Break one on purpose.** Delete a day from a staging model and confirm the
  coverage test fails loudly. A test you have not seen fail is a test you do
  not know works.

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

Today `pipeline.yml` runs `pytest` on Python 3.11 and 3.14 and `dbt parse`, on
every push and weekly. This stage turns it into two workflows:

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
  method, and the known limitations (no import adjustment yet, five unpriced
  fuel categories)
- Once you have 30+ consecutive green scheduled runs, screenshot the Actions
  history and put it near the top of the README. That image is worth more than
  any certificate, because it proves the thing ran without you.

---

## Stage 6b — Azure and Power BI excursion (dropped)

*Dropped from the capstone in October 2026 — see **The gate**. Kept as the
procedure if it is ever run; Power BI is built on the exported Parquet instead.*

**Needs:** Stage 7. **Bounded to about one week. Run once, then stop.**

This exists to produce Microsoft-stack evidence for the German market, without
making Azure the spine of the project.

1. **Set the €30 budget alert first**, while the subscription is still empty.
2. Create the database under the **Azure SQL Database free offer**: free for the
   lifetime of the subscription, 100,000 vCore-seconds and 32 GB a month. Leave
   **"Behavior when free limit reached" on auto-pause**, the default. The other
   option, *Continue using database for additional charges*, is the one that
   **cannot be reverted** to auto-pause (Microsoft Learn, checked 17.10.2026).
3. Do **not** use the 12-month free-services tier. It expires around September
   2027 and then bills silently rather than pausing.
4. Add `azuresql` as a second dbt target. Run `sql/01_schema.sql`, load, run
   `sql/02_dq_checks.sql`.
5. Build the `.pbix`: DirectQuery on the fact, import on dimensions, row-level
   security by zone. Twenty minutes, and a standard interview question at utilities.
6. Screenshot everything. Commit `.pbix` and a `.bacpac`. Let it auto-pause forever.

**Checkpoint 6b**

- The same dbt project builds green against both targets
- Deliberately insert `mw = -1` and confirm the CHECK constraint rejects it.
  A constraint you have not seen fire is a constraint you do not know works.
- `.pbix` and `.bacpac` are committed; the warehouse rebuilds from the `.bacpac`
- Budget alert has fired zero times

**What it earns, honestly stated:** *dbt project with two warehouse targets
(DuckDB and Azure SQL); CI runs `dbt build` on every pull request; Power BI
semantic model committed as `.pbix`.*

---

## Schedule against the Maßnahmebogen

Course blocks are taken from the Maßnahmebogen. The right-hand column is what
exists in the repository at the end of that block. Where the curriculum, which
is what is actually taught, differs from the Maßnahmebogen, the curriculum
governs: Modul IV runs 14.12.2026–06.01.2027.

| Dates | Course block | UE | Runbook work |
|---|---|---|---|
| 15.09.–07.10. | Python | 153 | **Stages 0–3.** Pull, parser, four trap tests, backfill, load to DuckDB, CI green, repo public. |
| 08.10.–19.10. | Datenbanken und Visualisierung | 72 | **Stage 6 (first half).** dbt project created, sources and staging done, first generic tests, `dim_datum` with DST logic. |
| 20.10.–28.10. | Analyse I und **Power BI** | 63 | **Stages 4–5** in parallel; intermediate and marts, star schema standing, `exports/` Parquet folder, Power BI page 1. |
| 29.10.–09.11. | Machine-Learning-Modelle | 72 | Baseline **first** — seasonal naive, same weekday last week. Then the price-spread forecast. If the model loses to the baseline, document that. |
| 10.11.–13.11. | Analyse II, DAX und APIs | 36 | DAX measures, Power BI pages 2 and 3. Measures in DAX, not precomputed in Power Query. |
| 16.11.–17.11. | Allgemeine Themen | 18 | **Stage 7.** README, lineage screenshot, `BENCHMARKS.md`. |
| 18.11.–20.11. | Nachhaltigkeit in der IT | 27 | The marginal-versus-average intensity section. This is the limitation an experienced interviewer opens first. |
| 23.11.–26.11. | Praxistage | 36 | **Stage 8.** Monte Carlo and Sobol, reproducible with a fixed seed. |
| **27.11.–04.12.** | **Abschlussprojekt** | 54 | Consolidation, submission, presentation. Six working days. The capstone must already be built when this opens. |
| **05.12.–05.01.** | **Modul IV** | 135 | PSM I and **Praktikumsgespräche**. Stages 9–10 fit in the margin. |

### The gate

**Stages 1–8 complete by 26 November.** The Abschlussprojekt block is 54 UE of
consolidation and presentation, not build time. Arriving at 27 November with
ingestion unfinished means submitting a project that does not yet compute
anything.

**Stages 9 and 10 have no course slot.** Orchestration and publication happen in
Modul IV alongside PSM I and the placement interviews. Budget for that
now rather than discovering it in December.

**DP-600 and the Azure excursion are dropped.** Fabric requires a work or school tenant, and the certification targets platform operations rather than inference. The hours go to the causal module and the GenAI extraction artifact instead.

### Why 26 November is earlier than it looks

Praktikumsgespräche begin **5 December**. The portfolio has to be presentable
then, not in January. A placement conversation is the earliest live application
channel available, it arrives ten weeks from now, and it is the one where a
working public repository does the most work per minute of conversation.

Power BI teaching starts **20 October**. PL-300 in November is supported by the
course, not left to self-study.

Reliable Power BI path: dbt writes the mart tables to `exports/` as Parquet and
Power BI Desktop reads that folder. The DuckDB ODBC route works but carries a
risk on a submission day that nobody needs.

Learn in the Greenbootcamps Azure tenant. **Build in your own subscription.**
Their access ends with the course, which is the month you start applying.

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
