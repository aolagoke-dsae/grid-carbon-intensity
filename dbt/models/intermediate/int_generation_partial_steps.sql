/*  Steps at which a series the zone publishes is missing: the SQL twin of
    src/checks/validate.incomplete_steps.

    A series counts once it appears anywhere in the zone's rows as
    generation. A step is reported if either leg reports it: RTE's hourly
    A75 states some series net, so a pumping hour carries only the
    consumption leg. A missing series is not required where
    config/sparse_series.csv exempts it on that local day, the same rows the
    coverage test reads: a series published only while a unit runs, one that
    has ended, one not yet published. At any other missing series the mix is
    partial, a recorded source gap say, and fact_intensity withholds the
    step's intensity.                                                          */
with stated as (
    select distinct zone_eic, psr_type, ts_utc
    from {{ ref('int_generation_gapfilled') }}
),
series as (
    select distinct zone_eic, psr_type
    from {{ ref('int_generation_gapfilled') }}
    where direction = 'generation'
),
steps as (
    select distinct
        g.zone_eic,
        g.ts_utc,
        cast(g.ts_utc at time zone 'UTC' at time zone z.iana_tz as date) as local_date
    from {{ ref('int_generation_gapfilled') }} g
    join {{ ref('dim_zone') }} z on z.zone_eic = g.zone_eic
    where g.direction = 'generation'
),
sparse as (
    select
        zone_eic,
        psr,
        cast(nullif(trim(coalesce(from_date, '')), '') as date) as from_date,
        cast(nullif(trim(coalesce(to_date, '')), '') as date)   as to_date
    from read_csv('{{ env_var("GRID_ROOT", "..") }}/config/sparse_series.csv',
                  header = true, all_varchar = true)
),
missing as (
    select st.zone_eic, st.ts_utc, st.local_date, se.psr_type
    from steps st
    join series se on se.zone_eic = st.zone_eic
    left join stated sd
           on  sd.zone_eic = st.zone_eic
           and sd.psr_type = se.psr_type
           and sd.ts_utc   = st.ts_utc
    where sd.zone_eic is null
)
select
    m.zone_eic,
    m.ts_utc,
    count(*)                                         as n_missing,
    string_agg(m.psr_type, ',' order by m.psr_type) as missing_psr_types
from missing m
where not exists (
    select 1
    from sparse sp
    where sp.zone_eic = m.zone_eic
      and sp.psr = m.psr_type
      and (sp.from_date is null or m.local_date >= sp.from_date)
      and (sp.to_date   is null or m.local_date <= sp.to_date))
group by 1, 2
