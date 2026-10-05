/*  Catches: an unattributed number.
    A figure without provenance is not auditable. Same discipline as the
    EUDR validator, different field.                                       */
select psr_type, fuel_name, ef_median_g_kwh, ef_source_citation
from {{ ref('dim_production_type') }}
where ef_source_citation is null
   or trim(ef_source_citation) = ''
