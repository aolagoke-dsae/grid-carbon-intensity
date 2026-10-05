with src as (select * from {{ source('entsoe', 'a11') }})
select
    zone_eic,
    direction,
    resolution,
    cast(step_hours as double)          as step_hours,
    cast(period_start_utc as timestamp) as period_start_utc,
    cast(position as integer)           as position,
    cast(quantity as double)            as flow_mw,
    cast(period_start_utc as timestamp)
      + to_milliseconds(cast(step_hours * (position - 1) * 3600000 as bigint)) as ts_utc
from src
