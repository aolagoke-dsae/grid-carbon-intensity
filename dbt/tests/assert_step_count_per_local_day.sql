/*  Catches: a naive A03 reader that silently loses most of a day.
    On the real DE-LU payload one series states 5 points for a 96-step day.
    Without expansion this test fails loudly instead of the totals being
    quietly wrong. DST days must show 92 or 100, not be reported as errors. */
with counted as (
    select
        g.zone_eic,
        g.psr_type,
        cast(g.ts_utc at time zone 'UTC' at time zone z.iana_tz as date) as local_date,
        g.step_hours,
        count(*) as steps_present
    from {{ ref('int_generation_energy') }} g
    join {{ ref('dim_zone') }} z on z.zone_eic = g.zone_eic
    group by 1, 2, 3, 4
),
expected as (
    select c.*, d.hours_in_local_day,
           cast(d.hours_in_local_day / c.step_hours as integer) as steps_expected
    from counted c
    join {{ ref('dim_date') }} d
      on d.zone_eic = c.zone_eic and d.local_date = c.local_date
)
select * from expected
where steps_present <> steps_expected
