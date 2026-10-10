-- TRAP 5, the other half: the curve filter must never delete a delivery period.
--
-- stg_entsoe__prices keeps one curve per (zone, delivery period). Point the
-- a44_curve var at a curve that a two-curve period does not carry -- a typo
-- such as 3 -- and that period's rows vanish. An absent period reads downstream
-- as "no prices were published", not as an error.
--
-- Checked per period, not for the model as a whole. The whole-model check this
-- replaces ("is the model empty?") passed while a44_curve=3 deleted DE-LU
-- outright, because FR and PL still had rows -- found in the 09.-10.10. audit.
select
    s.zone_eic,
    s.period_start_utc
from (
    select distinct zone_eic, cast(period_start_utc as timestamp) as period_start_utc
    from {{ source('entsoe', 'a44') }}
) s
left join (
    select distinct zone_eic, period_start_utc
    from {{ ref('stg_entsoe__prices') }}
) m
  on  m.zone_eic         = s.zone_eic
  and m.period_start_utc = s.period_start_utc
where m.zone_eic is null
