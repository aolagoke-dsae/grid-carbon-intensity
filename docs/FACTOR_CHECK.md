# Factor check — Checkpoint 4

A worksheet for the hand check that Checkpoint 4 requires: every number in
`config/ipcc_ar5_factors.csv` against IPCC AR5 WG3 Annex III, Table A.III.2.
The CSV columns below are copied from the file as committed on 18 October 2026.

**Source.** IPCC (2014), *Climate Change 2014: Mitigation of Climate Change*,
Working Group III, Annex III: Technology-specific cost and performance
parameters (Schlömer et al.), Table A.III.2, *Emissions of selected electricity
supply technologies* (gCO2eq/kWh), p. 1335.
PDF: <https://www.ipcc.ch/site/assets/uploads/2018/02/ipcc_wg3_ar5_annex-iii.pdf>

**Which columns.** The CSV holds life-cycle factors, so the AR5 columns below
are the *lifecycle emissions (incl. albedo effect)* Min / Median / Max, not the
*direct emissions* columns beside them.

**Where the AR5 values come from.** First filled on 18 October 2026 from the
reproduction of the table in Wikipedia's *Life-cycle greenhouse gas emissions
of energy sources*, because the IPCC PDF could not be opened from the session
that filled them; then confirmed row by row against the PDF itself, p. 1335,
by Adewole Olagoke the same evening. All twelve rows agree with the PDF. The
table's methane column, which the reproduction leaves out, gives hydropower
88 gCO2eq/kWh as a typical value: the evidence for decision 2.

## The 12 priced rows

| # | psrType | ENTSO-E fuel | AR5 row read | CSV median | CSV min | CSV max | Confidence | AR5 min | AR5 median | AR5 max | Match? | Note |
|---|---|---|---|---:|---:|---:|---|---:|---:|---:|---|---|
| 1 | B01 | Biomass | Biomass — dedicated | 230 | 130 | 420 | medium | 130 | 230 | 420 | yes | decision 4 |
| 2 | B02 | Fossil Brown coal/Lignite | Coal — PC (proxy) | 820 | 740 | 910 | low | 740 | 820 | 910 | yes | proxy: decision 1 |
| 3 | B03 | Fossil Coal-derived gas | Coal — PC (proxy) | 820 | 740 | 910 | low | 740 | 820 | 910 | yes | proxy: decision 1 |
| 4 | B04 | Fossil Gas | Gas — Combined Cycle | 490 | 410 | 650 | high | 410 | 490 | 650 | yes | |
| 5 | B05 | Fossil Hard coal | Coal — PC | 820 | 740 | 910 | high | 740 | 820 | 910 | yes | |
| 6 | B09 | Geothermal | Geothermal | 38 | 6 | 79 | high | 6.0 | 38 | 79 | yes | |
| 7 | B11 | Hydro Run-of-river | Hydropower | 24 | 1 | 2200 | medium | 1.0 | 24 | 2200 | yes | decision 2: CSV max now 24 |
| 8 | B12 | Hydro Water Reservoir | Hydropower | 24 | 1 | 2200 | medium | 1.0 | 24 | 2200 | yes | decision 2 |
| 9 | B14 | Nuclear | Nuclear | 12 | 3.7 | 110 | high | 3.7 | 12 | 110 | yes | |
| 10 | B16 | Solar | Solar PV — utility | 48 | 18 | 180 | high | 18 | 48 | 180 | yes | decision 3 |
| 11 | B18 | Wind Offshore | Wind offshore | 12 | 8 | 35 | high | 8.0 | 12 | 35 | yes | |
| 12 | B19 | Wind Onshore | Wind onshore | 11 | 7 | 56 | high | 7.0 | 11 | 56 | yes | |

All twelve rows match the reproduction, so on this evidence no CSV value needs
correcting. The same table gives Solar PV — rooftop as 26 / 41 / 60, used in
decision 3.

Not in this check: B06 oil, B15 other renewable, B17 waste and B20 other are
unpriced, and B10 pumped storage and B25 batteries are excluded as storage. The
priced share they leave is accepted and stated (Checkpoint 4, decided 18.10.2026).

## The mapping decisions

