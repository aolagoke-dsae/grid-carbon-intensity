/*  Catches: pumped-storage double counting.

    B10 appears twice in the same ENTSO-E document — once as
    inBiddingZone_Domain (generating) and once as outBiddingZone_Domain
    (pumping). Summing every TimeSeries inflates the mix and corrupts the
    denominator of any intensity computed from it.

    Asserted at the intermediate layer, which is where the split happens, so
    the test holds regardless of how the marts are later shaped.              */
with per_fuel_hour as (
    select
        zone_eic,
        psr_type,
        date_trunc('hour', ts_utc) as ts_hour_utc,
        sum(generation_mwh)        as gen_mwh,
        sum(consumption_mwh)       as cons_mwh,
        sum(generation_mwh) - sum(consumption_mwh) as net_mwh
    from {{ ref('int_generation_energy') }}
    group by 1, 2, 3
)
-- generation must never silently absorb the consumption leg
select *
from per_fuel_hour
where cons_mwh > 0
  and abs((gen_mwh - cons_mwh) - net_mwh) > 0.01
