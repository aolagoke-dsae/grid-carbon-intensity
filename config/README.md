# config/

Four tables, each kept once. They are CSV because DuckDB reads CSV directly, as
`dim_production_type` already does with the factor table, so Python and SQL
read the same file and cannot drift apart.

| File | Read by | What it holds |
|---|---|---|
| `zones.csv` | `entsoe_client.py` (request windows), `dim_zone` | Bidding zones with their IANA time zone. `in_analysis` marks the two zones the analysis covers; the other three are kept for the third-zone diagnostic, measured from `raw/` by `notebooks/third_zone.py` and never landed (`xml_to_parquet` skips them). |
| `sparse_series.csv` | `validate.load_coverage_policy`, `assert_step_count_per_local_day` | Series whose missing step is not a gap. A row without dates: published only while a unit runs, so a missing step is zero output. A row with `from_date` and/or `to_date`, local days, both inclusive: exempt inside that window only — a series that has ended, or one not yet published. |
| `source_gaps.csv` | `validate.load_coverage_policy`, `assert_step_count_per_local_day` | Gaps in the published data, recorded after inspection with their size. A gap of exactly the recorded size passes; any other fails. |
| `ipcc_ar5_factors.csv` | `intensity.py`, `dim_production_type` | Emission factor bands per production type, with a citation in every row: IPCC AR5 for all but lignite and hard coal, which carry Germany's values from Itten et al. (2023) since 19 October 2026 (`docs/FACTOR_CHECK.md`, decision 1). |

Verify every EIC in `zones.csv` against the Transparency Platform area list
before trusting it:
<https://transparencyplatform.zendesk.com/hc/en-us/articles/15885757676308>

`zones.csv` and `sparse_series.csv` replaced `zones.yml` on 17 October 2026.
YAML is the one format here that DuckDB cannot read, so the SQL coverage test
could not see which series are exempt. `from_date` and `to_date` were added on
18 October 2026, for German nuclear after April 2023, German coal-derived gas
before 2023 and French offshore wind before June 2023. On the 2021–2025 pulls
the SQL test and `check_stage3_coverage` agree exactly: with `source_gaps.csv`
emptied, both report the same 101 gaps, and none with it.

A change to `sparse_series.csv` or `source_gaps.csv` changes what the coverage
checks accept. Make it in a commit of its own, after inspecting the data.