Measured on the 2021–2025 data with `src/transform/intensity.py` (method
2.0.0), applied to each zone-year's annual generation mix: the point is the
intensity at the median factors, the interval the Monte Carlo 90% interval,
10,000 draws at the module's default seed. Shares are of priced generation.

### 1. Lignite (B02) and coal-derived gas (B03) on the coal row

Lignite is 16–22% of DE-LU's priced generation in 2021–2025; coal-derived gas
is about 1% from 2023, the first year it is published. AR5 has one coal row,
740 / 820 / 910. The lignite literature sits above it: Turconi et al. (2013)
give an overall range of 900–1,300 gCO2eq/kWh for lignite, against
750–1,050 for hard coal in direct combustion.

| DE-LU, gCO2eq/kWh | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|
| Point, as now | 339.2 | 360.7 | 321.3 | 302.0 | 298.8 |
| 90% interval, as now | 326–373 | 347–393 | 309–357 | 289–342 | 286–337 |
| Lignite at 900 instead of 820 | +16.0 | +17.3 | +14.4 | +13.6 | +12.8 |
| Lignite at 1,300 | +96.2 | +103.9 | +86.5 | +81.8 | +77.1 |
| Coal-derived gas, per +100 on its factor | — | — | +1.1 | +1.1 | +1.0 |

The proxy understates DE-LU, and above roughly 970–1,050 gCO2eq/kWh for
lignite, depending on the year, the corrected point would lie above DE-LU's
current 90% interval. Most of Turconi's range is above that.

**Recommendation, taken 18.10.2026 (commit `5d04521`).** Keep B02 on the coal
row for the figures published at WE 3,
marked `low`, and state the direction and the size of the error beside them.
The error lowers DE-LU's figures, so it cannot flatter the contrast with
France. Before Stage 8, replace B02 with a lignite factor that has a published
median and band; until then, run Stage 8 with B02 at 900 and at 1,300 as a
stated sensitivity and check whether the load-shift recommendation changes.
Keep B03 on the coal row: at about 1% of generation, every 100 gCO2eq/kWh its
true factor sits above 820 adds about 1 to DE-LU.

**A replacement, searched for on 19.10.2026.** No source publishes a median
with a range for lignite alone. The search covered Scite and the web:
harmonisation studies, reviews, life-cycle inventory reports and German agency
data. What exists, in gCO2eq/kWh:

| Source | Centre | Range | Catch |
|---|---|---|---|
| World Nuclear Association (2011) | 1,054, a mean | 790–1,372 | The only source with both. A mean, from the nuclear industry's trade body, with no per-study values; its own Figure 2 gives 1,069 |
| Itten et al. (2023) | — | 1,000–1,350, across countries | Per country, for the Swiss UVEK life-cycle inventory database. Germany's value is in section 4.2.4 and has not been read yet |
| Turconi et al. (2013) | — | 900–1,300, seven studies | The range used above |
| Ladage et al. (2021) | 1,052, Germany 2018 | — | CO2 only, with the supply chain; a point |
| ifeu (2015), quoted in Deutscher Bundestag (2015) | 1,183, Germany | — | A point, second-hand |

Whitaker et al. (2012) harmonised coal as a whole: median 980, interquartile
range 930–1,050. Lignite is in that pool but not reported on its own.

Measured as above, with decision 2's B11 band in place:

| DE-LU, gCO2eq/kWh | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|
| As now: point (90% interval) | 339.2 (324.7–366.2) | 360.7 (345.6–387.4) | 321.3 (307.5–348.5) | 302.0 (287.8–330.1) | 298.8 (284.5–327.6) |
| WNA, 1,054 (790–1,372) | 386.1 (347.5–440.0) | 411.4 (369.3–468.1) | 363.5 (328.9–412.9) | 341.9 (308.2–390.0) | 336.3 (304.2–383.1) |
| Itten's range, centre 1,052 (Ladage) | 385.7 (374.1–437.1) | 410.9 (398.9–464.9) | 363.1 (351.9–410.2) | 341.6 (329.8–387.5) | 336.0 (323.9–381.1) |
| Itten's range, centre 1,183 (ifeu) | 411.9 (385.1–446.8) | 439.3 (410.3–475.0) | 386.7 (362.4–419.9) | 363.9 (340.2–397.8) | 357.1 (334.1–390.9) |

