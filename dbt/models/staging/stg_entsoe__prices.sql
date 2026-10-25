{#-
  TRAP 5 -- the one that cannot be fixed downstream.

  A single DE-LU A44 payload for 2025 contains 732 TimeSeries: two complete,
  disagreeing day-ahead price curves of 366 days each. They share zone,
  businessType A62, contract A01, auction A01, currency and unit. The ONLY
  field that separates them is
      classificationSequence_AttributeInstanceComponent.position
  landed here as classification_sequence.

  Measured on raw/A44/10Y1001A1001A82H/2025/20261006T183150Z_9d48b590.xml,
  revision 1, on stated points -- which is what this model carries:
      curve 1   15,367 pts   PT60M 6,514 + PT15M 8,853
                median 90.80   min -250.32   max 583.40   negative 4.5 %
      curve 2   34,677 pts   PT15M throughout
                median 92.41   min -499.99   max 834.60   negative 6.5 %

  Selecting neither is not an option. `select *` returns both and every
  downstream average becomes a weighted mean of two different markets -- a
  number that is wrong, plausible, and stable enough to go unnoticed.

  DEFAULT: curve 1, overridable with `dbt build --vars '{a44_curve: 2}'`.
  Curve 1 is the day-ahead market's: hourly MTU until the German switch to
  15-minute MTU, then 15-minute. Its resolution changes exactly once, at
  2025-09-30T22:00Z = 1 Oct 2025 00:00 CEST. Curve 2 is 15-minute across the
  whole year, including the nine months before 15-minute MTU went live, so its
  earlier portion cannot be the binding day-ahead result.

  VERIFIED 19.10.2026 against SMARD filter 4169, the Bundesnetzagentur's
  day-ahead price, for every week of 2025 (notebooks/price_curves.py, rule
  fixed before the pull). Curve 1 equals SMARD to the cent at all 6,551 hours
  before the go-live and all 8,836 quarter-hours after it, its 93
  carried-forward A03 steps included. Curve 2 agrees at 0.23 % and 0.03 %,
  off by 7.9 and 11.7 EUR/MWh on average. The default was chosen for
  continuity on 08.10.2026; it now rests on that check. Curve 2's limits
  (-149.99 to 2,999.99 in 2021-2023) fit EXAA's separate 10:15 auction;
  that is circumstantial. 2021-2024, pulled the same evening and hourly
  throughout: curve 1 equals SMARD at every hour of every year, 35,064 in
  all; the means of curve 2's quarter-hours come within a cent at
  0.10-0.29 %.
-#}

with src as (

    select * from {{ source('entsoe', 'a44') }}

),

-- How many curves does each zone publish IN EACH DELIVERY PERIOD? Counted per
-- period, not per zone: a zone can publish one curve in one year and two in
-- the next, and counting across all years would filter the single-curve year
-- by a curve id it never carried, deleting it. count(distinct ...) ignores
-- nulls, so a period that omits the field scores 0, not 1 -- hence <= 1 below.
-- The parser leaves the column null rather than defaulting it to 1, because a
-- default would make a single-curve period indistinguishable from the first
-- curve of a two-curve one. FR, PL, NL and IE-SEM are expected to land here as
-- single-curve. A setting naming a curve that a two-curve period does not
-- carry still deletes that period: assert_every_price_period_survives_the_
-- curve_filter.sql fails when it does.
curve_count as (

    select
        zone_eic,
        period_start_utc,
        count(distinct classification_sequence) as n_curves
    from src
    group by 1, 2

),

picked as (

    select src.*
    from src
    join curve_count
      on  curve_count.zone_eic         = src.zone_eic
      and curve_count.period_start_utc = src.period_start_utc
    where curve_count.n_curves <= 1
       or src.classification_sequence = {{ var('a44_curve', 1) }}

)

select
    zone_eic,
    classification_sequence,
    curve_type,
    resolution,
    cast(step_hours as double)          as step_hours,
    cast(n_steps as integer)            as n_steps,
    cast(period_start_utc as timestamp) as period_start_utc,
    cast(position as integer)           as position,
    cast(quantity as double)            as price_eur_mwh,
    -- position is the POINT index within the Period, not the curve id. It
    -- reaches 100 on the 25-hour day. Keeping both columns under distinct
    -- names is the whole point of the rename.
    cast(period_start_utc as timestamp)
      + to_milliseconds(cast(step_hours * (position - 1) * 3600000 as bigint)) as ts_utc,
    source_sha256
from picked
