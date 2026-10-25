/*  Catches: an intensity that is not the median-factor mean of its step's
    complete mix. The SQL twin of src/checks/validate.check_stage5_intensity.

    The mix is rebuilt here from the gap-filled generation legs and the
    factor file itself, not from fact_generation's energy and emissions
    columns or dim_production_type, so a wrong join or a wrong unit in the fact
    path cannot also be in the check. A row is returned for
      - a step of the mix without an intensity row, or the reverse;
      - a reported value at a partial step, or at a step where series of
        different resolution meet, which would put an hour of energy into a
        quarter-hour; or a withheld value at a complete step with priced
        energy;
      - a value that differs from the recomputed mean: MWh on one side of the
        ratio and MW on the other, a consumption leg in the mix, a factor
        other than the median.
    A plausibility band could catch none of these: a weighted mean is
    unchanged when every weight is scaled (audit A10).                        */
with priced as (
    -- a median AND a band, as intensity.Factor.priced
    select psr_type, ef_median_g_kwh
    from read_csv_auto('{{ env_var("GRID_ROOT", "..") }}/config/ipcc_ar5_factors.csv',
                       header = true)
    where ef_median_g_kwh is not null
      and ef_min_g_kwh is not null
      and ef_max_g_kwh is not null
),
mix as (
    select
        g.zone_eic,
        g.ts_utc,
        count(distinct g.step_hours)                                          as n_step_lengths,
        sum(case when f.psr_type is not null
                 then g.mw * g.step_hours * f.ef_median_g_kwh end)
          / nullif(sum(case when f.psr_type is not null
                            then g.mw * g.step_hours end), 0)                 as recomputed
    from {{ ref('int_generation_gapfilled') }} g
    left join priced f
           on f.psr_type = g.psr_type
    where g.direction = 'generation'
    group by 1, 2
)
select
    coalesce(m.zone_eic, i.zone_eic) as zone_eic,
    coalesce(m.ts_utc, i.ts_utc)     as ts_utc,
    m.recomputed,
    i.intensity_g_kwh,
    i.is_partial,
    m.n_step_lengths
from mix m
full outer join {{ ref('fact_intensity') }} i
       on  i.zone_eic = m.zone_eic
       and i.ts_utc   = m.ts_utc
where m.zone_eic is null
   or i.zone_eic is null
   or ((i.is_partial or m.n_step_lengths > 1) and i.intensity_g_kwh is not null)
   or (not i.is_partial and m.n_step_lengths = 1 and (
           (m.recomputed is not null and i.intensity_g_kwh is null)
        or (m.recomputed is null and i.intensity_g_kwh is not null)
        or abs(i.intensity_g_kwh - m.recomputed) > 1e-9 * greatest(abs(m.recomputed), 1)))
