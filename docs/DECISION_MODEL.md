# The decision model: the design, fixed before any run

*Fixed on 31.10.2026, before any shift was computed, and confirmed the same day
by Adewole Olagoke: the six items at the end stand as drafted. Nothing here is
built or run yet. The commit is the record, as for every rule in this
repository, and a section written after the run will say so.*

## The question

For a plant that can move a block of load within the day, what does moving it
save, in euros and in tCO₂e, per zone, and with what uncertainty? And does the
result bear out the hypothesis recorded on 10.10.2026 (README, `e0102a0`): the
CO₂ saving differs sharply between DE-LU and FR, while the cost saving exists
in both?

## What is known before the rules

No shift has been computed, but the intensity a shift acts on has been
measured, so every rule below is set knowing this:

| 2025 | Level, gCO₂e/kWh | Within-day CV | Mean daily SD, gCO₂e/kWh |
|---|---:|---:|---:|
| DE-LU | 352 | 0.265 | 91.4 |
| FR | 32 | 0.144 | 4.6 |

The levels come from `fact_intensity_year` (25.10.2026), the CVs and DE-LU's
SD from `docs/THIRD_ZONE.md` (19.10.2026). France's SD was computed on
31.10.2026 by the notebook's method on the warehouse, which reproduces DE-LU's
91.4 and both CVs. An absolute saving scales roughly with the SD
(THIRD_ZONE.md), which puts DE-LU's near twenty times France's. A rule on the
absolute saving would therefore be set knowing its answer. A relative saving,
which the level does not enter, scales roughly with the CV, which puts the
ratio near 1.8.

## The plant (illustrative, and labelled so wherever it appears)

- A flexible process of 1 MW runs k = 4 consecutive hours a day, starting at
  08:00 local by default.
- It may start up to n = 4 hours earlier or later inside the same local day,
  so between 04:00 and 12:00. Daily energy stays 4 MWh.
- Figures are per MWh of the flexible block, so the plant's size drops out and
  every figure scales with the megawatts.
- On the clock-change days (trap 3), only start times that exist on the clock
  are offered, each once.

## The decision

- **Timing.** At 10:00 the day before, the plant fixes tomorrow's start on a
  forecast, then pays the price the auction clears. 10:00 is two hours before
  the day-ahead gate closure at 12:00, which is when the day-ahead load forecast
  is due (Reg. 543/2013, Art. 6(2)(b)). The generation forecasts, total and wind
  and solar, are due only by 18:00 (Art. 14(2)(c), (d)), after gate closure, so
  what a pull of them returns need not have existed at 10:00.
- **The Master Plan's "forecast error between day-ahead and realised price"**
  is read as the forecast's error against the cleared price. Intraday and
  imbalance prices are not in the data.
- **Choice.** The start with the lowest forecast cost.
- **Three forecasts:**
  - *perfect*: the cleared prices. This is the value of perfect information,
    reported as a bound.
  - *naive*: the same weekday a week earlier, the RUNBOOK's baseline.
  - *ML*: Modul 10's price-spread forecast, trained on 2021–2023. It uses only
    what is certain at 10:00: calendar features, prices to the day before, and
    the day-ahead load forecast. The Master Plan names the generation forecast
    instead, so a variant with it is reported, labelled as knowing more than the
    plant could rely on. ML replaces naive in a zone only if the shifts it
    chooses in 2024 save more than naive's do. It is judged by what it decides,
    not by its error, and if it loses, that stands.
- **Resolution.** Hourly. Quarter-hour prices (from 1 October 2025) are
  averaged to hours. France's A44 already states 30 September at quarter-hours,
  each hour's price repeated four times, so the average returns it unchanged.
  Quarter-hour intensities are energy-weighted to hours.

## What it saves

- **Per day.** The € saving is cost(08:00 start) − cost(chosen start), at the
  cleared prices. The CO₂ effect is emissions(08:00) − emissions(chosen), at
  each hour's intensity.
- **The CO₂ potential.** The carbon-optimal start, with the day's intensity
  known in advance and taken under each factor draw separately. It is what
  shifting could save if carbon decided, and it is reported beside the
  cost-driven shift.
- **Absolute and relative.** Each CO₂ figure is given in kgCO₂e per MWh and as a
  share of the default block's emissions. The first equals the second times the
  default block's intensity, so the zones' absolute ratio splits exactly into a
  level factor and a variability factor. That answers §2.3's question for the
  CO₂ saving: whether shifting pays because the mix is dirty or because it
  changes.
- **Withheld hours.** A day with a withheld intensity hour between 02:00 and
  18:00, the widest window any draw reaches, leaves the CO₂ figures for every
  draw alike, and is counted. The € figures keep every day.

## Uncertainty: the Master Plan's three inputs

