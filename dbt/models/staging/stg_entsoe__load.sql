{{ config(enabled = false) }}
{#-
  Disabled: a view over a missing file fails when it is created. The real
  raw/parquet/a65.parquet exists since the first A65 pull, 01.11.2026, but
  the committed sample (curated/sample/) and the dbt fixtures carry no A65,
  and CI builds both. Enable it with A65 added to both.
-#}
with src as (select * from {{ source('entsoe', 'a65') }})
select
    zone_eic,
    curve_type,
    resolution,
    cast(step_hours as double)          as step_hours,
    cast(n_steps as integer)            as n_steps,
    cast(period_start_utc as timestamp) as period_start_utc,
    cast(position as integer)           as position,
    cast(quantity as double)            as load_mw,
    cast(period_start_utc as timestamp)
      + to_milliseconds(cast(step_hours * (position - 1) * 3600000 as bigint)) as ts_utc,
    source_sha256
from src
