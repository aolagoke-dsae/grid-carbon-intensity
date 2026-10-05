-- Rename, cast, resolve position -> timestamp. No business logic.
with src as (
    select * from {{ source('entsoe', 'a75') }}
)
select
    zone_eic,
    psr_type,
    direction,
    curve_type,
    unit_name,
    resolution,
    cast(step_hours as double)              as step_hours,
    cast(n_steps as integer)                as n_steps,
    cast(period_start_utc as timestamp)     as period_start_utc,
    cast(position as integer)               as position,
    cast(quantity as double)                as quantity_mw,
    cast(period_start_utc as timestamp)
      + to_milliseconds(cast(step_hours * (position - 1) * 3600000 as bigint)) as ts_utc
from src
where psr_type is not null
