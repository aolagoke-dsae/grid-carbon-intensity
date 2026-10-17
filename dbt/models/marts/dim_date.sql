/*  TRAP 3 — daylight saving.
    A local calendar day has 23, 24 or 25 hours. At PT15M that is 92, 96 or
    100 steps. A rule asserting "= 96" reports two false failures a year and
    hides real gaps on exactly those days.

    Every day from each zone's first to its last day of generation data is
    generated here. Until 17.10.2026 the days were read from the facts, so a
    day missing from the data was missing from the calendar as well, and the
    coverage test had nothing to compare it with (audit B3).                 */
with span as (
    select
        g.zone_eic,
        z.iana_tz,
        cast(min(g.ts_utc) at time zone 'UTC' at time zone z.iana_tz as date) as first_day,
        cast(max(g.ts_utc) at time zone 'UTC' at time zone z.iana_tz as date) as last_day
    from {{ ref('int_generation_gapfilled') }} g
    join {{ ref('dim_zone') }} z on z.zone_eic = g.zone_eic
    where g.direction = 'generation'
    group by 1, 2
),
days as (
    select
        zone_eic,
        iana_tz,
        cast(unnest(generate_series(
            cast(first_day as timestamp), cast(last_day as timestamp), interval 1 day
        )) as date) as local_date
    from span
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
