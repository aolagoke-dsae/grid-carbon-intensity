"""Carbon intensity of the generation mix, with the published factor
uncertainty propagated through to an interval.

Why this module exists
----------------------
The first schema draft (`sql/01_schema.sql`, archived on 17.10.2026 in
`archive/azure-excursion/`) carried `intensity_p05`, `intensity_p95` and
`mc_draws`, and `config/ipcc_ar5_factors.csv` has carried a min/median/max
band per fuel. Nothing computed them. This closes
that gap: the interval is the differentiator, and until now it existed only
as a column definition.

Method
------
For one timestamp, intensity is the energy-weighted mean of the fuel factors:

    I = sum_f (MWh_f * EF_f) / sum_f MWh_f          [gCO2e/kWh]

restricted to fuels that carry a factor. Fuels deliberately left unpriced
(B10 and B25 storage, B15/B17/B20 undisclosed composition, B06 oil until a
factor is cited) are excluded from BOTH sides, and the share of energy that was priced is reported as `coverage_pct`
so a thin hour is visible rather than silently averaged away.

EF_f is not a point. AR5 publishes a range across surveyed studies, so each
draw samples EF_f and the spread of I across draws is the interval.

Choice of sampling distribution
-------------------------------
Revised 2026-10-17, method 2.0.0. Every priced fuel is sampled from a
two-piece lognormal built on its published min / median / max:

    EF = median * exp(sigma_lo * z)    for z < 0
    EF = median * exp(sigma_hi * z)    for z >= 0

    sigma_lo = ln(median / min) / Z_BAND,  sigma_hi = ln(max / median) / Z_BAND

where z is a standard-normal score truncated to [-Z_BAND, Z_BAND] and
Z_BAND = 1.96. Three properties follow, and each is tested:

- The published median is the median of the distribution: half the scores
  fall on each side of zero.
- The published min and max sit where the 2.5th and 97.5th percentiles of
  the untruncated distribution would be. Truncating the scores, rather than
  clipping the factors, keeps every draw inside the published band without
  piling mass on its edges, and it takes equal probability from both tails,
  so the median does not move.
- The skew comes from the band itself. Each side of the median has its own
  spread, so reservoir hydro (1 / 24 / 2200) keeps its long right side and coal
  (740 / 820 / 910) stays almost symmetric.

Why not a triangular with the median as its mode, which 1.0.0 used for every
band less than 10x skewed: for a skewed band the median of that triangular is
not the published median. Nuclear (3.7 / 12 / 110) came out at 37.7, wind
onshore (7 / 11 / 56) at 22.8, solar (18 / 48 / 180) at 76.6, so low-carbon
mixes were overstated, and on nuclear-heavy French mixes the deterministic
point fell outside its own 90% interval (test_intensity.py, the sweep test).
With min and max fixed, no triangular can even reach a median that close to
the floor. 1.0.0's lognormal for hydro kept the median but treated the max as
the 95th percentile with an open tail, so 5% of hydro draws exceeded the
largest value AR5 reports.

Sensitivity
-----------
`variance_contribution()` draws every factor once and reuses the same draws
for each fuel it pins at its median (common random numbers), so the result
cannot depend on the order of the mix. Intensity is linear in independent
factors, so the variance shares are first-order Sobol indices and sum to 1
up to Monte Carlo error. Because the reported quantity is the 90% interval,
not the variance, each fuel's share of the p05-p95 width is reported as well;
those shares need not sum to 1.
"""
from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

# The published min and max are read as the 2.5th and 97.5th percentiles of
# the fitted two-piece lognormal, and draws are confined between them.
BAND_TAIL = 0.025
Z_BAND = 1.959963984540054  # standard normal quantile at 1 - BAND_TAIL

METHOD_VERSION = "intensity-2.0.0"


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
    def sigma_lo(self) -> float:
        """Log-scale spread below the median; the min sits at z = -Z_BAND."""
        return math.log(self.median / self.lo) / Z_BAND

    @property
    def sigma_hi(self) -> float:
        """Log-scale spread above the median; the max sits at z = +Z_BAND."""
        return math.log(self.hi / self.median) / Z_BAND

    @property
    def distribution(self) -> str:
        if not self.priced:
            return "none"
        if self.lo == self.hi:
            return "point"
        return "two-piece lognormal"

    def quantile(self, z: np.ndarray) -> np.ndarray:
        """Factor value for standard-normal scores z in [-Z_BAND, Z_BAND]."""
        z = np.asarray(z, dtype=float)
        return self.median * np.exp(np.where(z < 0, self.sigma_lo, self.sigma_hi) * z)


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
            if f.priced and f.lo <= 0:
                raise ValueError(
                    f"{psr}: band floor {f.lo} must be positive -- the factor is "
                    "sampled on a log scale"
                )
            if not f.source:
                raise ValueError(f"{psr}: no source citation (provenance is a control)")
            if f.priced and "placeholder" in f.source.lower():
                # B06 was priced from a row that said so (audit A12): a
                # non-empty source column is not yet a citation.
                raise ValueError(f"{psr}: priced from a placeholder; cite a source or unprice it")
            out[psr] = f
    return out


