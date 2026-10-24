# Against Electricity Maps: the cross-check and the difference explained

RUNBOOK Checkpoint 5. **Run on 25.10.2026. The timing agrees; the level is
not settled.** The rule, committed in `6ee3cf2` before the first run, failed:
recomputed with Electricity Maps' own factors, our parse lands 7.2% (2024) and
4.8% (2025) above their published production-based means. Their extreme hours
and days are extreme in our series too, and seven of their eight seasonal
peaks and troughs fall on our hours. On energy-weighted means the gap is 2.9% and 0.4%, but
their page does not say which mean it reports.

## What was accessible

Electricity Maps sells its hourly series. None of the free routes fits a
public repository (checked 24.10.2026): the API has no free tier, only a
14-day trial (since 22.12.2025) whose data are for evaluation and must be
deleted afterwards; the five free CSV datasets a year are for internal Scope 2
accounting; academic access needs an address at an
accredited academic or research institution. Two things are public, and the
check uses only those:

- **Their method for Germany**, open source in
  [electricitymaps-contrib](https://github.com/electricitymaps/electricitymaps-contrib)
  (AGPL-3.0; values cited here, nothing copied). `DATA_SOURCES.md` names
  ENTSO-E as Germany's source of generation data, as it is ours. Their
  ENTSO-E parser maps each PsrType to a production mode, and
  `config/zones/DE.yaml`, with `config/defaults.yaml` where DE has no entry,
  gives each mode a life-cycle and a direct factor by year.
- **Their results for Germany**, on
  [Grid in Review 2025: Germany](https://www.electricitymaps.com/grid-in-review-2025/germany):
  the mean intensity of 2024 and 2025, production-based and flow-traced; the
  lowest and highest hour and day of each year; and the peak and trough of
  each season's mean day in 2025. Flow-traced figures count imports. The page
  states neither its time zone nor its factor type.

Both were read on 25.10.2026.

## Data

A75 for DE-LU (`10Y1001A1001A82H`), the newest accepted retrieval of each
year: 2024 retrieved 18.10.2026 00:19 UTC, 2025 retrieved 17.10.2026 21:26
UTC, both in `raw/manifest.csv`. Their area is Germany alone,
`10Y1001A1001A83F`, without Luxembourg.

## Method

`notebooks/em_crosscheck.py` computes three intensities for every complete
UTC hour, from one parse:

- **A, ours**: our median factors over the fuels we price, as Checkpoint 5
  computes it;
- **B, their factors**: their life-cycle factors on the same fuels, so B − A
  is the factor set;
- **C, their factors and coverage**: their factors on everything their parser
  counts as production, adding waste (as biomass), other and other renewable
  (as unknown), oil and storage discharge, so C − B is the coverage, and C is
  the counterpart of their production-based series.

An hour is complete when none of its quarter-hours is withheld and steps are
stated for all of it: 8,780 of 8,784 hours in 2024 and 8,749 of 8,760 in 2025.

**The rule**, written before the first run:

1. Hours as above.
2. A year's mean is the plain mean of its hourly intensities, with the
   energy-weighted mean reported beside it.
3. C agrees with their production-based mean if it lies within ±2% of it, in
   2024 and in 2025; then the difference is explained, and if not, it is
   investigated first.
4. Their extreme hours and days and their 2025 seasonal peaks and troughs are
   reported beside A, B and C, each time read as local time and as UTC, with
   no threshold, since those figures are flow-traced.

## Result

Mean intensity, gCO₂e/kWh: plain mean of hours, energy-weighted in brackets.

| Year | A, ours | B, their factors | C, their factors and coverage | Theirs, production-based | C against it | Theirs, flow-traced |
|---|---:|---:|---:|---:|---:|---:|
| 2024 | 375.4 (357.4) | 395.7 (376.5) | 394.3 (378.5) | 367.8 | +7.2% | 334.5 |
| 2025 | 370.4 (352.1) | 381.1 (361.9) | 379.8 (364.0) | 362.5 | +4.8% | 335.4 |

**Rule 3 fails in both years.** As stated, that means the generation data
disagree until shown otherwise.

## The investigation, after the run

Written after the result, changing nothing in it.

**Which mean.** On energy-weighted means C lies 2.9% (2024) and 0.4% (2025)
above their production-based means. Neither the page nor their methodology
page says how hours are averaged into a year.

**Which clock.** Read as UTC, seven of their eight 2025 seasonal peaks and
troughs fall on the same hour as C's, and the spring peak one hour away
(03:00 against 02:00). Read as local time, none does. Their times are UTC.

**Which hours.** Their extreme hours and days, as UTC, ranked in our series:

| Their figure | Time | Theirs | A | C | Rank in A | Rank in C |
|---|---|---:|---:|---:|---:|---:|
| Lowest hour 2024 | 23.08. 10:00 | 112.2 | 111 | 116 | 1 of 8,780 | 1 |
| Highest hour 2024 | 28.12. 01:00 | 651.1 | 707 | 745 | 21 | 21 |
| Lowest hour 2025 | 26.10. 09:00 | 97.0 | 93 | 102 | 1 of 8,749 | 3 |
| Highest hour 2025 | 24.03. 02:00 | 632.7 | 725 | 747 | 2 | 1 |
| Lowest day 2024 | 27.09. | 145.5 | 144 | 160 | 1 of 366 | 1 |
| Highest day 2024 | 11.01. | 589.1 | 638 | 671 | 5 | 4 |
| Lowest day 2025 | 04.10. | 111.3 | 109 | 120 | 1 of 365 | 1 |
| Highest day 2025 | 02.02. | 559.6 | 617 | 634 | 5 | 4 |

If our series were joined to the wrong hours, these would be ordinary hours
in it. They are its extremes: the lowest hour of each year is ours too, and
2025's highest is C's highest.

**Which factors.** On their direct factors C comes to 313.4 (2024) and 298.8
(2025), energy-weighted, far below their 367.8 and 362.5. Their published
figures are life-cycle, like ours.

**Verdict.** The timing of our series is confirmed by an independent one, a
second time after the solar peak of the week plot. The level is not
settled: within 0.4% in 2025 and 2.9% in 2024 if their mean is
energy-weighted, 4.8% and 7.2% if it is a plain mean. Three causes remain
open and cannot be told apart from public data: Luxembourg in our area, their
validation and gap-filling, and the factors' vintage (those cited are the
files of 25.10.2026, which may postdate the page). Their production-based
hourly series would settle it, and so would an A75 pull for `10Y1001A1001A83F`.

## The difference, explained

For 2025, energy-weighted, from our 352.1 gCO₂e/kWh to their headline 335.4:

| Step | gCO₂e/kWh | What it is |
|---|---:|---|
| A, ours | 352.1 | over the 95.2% of generation we price |
| Factor set | +9.8 | coal +13.4 (lignite +8.5, hard coal +4.9), gas +1.9, coal-derived gas −3.1, solar −2.3, hydro −0.4, wind +0.4 |
| Coverage | +2.2 | oil +4.5, other and other renewable +2.0, pumped-storage discharge −2.6, waste −1.7 |
| C | 364.0 | |
| Residual | −1.5 | to their production-based mean |
| Theirs, production-based | 362.5 | |
| Imports | −27.1 | their own figures |
| Theirs, flow-traced | 335.4 | |

**The factor set** is almost all coal. They price lignite and hard coal as one
mode, at 1,112.7 for 2025: EU-ETS verified emissions over ENTSO-E
generation, plus IPCC 2014's upstream share. Ours are 1,060 and 1,040, Germany's
values in Itten et al. (2023). Against that, they price coal-derived gas as
gas (503 against our 820) and solar at 35 against our 48. In 2024 their coal
factor is 1,140.4, and the factor set adds +19.1.

**The coverage** is the 4.8% of generation we leave unpriced. They price
oil at 1,070 and other generation at 700, both above the mix's mean, and
pumped-storage discharge at 246 and waste, as biomass, at 230, both below it.
The two directions nearly cancel.

**Imports** are the large part. Germany imported 63.15 TWh in 2025 and
exported 44.29, by their figures. The largest sources, Denmark (21.56 TWh at
110 g), France (17.72 TWh at 30 g) and Norway (15.57 TWh at 28 g), are far
cleaner than German generation, so the consumed mix is 27.1 g cleaner than the
generated one, 33.3 g in 2024. The hours fit: at their lowest hours their
flow-traced figure is 4–5 g below C, at their highest 94–114 g below it.
Imports lower the dirtiest hours most and barely touch the cleanest, though
four hours are an illustration, not a test.

**Life-cycle versus combustion plays no part.** Both sides use life-cycle
factors.

On plain means instead, the residual is −17.3 (2025) and −26.5 (2024). It is
small only if their mean is energy-weighted, which is the open point above.

Sources: Electricity Maps, Grid in Review 2025: Germany, and
electricitymaps-contrib (`DATA_SOURCES.md`, `config/zones/DE.yaml`,
`config/defaults.yaml`, `electricitymap/contrib/parsers/ENTSOE.py`), read on
25.10.2026. No data of theirs is stored in this repository beyond the
published figures cited above.
