/*  Catches: a consumption leg in the generation total, or one that is lost.

    B10 appears twice in the same ENTSO-E document — once as
    inBiddingZone_Domain (generating) and once as outBiddingZone_Domain
    (pumping). Summing every TimeSeries inflates the mix and corrupts the
    denominator of any intensity computed from it.

    Each (zone, fuel, step) of int_generation_energy must carry exactly the
    generation-direction mw of int_generation_gapfilled as generation_mw,
    and the consumption-direction mw as consumption_mw, and every step of
    either direction must be there. Until 17.10.2026 this test compared
    gen - cons with a net column defined as gen - cons, which cannot fail
    (audit B2), and it passed with pumping summed into generation.            */
with by_direction as (
    select
        zone_eic,
        psr_type,
        ts_utc,
        sum(case when direction = 'generation'  then mw end) as generation_mw,
        sum(case when direction = 'consumption' then mw end) as consumption_mw
    from {{ ref('int_generation_gapfilled') }}
    group by 1, 2, 3
)
select
    coalesce(s.zone_eic, e.zone_eic) as zone_eic,
    coalesce(s.psr_type, e.psr_type) as psr_type,
    coalesce(s.ts_utc, e.ts_utc)     as ts_utc,
    s.generation_mw                  as source_generation_mw,
    e.generation_mw,
    s.consumption_mw                 as source_consumption_mw,
    e.consumption_mw
from by_direction s
full outer join {{ ref('int_generation_energy') }} e
       on  e.zone_eic = s.zone_eic
       and e.psr_type = s.psr_type
       and e.ts_utc   = s.ts_utc
where s.zone_eic is null
   or e.zone_eic is null
   or abs(coalesce(s.generation_mw, 0)  - e.generation_mw)  > 1e-6
   or abs(coalesce(s.consumption_mw, 0) - e.consumption_mw) > 1e-6