Every candidate's point lies above the current interval in every year. With
decision 2 in place the interval is narrower than in the first table, and any
lignite factor above about 945–1,000, depending on the year, puts the point
outside it. WNA's band would make the interval 1.8–2.4 times as wide, lignite
then owning 52–68% of its width; Itten's range makes it 1.3–1.6 times as wide.

**Decision, taken 19.10.2026.** Before Stage 8, replace B02 with Germany's value
from Itten et al. (2023) as the centre, labelled a country value rather than a
median, and their range across countries, 1,000–1,350, as the band. It is one
recent source, resolved by country, covering mining, supply and the plant. Its
range is the spread across countries' fleets rather than uncertainty about
Germany's, in the way that AR5's ranges are the spread across studies. Until
Germany's value has been read off section 4.2.4 (p. 53 in the report's table of
contents), B02 stays on the coal row and Stage 8 runs the 900 and 1,300
sensitivity. If Germany's value cannot be had, the fallback is WNA's 1,054
(790–1,372), its centre labelled a mean.

Germany's lignite value, Itten et al. (2023), section 4.2.4: ______ kgCO2eq/kWh ·
read by ______ · date ______

### 2. One hydropower row for run-of-river (B11) and reservoirs (B12)

| | France | DE-LU |
|---|---:|---:|
| Run-of-river, share of priced generation | 7–9% | 2–4% |
| Its share of the interval's variance | 65–71% | 20–42% |
| Its share of the interval's width | 35–40% | 9–20% |
| 90% interval width, as now, gCO2eq/kWh | 74–84 | 46–53 |
| Width with B11 at 1 / 24 / 24 | 48–51 | 41–43 |

AR5's single hydropower row runs from 1 to 2,200. In the life-cycle
literature the high values come from reservoirs, where flooded organic matter
decays to methane; Turconi et al. (2013) report 2–5 gCO2eq/kWh for run-of-river
plants and 11–20 for dam reservoirs in the studies they reviewed, and name
reservoir methane as the source of the large variation. A run-of-river plant
has no reservoir, yet under the current mapping its share of that tail decides
most of France's interval. Reported as it stands, Stage 8 would name
run-of-river hydro as France's dominant uncertainty, which is a property of
the band rather than of the plants.

**Recommendation, taken 18.10.2026 (commit `7eb577e`).** Split the mapping. B12 keeps AR5's hydropower row as it is.
B11 keeps AR5's minimum and median and sets its maximum to the median,
1 / 24 / 24, with the reason in the `source` column. `load_factors` accepts a
band whose maximum equals its median, and the sampler then draws only between
1 and 24, so the published median stays the median. The point does not move;
France's interval narrows by 35–40%. A median of 24 sits at the top of
the run-of-river evidence, between Turconi's 2–5 and a median of 23 found by another
study that Guidi et al. (2023) review, so it errs high. If a
run-of-river source with a published minimum, median and maximum turns up,
use it instead.

### 3. Utility (B16 on Solar PV — utility) versus rooftop

| | DE-LU | France |
|---|---:|---:|
| Solar, share of priced generation | 9.5–17.7% | 2.7–5.8% |
| Point if B16 used rooftop (26 / 41 / 60) | −0.7 to −1.2 | −0.2 to −0.4 |
| Upper end of the 90% interval | −2.3 to −5.5 | −0.5 to −0.7 |

**Recommendation, taken 18.10.2026 (commit `5d04521`).** Keep utility PV and
record why. ENTSO-E's B16 does not
separate rooftop from ground-mounted plants; utility's band, 18–180, contains
rooftop's, 26–60, so the interval stays on the safe side; and the medians
differ by 7 gCO2eq/kWh, which moves DE-LU by at most 1.2 and France by at most
0.4. A blended factor would be a number no table publishes, for less than a
gram.

### 4. Biomass (B01) on AR5's dedicated-biomass row

AR5's biomass row covers dedicated energy crops and crop residues only.
Germany's biomass category is broader. Of its 42–47 TWh of biomass electricity
outside waste plants in 2021–2025, 65–67% is biogas, 23–24% solid biomass,
6–7% biomethane and about 4% sewage and landfill gas (Umweltbundesamt, 2026,
Table 3). ENTSO-E's B01 is 82–86% of that total; the measurement assumes it has
the same mix. Biogenic waste, 5.4–5.8 TWh, is left out, because ENTSO-E
reports waste under B17.

