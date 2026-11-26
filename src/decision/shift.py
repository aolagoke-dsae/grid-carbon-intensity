"""The decision model's core: where a flexible block of load starts, and what
moving it saves, in euros and in kgCO2e, per MWh of the block.

The design was fixed on 31.10.2026 and amended on 02.11.2026, before any shift
was computed (docs/DECISION_MODEL.md). This module implements it; it decides
nothing the document leaves open without saying so below, under
**Rules this module adds**.

The plant (illustrative, and labelled so wherever it appears)
--------------------------------------------------------------
A 1 MW process runs K_HOURS = 4 consecutive hours a day, from 08:00 local by
default. It may start up to n hours earlier or later inside the same local
day; n = 4 for the point and the tested intervals (A2), 2-6 as scenarios.
Every figure is per MWh of the block, so the plant's size drops out: a block's
cost per MWh is the mean of its hourly prices, its emissions per MWh the mean
of its hourly intensities (gCO2e/kWh equals kgCO2e/MWh).

The decision
------------
At 10:00 the day before, the start with the lowest *forecast* cost is chosen;
the plant then pays the cleared price. This module carries two forecasts:

- ``perfect``: the cleared prices themselves, the value of perfect
  information, reported as a bound and never as the point;
- ``naive``: the same weekday a week earlier, the RUNBOOK's baseline.

The ML forecast (Modul 10) plugs in as one more forecast array of the same
shape; ``decide_day`` takes any.

What it saves
-------------
- € saving = cost(default start) - cost(chosen start), at cleared prices.
- CO2 effect = emissions(default) - emissions(chosen), at each hour's
  intensity, per factor draw when draws are given.
- CO2 potential = default emissions minus those of the carbon-optimal start,
  chosen with the day's intensity known and under each draw separately.
- Each CO2 figure absolute (kgCO2e/MWh) and relative (share of the default
  block's emissions): absolute = relative x the default block's intensity,
  exactly, so a ratio of zones splits into a level and a variability factor.
- A day with a withheld intensity hour between 02:00 and 18:00, the widest
  window any n reaches, leaves every CO2 figure of that day empty and is
  counted; the € figures keep every day.

Every CO2 figure is hourly location-based Scope 2 accounting on the grid's
average, production-based intensity (A1): not marginal, imports not counted.

Rules this module adds (proposed 26.11.2026, before any run on real data)
------------------------------------------------------------------------
The design leaves five mechanics open. Each is the least committal reading,
and each is tested:

R1. Ties. A start replaces the default only if its forecast cost is lower by
    more than TIE_TOL euro per MWh. Among equally cheap alternatives the one
    nearest the default wins, then the earlier. A plant does not move for
    nothing, and the result does not depend on float noise.
R2. The 25-hour day. "Each start once" (design, *The plant*) keeps the first
    occurrence of the repeated hour, the one on summer time. Every block runs
    K_HOURS real hours, so on that day a block over the repeated hour ends one
    clock hour earlier than its label suggests.
R3. The naive forecast of an hour is the cleared price of the same clock hour
    seven local days earlier. The second 02:00 of a 25-hour day takes the
    week-earlier 02:00. An hour the week-earlier day lacks (02:00 after a
    23-hour day) has no forecast.
R4. A start whose block contains an hour without forecast is not offered. If
    no start but the default has a whole forecast, the default stands, the
    saving is zero and the day is flagged ``forecast_whole = False``; the first
    seven days of a series are such days for ``naive``.
R5. Hours. Prices are averaged to the UTC hour, intensities energy-weighted
    (sum of emissions over sum of priced energy). An hour that its steps do
    not cover whole, or that holds a withheld step, has no value. Both zones
    change clock on whole UTC hours, so a UTC hour is a local hour.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

K_HOURS = 4
DEFAULT_START = 8
N_POINT = 4
N_SCENARIOS = (2, 3, 4, 5, 6)
N_MAX = max(N_SCENARIOS)
# The widest window any start reaches: 02:00 to 18:00 at n = 6.
CO2_WINDOW = (DEFAULT_START - N_MAX, DEFAULT_START + N_MAX + K_HOURS)
TIE_TOL = 1e-9
FORECASTS = ("perfect", "naive")
METHOD_VERSION = "shift-0.1.0"


# --------------------------------------------------------------------------
# Hours: from the marts' steps to one row per real hour of each local day
# --------------------------------------------------------------------------
def _covered(step_hours: pd.Series) -> bool:
    return bool(np.isclose(step_hours.sum(), 1.0))


def hourly_prices(steps: pd.DataFrame) -> pd.DataFrame:
    """Cleared prices per UTC hour (R5): the mean of the hour's steps.

    ``steps`` has ``ts_utc``, ``step_hours`` and ``price_eur_mwh`` (one zone,
    as in fact_price). A quarter-hour series is averaged to hours, which
    returns France's 30.09.2025, each hour stated four times, unchanged. An
    hour its steps do not cover whole gets NaN.
    """
    s = steps.assign(hour_utc=pd.to_datetime(steps["ts_utc"]).dt.floor("h"))
    g = s.groupby("hour_utc", sort=True)
    out = g["price_eur_mwh"].mean().to_frame("price_eur_mwh")
    whole = g["step_hours"].apply(_covered)
    out.loc[~whole, "price_eur_mwh"] = np.nan
    return out.reset_index()


def hourly_intensity(steps: pd.DataFrame) -> pd.DataFrame:
    """The point intensity per UTC hour (R5), energy-weighted.

    ``steps`` has ``ts_utc``, ``step_hours``, ``priced_mwh``, ``emissions_kg``
    and ``intensity_g_kwh`` (one zone, as in fact_intensity). The hour's value
    is the sum of its emissions over the sum of its priced energy, not the
    mean of its steps' intensities. It is NaN if a step is withheld
    (``intensity_g_kwh`` null) or the steps do not cover the hour whole.
    """
    s = steps.assign(hour_utc=pd.to_datetime(steps["ts_utc"]).dt.floor("h"))
    g = s.groupby("hour_utc", sort=True)
    out = pd.DataFrame({
        "priced_mwh": g["priced_mwh"].sum(),
        "emissions_kg": g["emissions_kg"].sum(),
    })
    reported = g["intensity_g_kwh"].apply(lambda x: bool(x.notna().all()))
    whole = g["step_hours"].apply(_covered)
    out["intensity_g_kwh"] = np.where(reported & whole, out["emissions_kg"] / out["priced_mwh"], np.nan)
    return out.reset_index()


def hourly_energy_by_fuel(generation: pd.DataFrame, fuels: list[str]) -> pd.DataFrame:
    """Priced generation energy per UTC hour and fuel, MWh, one column a fuel.

    ``generation`` has ``ts_utc``, ``psr_type``, ``direction`` and ``mwh`` (one
    zone, as in fact_generation). Only the generation leg of ``fuels`` counts,
    the fuels dim_factor_draw prices. Under factor draw d an hour's intensity
    is energy . ef_d / its priced energy (``intensity_draws``); at the median
    factors that is ``hourly_intensity``'s value.
    """
    g = generation[(generation["direction"] == "generation") & generation["psr_type"].isin(fuels)]
    g = g.assign(hour_utc=pd.to_datetime(g["ts_utc"]).dt.floor("h"))
    wide = g.pivot_table(index="hour_utc", columns="psr_type", values="mwh",
                         aggfunc="sum", fill_value=0.0)
    return wide.reindex(columns=fuels, fill_value=0.0).sort_index()


def intensity_draws(energy: np.ndarray, draws: np.ndarray) -> np.ndarray:
    """Hourly intensity under every factor draw, shape (n_draws, n_hours).

    ``energy`` is (n_hours, n_fuels) MWh, ``draws`` (n_draws, n_fuels)
    gCO2e/kWh, columns in the same order. An hour without priced energy is NaN.
    """
    energy = np.asarray(energy, dtype=float)
    total = energy.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return (np.asarray(draws, dtype=float) @ energy.T) / np.where(total > 0, total, np.nan)


def local_hours(hourly: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Add each UTC hour's local date and clock hour, and its occurrence.

    ``occurrence`` is 0, and 1 for the second 02:00 of a 25-hour day. The
    frame is first completed to every UTC hour between its first and last, so
    an hour a series lacks (France's intensity has gaps of up to three hours)
    is a row with NaN values rather than a missing row: a block is k real
    hours, never k rows across a gap. A local day then has 23, 24 or 25 rows,
    except at the series' edges.
    """
    out = hourly.copy()
    out["hour_utc"] = pd.to_datetime(out["hour_utc"])
    if out["hour_utc"].duplicated().any():
        raise ValueError("one row per UTC hour expected")
    grid = pd.date_range(out["hour_utc"].min(), out["hour_utc"].max(), freq="h")
    out = out.set_index("hour_utc").reindex(grid).rename_axis("hour_utc").reset_index()
    utc = out["hour_utc"]
    if utc.dt.tz is None:
        utc = utc.dt.tz_localize("UTC")
    local = utc.dt.tz_convert(tz)
    out["local_date"] = local.dt.date
    out["local_hour"] = local.dt.hour.astype(int)
    out = out.sort_values("hour_utc", kind="stable").reset_index(drop=True)
    out["occurrence"] = out.groupby(["local_date", "local_hour"]).cumcount().astype(int)
    return out


