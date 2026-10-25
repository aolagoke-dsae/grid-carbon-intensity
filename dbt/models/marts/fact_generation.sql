/*  One row per zone, production type, direction and step: exactly the rows
    entsoe_parse.parse() produces from the same payloads, so the mart's row
    count can be checked against the parser's (RUNBOOK Checkpoint 6).

    Each row carries its energy, its median factor and, for priced
    generation, its emissions at that factor. A sum over any grouping is a sum
    of stated rows, and the intensity of any grouping is
    sum(emissions_kg) / sum(mwh) over its priced generation rows. Consumption
    legs keep their energy and carry no emissions: pumping is not generation
    (trap 2). MWh times gCO2e/kWh is kgCO2e.

    source_sha256 is the key of the row's retrieval in raw/manifest.csv
    (tests/assert_every_fact_row_resolves_to_the_manifest.sql).               */
select
    g.zone_eic,
    g.psr_type,
    g.direction,
    g.ts_utc,
    cast(g.ts_utc at time zone 'UTC' at time zone z.iana_tz as date)  as local_date,
    g.resolution,
    g.step_hours,
    g.mw,
    g.mw * g.step_hours                                              as mwh,
    g.direction = 'generation' and p.is_priced                       as is_priced_generation,
    p.ef_median_g_kwh,
    case when g.direction = 'generation' and p.is_priced
         then g.mw * g.step_hours * p.ef_median_g_kwh end            as emissions_kg,
    g.was_carried,
    g.source_sha256
from {{ ref('int_generation_gapfilled') }} g
left join {{ ref('dim_zone') }} z on z.zone_eic = g.zone_eic
left join {{ ref('dim_production_type') }} p on p.psr_type = g.psr_type
