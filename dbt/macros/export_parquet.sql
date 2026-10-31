{#-
  The post-hook of every mart: a copy of the table just built, as Parquet, in
  GRID_ROOT/exports/<model>.parquet. Power BI Desktop reads that folder, the
  reliable path RUNBOOK's gate describes. exports/ holds ENTSO-E-derived data
  in bulk, so only its README is committed (.gitignore; README, Licence).

  Nothing is written on the `sample` target: its data is synthetic, and its
  build must never overwrite a real export.
-#}
{% macro export_parquet() -%}
{%- if target.name != 'sample' -%}
copy (select * from {{ this }}) to '{{ env_var("GRID_ROOT", "..") }}/exports/{{ this.identifier }}.parquet' (format parquet)
{%- endif -%}
{%- endmacro %}
