/*  One day-ahead price per zone and delivery step, every step of every
    period: the curve trap 5 selects (stg_entsoe__prices), with A03's
    repeated prices carried forward (int_prices_gapfilled).

    The step is the market time unit: hourly, and 15-minute from 1 October
    2025 in DE-LU and from 30 September 2025 in France. A price is per MWh, so
    no conversion applies; negative prices are real and left alone.

    source_sha256 is the key of the row's retrieval in raw/manifest.csv
    (tests/assert_every_fact_row_resolves_to_the_manifest.sql).               */
select
    p.zone_eic,
    p.ts_utc,
    cast(p.ts_utc at time zone 'UTC' at time zone z.iana_tz as date)  as local_date,
    p.resolution,
    p.step_hours,
    p.price_eur_mwh,
    p.classification_sequence,
    p.was_carried,
    p.source_sha256
from {{ ref('int_prices_gapfilled') }} p
left join {{ ref('dim_zone') }} z on z.zone_eic = p.zone_eic
