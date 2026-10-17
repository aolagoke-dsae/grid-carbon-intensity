# config/

Four tables, each kept once. They are CSV because DuckDB reads CSV directly, as
`dim_production_type` already does with the factor table, so Python and SQL
read the same file and cannot drift apart.

| File | Read by | What it holds |
|---|---|---|
| `zones.csv` | `entsoe_client.py` (request windows) | Bidding zones with their IANA time zone. `in_analysis` marks the two zones the analysis covers; the other three are kept for the third-zone diagnostic. |
| `sparse_series.csv` | `validate.load_coverage_policy` | Series a zone publishes only while a unit runs. A missing step in them is zero output, not a gap. |
| `source_gaps.csv` | `validate.load_coverage_policy` | Gaps in the published data, recorded after inspection with their size. A gap of exactly the recorded size passes; any other fails. |
| `ipcc_ar5_factors.csv` | `intensity.py`, `dim_production_type` | Emission factor bands per production type, with a citation in every row. |

Verify every EIC in `zones.csv` against the Transparency Platform area list
before trusting it:
<https://transparencyplatform.zendesk.com/hc/en-us/articles/15885757676308>

`zones.csv` and `sparse_series.csv` replaced `zones.yml` on 17 October 2026.
YAML is the one format here that DuckDB cannot read, so a SQL coverage test
could not have seen which series are exempt.

A change to `sparse_series.csv` or `source_gaps.csv` changes what the coverage
checks accept. Make it in a commit of its own, after inspecting the data.
