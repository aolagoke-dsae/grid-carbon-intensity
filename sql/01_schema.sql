/* Project A - gold layer, Azure SQL.
   Revised after inspecting a real DE-LU A75 payload (2026-08-07):
     - DE-LU publishes at PT15M, so the grain is quarter-hourly, not hourly.
     - Mixed resolutions coexist across zones, so step_hours is a stored column.
     - Generation and consumption arrive in the same document and must be split.
     - Provenance is a NOT NULL column, not a README claim.                     */

IF OBJECT_ID('fact_intensity','U')            IS NOT NULL DROP TABLE fact_intensity;
IF OBJECT_ID('fact_generation_quarterhourly','U') IS NOT NULL DROP TABLE fact_generation_quarterhourly;
IF OBJECT_ID('dim_production_type','U')       IS NOT NULL DROP TABLE dim_production_type;
IF OBJECT_ID('dim_bidding_zone','U')          IS NOT NULL DROP TABLE dim_bidding_zone;
IF OBJECT_ID('ingest_batch','U')              IS NOT NULL DROP TABLE ingest_batch;
GO

CREATE TABLE ingest_batch (
    batch_id        UNIQUEIDENTIFIER  NOT NULL PRIMARY KEY,
    retrieved_at    DATETIME2(0)      NOT NULL,
    source_url      NVARCHAR(500)     NOT NULL,   -- token redacted
    http_status     INT               NOT NULL,
    payload_bytes   BIGINT            NOT NULL CHECK (payload_bytes > 0),
    payload_sha256  CHAR(64)          NOT NULL,
    document_type   CHAR(3)           NOT NULL
);
GO

CREATE TABLE dim_bidding_zone (
    zone_key     INT IDENTITY PRIMARY KEY,
    eic_code     CHAR(16)     NOT NULL UNIQUE,
    zone_key_txt NVARCHAR(16) NOT NULL,
    zone_name    NVARCHAR(80) NOT NULL,
    country_iso2 CHAR(2)      NOT NULL,
    iana_tz      NVARCHAR(40) NOT NULL     -- needed for local-day DST checks
);
GO

CREATE TABLE dim_production_type (
    prod_type_key        INT IDENTITY PRIMARY KEY,
    psr_type             CHAR(3)       NOT NULL UNIQUE,   -- B01..B20
    fuel_name            NVARCHAR(60)  NOT NULL,
    ef_median_g_kwh      DECIMAL(8,2)      NULL,          -- NULL = deliberately unpriced
    ef_min_g_kwh         DECIMAL(8,2)      NULL,
    ef_max_g_kwh         DECIMAL(8,2)      NULL,
    ef_confidence        NVARCHAR(10)  NOT NULL,          -- high|medium|low|unknown|excluded
    ef_source_citation   NVARCHAR(300) NOT NULL,          -- provenance as a control
    CONSTRAINT ck_ef_band CHECK (
        ef_median_g_kwh IS NULL
        OR (ef_min_g_kwh <= ef_median_g_kwh AND ef_median_g_kwh <= ef_max_g_kwh)
    )
);
GO

CREATE TABLE fact_generation_quarterhourly (
    zone_key       INT            NOT NULL REFERENCES dim_bidding_zone(zone_key),
    prod_type_key  INT            NOT NULL REFERENCES dim_production_type(prod_type_key),
    ts_utc         DATETIME2(0)   NOT NULL,
    direction      VARCHAR(11)    NOT NULL CHECK (direction IN ('generation','consumption')),
    step_hours     DECIMAL(4,3)   NOT NULL CHECK (step_hours IN (0.25,0.5,1.0)),
    mw             DECIMAL(14,3)  NOT NULL CHECK (mw >= 0),
    mwh            AS (CAST(mw * step_hours AS DECIMAL(16,4))) PERSISTED,
    was_carried    BIT            NOT NULL,   -- TRUE if value inferred from an A03 gap
    batch_id       UNIQUEIDENTIFIER NOT NULL REFERENCES ingest_batch(batch_id),
    CONSTRAINT pk_fgq PRIMARY KEY (zone_key, prod_type_key, direction, ts_utc)
);
CREATE INDEX ix_fgq_ts ON fact_generation_quarterhourly (ts_utc) INCLUDE (mw, step_hours);
GO

CREATE TABLE fact_intensity (
    zone_key         INT           NOT NULL REFERENCES dim_bidding_zone(zone_key),
    ts_utc           DATETIME2(0)  NOT NULL,
    total_mwh        DECIMAL(16,4) NOT NULL,
    priced_mwh       DECIMAL(16,4) NOT NULL,   -- excludes unpriced psrTypes
    coverage_pct     AS (CASE WHEN total_mwh = 0 THEN NULL
                             ELSE CAST(100.0 * priced_mwh / total_mwh AS DECIMAL(5,2)) END) PERSISTED,
    intensity_median DECIMAL(8,2)  NOT NULL,
    intensity_p05    DECIMAL(8,2)      NULL,
    intensity_p95    DECIMAL(8,2)      NULL,
    mc_draws         INT               NULL,
    method_version   NVARCHAR(20)  NOT NULL,
    CONSTRAINT pk_fi PRIMARY KEY (zone_key, ts_utc),
    CONSTRAINT ck_band CHECK (intensity_p05 IS NULL OR intensity_p05 <= intensity_median),
    CONSTRAINT ck_band2 CHECK (intensity_p95 IS NULL OR intensity_median <= intensity_p95)
);
GO
