/*  Catches: a biased sampler. The acceptance criterion of the whole build:
    the deterministic point, every fuel at its median factor, must fall inside
    the 90% interval built around it. If it escapes, the propagation is wrong,
    not the estimate, and no figure is published (README). In Python the same
    criterion is tested on 729 French-like mixes
    (src/transform/test_intensity.py); here it is checked at every step the
    warehouse reports, and for every yearly figure.

    Disabled until 25.10.2026, while no fact carried both the point and the
    band. Until 17.10.2026 this file was a `select ... where false` guard,
    which dbt reported as a PASS although it tested nothing (audit B7).

    A row is returned for a reported point without a full interval, an
    interval without a point, bounds out of order, or a point outside them.
    The bounds are percentiles of floating-point draws, so a point equal to
    one, as at a fuel whose median is the top of its band, passes within
    1e-9.                                                                     */
with judged as (
    select zone_eic, cast(ts_utc as varchar) as step_or_year, intensity_g_kwh, intensity_p05_g_kwh,
           intensity_p50_g_kwh, intensity_p95_g_kwh
    from {{ ref('fact_intensity') }}
    union all
    -- the yearly figures too, since 31.10.2026: the number that is published
    select zone_eic, cast(year as varchar), intensity_g_kwh, intensity_p05_g_kwh,
           intensity_p50_g_kwh, intensity_p95_g_kwh
    from {{ ref('fact_intensity_year') }}
)
select
    zone_eic,
    step_or_year,
    intensity_p05_g_kwh,
    intensity_g_kwh,
    intensity_p95_g_kwh
from judged
where (intensity_g_kwh is not null
       and (intensity_p05_g_kwh is null or intensity_p50_g_kwh is null or intensity_p95_g_kwh is null))
   or (intensity_g_kwh is null
       and (intensity_p05_g_kwh is not null or intensity_p50_g_kwh is not null or intensity_p95_g_kwh is not null))
   or intensity_p05_g_kwh > intensity_p50_g_kwh
   or intensity_p50_g_kwh > intensity_p95_g_kwh
   or intensity_g_kwh < intensity_p05_g_kwh - 1e-9 * greatest(abs(intensity_p05_g_kwh), 1)
   or intensity_g_kwh > intensity_p95_g_kwh + 1e-9 * greatest(abs(intensity_p95_g_kwh), 1)
