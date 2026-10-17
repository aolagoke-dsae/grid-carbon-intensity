/*  TRAP 4 — the unit is MAW: power, not energy.

    Energy for a step is MW x step_hours. At PT15M that factor is 0.25.
    Weighting an intensity average by MW rather than MWh gives subtly wrong
    answers the moment zones at different resolutions are combined - and
    DE-LU is PT15M while several neighbours still publish PT60M.

    TRAP 3 (PT15M and daylight saving) is not handled here: everything stays
    in UTC. The local calendar day, with its 92- and 100-step edge cases, is
    resolved in dim_date and asserted in tests/assert_step_count_per_local_day.sql. */

select
    zone_eic,
    psr_type,
    ts_utc,
    step_hours,
    resolution,
    generation_mw,
    consumption_mw,
    net_mw,
    generation_mw  * step_hours as generation_mwh,
    consumption_mw * step_hours as consumption_mwh,
    was_carried,
    source_sha256
from {{ ref('int_generation_net') }}
