/*  Catches: a fact that counts a step twice. fact_generation's grain is zone,
    production type, direction and step; fact_intensity's and fact_price's
    are zone and step. A second row would double the energy, the emissions or
    the weight of a price, and every sum built on it would stay plausible.  */
select 'fact_generation' as fact, zone_eic, ts_utc, psr_type || ' ' || direction as key, count(*) as n_rows
from {{ ref('fact_generation') }}
group by 1, 2, 3, 4
having count(*) > 1
union all
select 'fact_intensity', zone_eic, ts_utc, '', count(*)
from {{ ref('fact_intensity') }}
group by 1, 2, 3, 4
having count(*) > 1
union all
select 'fact_price', zone_eic, ts_utc, '', count(*)
from {{ ref('fact_price') }}
group by 1, 2, 3, 4
having count(*) > 1