# --------------------------------------------------------------------------
# One day
# --------------------------------------------------------------------------
def candidate_starts(labels, n: int = N_POINT, k: int = K_HOURS,
                     default: int = DEFAULT_START) -> np.ndarray:
    """Indices into the day's real hours at which a block may start.

    ``labels`` are the day's local clock hours in time order (23, 24 or 25).
    A start is offered if its clock hour lies within n of the default, it
    exists on the clock that day, it is the first occurrence of its clock hour
    (R2), and its block of k real hours ends inside the day.
    """
    labels = list(labels)
    if default not in labels:
        raise ValueError(f"the default start {default:02d}:00 is not on this day's clock")
    seen, idx = set(), []
    for i, h in enumerate(labels):
        if abs(h - default) <= n and h not in seen and i + k <= len(labels):
            idx.append(i)
            seen.add(h)
    return np.asarray(idx, dtype=int)


def block_means(values: np.ndarray, starts: np.ndarray, k: int = K_HOURS) -> np.ndarray:
    """Mean over each block of k real hours, along the last axis.

    ``values`` (..., n_hours) -> (..., len(starts)). NaN in a block makes its
    mean NaN.
    """
    v = np.asarray(values, dtype=float)
    windows = np.stack([v[..., s:s + k] for s in starts], axis=-2)
    return windows.mean(axis=-1)


