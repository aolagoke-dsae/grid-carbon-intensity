# The Azure excursion (archived)

Archived on 17 October 2026. The excursion was dropped from the capstone in
October 2026 (RUNBOOK, **The gate**): Fabric needs a work or school tenant,
and Power BI is built on the exported Parquet instead. Until this date the
procedure stood in the RUNBOOK and in `docs/ARCHITECTURE.md`, and its T-SQL in
`sql/`, so the repository both dropped the excursion and specified it (audit
D7). It is kept here as it was, for reference only.

**The T-SQL in `sql/` runs nowhere.**

- DuckDB, the warehouse this project uses, stops at `CREATE OR ALTER`.
- On Azure SQL, `AT TIME ZONE` needs Windows time-zone names
  ("W. Europe Standard Time"), not IANA ones ("Europe/Berlin"), so the DST
  logic in `02_dq_checks.sql` would fail there too.
- `01_schema.sql` requires a `batch_id` on every fact row. The landing now
  records provenance differently: `source_sha256` on every row, the key of the
  retrieval's row in `raw/manifest.csv` (audit B6).

The DST-aware coverage check that `02_dq_checks.sql` expressed lives in
`dbt/tests/assert_step_count_per_local_day.sql`, which runs.

### Stage 6b — Azure and Power BI excursion (dropped)

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

## The same procedure, as `docs/ARCHITECTURE.md` stated it

*Dropped from Project A in October 2026 (RUNBOOK, The gate). Kept as the
procedure if it is ever run.*

Run **once**, at the end, for about a week, on Project A only:

1. Set the €30 budget alert while the subscription is still empty.
2. Create the database under the **Azure SQL Database free offer** — free for
   the lifetime of the subscription, with **"Behavior when free limit reached"
   left on auto-pause**, the default. The other option, *Continue using database
   for additional charges*, cannot be reverted to auto-pause once chosen
   (Microsoft Learn, checked 17.10.2026).
3. Point the same dbt project at it as a second target. Run `sql/01_schema.sql`
   and `sql/02_dq_checks.sql`.
4. Build the `.pbix` on top. Screenshot everything.
5. Commit `.pbix` and a `.bacpac`. Let the database auto-pause permanently.

Do **not** build on the 12-month free-services tier: it expires around
September 2027 and resources are then billed silently rather than paused.

What this earns, honestly stated: *dbt project with two warehouse targets
(DuckDB and Azure SQL); CI runs `dbt build` on every pull request; Power BI
semantic model committed as `.pbix`.* Stronger than either stack alone, with
zero ongoing exposure.
