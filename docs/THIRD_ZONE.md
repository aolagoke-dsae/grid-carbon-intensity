# Third zone: the diagnostic and the choice

Master Plan §2.3. **Decided 19 October 2026: PL.** The choice was measured, not
assumed, and the rule that made it was committed before the three candidate
payloads existed.

## The question

DE-LU and FR differ in two things at once. Germany is both more carbon-intensive
and more variable within the day than France, so a result that differs between
them cannot say which property caused it: whether shifting load pays because the
mix is dirty, or because the mix changes. A third zone breaks that confound if it
is chosen from the right place, so the three candidates `config/zones.csv` keeps
(NL, PL and IE-SEM) were measured on the same terms as the pair.

## Data

A75 (actual generation per production type, process type A16) for the local
calendar year 2025, one request per zone, the newest accepted retrieval of each:

| Zone | EIC | Retrieved, UTC | Bytes | Resolution |
|---|---|---|---:|---|
| DE-LU | `10Y1001A1001A82H` | 17.10.2026 21:26 | 74,651,377 | PT15M |
| FR | `10YFR-RTE------C` | 17.10.2026 21:29 | 61,736,829 | PT15M |
| NL | `10YNL----------L` | 19.10.2026 20:24 | 67,149,385 | PT15M |
| PL | `10YPL-AREA-----S` | 19.10.2026 20:25 | 56,557,510 | PT15M |
| IE-SEM | `10Y1001A1001A59C` | 19.10.2026 20:26 | 18,864,412 | PT30M |

Each file hashes to the digest in its name and in its row of `raw/manifest.csv`,
and the token is redacted in every logged URL. The three candidates stay in
`raw/`: since commit `3c4457d`, `xml_to_parquet` lands only the zones in the
analysis, so the warehouse and every intensity figure are unchanged.

## Method

`notebooks/third_zone.py` reads each payload with the project's parser
(`entsoe_parse.parse`) and reports three numbers over the zone's complete
hours:

- **level**: the mean intensity weighted by priced energy, at the median
  factors of `config/ipcc_ar5_factors.csv`, gCO2e/kWh;
- **within-day CV**: the coefficient of variation of hourly intensity within
  each complete local day, averaged over the days. It is a CV and not a standard
  deviation, so the level does not leak back into the measure of variability;
- **priced share**: the share of generation that carries a factor.

An hour is complete when every series the zone states in at least 95% of its
hours is stated for all of that hour.

**The rule** was written into the notebook in commit `3c4457d` at 20:12 UTC,
twelve minutes before the first candidate payload was retrieved:

1. A candidate qualifies if its priced share is at least DE-LU's minus 5
   percentage points and at least 300 of its local days are complete.
2. Each zone is placed on a plane with FR at (0, 0) and DE-LU at (1, 1):
   u = (L − L_FR) / (L_DE − L_FR) for the level, v = (C − C_FR) / (C_DE − C_FR)
   for the mean CV. The qualifying candidate furthest from the diagonal,
   measured as |u − v|, is chosen. |u − v| is twice the area of the triangle the
   three zones span, so it is zero when level and variability cannot be told
   apart.
3. If the two best scores lie within 0.1 of each other, the higher priced share
   decides.
4. The choice is rechecked with the median CV in place of the mean.
5. No zone is chosen if DE-LU is not more variable than FR.

## Result

| Zone | Generation in the payload, TWh | Complete hours | Complete days | Level, gCO2e/kWh | Within-day CV, mean (median) | Priced share | Largest unpriced |
|---|---:|---:|---:|---:|---:|---:|---|
| DE-LU | 439.2 | 99.9% | 360 | 352 | 0.265 (0.269) | 95.2% | B10 2.3%, B17 1.3%, B06 0.6% |
| FR | 533.9 | 99.9% | 363 | 32 | 0.144 (0.141) | 97.7% | B10 1.6%, B17 0.6%, B06 0.2% |
| NL | 118.0 | 100.0% | 365 | 406 | 0.224 (0.203) | 64.6% | B20 33.1%, B17 2.4% |
| **PL** | 159.0 | 100.0% | 365 | **664** | **0.150 (0.157)** | 94.8% | B20 3.3%, B06 0.9%, B10 0.7% |
| IE-SEM | 26.9 | 98.6% | 296 | 232 | 0.212 (0.193) | 92.5% | B06 4.4%, B08 1.8%, B10 1.2% |

