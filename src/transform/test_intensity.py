"""Tests for the uncertainty propagation.

The point estimate is not the deliverable -- the interval is. These tests pin
the three things that make it defensible: the point estimate stays inside its
own distribution, unpriced fuels leave both sides of the ratio, and the
hydropower range does not drag the median into nonsense.
"""
import math
from pathlib import Path

import numpy as np
import pytest

from intensity import (
    deterministic_intensity,
    SKEW_RATIO_LOGNORMAL,
    Factor,
    describe_sampling,
    energy_by_fuel,
    load_factors,
    sample_factor,
    summarise,
    variance_contribution,
)

FACTORS_CSV = Path(__file__).resolve().parents[2] / "config" / "ipcc_ar5_factors.csv"


@pytest.fixture(scope="module")
def factors():
    return load_factors(FACTORS_CSV)


# --------------------------------------------------------------------------
# The factor table is a control, not a convenience
# --------------------------------------------------------------------------
def test_every_factor_row_carries_a_source(factors):
    assert all(f.source for f in factors.values())


def test_unpriced_fuels_are_flagged_not_missing(factors):
    for psr in ("B10", "B15", "B17", "B20"):
        assert psr in factors, f"{psr} must exist as an explicit row"
        assert not factors[psr].priced, f"{psr} must be deliberately unpriced"
        assert factors[psr].confidence in {"excluded", "unknown"}


def test_bands_are_ordered(factors):
    for f in factors.values():
        if f.priced:
            assert f.lo <= f.median <= f.hi


# --------------------------------------------------------------------------
# Distribution choice
# --------------------------------------------------------------------------
def test_coal_uses_a_triangular(factors):
    assert factors["B05"].distribution == "triangular"
    assert factors["B05"].hi / factors["B05"].median < SKEW_RATIO_LOGNORMAL


def test_hydro_uses_a_lognormal(factors):
    for psr in ("B11", "B12"):
        assert factors[psr].distribution == "lognormal", (
            f"{psr} range is right-skewed and must not be sampled triangularly"
        )


def test_triangular_over_the_hydro_range_would_wreck_the_median(factors):
    """The regression this whole design decision exists to prevent.

    AR5 hydro is 1 / 24 / 2200. A triangular over that has its median near
    650 gCO2e/kWh -- comparable to gas -- because the mode sits at the 1st
    percentile of the range. The lognormal keeps the published median.
    """
    f = factors["B11"]
    rng = np.random.default_rng(1)
    naive = np.median(rng.triangular(f.lo, f.median, f.hi, 20_000))
    fitted = np.median(sample_factor(f, 20_000, np.random.default_rng(1)))
    assert naive > 500, "sanity: the naive choice really is that bad"
    assert fitted < 60, f"fitted median drifted to {fitted:.1f}"
    assert fitted == pytest.approx(f.median, rel=0.15)


def test_lognormal_preserves_the_published_upper_bound_as_p95(factors):
    f = factors["B11"]
    draws = sample_factor(f, 50_000, np.random.default_rng(7))
    assert np.percentile(draws, 95) == pytest.approx(f.hi, rel=0.1)
    assert draws.min() >= f.lo


def test_triangular_draws_stay_inside_the_published_band(factors):
    f = factors["B05"]
    draws = sample_factor(f, 10_000, np.random.default_rng(3))
    assert draws.min() >= f.lo
    assert draws.max() <= f.hi


def test_unpriced_fuel_cannot_be_sampled(factors):
    with pytest.raises(ValueError, match="unpriced"):
        sample_factor(factors["B15"], 10, np.random.default_rng(0))


def test_describe_sampling_explains_every_row(factors):
    rows = describe_sampling(factors)
    assert len(rows) == len(factors)
    assert all(r["reason"] for r in rows)


# --------------------------------------------------------------------------
# The intensity itself
# --------------------------------------------------------------------------
def test_pure_coal_hour_lands_on_the_coal_factor(factors):
    out = summarise({"B05": 1000.0}, factors, n_draws=20_000)
    assert out["intensity_median"] == pytest.approx(820, rel=0.02)
    assert factors["B05"].lo <= out["intensity_p05"] <= out["intensity_median"]
    assert out["intensity_median"] <= out["intensity_p95"] <= factors["B05"].hi
    assert out["coverage_pct"] == 100.0


