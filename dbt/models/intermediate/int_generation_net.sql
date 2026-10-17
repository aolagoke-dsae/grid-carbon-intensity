/*  TRAP 2 — outBiddingZone_Domain is consumption, not generation.

    Pumped storage (B10) appears twice in the same document: once generating,
    once pumping. Summing every TimeSeries inflates the mix and corrupts the
    denominator of the intensity calculation. The 2025 payloads carry
    consumption legs for other fuels as well: B16 and B19 in DE-LU, six fuels
    in France.

    Generation and consumption are kept as separate columns so the net
    position is available without ever double-counting the gross.

    A full outer join. A step in which a unit only pumps has no generation
    row, and the left join used until 17.10.2026 dropped its consumption
    (audit B1). step_hours is part of the key: two legs at different
    resolutions stay separate rows, so neither is weighted with the other's
    step length, and assert_one_row_per_zone_fuel_step fails on them.         */

with g as (
    select zone_eic, psr_type, ts_utc, step_hours, resolution, mw, was_carried, source_sha256
    from {{ ref('int_generation_gapfilled') }}
    where direction = 'generation'
),
c as (
    select zone_eic, psr_type, ts_utc, step_hours, resolution, mw, was_carried, source_sha256
    from {{ ref('int_generation_gapfilled') }}
    where direction = 'consumption'
)
select
    coalesce(g.zone_eic, c.zone_eic)            as zone_eic,
    coalesce(g.psr_type, c.psr_type)            as psr_type,
    coalesce(g.ts_utc, c.ts_utc)                as ts_utc,
    coalesce(g.step_hours, c.step_hours)        as step_hours,
    coalesce(g.resolution, c.resolution)        as resolution,
    coalesce(g.mw, 0)                           as generation_mw,
    coalesce(c.mw, 0)                           as consumption_mw,
    coalesce(g.mw, 0) - coalesce(c.mw, 0)       as net_mw,
    coalesce(g.was_carried, false)
      or coalesce(c.was_carried, false)         as was_carried,
    coalesce(g.source_sha256, c.source_sha256)  as source_sha256
from g
full outer join c
       on  c.zone_eic   = g.zone_eic
       and c.psr_type   = g.psr_type
       and c.ts_utc     = g.ts_utc
       and c.step_hours = g.step_hours