| Zone | u, level | v, variability | \|u − v\| | Qualifies |
|---|---:|---:|---:|---|
| NL | 1.17 | 0.66 | 0.51 | no: priced share 64.6% against DE-LU's 95.2% |
| **PL** | **1.98** | **0.05** | **1.93** | yes |
| IE-SEM | 0.63 | 0.56 | 0.07 | no: 296 complete days |

Rule 5 holds: DE-LU's CV is 0.265 against FR's 0.144. PL is the only candidate
that qualifies, and it would also lead without rule 1, at 1.93 against 0.51 and
0.07. The median CV gives the same choice.

The parser met no step stated twice in any zone and no code outside its PSR map
except B08 (peat) in IE-SEM, discussed below.

## Why PL breaks the confound

Within the day, PL is as flat as France: a CV of 0.150 against 0.144. Its level
is about twenty times France's, 664 against 32 gCO2e/kWh, and almost twice
Germany's 352. On the plane it sits at (1.98, 0.05), close to the level axis.
That is the cell §2.3 expected Poland to fill, now measured.

With PL, the three zones separate the two properties:

- **FR and PL** share a within-day CV and differ about twentyfold in level, so a
  difference between them comes from the level.
- **DE-LU and PL** reach about the same absolute within-day spread, a mean daily
  standard deviation of 91.4 and 96.5 gCO2e/kWh, from opposite ends. DE-LU gets
  there through relative variability (CV 0.265 at 352), PL through its level
  (0.150 at 664). That spread is roughly what a saving per shifted kWh scales
  with.

PL's flatness is a winter property. Its CV is 0.094 from October to March and
0.206 from April to September, when solar, 12% of its generation, lowers the
midday intensity. The same halves give 0.167 and 0.363 in DE-LU, and 0.136 and
0.152 in FR. A comparison by season should therefore expect PL to look less flat
in summer, though still well below DE-LU.

## Robustness

`python notebooks/third_zone.py --sensitivity` reruns the rule under other
factor tables:

| Factors | NL: level, CV, \|u − v\| | PL: level, CV, \|u − v\| | IE-SEM: level, CV, \|u − v\| | Choice |
|---|---:|---:|---:|---|
| Medians (the result) | 406, 0.224, 0.51 | 664, 0.150, 1.93 | 232, 0.212, 0.07 | PL |
| Every factor at its band minimum | 336, 0.229, 0.71 | 571, 0.158, 2.27 | 192, 0.215, 0.34 | PL |
| Every factor at its band maximum | 544, 0.198, 0.27 | 878, 0.132, 2.01 | 329, 0.180, 0.21 | PL |
| PL's coal at Poland's own values | 406, 0.224, 0.51 | 697, 0.150, 2.03 | 232, 0.212, 0.07 | PL |

The choice is the same with the median CV in every row.

- **Factor bands.** The band ends move every zone at once. PL stays the choice
  and moves further off the diagonal.
- **Zone-agnostic factors.** Polish coal is priced at Germany's values from
  Itten et al. (2023), lignite 1,060 and hard coal 1,040
  (`docs/FACTOR_CHECK.md`, decision 1). The same figure, Fig. 4.5, puts
  Poland's own at 1,094 and 1,115. With those values PL's level rises by 33 to
  697 and its score to 2.03.
- **A second code path.** `xml_to_parquet`'s own parser plus pandas, written
  separately, gives the same level, priced share and both CV statistics to the
  third decimal for all five zones. That path dropped the two clock-change days.
  DE-LU and FR also agree with a query on the warehouse.
