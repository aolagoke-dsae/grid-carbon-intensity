/*  TRAP 4 — daylight saving.
    A local calendar day has 23, 24 or 25 hours. At PT15M that is 92, 96 or
    100 steps. A rule asserting "= 96" reports two false failures a year and
    hides real gaps on exactly those days.                                   */
with days as (
    select distinct
        z.zone_eic,
        z.iana_tz,
        cast(g.ts_utc at time zone 'UTC' at time zone z.iana_tz as date) as local_date
    from {{ ref('int_generation_energy') }} g
    join {{ ref('dim_zone') }} z on z.zone_eic = g.zone_eic
),
enriched as (
    select
        zone_eic, local_date, iana_tz,
        date_diff('hour',
            cast(local_date as timestamp) at time zone iana_tz,
            cast(local_date + interval 1 day as timestamp) at time zone iana_tz
        ) as hours_in_local_day
    from days
)
select
    zone_eic, local_date, iana_tz, hours_in_local_day,
    date_part('year', local_date)   as year,
    date_part('month', local_date)  as month,
    date_part('isodow', local_date) as iso_weekday,
    date_part('isodow', local_date) >= 6 as is_weekend,
    hours_in_local_day <> 24             as is_dst_transition
from enriched
