/*  TRAP 1 — curveType A03 omits repeated values.

    A real DE-LU payload states 5 points for a 96-step day on psrType B15.
    A naive read emits 5 rows and silently loses 95% of that day: no error,
    just wrong totals. Here the full position scaffold is generated and, for
    A03, the last stated value is carried forward.

    Only A03. An A01 series states every position, so a missing one is
    missing data: it stays NULL and the not_null test on mw fails. Until
    17.10.2026 both curve types were carried forward alike (audit A6). An
    A03 series without a position 1 leaves NULL leading rows that the same
    test catches; they used to be filtered out without a word.

    was_carried is kept so the share of inferred values stays auditable.      */

with periods as (
    select distinct
        zone_eic, psr_type, direction, curve_type, source_sha256,
        period_start_utc, resolution, step_hours, n_steps
    from {{ ref('stg_entsoe__generation') }}
),

scaffold as (
    select
        p.*,
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
        case
            when curve_type = 'A03' then last_value(quantity_mw ignore nulls) over (
                partition by zone_eic, psr_type, direction, period_start_utc
                order by position
                rows between unbounded preceding and current row
            )
            else quantity_mw
        end                                         as mw_filled,
        quantity_mw is null and curve_type = 'A03'  as was_carried
    from joined
)

select
    zone_eic,
    psr_type,
    direction,
    curve_type,
    resolution,
    step_hours,
    n_steps,
    position,
    period_start_utc
      + to_milliseconds(cast(step_hours * (position - 1) * 3600000 as bigint)) as ts_utc,
    mw_filled as mw,
    was_carried,
    source_sha256
from filled
