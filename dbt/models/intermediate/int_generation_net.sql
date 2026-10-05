/*  TRAP 2 — outBiddingZone_Domain is consumption, not generation.

    Pumped storage (B10) appears twice in the same document: once generating,
    once pumping. Summing every TimeSeries inflates the mix and corrupts the
    denominator of the intensity calculation.

    Generation and consumption are kept as separate columns so the net
    position is available without ever double-counting the gross.            */

with g as (
    select zone_eic, psr_type, ts_utc, step_hours, resolution, mw, was_carried
    from {{ ref('int_generation_gapfilled') }}
    where direction = 'generation'
),
c as (
    select zone_eic, psr_type, ts_utc, mw as consumption_mw
    from {{ ref('int_generation_gapfilled') }}
    where direction = 'consumption'
)
select
    g.zone_eic,
    g.psr_type,
    g.ts_utc,
    g.step_hours,
    g.resolution,
    g.mw                                  as generation_mw,
    coalesce(c.consumption_mw, 0)         as consumption_mw,
    g.mw - coalesce(c.consumption_mw, 0)  as net_mw,
    g.was_carried
from g
left join c
       on  c.zone_eic = g.zone_eic
       and c.psr_type = g.psr_type
       and c.ts_utc   = g.ts_utc
