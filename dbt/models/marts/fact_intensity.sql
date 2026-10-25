/*  The intensity of every generation step with its Monte Carlo interval. The
    point is the SQL twin of RUNBOOK Checkpoint 5,
    intensity.deterministic_intensity over the steps validate.incomplete_steps
    leaves complete.

    intensity_g_kwh is the energy-weighted mean of the median factors over
    the fuels that carry one, emissions_kg / priced_mwh. Unpriced fuels are
    left out of both sides, so every value describes priced_share_pct of the
    step's generation, and that share stands beside it ("every intensity
    figure carries its priced share", README). A step at which a series the
    zone publishes is missing is partial (int_generation_partial_steps): its
    mix is biased by what is absent, so its intensity is withheld, and the
    missing series are named.

    A step where series of different resolution meet is withheld as well
    (is_mixed_resolution): a per-step mix would put an hour of energy into a
    quarter-hour. The 2021-2025 pulls have none; the fixture's French day that
    changes resolution has 23. tests/assert_intensity_recomputed_from_the_mix.sql
    fails on any value reported at one.

    The interval is the 5th to 95th percentile of the step's mix under the
    factor draws every step shares (dim_factor_draw, int_intensity_interval),
    reported and withheld with the point. p50 is the median of the draws: it
    sits above the point wherever the bands reach further above their median
    than below it, and the point must lie inside the interval
    (tests/assert_deterministic_within_mc_interval.sql).                     */
with steps as (
    select
        zone_eic,
        ts_utc,
        min(local_date)                                                  as local_date,
        min(step_hours)                                                  as step_hours,
        count(distinct step_hours)                                       as n_step_lengths,
        sum(mwh)                                                         as total_mwh,
        coalesce(sum(case when is_priced_generation then mwh end), 0)    as priced_mwh,
        coalesce(sum(emissions_kg), 0)                                   as emissions_kg
    from {{ ref('fact_generation') }}
    where direction = 'generation'
    group by 1, 2
),

judged as (
    select
        s.*,
        p.zone_eic is not null                                           as is_partial,
        p.missing_psr_types,
        p.zone_eic is null and s.n_step_lengths = 1 and s.priced_mwh > 0 as is_reported
    from steps s
    left join {{ ref('int_generation_partial_steps') }} p
           on  p.zone_eic = s.zone_eic
           and p.ts_utc   = s.ts_utc
)

select
    j.zone_eic,
    j.ts_utc,
    j.local_date,
    j.step_hours,
    j.n_step_lengths,
    j.n_step_lengths > 1                                                  as is_mixed_resolution,
    j.total_mwh,
    j.priced_mwh,
    case when j.total_mwh > 0 then 100 * j.priced_mwh / j.total_mwh end  as priced_share_pct,
    j.emissions_kg,
    j.is_partial,
    j.missing_psr_types,
    case when j.is_reported then j.emissions_kg / j.priced_mwh end        as intensity_g_kwh,
    case when j.is_reported then q.intensity_p05_g_kwh end                as intensity_p05_g_kwh,
    case when j.is_reported then q.intensity_p50_g_kwh end                as intensity_p50_g_kwh,
    case when j.is_reported then q.intensity_p95_g_kwh end                as intensity_p95_g_kwh,
    case when j.is_reported then q.mc_draws end                           as mc_draws
from judged j
left join {{ ref('int_intensity_interval') }} q
       on  q.zone_eic = j.zone_eic
       and q.ts_utc   = j.ts_utc