def band_scores(n_draws: int, n_cols: int, rng: np.random.Generator) -> np.ndarray:
    """Standard-normal scores truncated to [-Z_BAND, Z_BAND], shape (n_draws, n_cols).

    Drawn by rejection: about 5% of scores fall outside and are redrawn.
    Columns are filled in order, so a fixed seed gives fixed draws.
    """
    out = np.empty((n_draws, n_cols), dtype=float)
    for j in range(n_cols):
        kept = np.empty(0, dtype=float)
        while kept.size < n_draws:
            z = rng.standard_normal(n_draws)
            kept = np.concatenate([kept, z[np.abs(z) <= Z_BAND]])
        out[:, j] = kept[:n_draws]
    return out


def sample_factor(f: Factor, n_draws: int, rng: np.random.Generator) -> np.ndarray:
    """n_draws samples of one fuel's emission factor, in gCO2e/kWh."""
    if not f.priced:
        raise ValueError(f"{f.psr_type} is unpriced and must be excluded, not sampled")
    return f.quantile(band_scores(n_draws, 1, rng)[:, 0])


def factor_matrix(
    psrs: list[str], factors: dict[str, Factor], n_draws: int, rng: np.random.Generator
) -> np.ndarray:
    """Factor draws for several fuels, one column each, shape (n_draws, len(psrs))."""
    z = band_scores(n_draws, len(psrs), rng)
    return np.column_stack([factors[p].quantile(z[:, j]) for j, p in enumerate(psrs)])


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
                "sigma_lo": round(f.sigma_lo, 4) if f.priced else None,
                "sigma_hi": round(f.sigma_hi, 4) if f.priced else None,
                "confidence": f.confidence,
                "reason": (
                    "unpriced -- excluded from numerator and denominator"
                    if not f.priced
                    else "no published spread -- every draw is the median"
                    if f.lo == f.hi
                    else "two-piece lognormal: published median kept, min and max at "
                    "the 2.5th and 97.5th percentiles, every draw inside the band"
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


def _priced_fuels(mix: dict[str, float], factors: dict[str, Factor]) -> list[str]:
    """The priced fuels of a mix, sorted, so no result depends on dict order."""
    return sorted(p for p in mix if p in factors and factors[p].priced)


def intensity_draws(
    mix: dict[str, float],
    factors: dict[str, Factor],
    n_draws: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, float, float]:
    """Intensity distribution for one timestamp.

    Returns (draws [gCO2e/kWh], total_mwh, priced_mwh).
    """
    total = sum(mix.values())
    psrs = _priced_fuels(mix, factors)
    weights = np.array([mix[p] for p in psrs], dtype=float)
    priced_mwh = float(weights.sum())
    if priced_mwh <= 0:
        return np.full(n_draws, np.nan), total, 0.0
    ef = factor_matrix(psrs, factors, n_draws, rng)
    return ef @ weights / priced_mwh, total, priced_mwh


def deterministic_intensity(
    mix: dict[str, float], factors: dict[str, Factor]
) -> float | None:
    """The number you would report if you ignored uncertainty.

    Energy-weighted mean over the priced fuels, each at its MEDIAN factor --
    no sampling. It exists so the acceptance criterion can be checked:
    this point must fall inside the Monte Carlo 90% interval. Every factor's
    draws keep the published median, so the point can differ from the median
    of the draws only because the bands are asymmetric -- most AR5 bands reach
    further above the median than below it -- and never because the sampler
    moved a fuel's centre, which is what 1.0.0 did.
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

    Every factor is drawn once. Each fuel is then pinned at its median while
    all other fuels keep exactly the same draws (common random numbers), so no
    share can change with the order of the mix. Until 2.0.0 each pinned run
    drew a fresh random stream: the same mix gave shares summing to 1.0 with
    hydro listed first and 4.5 with hydro listed last (see the test).

    Two shares per fuel, both floored at zero:

    - `variance_share`: the fraction of the variance that disappears. The
      intensity is linear in independent factors, so these are the first-order
      Sobol indices, and they sum to 1 up to Monte Carlo error.
    - `width_share`: the fraction of the p05-p95 width that disappears. The
      interval is what gets reported, and a heavy tail can own most of the
      variance while moving the interval far less. These need not sum to 1.

    Returns [] when nothing varies.
    """
    psrs = _priced_fuels(mix, factors)
    weights = np.array([mix[p] for p in psrs], dtype=float)
    total = float(weights.sum())
    if total <= 0:
        return []
    ef = factor_matrix(psrs, factors, n_draws, np.random.default_rng(seed))
    full = ef @ weights / total
    var_full = float(np.var(full))
    if var_full == 0 or not np.isfinite(var_full):
        return []
    p05, p95 = np.percentile(full, [5, 95])
    width_full = float(p95 - p05)
    out = []
    for j, psr in enumerate(psrs):
        pinned = full - weights[j] * (ef[:, j] - factors[psr].median) / total
        q05, q95 = np.percentile(pinned, [5, 95])
        width_share = 1.0 - float(q95 - q05) / width_full if width_full > 0 else 0.0
        out.append(
            {
                "psr_type": psr,
                "fuel": factors[psr].fuel,
                "mwh": mix[psr],
                "variance_share": round(max(1.0 - float(np.var(pinned)) / var_full, 0.0), 4),
                "width_share": round(max(width_share, 0.0), 4),
            }
        )
    return sorted(out, key=lambda r: -r["variance_share"])
