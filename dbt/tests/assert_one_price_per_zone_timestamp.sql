-- The invariant that makes TRAP 5 impossible to reintroduce quietly.
--
-- If the curve filter in stg_entsoe__prices.sql is dropped, weakened, or the
-- a44_curve var selects a value that coexists with another, every timestamp
-- appears twice and this test returns rows. A duplicated timestamp is the
-- failure that produces a plausible wrong average rather than an error, so it
-- has to be asserted rather than eyeballed.
--
-- The opposite mistake -- a curve setting that deletes delivery periods -- is
-- covered by assert_every_price_period_survives_the_curve_filter.sql.
select
    zone_eic,
    ts_utc,
    count(*) as n_rows,
    count(distinct classification_sequence) as n_curves
from {{ ref('stg_entsoe__prices') }}
group by 1, 2
having count(*) > 1
