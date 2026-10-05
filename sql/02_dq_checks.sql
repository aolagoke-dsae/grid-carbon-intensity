/* Data-quality gate. The DST logic is the part worth talking about in an
   interview: a local calendar day has 23, 24 or 25 hours, so at PT15M the
   expected step count is 92, 96 or 100. A naive "= 96" rule reports two
   false failures a year and hides real gaps on those same days.            */

CREATE OR ALTER VIEW v_dq_step_coverage AS
WITH local_days AS (
    SELECT  f.zone_key,
            z.iana_tz,
            f.prod_type_key,
            f.step_hours,
            CAST(f.ts_utc AT TIME ZONE 'UTC' AT TIME ZONE z.iana_tz AS date) AS local_date,
            COUNT(*) AS steps_present
    FROM    fact_generation_quarterhourly f
    JOIN    dim_bidding_zone z ON z.zone_key = f.zone_key
    WHERE   f.direction = 'generation'
    GROUP BY f.zone_key, z.iana_tz, f.prod_type_key, f.step_hours,
             CAST(f.ts_utc AT TIME ZONE 'UTC' AT TIME ZONE z.iana_tz AS date)
),
expected AS (
    SELECT  ld.*,
            DATEDIFF(hour,
                CAST(ld.local_date AS datetime2) AT TIME ZONE ld.iana_tz,
                CAST(DATEADD(day,1,ld.local_date) AS datetime2) AT TIME ZONE ld.iana_tz
            ) AS hours_in_local_day
    FROM local_days ld
)
SELECT  zone_key, prod_type_key, local_date, step_hours,
        steps_present,
        CAST(hours_in_local_day / step_hours AS int) AS steps_expected,
        hours_in_local_day,
        CASE
          WHEN steps_present = CAST(hours_in_local_day / step_hours AS int)
               AND hours_in_local_day = 23 THEN 'OK_DST_SPRING_FORWARD'
          WHEN steps_present = CAST(hours_in_local_day / step_hours AS int)
               AND hours_in_local_day = 25 THEN 'OK_DST_FALL_BACK'
          WHEN steps_present = CAST(hours_in_local_day / step_hours AS int) THEN 'OK'
          WHEN steps_present <  CAST(hours_in_local_day / step_hours AS int) THEN 'MISSING_STEPS'
          ELSE 'DUPLICATE_STEPS'
        END AS dq_status
FROM expected;
GO

/* Every psrType actually present must resolve to a factor row, priced or
   explicitly unpriced. An unmatched code means silent under-counting.      */
CREATE OR ALTER VIEW v_dq_unmapped_fuels AS
SELECT DISTINCT p.psr_type, p.fuel_name, p.ef_confidence
FROM   fact_generation_quarterhourly f
JOIN   dim_production_type p ON p.prod_type_key = f.prod_type_key
WHERE  f.direction = 'generation'
  AND  p.ef_median_g_kwh IS NULL;
GO

/* How much of each step's energy is actually priced. Below ~95% the
   intensity figure should not be published without a caveat.               */
CREATE OR ALTER VIEW v_dq_factor_coverage AS
SELECT  zone_key, ts_utc, total_mwh, priced_mwh, coverage_pct,
        CASE WHEN coverage_pct >= 99 THEN 'OK'
             WHEN coverage_pct >= 95 THEN 'ACCEPTABLE'
             ELSE 'INSUFFICIENT_COVERAGE' END AS dq_status
FROM    fact_intensity;
GO
