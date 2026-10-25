# curated/sample/ — a synthetic sample

Made, not pulled. Every number in it is invented and nothing comes from
ENTSO-E, so it is MIT like the code. A sample of the real data is not an
option: ENTSO-E's Terms of Use open neither A75 nor A44 for re-use, and any
other re-use needs each data owner's prior agreement (README, **Licence**).

## What it holds

`raw/`, laid out as the pipeline lands the real data: three payloads stored
as `src/ingest/raw_store.py` stores a retrieval, their rows in
`manifest.csv`, and `parquet/` as `src/transform/xml_to_parquet.py` lands
them.

| Payload | Days (local) | What it carries |
|---|---|---|
| A75, DE-LU | 29–30 March 2026, quarter-hourly | the spring transition (92 quarter-hours), A03 carry-forward, a pump-only series |
| A75, France | 25–26 October 2026, hourly, then quarter-hourly | the autumn transition (25 hours), a series stated net, a day that changes resolution, hard coal published only while a unit runs |
| A44, DE-LU | 30 March 2026 | two day-ahead price curves that only `classificationSequence` tells apart (trap 5) |

They are the payloads the dbt fixture tests build on
(`src/transform/sample_data.py`), with France's offshore wind published from
the first day, so the sample builds against the real `config/`.

## Building it

From the repository root, without a token:

```bash
pip install -r requirements.txt
cp dbt/profiles.example.yml dbt/profiles.yml
mkdir -p warehouse
GRID_ROOT=. dbt build --project-dir dbt --profiles-dir dbt --target sample
```

The `sample` target reads `curated/sample/raw/` in place of `raw/` and
writes `warehouse/sample.duckdb`, so the real warehouse is never touched.
CI's dbt job runs this build on every push. It shows that the pipeline runs
from a clean clone; it reproduces no figure. The real figures need the
ENTSO-E pulls (RUNBOOK, Stage 6).

After a change to the fixtures, rebuild the sample with
`python -m src.transform.sample_data`. `src/transform/test_sample_data.py`
fails while the committed sample differs from what the builder makes, or if
a value of the real payload `test_parse.py` quotes appears in it.