def choose(costs: np.ndarray, start_labels: np.ndarray, default: int = DEFAULT_START) -> int:
    """Position in ``costs`` of the start chosen on them (R1, R4).

    The cheapest start, where a start other than the default must beat it by
    more than TIE_TOL; among equals the nearest the default, then the earlier.
    NaN costs are not offered. If the default's own cost is NaN, the cheapest
    whole alternative is taken; if none is whole, the default stands.
    """
    costs = np.asarray(costs, dtype=float)
    start_labels = np.asarray(start_labels)
    d = int(np.flatnonzero(start_labels == default)[0])
    ok = ~np.isnan(costs)
    if not ok.any():
        return d
    best = costs[ok].min()
    if ok[d] and costs[d] <= best + TIE_TOL:
        return d
    tied = np.flatnonzero(ok & (costs <= best + TIE_TOL))
    order = np.lexsort((start_labels[tied], np.abs(start_labels[tied] - default)))
    return int(tied[order[0]])


@dataclass(frozen=True)
class DayResult:
    start: int                    # chosen start, local clock hour
    eur_saving: float             # €/MWh of the block, at cleared prices
    default_cost: float           # €/MWh, the 08:00 block at cleared prices
    forecast_whole: bool          # R4: at least one alternative had a whole forecast
    co2_withheld: bool            # a withheld intensity hour in CO2_WINDOW
    default_intensity: np.ndarray  # kgCO2e/MWh of the 08:00 block, per draw
    co2_effect: np.ndarray        # kgCO2e/MWh, the chosen shift, per draw
    co2_potential: np.ndarray     # kgCO2e/MWh, the carbon-optimal shift, per draw
    carbon_start: np.ndarray      # clock hour of the carbon-optimal start, per draw

    @property
    def co2_effect_rel(self) -> np.ndarray:
        return self.co2_effect / self.default_intensity

    @property
    def co2_potential_rel(self) -> np.ndarray:
        return self.co2_potential / self.default_intensity


