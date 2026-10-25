/*  TRAP 1, for prices: curveType A03 omits a price that repeats.

    The day-ahead curves are A03 step curves, and a stated-point model loses
    every repeated price: 116 of curve 1's 15,483 steps in DE-LU's 2025 (0.75%),
    which a join on ts_utc silently drops. Here, as for generation, the full
    position scaffold of every period is generated and an A03 price is
    carried forward from the last stated one. An A01 price is never carried:
    a missing one stays NULL, and the not_null test on fact_price fails.
    entsoe_prices_parse.parse_prices expands the same way, and
    src/transform/test_dbt_models.py compares the two.

    Trap 5 is resolved before this model: stg_entsoe__prices keeps one curve
    per delivery period, so a scaffold never mixes curves.                     */
with periods as (
    select distinct
        zone_eic, classification_sequence, curve_type, source_sha256,
        period_start_utc, resolution, step_hours, n_steps
    from {{ ref('stg_entsoe__prices') }}
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
        g.price_eur_mwh
    from scaffold s
    left join {{ ref('stg_entsoe__prices') }} g
           on  g.zone_eic         = s.zone_eic
           and g.period_start_utc = s.period_start_utc
           and g.position         = s.position
           and g.classification_sequence is not distinct from s.classification_sequence
),

filled as (
    select
        *,
        case
            when curve_type = 'A03' then last_value(price_eur_mwh ignore nulls) over (
                partition by zone_eic, classification_sequence, period_start_utc
                order by position
                rows between unbounded preceding and current row
            )
            else price_eur_mwh
        end                                            as price_filled,
        price_eur_mwh is null and curve_type = 'A03'   as was_carried
    from joined
)

select
    zone_eic,
    classification_sequence,
    curve_type,
    resolution,
    step_hours,
    n_steps,
    position,
    period_start_utc
      + to_milliseconds(cast(step_hours * (position - 1) * 3600000 as bigint)) as ts_utc,
    price_filled as price_eur_mwh,
    was_carried,
    source_sha256
from filled
