/*  The intensity of each zone and local calendar year, with its 90% interval:
    the first defensible number (RUNBOOK Stage 6, WE 6), as a table the
    Power BI page of WE 7 reads from exports/.

    Over the steps fact_intensity reports: the point is emissions over priced
    energy at the median factors, as Checkpoint 5 computes it. The interval
    comes from the draws every step shares (dim_factor_draw): each draw's
    factors weighted by the year's priced energy by fuel, then the 5th, 50th
    and 95th percentiles over the draws. A factor's error is the same in
    every hour, so the year's interval is as wide as its errors; drawn afresh
    at each step they would average out and the interval would shrink.
    check_stage6_marts recomputes every row from the parser's rows.            */
with years as (
    select
        zone_eic,
        year(local_date)                                                   as year,
        count(*)                                                           as n_steps,
        count(intensity_g_kwh)                                             as n_reported,
        sum(total_mwh) filter (where intensity_g_kwh is not null)          as total_mwh,
        sum(priced_mwh) filter (where intensity_g_kwh is not null)         as priced_mwh,
        sum(emissions_kg) filter (where intensity_g_kwh is not null)       as emissions_kg
    from {{ ref('fact_intensity') }}
    group by 1, 2
),

mix as (
    select g.zone_eic, year(i.local_date) as year, g.psr_type, sum(g.mwh) as mwh
    from {{ ref('fact_generation') }} g
    join {{ ref('fact_intensity') }} i
      on  i.zone_eic = g.zone_eic
      and i.ts_utc   = g.ts_utc
    where g.is_priced_generation and i.intensity_g_kwh is not null
    group by 1, 2, 3
),

drawn as (
    select m.zone_eic, m.year, d.draw_id, sum(m.mwh * d.ef_g_kwh) / sum(m.mwh) as g_kwh
    from mix m
    join {{ ref('dim_factor_draw') }} d on d.psr_type = m.psr_type
    group by 1, 2, 3
),

band as (
    select
        zone_eic,
        year,
        quantile_cont(g_kwh, 0.05) as p05,
        quantile_cont(g_kwh, 0.50) as p50,
        quantile_cont(g_kwh, 0.95) as p95,
        count(*)                   as mc_draws
    from drawn
    group by 1, 2
)

select
    y.zone_eic,
    y.year,
    y.n_steps,
    y.n_reported,
    y.total_mwh,
    y.priced_mwh,
    100 * y.priced_mwh / y.total_mwh   as priced_share_pct,
    y.emissions_kg / y.priced_mwh       as intensity_g_kwh,
    b.p05                               as intensity_p05_g_kwh,
    b.p50                               as intensity_p50_g_kwh,
    b.p95                               as intensity_p95_g_kwh,
    b.mc_draws
from years y
left join band b
       on  b.zone_eic = y.zone_eic
       and b.year     = y.year
