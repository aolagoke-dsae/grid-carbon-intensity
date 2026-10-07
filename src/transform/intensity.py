"""Carbon intensity of the generation mix, with the published factor
uncertainty propagated through to an interval.

Why this module exists
----------------------
`sql/01_schema.sql` has carried `intensity_p05`, `intensity_p95` and
`mc_draws` since the first draft, and `config/ipcc_ar5_factors.csv` has
carried a min/median/max band per fuel. Nothing computed them. This closes
that gap: the interval is the differentiator, and until now it existed only
as a column definition.

Method
------
For one timestamp, intensity is the energy-weighted mean of the fuel factors:

    I = sum_f (MWh_f * EF_f) / sum_f MWh_f          [gCO2e/kWh]

restricted to fuels that carry a factor. Fuels deliberately left unpriced
(B10 storage, B15/B17/B20 undisclosed composition) are excluded from BOTH
sides, and the share of energy that was priced is reported as `coverage_pct`
so a thin hour is visible rather than silently averaged away.

EF_f is not a point. AR5 publishes a range across surveyed studies, so each
draw samples EF_f and the spread of I across draws is the interval.

Choice of sampling distribution
-------------------------------
Three-point information (min, median, max) normally implies a triangular
distribution. That is the default here, but it is wrong for hydropower:
AR5 gives 1 / 24 / 2200 gCO2e/kWh, where the 2200 comes from a handful of
tropical reservoir studies with large methane fluxes. A triangular over that
range has mean (1 + 24 + 2200)/3 = 742 gCO2e/kWh -- thirty times the median,
and it would make a hydro-heavy hour look dirtier than lignite.

So for any fuel whose max exceeds its median by more than
SKEW_RATIO_LOGNORMAL, this module fits a lognormal that keeps the stated
median as the median and treats the stated max as the 95th percentile. The
heavy tail survives, the central estimate does not move, and the mean stops
being nonsense. Which rule fired for which fuel is reported, not hidden --
see `describe_sampling()`.

Sensitivity
-----------
`variance_contribution()` freezes one fuel at its median, recomputes the
spread, and reports how much of the variance disappears. That is a
first-order sensitivity index: it answers "which factor is the interval
actually made of", which is the question a reviewer asks next.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# A max more than this many times the median means the published range is a
# skewed tail, not symmetric uncertainty. Hydro (2200/24 = 92) trips it;
# coal (910/820 = 1.1) does not.
SKEW_RATIO_LOGNORMAL = 10.0

# Standard normal quantile at 0.95, used to map a stated max onto the 95th
# percentile of the fitted lognormal.
Z95 = 1.6448536269514722

METHOD_VERSION = "intensity-1.0.0"


@dataclass(frozen=True)
class Factor:
    psr_type: str
    fuel: str
    median: float | None
    lo: float | None
    hi: float | None
    confidence: str
    source: str

    @property
    def priced(self) -> bool:
        """A fuel is priced only if it carries a median AND a band."""
        return self.median is not None and self.lo is not None and self.hi is not None

    @property
    def skewed(self) -> bool:
        return self.priced and self.hi > self.median * SKEW_RATIO_LOGNORMAL

    @property
    def distribution(self) -> str:
        if not self.priced:
            return "none"
        return "lognormal" if self.skewed else "triangular"


def _maybe_float(s: str) -> float | None:
    s = (s or "").strip()
    return float(s) if s else None


def load_factors(path: str | Path) -> dict[str, Factor]:
    """Read config/ipcc_ar5_factors.csv into {psr_type: Factor}.

    A row with no median is kept, not dropped: the schema treats "deliberately
    unpriced, with a stated reason" as different from "missing", and so does
    check_stage4_factors.
    """
    out: dict[str, Factor] = {}
    with Path(path).open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            psr = row["psr_type"].strip()
            if not psr:
                continue
            f = Factor(
                psr_type=psr,
                fuel=row["fuel"].strip(),
                median=_maybe_float(row["ef_median_g_kwh"]),
                lo=_maybe_float(row["ef_min_g_kwh"]),
                hi=_maybe_float(row["ef_max_g_kwh"]),
                confidence=row["confidence"].strip(),
                source=row["source"].strip(),
            )
            if f.median is not None and not f.priced:
                raise ValueError(
                    f"{psr}: median given without a full min/max band -- "
                    "an unbanded factor cannot be propagated"
                )
            if f.priced and not (f.lo <= f.median <= f.hi):
                raise ValueError(f"{psr}: band {f.lo}/{f.median}/{f.hi} is not ordered")
            if not f.source:
                raise ValueError(f"{psr}: no source citation (provenance is a control)")
            out[psr] = f
    return out


def sample_factor(f: Factor, n_draws: int, rng: np.random.Generator) -> np.ndarray:
    """n_draws samples of one fuel's emission factor, in gCO2e/kWh."""
    if not f.priced:
        raise ValueError(f"{f.psr_type} is unpriced and must be excluded, not sampled")
    if f.lo == f.hi:
        return np.full(n_draws, f.median, dtype=float)
    if f.skewed:
        mu = math.log(f.median)
        sigma = (math.log(f.hi) - mu) / Z95
        draws = rng.lognormal(mean=mu, sigma=sigma, size=n_draws)
        # The fitted tail is unbounded; the published floor still applies.
        return np.clip(draws, f.lo, None)
    return rng.triangular(left=f.lo, mode=f.median, right=f.hi, size=n_draws)