The Umweltbundesamt publishes a life-cycle factor for each pathway, in
gCO2eq/kWh of electricity:

| Pathway | As of 08/2019 | 2024, provisional (as of 09/2025) |
|---|---:|---:|
| Solid biomass | 74 | 63 |
| Liquid biomass | 203 | 676 |
| Biogas | 345 | 282 |
| Biomethane | 291 | 259 |
| Sewage gas | 126 | 103 |
| Landfill gas | 126 | 134 |

Weighted by each year's mix, the 2024 factors give a German biomass factor of
222–225 and the 2019 factors 267–271; without sewage and landfill gas, in case
ENTSO-E counts them elsewhere, 227–230 and 273–276. AR5's row is 230 (130–420).

| DE-LU, gCO2eq/kWh | 2021 | 2022 | 2023 | 2024 | 2025 |
|---|---:|---:|---:|---:|---:|
| Biomass, share of priced generation | 7.9% | 8.0% | 8.7% | 8.8% | 8.6% |
| Point, UBA 2024 factors | −0.4 | −0.4 | −0.7 | −0.6 | −0.7 |
| Point, UBA 2019 factors | +3.2 | +3.2 | +3.2 | +3.5 | +3.3 |
| Bound: all solid biomass (63) | −13.1 | −13.3 | −14.5 | −14.6 | −14.4 |
| Bound: all biogas (345) | +9.0 | +9.1 | +10.0 | +10.1 | +9.9 |
| Biomass's share of the interval's width, as now | 7% | 8% | 10% | 10% | 9% |

Without sewage and landfill gas the point moves by −0.3 to 0.0 with the 2024
factors and by +3.6 to +4.0 with the 2019 ones. With AR5's band scaled to the
German value, the interval changes by at most 1.8. France's biomass is 0.5–0.8% of its priced generation, and France moves
by under 0.4. For the biomass error to equal the smallest lignite error in the
first table (+12.8 in 2025), Germany's biomass factor would have to be 376–393,
about 1.7 times the 2024 value.

Two limits on the UBA numbers. They charge part of each CHP plant's emissions
to its heat (the Finnish method) and leave out land-use change (Lauf et al.,
2026), so a factor charging everything to electricity would be higher. And
they were read from the data labels of two UBA slides (Lauf, 2025; Lauf et
al., 2019), because the report's own tables (Climate Change 11/2026, sections
4.6–4.10) could not be opened from the session that measured them. On both
slides every biomass label checks against the others, the gross avoidance
factor minus the emission factor giving the net one, but the values still want the
check against the report that AR5 had.

**Decision, taken 19.10.2026.** Keep B01 on AR5's row and state the error in
its `source` column. The German value lies inside the row's band, from 8 below
its median to 46 above, and moves DE-LU by at most 4.0, about a tenth of what
the lignite candidates do. The row matters through its band instead: at
130–420 it already owns 7–10% of DE-LU's interval width.

UBA biomass factors checked against Climate Change 11/2026, sections 4.6–4.10:
______ · by ______ · date ______

## If a number differs from the PDF

None did on 18 October 2026. For a later check:

1. Correct the row in `config/ipcc_ar5_factors.csv`, including its `source` column.
2. Run `pytest` and the Checkpoint 4 call, `check_stage4_factors(rows, factors)`.
3. Commit the CSV on its own, with the AR5 values in the commit message.
4. Rerun Stage 5 and `dbt build`: every intensity figure, and `dim_production_type`,
   reads these rows. Stage 8 samples the min and max.

Decisions 1–3 were taken on 18 October 2026. Decision 2 changed a value
and went in a commit of its own (`7eb577e`); decisions 1 and 3 changed only the
reasons in the `source` column, the README and the runbook (`5d04521`).
On 19 October 2026 decision 1 gained its replacement and decision 4 was taken;
both changed reasons only, no value.

The check is recorded under Checkpoint 4 in the runbook, and this worksheet is
committed as its record.