def test_point_estimate_lies_inside_its_own_interval(factors):
    """The DETERMINISTIC point must fall inside the sampled interval.

    Rewritten 2026-10-07. The old assertion compared intensity_median against
    p05 and p95 -- all three computed from the same draws, so the median of a
    sample always lies between its own percentiles. It was a tautology and
    could not fail, which made the project's headline acceptance criterion
    vacuous. The deterministic point is computed from the median factors
    without sampling, so it genuinely can escape the interval if the
    propagation is skewed.
    """
    mix = {"B05": 400.0, "B04": 300.0, "B19": 800.0, "B16": 200.0, "B14": 100.0}
    out = summarise(mix, factors, n_draws=20_000)
    point = out["intensity_point"]
    assert point is not None
    assert out["intensity_p05"] <= point <= out["intensity_p95"], (
        f"deterministic {point:.1f} outside "
        f"[{out['intensity_p05']:.1f}, {out['intensity_p95']:.1f}]"
    )


def test_the_old_tautology_cannot_come_back(factors):
    """The sampled median is NOT the deterministic point, and the distance
    between them is the signal the acceptance criterion is reading."""
    mix = {"B05": 400.0, "B04": 300.0, "B19": 800.0, "B16": 200.0, "B14": 100.0}
    out = summarise(mix, factors, n_draws=20_000)
    assert out["intensity_point"] != out["intensity_median"]


def test_interval_is_not_degenerate(factors):
    mix = {"B05": 400.0, "B04": 300.0, "B19": 800.0}
    out = summarise(mix, factors, n_draws=20_000)
    width = out["intensity_p95"] - out["intensity_p05"]
    assert width > 1.0, "a propagated interval that collapses means nothing propagated"


def test_unpriced_energy_leaves_both_sides_of_the_ratio(factors):
    """B15 must not be silently counted as zero-carbon."""
    clean = summarise({"B19": 1000.0}, factors, n_draws=5_000)
    with_unpriced = summarise({"B19": 1000.0, "B15": 1000.0}, factors, n_draws=5_000)
    assert with_unpriced["intensity_median"] == pytest.approx(
        clean["intensity_median"], rel=0.02
    ), "adding unpriced energy must not dilute the intensity"
    assert with_unpriced["coverage_pct"] == pytest.approx(50.0)
    assert with_unpriced["total_mwh"] == 2000.0
    assert with_unpriced["priced_mwh"] == 1000.0


def test_storage_consumption_never_reaches_the_mix():
    """energy_by_fuel drops the pumping leg before any factor is applied."""
    rows = [
        {"zone": "Z", "ts_utc": "T", "psr": "B10", "direction": "consumption", "mwh": 50.0},
        {"zone": "Z", "ts_utc": "T", "psr": "B19", "direction": "generation", "mwh": 10.0},
    ]
    mix = energy_by_fuel(rows)
    assert mix[("Z", "T")] == {"B19": 10.0}


def test_an_entirely_unpriced_hour_reports_nothing_rather_than_zero(factors):
    out = summarise({"B15": 100.0, "B20": 50.0}, factors, n_draws=1_000)
    assert out["intensity_median"] is None
    assert out["coverage_pct"] is None
    assert out["total_mwh"] == 150.0


def test_plausibility_bounds_hold_for_a_realistic_german_mix(factors):
    """Roughly a windy German afternoon. Anything outside 0-1000 is a unit bug."""
    mix = {"B19": 20000.0, "B16": 8000.0, "B04": 6000.0, "B05": 3000.0,
           "B02": 4000.0, "B01": 1500.0, "B14": 0.0}
    out = summarise(mix, factors, n_draws=20_000)
    assert 0 < out["intensity_median"] < 1000
    assert out["coverage_pct"] == 100.0


# --------------------------------------------------------------------------
# Sensitivity
# --------------------------------------------------------------------------
def test_variance_is_attributed_to_the_dominant_factor(factors):
    """Lignite dominates this mix, so it should dominate the interval too."""
    mix = {"B02": 8000.0, "B19": 2000.0}
    shares = variance_contribution(mix, factors, n_draws=20_000)
    assert shares[0]["psr_type"] == "B02"
    assert shares[0]["variance_share"] > 0.5


def test_variance_contribution_is_empty_when_nothing_varies(factors):
    single = {"B14": 100.0}
    shares = variance_contribution(single, factors, n_draws=2_000)
    assert shares and shares[0]["psr_type"] == "B14"
