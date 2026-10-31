# exports/ — the marts as Parquet, for Power BI

Every `dbt build` on the real data writes each table of the marts here, one
file per table (`dbt/macros/export_parquet.sql`): `fact_intensity_year`, the
yearly figure with its 90% interval; `fact_intensity`, every step with its
interval; `fact_generation`, `fact_price` and the four dimensions. Power BI
Desktop reads the files from this folder, the reliable path the RUNBOOK
describes under **The gate**.

They hold ENTSO-E-derived data in bulk, so they stay on the machine that
built them: only this README is committed (`.gitignore`; README, **Licence**).
The `sample` target writes nothing here.
