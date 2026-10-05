/*  Reads config/ipcc_ar5_factors.csv directly rather than via a dbt seed.

    One copy of the factor table, in config/, where intensity.py already reads
    it. A seed would mean a second copy and an inevitable drift between the
    Python interval and the SQL join.

    Note the two distributions: intensity.py fits a LOGNORMAL where the band is
    strongly right-skewed (hydro at 1 / 24 / 2200) and a triangular otherwise.
    This model carries the band, not the sampling — the sampling stays in one
    place, in Python.                                                          */
with src as (
    select * from read_csv_auto('../config/ipcc_ar5_factors.csv', header = true)
)
select
    psr_type,
    fuel                         as fuel_name,
    ef_median_g_kwh,
    ef_min_g_kwh,
    ef_max_g_kwh,
    confidence                   as ef_confidence,
    source                       as ef_source_citation,
    ef_median_g_kwh is not null  as is_priced
from src
