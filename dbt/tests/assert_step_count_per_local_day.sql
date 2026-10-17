/*  Catches: a missing step, a missing day, and a daylight-saving day counted
    as 24 hours. The SQL twin of check_stage3_coverage, reading the same two
    policy files, so the two cannot disagree.

    Every generation series of a zone is checked on every day of the zone's
    calendar in dim_date, so a day with no rows at all shows as 0 of 96.
    Until 17.10.2026 only the (zone, fuel, day) combinations that had rows
    were counted, and dim_date came from the same rows: a missing day passed,
    and RUNBOOK Checkpoint 7's "delete a day" could not fail (audit B3).

    A shortfall passes in two cases only:
      - the series is in config/sparse_series.csv: published only while a
        unit runs, so a missing step is zero output;
      - config/source_gaps.csv records a gap of exactly that size for that
        zone, day and fuel.
    A series absent on a day takes its step length from its latest row.     */
with gen as (
    select
        g.zone_eic,
        g.psr_type,
        g.ts_utc,
        g.step_hours,
        cast(g.ts_utc at time zone 'UTC' at time zone z.iana_tz as date) as local_date
    from {{ ref('int_generation_gapfilled') }} g
    join {{ ref('dim_zone') }} z on z.zone_eic = g.zone_eic
    where g.direction = 'generation'
),
series as (
    select zone_eic, psr_type, arg_max(step_hours, ts_utc) as series_step
    from gen
    group by 1, 2
),
counted as (
    select
        zone_eic, psr_type, local_date,
        count(distinct ts_utc)       as steps_present,
        arg_max(step_hours, ts_utc)  as day_step
    from gen
    group by 1, 2, 3
),
expected as (
    select
        d.zone_eic,
        s.psr_type,
        d.local_date,
        d.hours_in_local_day,
        coalesce(c.steps_present, 0) as steps_present,
        cast(round(d.hours_in_local_day / coalesce(c.day_step, s.series_step)) as integer)
                                     as steps_expected
    from {{ ref('dim_date') }} d
    join series s on s.zone_eic = d.zone_eic
    left join counted c
           on  c.zone_eic   = d.zone_eic
           and c.psr_type   = s.psr_type
           and c.local_date = d.local_date
),
sparse as (
    select zone_eic, psr
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
left join sparse sp
       on sp.zone_eic = e.zone_eic and sp.psr = e.psr_type
left join recorded r
       on r.zone_eic = e.zone_eic and r.local_date = e.local_date and r.psr = e.psr_type
where e.steps_present <> e.steps_expected
  and not (e.steps_present < e.steps_expected and sp.psr is not null)
  and not coalesce(e.steps_present < e.steps_expected
                   and r.missing_steps = e.steps_expected - e.steps_present, false)
