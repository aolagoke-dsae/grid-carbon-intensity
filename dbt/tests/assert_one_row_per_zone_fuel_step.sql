/*  Catches: two rows for one zone, fuel and step after the direction split.

    int_generation_net joins the two legs on step_hours as well, so legs at
    different resolutions cannot be weighted with one step length. If they
    ever meet, they arrive here as two rows instead of a quietly wrong one.  */
select zone_eic, psr_type, ts_utc, count(*) as n_rows
from {{ ref('int_generation_net') }}
group by 1, 2, 3
having count(*) > 1
