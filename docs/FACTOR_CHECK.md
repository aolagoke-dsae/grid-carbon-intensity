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
| 1 | B01 | Biomass | Biomass — dedicated | 230 | 130 | 420 | medium | 130 | 230 | 420 | yes | |
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

## The three mapping decisions

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

## If a number differs from the PDF

None did on 18 October 2026. For a later check:

1. Correct the row in `config/ipcc_ar5_factors.csv`, including its `source` column.
2. Run `pytest` and the Checkpoint 4 call, `check_stage4_factors(rows, factors)`.
3. Commit the CSV on its own, with the AR5 values in the commit message.
4. Rerun Stage 5 and `dbt build`: every intensity figure, and `dim_production_type`,
   reads these rows. Stage 8 samples the min and max.

All three decisions were taken on 18 October 2026. Decision 2 changed a value
and went in a commit of its own (`7eb577e`); decisions 1 and 3 changed only the
reasons in the `source` column, the README and the runbook (`5d04521`).

The check is recorded under Checkpoint 4 in the runbook, and this worksheet is
committed as its record.

Confirmed against the PDF by: Adewole Olagoke · 18 October 2026 · IPCC PDF, p. 1335

## References

Guidi, G., Violante, A. C., & De Iuliis, S. (2023). Environmental impact of
electricity generation technologies: A comparison between conventional, nuclear,
and renewable technologies. *Energies, 16*(23), 7847.
https://doi.org/10.3390/en16237847

IPCC. (2014). Annex III: Technology-specific cost and performance parameters
(S. Schlömer et al.). In *Climate Change 2014: Mitigation of Climate Change.
Contribution of Working Group III to the Fifth Assessment Report of the
Intergovernmental Panel on Climate Change*. Cambridge University Press.

Turconi, R., Boldrin, A., & Astrup, T. (2013). Life cycle assessment (LCA) of
electricity generation technologies: Overview, comparability and limitations.
*Renewable and Sustainable Energy Reviews, 28*, 555–565.
https://doi.org/10.1016/j.rser.2013.08.013

Wikipedia. (n.d.). Life-cycle greenhouse gas emissions of energy sources.
Retrieved 18 October 2026, from
https://en.wikipedia.org/wiki/Life-cycle_greenhouse_gas_emissions_of_energy_sources
