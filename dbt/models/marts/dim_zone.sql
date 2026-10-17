/*  Bidding zones, read from config/zones.csv: the file entsoe_client.py uses
    for the request windows, so the two cannot disagree. Until 17.10.2026 two
    zones were hard-coded here, and the rows of any other zone fell out of
    every join to this table, coverage test included (audit B8). iana_tz is
    required: the coverage test resolves the local calendar day, which has
    23, 24 or 25 hours.                                                       */
select
    eic                   as zone_eic,
    "key"                 as zone_key,
    "name"                as zone_name,
    country               as country_iso2,
    tz                    as iana_tz,
    in_analysis = 'yes'   as in_analysis
from read_csv('{{ env_var("GRID_ROOT", "..") }}/config/zones.csv', header = true, all_varchar = true)
