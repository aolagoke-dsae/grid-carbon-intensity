/*  Catches: a missing step, a missing day, and a daylight-saving day counted
    as 24 hours. The SQL twin of check_stage3_coverage, reading the same two
    policy files, so the two cannot disagree.

    Every generation series of a zone is checked on every day of the zone's
    calendar in dim_date, so a day with no rows at all shows as 0 of 96.
    Until 17.10.2026 only the (zone, fuel, day) combinations that had rows
    were counted, and dim_date came from the same rows: a missing day passed,
    and RUNBOOK Checkpoint 7's "delete a day" could not fail (audit B3).

    Two rules since 18.10.2026, as in find_gaps:
      - a step counts if either leg reports it. RTE's hourly A75 states
        pumped storage, reservoir hydro and coal net, one leg per hour, so a
        pumping hour has no generation row. Only generation series are
        checked; a consumption leg only covers;
      - coverage is measured in time, on a quarter-hour grid, not by counting
        rows: France moved from PT60M to PT15M on 19.12.2024, and that day
        has one hourly row and 92 quarter-hours. steps_present and
        steps_expected are in the finest step of the day.

    A shortfall passes in two cases only:
      - config/sparse_series.csv exempts the series on that day: on every
        day where the row has no dates (published only while a unit runs),
        else from from_date to to_date, local days, both inclusive (a series
        that has ended, or one not yet published);
      - config/source_gaps.csv records a gap of exactly that size for that
        zone, day and fuel.
    A series absent on a day is measured in the zone's finest step that day,
    and in its own latest step only on a day when the zone has no row at all:
    French offshore wind is absent on whole days in June 2023, when France
    published hourly, and its latest rows are quarter-hours.                  */
with legs as (
    select
        g.zone_eic,
        g.psr_type,
        g.direction,
        g.ts_utc,
        g.step_hours,
        cast(g.ts_utc at time zone 'UTC' at time zone z.iana_tz as date) as local_date
    from {{ ref('int_generation_gapfilled') }} g
    join {{ ref('dim_zone') }} z on z.zone_eic = g.zone_eic
),
series as (
    select zone_eic, psr_type, arg_max(step_hours, ts_utc) as series_step
    from legs
    where direction = 'generation'
    group by 1, 2
),
zone_day as (
    select zone_eic, local_date, min(step_hours) as zone_step
    from legs
    group by 1, 2
),
quarters as (
    select
        l.zone_eic, l.psr_type, l.local_date, l.ts_utc, l.step_hours,
        unnest(generate_series(0, cast(round(l.step_hours * 4) as integer) - 1)) as q
    from legs l
    join series s on s.zone_eic = l.zone_eic and s.psr_type = l.psr_type
),
counted as (
    select
        zone_eic, psr_type, local_date,
        count(distinct ts_utc + to_minutes(cast(15 * q as bigint))) as quarters_present,
        min(step_hours)                                             as day_step
    from quarters
    group by 1, 2, 3
),
expected as (
    select
        d.zone_eic,
        s.psr_type,
        d.local_date,
        d.hours_in_local_day,
        cast(round(coalesce(c.quarters_present, 0) * 0.25
                   / coalesce(c.day_step, zd.zone_step, s.series_step)) as integer) as steps_present,
        cast(round(d.hours_in_local_day
                   / coalesce(c.day_step, zd.zone_step, s.series_step)) as integer) as steps_expected
    from {{ ref('dim_date') }} d
    join series s on s.zone_eic = d.zone_eic
    left join counted c
           on  c.zone_eic   = d.zone_eic
           and c.psr_type   = s.psr_type
           and c.local_date = d.local_date
    left join zone_day zd
           on  zd.zone_eic   = d.zone_eic
           and zd.local_date = d.local_date
),
sparse as (
    select
        zone_eic,
        psr,
        cast(nullif(trim(coalesce(from_date, '')), '') as date) as from_date,
        cast(nullif(trim(coalesce(to_date, '')), '') as date)   as to_date
    from read_csv('{{ env_var("GRID_ROOT", "..") }}/config/sparse_series.csv',
                  header = true, all_varchar = true)
),
recorded as (
    select zone_eic, cast(local_date as date) as local_date, psr,
           cast(missing_steps as integer) as missing_steps
    from read_csv('{{ env_var("GRID_ROOT", "..") }}/config/source_gaps.csv',
                  header = true, all_varchar = true)
)
select e.*
from expected e
left join recorded r
       on r.zone_eic = e.zone_eic and r.local_date = e.local_date and r.psr = e.psr_type
where e.steps_present <> e.steps_expected
  and not (e.steps_present < e.steps_expected and exists (
        select 1
        from sparse sp
        where sp.zone_eic = e.zone_eic
          and sp.psr = e.psr_type
          and (sp.from_date is null or e.local_date >= sp.from_date)
          and (sp.to_date   is null or e.local_date <= sp.to_date)))
  and not coalesce(e.steps_present < e.steps_expected
                   and r.missing_steps = e.steps_expected - e.steps_present, false)