def decide_day(labels, price, forecast, intensity, n: int = N_POINT,
               k: int = K_HOURS, default: int = DEFAULT_START) -> DayResult:
    """Decide one local day.

    ``labels``, ``price`` and ``forecast`` have one entry per real hour of the
    day, in time order. ``intensity`` is (n_hours,) for the point or
    (n_draws, n_hours) for the factor draws; the CO2 arrays of the result have
    one entry per draw (one for the point).
    """
    labels = np.asarray(labels, dtype=int)
    price = np.asarray(price, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    intensity = np.atleast_2d(np.asarray(intensity, dtype=float))
    if not (len(labels) == len(price) == len(forecast) == intensity.shape[1]):
        raise ValueError("labels, prices, forecast and intensity must cover the same hours")

    starts = candidate_starts(labels, n, k, default)
    start_labels = labels[starts]
    d = int(np.flatnonzero(start_labels == default)[0])

    f_cost = block_means(forecast, starts, k)
    alternatives = np.delete(f_cost, d)
    forecast_whole = bool((~np.isnan(alternatives)).any())
    c = choose(f_cost, start_labels, default) if forecast_whole else d

    cost = block_means(price, starts, k)
    eur = cost[d] - cost[c]

    lo, hi = CO2_WINDOW
    window = (labels >= lo) & (labels < hi)
    co2_withheld = bool(np.isnan(intensity[:, window]).any())
    n_draws = intensity.shape[0]
    if co2_withheld:
        nan = np.full(n_draws, np.nan)
        return DayResult(int(start_labels[c]), float(eur), float(cost[d]), forecast_whole,
                         True, nan, nan.copy(), nan.copy(), np.full(n_draws, -1))

    em = block_means(intensity, starts, k)                 # (n_draws, n_starts)
    base = em[:, d]
    carbon = np.argmin(em, axis=1)
    # The default keeps ties here too: it is the first column of the minimum
    # only if it is the minimum; argmin's first-index rule is replaced by R1.
    at_default = em[:, d] <= em[np.arange(n_draws), carbon] + TIE_TOL
    carbon = np.where(at_default, d, carbon)
    return DayResult(
        start=int(start_labels[c]),
        eur_saving=float(eur),
        default_cost=float(cost[d]),
        forecast_whole=forecast_whole,
        co2_withheld=False,
        default_intensity=base,
        co2_effect=base - em[:, c],
        co2_potential=base - em[np.arange(n_draws), carbon],
        carbon_start=start_labels[carbon],
    )


# --------------------------------------------------------------------------
# Forecasts
# --------------------------------------------------------------------------
def naive_forecast(hours: pd.DataFrame) -> pd.Series:
    """The cleared price of the same clock hour seven local days earlier (R3).

    ``hours`` is ``local_hours``'s frame with ``price_eur_mwh``. Returns a
    series aligned to its rows.
    """
    week = hours[["local_date", "local_hour", "occurrence", "price_eur_mwh"]].copy()
    week = week[week["occurrence"] == 0]
    week["local_date"] = pd.to_datetime(week["local_date"]) + pd.Timedelta(days=7)
    week = week.rename(columns={"price_eur_mwh": "forecast"}).drop(columns="occurrence")
    key = hours[["local_date", "local_hour"]].copy()
    key["local_date"] = pd.to_datetime(key["local_date"])
    merged = key.merge(week, on=["local_date", "local_hour"], how="left", validate="many_to_one")
    return pd.Series(merged["forecast"].to_numpy(), index=hours.index, name="forecast")


def forecast_prices(hours: pd.DataFrame, forecast: str) -> np.ndarray:
    """The forecast named ``forecast`` for every row of ``hours``."""
    if forecast == "perfect":
        return hours["price_eur_mwh"].to_numpy(dtype=float)
    if forecast == "naive":
        return naive_forecast(hours).to_numpy(dtype=float)
    raise ValueError(f"unknown forecast {forecast!r}; known: {FORECASTS}")


# --------------------------------------------------------------------------
# A zone: every day
# --------------------------------------------------------------------------
def decide_zone(hours: pd.DataFrame, forecast: str = "naive", n: int = N_POINT,
                intensity: np.ndarray | None = None) -> tuple[pd.DataFrame, dict]:
    """Decide every local day of one zone.

    ``hours`` is ``local_hours``'s frame with ``price_eur_mwh`` and the point
    ``intensity_g_kwh``. ``intensity``, optional, is (n_draws, len(hours)):
    the hourly intensity under each factor draw (``intensity_draws``), aligned
    to the rows of ``hours``. Without it the point intensity is the only draw.

    Returns one row per day, with the point and, under draws, the 5th, 50th
    and 95th percentiles of the CO2 figures; and per year, per draw, the sums
    from which the yearly figures follow (``yearly``).
    """
    hours = hours.reset_index(drop=True)
    f = forecast_prices(hours, forecast)
    point = hours["intensity_g_kwh"].to_numpy(dtype=float)
    rows, acc = [], {}
    for date, idx in hours.groupby("local_date", sort=True).indices.items():
        labels = hours["local_hour"].to_numpy()[idx]
        if DEFAULT_START not in labels:
            continue                                   # a day cut off at the series' edge
        price = hours["price_eur_mwh"].to_numpy(dtype=float)[idx]
        r0 = decide_day(labels, price, f[idx], point[idx], n=n)
        row = {
            "local_date": date, "forecast": forecast, "n_flex": n, "start_hour": r0.start,
            "eur_saving_per_mwh": r0.eur_saving, "default_cost_eur_mwh": r0.default_cost,
            "forecast_whole": r0.forecast_whole, "co2_withheld": r0.co2_withheld,
            "default_intensity_g_kwh": r0.default_intensity[0],
            "co2_effect_kg_mwh": r0.co2_effect[0],
            "co2_potential_kg_mwh": r0.co2_potential[0],
            "carbon_start_hour": int(r0.carbon_start[0]),
        }
        year = pd.Timestamp(date).year
        if intensity is not None:
            rd = decide_day(labels, price, f[idx], np.asarray(intensity)[:, idx], n=n)
            for name, arr in (("co2_effect", rd.co2_effect), ("co2_potential", rd.co2_potential)):
                q = np.percentile(arr, [5, 50, 95]) if not rd.co2_withheld else [np.nan] * 3
                row.update({f"{name}_p05_kg_mwh": q[0], f"{name}_p50_kg_mwh": q[1],
                            f"{name}_p95_kg_mwh": q[2]})
            draws = rd
        else:
            draws = r0
        a = acc.setdefault(year, {"days": 0, "co2_days": 0, "eur": 0.0, "default_cost": 0.0,
                                  "default_em": 0.0, "effect": 0.0, "potential": 0.0})
        a["days"] += 1
        a["eur"] += r0.eur_saving
        a["default_cost"] += r0.default_cost
        if not draws.co2_withheld:
            a["co2_days"] += 1
            a["default_em"] = a["default_em"] + draws.default_intensity
            a["effect"] = a["effect"] + draws.co2_effect
            a["potential"] = a["potential"] + draws.co2_potential
        rows.append(row)
    return pd.DataFrame(rows), acc


def yearly(acc: dict) -> pd.DataFrame:
    """The yearly figures from ``decide_zone``'s sums, one row per year.

    € per MWh is the mean over all days; CO2 per MWh the mean over the days
    with CO2 figures, and the relative figures the sum of the effect over the
    sum of the default emissions, draw by draw. Under draws each figure gets
    its 5th, 50th and 95th percentile.
    """
    out = []
    for year, a in sorted(acc.items()):
        row = {"year": year, "n_days": a["days"], "n_co2_days": a["co2_days"],
               "n_co2_withheld": a["days"] - a["co2_days"],
               "eur_saving_per_mwh": a["eur"] / a["days"] if a["days"] else np.nan}
        if a["co2_days"]:
            figs = {
                "co2_effect_kg_mwh": np.atleast_1d(a["effect"]) / a["co2_days"],
                "co2_potential_kg_mwh": np.atleast_1d(a["potential"]) / a["co2_days"],
                "co2_effect_rel": np.atleast_1d(a["effect"]) / np.atleast_1d(a["default_em"]),
                "co2_potential_rel": np.atleast_1d(a["potential"]) / np.atleast_1d(a["default_em"]),
            }
            for name, arr in figs.items():
                if arr.size == 1:
                    row[name] = float(arr[0])
                else:
                    p05, p50, p95 = np.percentile(arr, [5, 50, 95])
                    row.update({f"{name}_p05": p05, f"{name}_p50": p50, f"{name}_p95": p95})
        out.append(row)
    return pd.DataFrame(out)
