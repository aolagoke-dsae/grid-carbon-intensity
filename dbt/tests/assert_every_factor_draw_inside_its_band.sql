/*  Catches: draws that are not draws of dim_production_type's factors. A
    row is returned for a priced fuel without draws, draws for a fuel the
    table does not price, a fuel with fewer draws than the others, or a draw
    outside its fuel's published band.

    dim_factor_draw is drawn in Python from the factor file under GRID_ROOT,
    dim_production_type read from it in SQL. A build that pointed the two at
    different files, or a sampler that let a draw escape its band, would
    otherwise pass every other test: the intervals are not recomputed in SQL. */
with drawn as (
    select psr_type, count(*) as n_draws, min(ef_g_kwh) as lowest, max(ef_g_kwh) as highest
    from {{ ref('dim_factor_draw') }}
    group by 1
)
select
    coalesce(p.psr_type, d.psr_type) as psr_type,
    p.is_priced,
    d.n_draws,
    d.lowest,
    d.highest,
    p.ef_min_g_kwh,
    p.ef_max_g_kwh
from {{ ref('dim_production_type') }} p
full outer join drawn d on d.psr_type = p.psr_type
where (p.is_priced and d.psr_type is null)
   or (d.psr_type is not null and (p.psr_type is null or not p.is_priced))
   or d.n_draws <> (select max(n_draws) from drawn)
   or d.lowest  < p.ef_min_g_kwh - 1e-9 * p.ef_min_g_kwh
   or d.highest > p.ef_max_g_kwh + 1e-9 * p.ef_max_g_kwh
