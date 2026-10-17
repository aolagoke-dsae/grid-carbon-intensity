"""Tests for the uncertainty propagation.

The point estimate is not the deliverable -- the interval is. These tests pin
what makes it defensible: every factor keeps its published median and stays
inside its published band, the deterministic point stays inside its own
interval on low-carbon mixes as well as fossil ones, unpriced fuels leave both
sides of the ratio, and no result depends on the order in which a mix is
written down.
"""
import itertools
from pathlib import Path

import numpy as np
import pytest

from intensity import (
    Z_BAND,
    Factor,
    describe_sampling,
    energy_by_fuel,
    factor_matrix,
    load_factors,
    sample_factor,
    summarise,
    variance_contribution,
)

FACTORS_CSV = Path(__file__).resolve().parents[2] / "config" / "ipcc_ar5_factors.csv"

# A low-carbon mix with hydro in it, written down in two orders.
HYDRO_FIRST = {"B11": 300.0, "B04": 2000.0, "B14": 6000.0, "B16": 800.0, "B19": 1200.0, "B18": 500.0}
HYDRO_LAST = {k: HYDRO_FIRST[k] for k in ["B04", "B14", "B16", "B19", "B18", "B11"]}


@pytest.fixture(scope="module")
def factors():
    return load_factors(FACTORS_CSV)


def _priced(factors):
    return {p: f for p, f in factors.items() if f.priced}


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


