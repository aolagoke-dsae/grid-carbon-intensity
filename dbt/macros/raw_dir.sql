{#-
  The landed data the models read: raw/ under GRID_ROOT, or the synthetic
  sample in curated/sample/raw/ on the `sample` target, which builds
  warehouse/sample.duckdb from it (dbt/profiles.example.yml). Both hold
  manifest.csv and parquet/ at the same places. The sources in
  models/staging/_sources.yml repeat this choice inline, because YAML is
  rendered without the project's macros.
-#}
{% macro raw_dir() -%}
{{ env_var('GRID_ROOT', '..') }}/{{ 'curated/sample/raw' if target.name == 'sample' else 'raw' }}
{%- endmacro %}