def describe_sampling(factors: dict[str, Factor]) -> list[dict]:
    """What was sampled how, and why. Belongs in the methodology document."""
    rows = []
    for psr, f in sorted(factors.items()):
        rows.append(
            {
                "psr_type": psr,
                "fuel": f.fuel,
                "distribution": f.distribution,
                "median": f.median,
                "lo": f.lo,
                "hi": f.hi,
                "hi_over_median": round(f.hi / f.median, 1) if f.priced else None,
                "confidence": f.confidence,
                "reason": (
                    "unpriced -- excluded from numerator and denominator"
                    if not f.priced
                    else "published range is right-skewed; lognormal keeps the median "
                    "and treats max as p95"
                    if f.skewed
                    else "three-point band, symmetric enough for a triangular"
                ),
            }
        )
    return rows


def energy_by_fuel(rows: list[dict]) -> dict[tuple, dict[str, float]]:
    """Fold parsed rows into {(zone, ts_utc): {psr_type: MWh}}.

    Consumption rows are dropped here: pumped storage appears in the same
    document as both generation and pumping, and counting the pumping leg as
    generation inflates the denominator.
    """
    out: dict[tuple, dict[str, float]] = {}
    for r in rows:
        if r["direction"] != "generation":
            continue
        key = (r["zone"], r["ts_utc"])
        out.setdefault(key, {})
        out[key][r["psr"]] = out[key].get(r["psr"], 0.0) + float(r["mwh"])
    return out


def intensity_draws(
    mix: dict[str, float],
    factors: dict[str, Factor],
    n_draws: int,
    rng: np.random.Generator,
    _frozen: str | None = None,
) -> tuple[np.ndarray, float, float]:
    """Intensity distribution for one timestamp.

    Returns (draws [gCO2e/kWh], total_mwh, priced_mwh).
    `_frozen` pins one fuel at its median, for the sensitivity analysis.
    """
    total = sum(mix.values())
    priced = {p: e for p, e in mix.items() if p in factors and factors[p].priced}
    priced_mwh = sum(priced.values())
    if priced_mwh <= 0:
        return np.full(n_draws, np.nan), total, 0.0

    numerator = np.zeros(n_draws, dtype=float)
    for psr, mwh in priced.items():
        f = factors[psr]
        if psr == _frozen:
            ef = np.full(n_draws, f.median, dtype=float)
        else:
            ef = sample_factor(f, n_draws, rng)
        numerator += mwh * ef
    return numerator / priced_mwh, total, priced_mwh


def deterministic_intensity(
    mix: dict[str, float], factors: dict[str, Factor]
) -> float | None:
    """The number you would report if you ignored uncertainty.

    Energy-weighted mean over the priced fuels, each at its MEDIAN factor --
    no sampling. It exists so the acceptance criterion can be checked:
    this point must fall inside the Monte Carlo 90% interval. Comparing the
    two is also the cheapest detector of a skewed propagation, because the
    bands are not symmetric: lo-to-median is narrower than median-to-hi for
    most AR5 fuels, so the sampled median sits above this point by design,
    and a large gap means the lognormal fit is doing more than intended.
    """
    priced = {p: e for p, e in mix.items() if p in factors and factors[p].priced}
    tot = sum(priced.values())
    if tot <= 0:
        return None
    return sum(e * factors[p].median for p, e in priced.items()) / tot


def summarise(
    mix: dict[str, float],
    factors: dict[str, Factor],
    n_draws: int = 10_000,
    seed: int = 20260917,
) -> dict:
    """One fact_intensity row: median, 90% interval, coverage, provenance."""
    rng = np.random.default_rng(seed)
    draws, total, priced_mwh = intensity_draws(mix, factors, n_draws, rng)
    if not np.isfinite(draws).any():
        return {
            "total_mwh": total,
            "priced_mwh": 0.0,
            "coverage_pct": None,
            "intensity_point": None,
            "intensity_median": None,
            "intensity_p05": None,
            "intensity_p95": None,
            "mc_draws": n_draws,
            "method_version": METHOD_VERSION,
        }
    return {
        "total_mwh": total,
        "priced_mwh": priced_mwh,
        "coverage_pct": round(100.0 * priced_mwh / total, 2) if total else None,
        "intensity_point": deterministic_intensity(mix, factors),
        "intensity_median": float(np.median(draws)),
        "intensity_p05": float(np.percentile(draws, 5)),
        "intensity_p95": float(np.percentile(draws, 95)),
        "mc_draws": n_draws,
        "method_version": METHOD_VERSION,
    }


def variance_contribution(
    mix: dict[str, float],
    factors: dict[str, Factor],
    n_draws: int = 10_000,
    seed: int = 20260917,
) -> list[dict]:
    """First-order sensitivity: which fuel's factor the interval is made of.

    Freeze one fuel at its median, recompute the variance, and report the
    fraction of variance that disappeared. Shares are reported raw -- they do
    not sum to exactly 1 because factor draws interact through the weighting.
    """
    base = intensity_draws(mix, factors, n_draws, np.random.default_rng(seed))[0]
    var_full = float(np.var(base))
    if var_full == 0 or not np.isfinite(var_full):
        return []
    out = []
    for psr in sorted(p for p in mix if p in factors and factors[p].priced):
        frozen = intensity_draws(
            mix, factors, n_draws, np.random.default_rng(seed), _frozen=psr
        )[0]
        share = 1.0 - float(np.var(frozen)) / var_full
        out.append(
            {
                "psr_type": psr,
                "fuel": factors[psr].fuel,
                "mwh": mix[psr],
                "variance_share": round(max(share, 0.0), 4),
            }
        )
    return sorted(out, key=lambda r: -r["variance_share"])