- **PL's payload against a published source.** Hard coal and lignite are 52.1%
  of the payload and 52.7% in Forum Energii's review of 2025. Onshore wind is
  13.8% in both. The payload's totals are lower: 52.2 TWh of hard coal against
  57.6, and 30.6 of lignite against 33.5. Its shares, which are what an
  intensity depends on, agree.

## The two candidates not chosen

**NL** fails rule 1 at a priced share of 64.6%. B20 ("Other") is a third of its
payload, 39.0 TWh, and no cited factor can price "other". §2.3's remedy for a
small gap, adding the missing factor with a citation, therefore does not apply.
The payload also falls short of what the Netherlands generated. It holds
0.5 TWh of solar against 25.5 TWh in CBS's provisional 2025 figures, and 7.1 TWh
of onshore wind against 16.4. Its within-day CV is understated as well, and even
as measured it scores 0.51.

**IE-SEM** fails rule 1 on completeness, with 296 complete days, and sits almost
on the diagonal in any case (0.07). Its payload is short too:

- **March 2025.** The payload holds 2,354 GWh of generation for the whole island,
  against March demand of 3,673 GWh in Wind Energy Ireland's figures.
- **Wind share.** Wind is 53% of the payload's first quarter, against the 38%
  Wind Energy Ireland reports.

The payload also contains B08 (peat), 478 GWh in 2025, which §2.3 flagged as
worth a look if it appeared. Bord na Móna announced in January 2024 that
Edenderry had burned peat for the last time. The likeliest reading is that
Edenderry's biomass output is still registered as peat on the platform.
Generation per unit (A73) would settle it but was not pulled. B08 has no row in
the PSR map or in the factor table.

## Limits

- One factor table serves every zone (see Robustness).
- Intensity is production-based, as in the rest of the analysis: generation
  within the zone counts, and imports and exports do not.
- Intensity is hourly. The quarter-hours of DE-LU, FR, NL and PL and the
  IE-SEM half-hours are summed to the hour. The data cover one year, 2025.
- PL's unpriced 5.2% is B20 3.3%, B06 0.9%, B10 0.7% and smaller rows; DE-LU's
  unpriced share is 4.8%.

## What follows

Choosing PL does not yet add it to the analysis. §2.3 schedules the build for
Phase 4 or Modul 10: A44 prices for PL, a third zone through dbt and the marts,
and another column on every Power BI page. Until then `config/zones.csv` keeps
PL at `in_analysis = no`, and nothing in the warehouse changes.

Pulls run by Adewole Olagoke, 19 October 2026, 20:24–20:26 UTC. Measured with
`notebooks/third_zone.py` as committed alongside this record.

## References

Engineers Ireland. (2025). *Wind farms provided 38% of Ireland's electricity in
2025 Q1* (figures from Wind Energy Ireland).
https://www.engineersireland.ie/Engineers-Journal/wind-farms-provided-38-of-irelands-electricity-in-2025-q1

Forum Energii. (2026). *2025_wrapped: A rapid review of the most interesting
power-sector data from 2025*. https://www.forum-energii.eu/en/2025_wrapped

Itten, R., Oberschelp, C., Kröhnert, H., & Stucki, M. (2023). *Life cycle
inventories of solid fossil fuels: Updates for electricity generation from hard
coal, lignite and peat*. ZHAW Zürcher Hochschule für Angewandte
Wissenschaften. https://doi.org/10.21256/zhaw-30218

Midlands 103. (2024, January 2). *Midlands power station stops burning peat
after decades*.
https://www.midlands103.com/news/midlands-news/midlands-power-station-stops-burning-peat-after-decades

Statistics Netherlands. (2026). *Production and export of electricity at record
levels*.
https://www.cbs.nl/en-gb/news/2026/11/production-and-export-of-electricity-at-record-levels