def test_a_band_floor_of_zero_is_refused(tmp_path):
    """The factor is sampled on a log scale, so a floor of 0 has no meaning."""
    csv = tmp_path / "factors.csv"
    csv.write_text(
        "psr_type,fuel,ef_median_g_kwh,ef_min_g_kwh,ef_max_g_kwh,confidence,source\n"
        "B99,Test fuel,10,0,20,low,test row\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="positive"):
        load_factors(csv)


# --------------------------------------------------------------------------
# Sampling: the two-piece lognormal (method 2.0.0, 17.10.2026)
# --------------------------------------------------------------------------
def test_every_priced_fuel_keeps_its_published_median(factors):
    """The regression the 2.0.0 sampler exists for.

    1.0.0 used a triangular with the published median as its mode. For a
    skewed band that moves the median: nuclear came out at 37.7 against a
    published 12, wind onshore at 22.8 against 11, solar at 76.6 against 48.
    """
    for psr, f in _priced(factors).items():
        draws = sample_factor(f, 200_000, np.random.default_rng(11))
        assert np.median(draws) == pytest.approx(f.median, rel=0.02), psr


def test_every_draw_stays_inside_the_published_band(factors):
    """1.0.0's hydro lognormal had an open tail: 5% of draws exceeded 2200."""
    for psr, f in _priced(factors).items():
        draws = sample_factor(f, 50_000, np.random.default_rng(5))
        assert draws.min() >= f.lo, psr
        assert draws.max() <= f.hi, psr


def test_the_score_range_maps_onto_the_published_band(factors):
    for psr, f in _priced(factors).items():
        lo, hi = f.quantile(np.array([-Z_BAND, Z_BAND]))
        assert lo == pytest.approx(f.lo), psr
        assert hi == pytest.approx(f.hi), psr


def test_the_skew_comes_from_the_band(factors):
    """Hydro keeps its long right side; coal stays almost symmetric."""

    def right_over_left(d):
        m = np.median(d)
        return (np.percentile(d, 90) - m) / (m - np.percentile(d, 10))

    hydro = sample_factor(factors["B11"], 100_000, np.random.default_rng(2))
    coal = sample_factor(factors["B05"], 100_000, np.random.default_rng(2))
    assert right_over_left(hydro) > 10
    assert right_over_left(coal) == pytest.approx(1.0, abs=0.15)


def test_a_triangular_over_the_hydro_range_would_wreck_the_median(factors):
    """Why no triangular is used anywhere.

    AR5 hydro is 1 / 24 / 2200. A triangular over that has its median near
    650 gCO2e/kWh -- comparable to gas -- because the mode sits at the 1st
    percentile of the range.
    """
    f = factors["B11"]
    naive = np.median(np.random.default_rng(1).triangular(f.lo, f.median, f.hi, 20_000))
    fitted = np.median(sample_factor(f, 20_000, np.random.default_rng(1)))
    assert naive > 500, "sanity: the naive choice really is that bad"
    assert fitted == pytest.approx(f.median, rel=0.05)


def test_unpriced_fuel_cannot_be_sampled(factors):
    with pytest.raises(ValueError, match="unpriced"):
        sample_factor(factors["B15"], 10, np.random.default_rng(0))


def test_describe_sampling_explains_every_row(factors):
    rows = describe_sampling(factors)
    assert len(rows) == len(factors)
    assert all(r["reason"] for r in rows)
    assert {r["distribution"] for r in rows if r["median"] is not None} == {"two-piece lognormal"}


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


@pytest.mark.parametrize(
    "mix",
    [
        {"B14": 70.0, "B11": 8.0, "B12": 4.0, "B19": 8.0, "B16": 4.0, "B04": 5.0, "B01": 1.0},
        {"B14": 80.0, "B19": 10.0, "B16": 5.0, "B04": 5.0},
    ],
    ids=["french-nuclear-heavy", "french-no-hydro"],
)
def test_point_estimate_lies_inside_its_interval_on_low_carbon_mixes(factors, mix):
    """Both mixes failed under 1.0.0: the point sat below p05."""
    out = summarise(mix, factors, n_draws=20_000)
    assert out["intensity_p05"] <= out["intensity_point"] <= out["intensity_p95"]


def test_acceptance_criterion_holds_across_french_like_mixes(factors):
    """729 French-like mixes, nuclear 50-80 with hydro, wind, solar, gas and
    biomass at three levels each. With the 1.0.0 sampler, 720 of them put the
    deterministic point outside its own 90% interval (same grid, 20,000 draws,
    seed 3)."""
    levels = {"B01": [0.5, 1.5, 3], "B04": [2, 6, 10], "B11": [3, 8, 13],
              "B14": [50, 65, 80], "B16": [1, 4, 8], "B19": [3, 8, 13]}
    psrs = sorted(levels)
    ef = factor_matrix(psrs, factors, 20_000, np.random.default_rng(3))
    medians = np.array([factors[p].median for p in psrs])
    failures = []
    for combo in itertools.product(*(levels[p] for p in psrs)):
        w = np.array(combo, dtype=float)
        p05, p95 = np.percentile(ef @ w / w.sum(), [5, 95])
        if not p05 <= medians @ w / w.sum() <= p95:
            failures.append(dict(zip(psrs, combo)))
    assert not failures, f"{len(failures)} of 729 mixes fail, e.g. {failures[0]}"


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


def test_results_do_not_depend_on_the_order_of_the_mix(factors):
    assert summarise(HYDRO_FIRST, factors) == summarise(HYDRO_LAST, factors)


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


def test_sensitivity_does_not_depend_on_the_order_of_the_mix(factors):
    """Audit A3. Under 1.0.0 each pinned run drew a fresh random stream, and
    this mix gave variance shares summing to 1.000 with hydro first and 4.486
    with hydro last: every fuel after hydro inherited part of its variance."""
    first = variance_contribution(HYDRO_FIRST, factors, n_draws=20_000)
    last = variance_contribution(HYDRO_LAST, factors, n_draws=20_000)
    assert first == last


def test_variance_shares_sum_to_one(factors):
    """Intensity is linear in independent factors, so the first-order indices
    account for all of the variance."""
    shares = variance_contribution(HYDRO_FIRST, factors, n_draws=50_000)
    assert sum(r["variance_share"] for r in shares) == pytest.approx(1.0, abs=0.03)


def test_width_shares_are_reported_and_bounded(factors):
    shares = variance_contribution(HYDRO_FIRST, factors, n_draws=20_000)
    assert all(0.0 <= r["width_share"] <= 1.0 for r in shares)


def test_variance_contribution_is_empty_when_nothing_varies():
    """Rewritten 17.10.2026: the old version of this test asserted a NON-empty
    result, for a nuclear-only mix whose factor does vary (audit A10)."""
    fixed = {"X01": Factor(psr_type="X01", fuel="Fixed", median=100.0, lo=100.0,
                           hi=100.0, confidence="test", source="test row")}
    assert variance_contribution({"X01": 50.0}, fixed, n_draws=1_000) == []


def test_a_single_varying_fuel_owns_all_of_the_spread(factors):
    shares = variance_contribution({"B14": 100.0}, factors, n_draws=2_000)
    assert [r["psr_type"] for r in shares] == ["B14"]
    assert shares[0]["variance_share"] == pytest.approx(1.0)
    assert shares[0]["width_share"] == pytest.approx(1.0)
