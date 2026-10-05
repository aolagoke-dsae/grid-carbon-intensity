/*  TRAP 1 — curveType A03 omits repeated values.

    A real DE-LU payload states 5 points for a 96-step day on psrType B15.
    A naive read emits 5 rows and silently loses 95% of that day: no error,
    just wrong totals. Here the full position scaffold is generated and the
    last stated value is carried forward.

    was_carried is kept so the share of inferred values stays auditable.      */

with periods as (
    select distinct
        zone_eic, psr_type, direction,
        period_start_utc, resolution, step_hours, n_steps
    from {{ ref('stg_entsoe__generation') }}
),

scaffold as (
    select
        p.zone_eic, p.psr_type, p.direction,
        p.period_start_utc, p.resolution, p.step_hours, p.n_steps,
        unnest(generate_series(1, p.n_steps)) as position
    from periods p
),

joined as (
    select
        s.*,
        g.quantity_mw
    from scaffold s
    left join {{ ref('stg_entsoe__generation') }} g
           on  g.zone_eic         = s.zone_eic
           and g.psr_type         = s.psr_type
           and g.direction        = s.direction
           and g.period_start_utc = s.period_start_utc
           and g.position         = s.position
),

filled as (
    select
        *,
        last_value(quantity_mw ignore nulls) over (
            partition by zone_eic, psr_type, direction, period_start_utc
            order by position
            rows between unbounded preceding and current row
        ) as mw_filled,
        quantity_mw is null as was_carried
    from joined
)

select
    zone_eic,
    psr_type,
    direction,
    resolution,
    step_hours,
    n_steps,
    position,
    period_start_utc
      + to_milliseconds(cast(step_hours * (position - 1) * 3600000 as bigint)) as ts_utc,
    mw_filled as mw,
    was_carried
from filled
where mw_filled is not null          -- leading gaps before the first stated point
