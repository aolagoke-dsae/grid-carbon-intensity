/*  Catches: a fact row that cannot be traced to the download it came from.

    RUNBOOK Checkpoint 6. Every landed row carries source_sha256, the digest of
    its payload, and raw/manifest.csv records every retrieval with its digest,
    URL (token redacted), status and time. A fact row whose digest is missing,
    or matches only a rejected retrieval, has no provenance, and provenance is
    a column here, not a comment (docs/ARCHITECTURE.md, honesty rule 3).

    fact_intensity is built from fact_generation alone, so it is covered
    through it.                                                               */
with accepted as (
    select distinct sha256
    from read_csv('{{ env_var("GRID_ROOT", "..") }}/raw/manifest.csv',
                  header = true, all_varchar = true)
    where rejected = '0'
),
digests as (
    select 'fact_generation' as fact, source_sha256, count(*) as n_rows
    from {{ ref('fact_generation') }}
    group by 1, 2
    union all
    select 'fact_price' as fact, source_sha256, count(*) as n_rows
    from {{ ref('fact_price') }}
    group by 1, 2
)
select d.*
from digests d
left join accepted a on a.sha256 = d.source_sha256
where a.sha256 is null