Confirmed against the PDF by: Adewole Olagoke · 18 October 2026 · IPCC PDF, p. 1335

## References

Deutscher Bundestag, Wissenschaftliche Dienste. (2015). *CO2-Bilanz der
Nutzung fossiler Energieträger zur Stromerzeugung* (WD 8 - 3000 - 038/15).
https://www.bundestag.de/resource/blob/405734/9e7caa5246d56ad7d823cd0328543d91/wd-8-038-15-pdf-data.pdf

Guidi, G., Violante, A. C., & De Iuliis, S. (2023). Environmental impact of
electricity generation technologies: A comparison between conventional, nuclear,
and renewable technologies. *Energies, 16*(23), 7847.
https://doi.org/10.3390/en16237847

IPCC. (2014). Annex III: Technology-specific cost and performance parameters
(S. Schlömer et al.). In *Climate Change 2014: Mitigation of Climate Change.
Contribution of Working Group III to the Fifth Assessment Report of the
Intergovernmental Panel on Climate Change*. Cambridge University Press.

Itten, R., Oberschelp, C., Kröhnert, H., & Stucki, M. (2023). *Life cycle
inventories of solid fossil fuels: Updates for electricity generation from hard
coal, lignite and peat*. ZHAW Zürcher Hochschule für Angewandte
Wissenschaften. https://doi.org/10.21256/zhaw-30218

Ladage, S., Blumenberg, M., Franke, D., et al. (2021). On the climate benefit
of a coal-to-gas shift in Germany's electric power sector. *Scientific Reports,
11*. https://doi.org/10.1038/s41598-021-90839-7

Lauf, T. (2025). *Emissionsbilanz erneuerbarer Energieträger mit dem Fokus auf
Windenergie* [Conference presentation]. Windenergietage 2025, 13 November 2025.
Umweltbundesamt.
https://windenergietage.de/2025/wp-content/uploads/sites/10/2025/09/Lauf-Emmissionsbilanz.pdf

Lauf, T., Memmler, M., & Schneider, S. (2019). *Ergebnisse und Ausblick der
Emissionsbilanzierung erneuerbarer Energien* [Workshop presentation].
Dessau-Roßlau, 26 November 2019. Umweltbundesamt.
https://www.umweltbundesamt.de/sites/default/files/medien/376/dokumente/7_lauf_ergebnisse_der_emissionsbilanz_erneuerbarer_energietraeger.pdf

Lauf, T., Memmler, M., & Schneider, S. (2026). *Emissionsbilanz erneuerbarer
Energieträger 2024: Bestimmung der vermiedenen Emissionen im Jahr 2024*
(Climate Change 11/2026). Umweltbundesamt.
https://www.umweltbundesamt.de/system/files/medien/11850/publikationen/2026-01/11_2026_CC.pdf

Turconi, R., Boldrin, A., & Astrup, T. (2013). Life cycle assessment (LCA) of
electricity generation technologies: Overview, comparability and limitations.
*Renewable and Sustainable Energy Reviews, 28*, 555–565.
https://doi.org/10.1016/j.rser.2013.08.013

Umweltbundesamt. (2026). *Zeitreihen zur Entwicklung der erneuerbaren
Energien in Deutschland*, Tabelle 3: Bruttostromerzeugung aus erneuerbaren
Energien (Stand: Februar 2026).
https://www.umweltbundesamt.de/system/files/document/zeitreihen-zur-entwicklung-der-erneuerbaren-energien-in-deutschland-excel_uba_deu_0_0.xlsx.pdf

Whitaker, M., Heath, G. A., O'Donoughue, P., et al. (2012). Life cycle
greenhouse gas emissions of coal-fired electricity generation. *Journal of
Industrial Ecology, 16*(S1). https://doi.org/10.1111/j.1530-9290.2012.00465.x

Wikipedia. (n.d.). Life-cycle greenhouse gas emissions of energy sources.
Retrieved 18 October 2026, from
https://en.wikipedia.org/wiki/Life-cycle_greenhouse_gas_emissions_of_energy_sources

World Nuclear Association. (2011). *Comparison of lifecycle greenhouse gas
emissions of various electricity generation sources*.
https://world-nuclear.org/images/articles/comparison_of_lifecycle.pdf