| Input | How it varies | What it moves |
|---|---|---|
| Emission factors | The 10,000 shared draws of `dim_factor_draw`, the same in both zones | CO₂, and the carbon-optimal start |
| Forecast error | Whole days of the forecast's own residuals in the same year, resampled and added to the cleared prices | The cost-driven start, so € and its CO₂ effect |
| Flexibility | n, a whole number of hours drawn evenly from 2 to 6, the same in both zones | Every start |

- **Output.** Each zone-year gets the point, the median and the 90% interval,
  and so does each ratio of one zone to the other. A ratio is taken draw by
  draw, so an error both zones share moves both sides of it together.
- **The point.** Every input is at its centre: n = 4, the median factors, and
  the forecast as made. The point must lie inside its own interval, or the build
  fails, as at every step of `fact_intensity`.
- **Perfect foresight** tops the € distribution by construction. It is reported
  as the bound it is, never as the point.
- **Sobol.** Saltelli's design over the three inputs as groups, on 10,000 base
  rows. Matrix A is the interval's sample, and B is drawn independently, its
  factors from `mc_seed` + 1. First and total order are given per input.
- **Checkpoint 8, amended with this design (RUNBOOK, Stage 8).** It asked that
  the indices sum to about 1. That holds for the intensity, which is linear in
  the factors. It does not hold for a saving whose start is chosen: n and the
  forecast error interact through the choice, and the factors interact with
  both. So the first-order sum is reported, not required, and the driver is
  named by total order.
- **Convergence**, also Checkpoint 8's. The bounds must move less than 1% at
  20,000 base rows, or, where an interval contains zero, less than 1% of its
  width. If they move more, the figures are given at 20,000, with the movement
  stated.

## Rules fixed before any run

The rules are tested on 2025, the plan's year and the one the forecast is not
chosen on:

- **H1, the CO₂ saving differs (README).** DE-LU's relative CO₂ potential
  exceeds France's: the 90% interval of their ratio lies above 1. "Sharply" is
  read as clear of the uncertainty, not as a factor. The CVs make H1 likely but
  do not settle it: they measure the whole day, while the shift sees 02:00 to
  18:00 and averages over a 4-hour block.
- **H2, a cost saving in both (README).** In each zone, the 90% interval of the
  € saving per MWh lies above zero, on the forecast in use.
- **H3, cost and carbon together in DE-LU (Master Plan §2.3).** In DE-LU, the
  CO₂ effect of the cost-driven shift has its 90% interval above zero. France's
  is reported only: §2.3 expects none there, and no interval can show an absence
  without a margin.

Reported, not tested:

- the absolute potential and its split;
- France's CO₂ effect of the cost-driven shift;
- the perfect-foresight bounds;
- 2021–2024 on the naive forecast.

Stated with every figure: the intensity is average, not marginal (Modul 9), and
production-based, so imports do not count.

## Where it lives

`src/decision/shift.py` holds the optimisation and the sampling, tested in
pytest. A dbt Python model runs it, as one runs `intensity.py`. The Master Plan
keeps optimisation out of dbt, and here dbt only runs the module. It writes two
tables, both exported for Power BI pages 2 and 3:

- `fact_shift_day`: each day's chosen start and saving with its interval, for
  the DAX measures and the calendar heatmap;
- `fact_shift_year`: the yearly figures with their intervals and Sobol shares.

## What it needs

- A65 with process type A01, ENTSO-E's day-ahead load forecast, for DE-LU and
  FR, 2021–2025, for the ML forecast. This is a pull with your token; WE 8 fits.
- A69, the day-ahead wind and solar forecast, only for the labelled variant.
- PL, only if it comes in (item 6): A44 for 2025. Its A75 for 2025 has been in
  `raw/` since 19.10.2026.

## Confirmed on 31.10.2026

The six items put for confirmation stand as drafted. Where an item offered a
choice, the design as written settles it:

1. The block: k = 4 hours, 08:00 by default, n = 4, drawn from 2 to 6.
2. Deciding at 10:00 the day before, on a forecast that may use the load
   forecast but not tomorrow's generation forecast, with ML in use only if its
   2024 shifts save more than naive's. Deciding on cleared prices instead would
   remove the forecast error, one of the three inputs.
3. H1 on the relative potential, H2 on the € saving, and H3 on DE-LU's
   co-benefit, tested rather than only reported.
4. "Sharply" as the interval clear of 1, not a factor.
5. The Checkpoint 8 amendment: the first-order sum reported, and the driver
   named by total order. It is made in the RUNBOOK with this design.
6. PL stays outside the tested rules. With relative figures, two zones already
   split level from variability, so PL would test that split rather than make
   it: a dirty but flat zone should show France's relative saving and a large
   absolute one. If it comes in (Master Plan §2.3: in Modul 10, if there is
   room), its figures are reported by the same method. It needs A44 for 2025, a
   third zone through the marts and a column on every page.

## Reference

Commission Regulation (EU) No 543/2013 of 14 June 2013 on submission and
publication of data in electricity markets. *Official Journal of the European
Union*, L 163, 15.6.2013, 1–12. https://eur-lex.europa.eu/eli/reg/2013/543/oj
