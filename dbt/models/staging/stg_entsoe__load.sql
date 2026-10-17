{{ config(enabled = false) }}
{#-
  Disabled until raw/parquet/a65.parquet exists. A view over a missing file
  fails when it is created, so with this model enabled `dbt build` could not
  go green on the data that does exist. Remove the config line after the
  first A65 pull.
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
