/* Bidding zones. iana_tz is required: the DST coverage test resolves the local
   calendar day, and a local day has 23, 24 or 25 hours. */
select * from (values
    ('10Y1001A1001A82H', 'DE_LU', 'Germany-Luxembourg', 'DE', 'Europe/Berlin'),
    ('10YFR-RTE------C', 'FR',    'France',             'FR', 'Europe/Paris')
) as t(zone_eic, zone_key, zone_name, country_iso2, iana_tz)
