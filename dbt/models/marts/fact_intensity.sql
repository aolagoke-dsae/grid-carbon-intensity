/*  The deterministic intensity of every generation step: the SQL twin of
    RUNBOOK Checkpoint 5, intensity.deterministic_intensity over the steps
    validate.incomplete_steps leaves complete.

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

    The Monte Carlo interval is not here yet: RUNBOOK Stage 6, WE 6.          */
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
)
select
    s.zone_eic,
    s.ts_utc,
    s.local_date,
    s.step_hours,
    s.n_step_lengths,
    s.n_step_lengths > 1                                                  as is_mixed_resolution,
    s.total_mwh,
    s.priced_mwh,
    case when s.total_mwh > 0 then 100 * s.priced_mwh / s.total_mwh end  as priced_share_pct,
    s.emissions_kg,
    p.zone_eic is not null                                                as is_partial,
    p.missing_psr_types,
    case when p.zone_eic is null and s.n_step_lengths = 1 and s.priced_mwh > 0
         then s.emissions_kg / s.priced_mwh end                           as intensity_g_kwh
from steps s
left join {{ ref('int_generation_partial_steps') }} p
       on  p.zone_eic = s.zone_eic
       and p.ts_utc   = s.ts_utc
