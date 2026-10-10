{#-
  TRAP 5 -- the one that cannot be fixed downstream.

  A single DE-LU A44 payload for 2025 contains 732 TimeSeries: two complete,
  disagreeing day-ahead price curves of 366 days each. They share zone,
  businessType A62, contract A01, auction A01, currency and unit. The ONLY
  field that separates them is
      classificationSequence_AttributeInstanceComponent.position
  landed here as classification_sequence.

  Measured on raw/A44/10Y1001A1001A82H/2025.xml, revision 1, on stated
  points -- which is what this model carries:
      curve 1   15,367 pts   PT60M 6,514 + PT15M 8,853
                median 90.80   min -250.32   max 583.40   negative 4.5 %
      curve 2   34,677 pts   PT15M throughout
                median 92.41   min -499.99   max 834.60   negative 6.5 %

  Selecting neither is not an option. `select *` returns both and every
  downstream average becomes a weighted mean of two different markets -- a
  number that is wrong, plausible, and stable enough to go unnoticed.

  DEFAULT: curve 1, overridable with `dbt build --vars '{a44_curve: 2}'`.
  The reason is continuity, not quality. Curve 1 is the series that was
  actually binding at each moment: hourly MTU until the German switch to
  15-minute MTU, then 15-minute. Its resolution changes exactly once, at
  2025-09-30T22:00Z = 1 Oct 2025 00:00 CEST. Curve 2 is 15-minute across the
  whole year, including the nine months before 15-minute MTU went live, so its
  earlier portion cannot be the binding day-ahead result.

  NOT YET SETTLED: which curve ENTSO-E regards as authoritative. The
  independent check is SMARD filter 4169, and the only SMARD file on disk is a
  September 2026 week -- the 2025 weeks still have to be pulled. Until then
  this is a documented default, not a verified one. Curve 2's floor of -499.99
  sits on the EPEX technical limit and it carries 44 % more negative intervals,
  which reads as genuine 15-minute clearing; that is evidence, not proof.
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
    resolution,
    cast(step_hours as double)          as step_hours,
    cast(period_start_utc as timestamp) as period_start_utc,
    cast(position as integer)           as position,
    cast(quantity as double)            as price_eur_mwh,
    -- position is the POINT index within the Period, not the curve id. It
    -- reaches 100 on the 25-hour day. Keeping both columns under distinct
    -- names is the whole point of the rename.
    cast(period_start_utc as timestamp)
      + to_milliseconds(cast(step_hours * (position - 1) * 3600000 as bigint)) as ts_utc
from picked
