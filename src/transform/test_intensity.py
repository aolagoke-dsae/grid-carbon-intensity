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
    MC_SEED,
    Z_BAND,
    Factor,
    describe_sampling,
    energy_by_fuel,
    factor_matrix,
    intensity_draws,
    load_factors,
    sample_factor,
    shared_factor_draws,
    step_intervals,
    summarise,
    variance_contribution,
)

FACTORS_CSV = Path(__file__).resolve().parents[2] / "config" / "ipcc_ar5_factors.csv"

# A low-carbon mix with reservoir hydro in it, written down in two orders.
# Reservoir (B12), not run-of-river: since 18.10.2026 only B12 carries
# AR5's long hydropower tail, which is what makes the order bug visible.
HYDRO_FIRST = {"B12": 300.0, "B04": 2000.0, "B14": 6000.0, "B16": 800.0, "B19": 1200.0, "B18": 500.0}
HYDRO_LAST = {k: HYDRO_FIRST[k] for k in ["B04", "B14", "B16", "B19", "B18", "B12"]}


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
    for psr in ("B06", "B10", "B15", "B17", "B20", "B25"):
        assert psr in factors, f"{psr} must exist as an explicit row"
        assert not factors[psr].priced, f"{psr} must be deliberately unpriced"
        assert factors[psr].confidence in {"excluded", "unknown"}


def test_proxies_say_so(factors):
    """AR5 has one coal row. Coal-derived gas borrows it, which is a proxy,
    not a citation (audit A12). Lignite borrowed it too until 19.10.2026."""
    assert factors["B03"].confidence == "low"
    assert factors["B03"].source.startswith("Proxy")


def test_lignite_is_priced_as_lignite(factors):
    """Decided 19.10.2026 (docs/FACTOR_CHECK.md, decision 1). Lignite is
    DE-LU's largest fossil source, and on AR5's coal row (740 / 820 / 910) it
    understated DE-LU by 38-52 gCO2e/kWh, 2021-2025. No lignite source
    publishes a median, so B02 carries Germany's value read off Itten et al.
    (2023), Fig. 4.5, with their range across countries as the band."""
    lig, ar5_coal = factors["B02"], factors["B03"]  # B03 still uses the AR5 row
    assert (lig.lo, lig.median, lig.hi) == (1000.0, 1060.0, 1350.0)
    assert lig.lo > ar5_coal.hi, "the lignite band must clear the whole coal row"
    assert not lig.source.startswith("Proxy") and "Itten" in lig.source
    assert lig.confidence == "medium"


def test_hard_coal_is_priced_for_germany(factors):
    """Decided 19.10.2026 (docs/FACTOR_CHECK.md, decision 1), after lignite.
    The same figure puts German hard coal at 1.04 kgCO2e/kWh, above the whole
    AR5 coal row, which understated DE-LU by a further 14-29 gCO2e/kWh,
    2021-2025. Germany's value is the centre and the range across countries
    the band; only coal-derived gas stays on the AR5 row."""
    hard, ar5_coal = factors["B05"], factors["B03"]
    assert (hard.lo, hard.median, hard.hi) == (861.0, 1040.0, 1320.0)
    assert (ar5_coal.lo, ar5_coal.median, ar5_coal.hi) == (740.0, 820.0, 910.0)
    assert hard.median > ar5_coal.hi
    assert not hard.source.startswith("Proxy") and "Itten" in hard.source
    assert hard.confidence == "medium"


def test_a_priced_placeholder_is_refused(tmp_path):
    """Until 17.10.2026 oil was priced from a row reading "placeholder
    pending a cited source", and the provenance test only checked that the
    text was not empty."""
    csv = tmp_path / "factors.csv"
    csv.write_text(
        "psr_type,fuel,ef_median_g_kwh,ef_min_g_kwh,ef_max_g_kwh,confidence,source\n"
        "B06,Fossil Oil,650,510,840,low,No AR5 oil row - placeholder pending a cited source\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="placeholder"):
        load_factors(csv)


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
    """Reservoir hydro keeps its long right side; AR5's coal row stays almost
    symmetric. Since 19.10.2026 only coal-derived gas (B03) uses that row:
    hard coal (B05) carries Germany's value and a band of its own."""

    def right_over_left(d):
        m = np.median(d)
        return (np.percentile(d, 90) - m) / (m - np.percentile(d, 10))

    hydro = sample_factor(factors["B12"], 100_000, np.random.default_rng(2))
    coal = sample_factor(factors["B03"], 100_000, np.random.default_rng(2))
    assert right_over_left(hydro) > 10
    assert right_over_left(coal) == pytest.approx(1.0, abs=0.15)


def test_a_triangular_over_the_hydro_range_would_wreck_the_median(factors):
    """Why no triangular is used anywhere.

    AR5 hydro is 1 / 24 / 2200 (B12, reservoirs). A triangular over that has
    its median near 650 gCO2e/kWh -- comparable to gas -- because the mode
    sits at the 1st percentile of the range.
    """
    f = factors["B12"]
    naive = np.median(np.random.default_rng(1).triangular(f.lo, f.median, f.hi, 20_000))
    fitted = np.median(sample_factor(f, 20_000, np.random.default_rng(1)))
    assert naive > 500, "sanity: the naive choice really is that bad"
    assert fitted == pytest.approx(f.median, rel=0.05)


def test_run_of_river_carries_no_reservoir_tail(factors):
    """Decided 18.10.2026 (docs/FACTOR_CHECK.md, decision 2). AR5 has one
    hydropower row, and its upper end is reservoir methane. Run-of-river keeps
    AR5's minimum and median and stops at the median; reservoirs keep the row.
    Under the full band run-of-river owned 65-71% of France's interval
    variance, 2021-2025."""
    ror, res = factors["B11"], factors["B12"]
    assert (ror.lo, ror.median, ror.hi) == (1.0, 24.0, 24.0)
    assert (res.lo, res.median, res.hi) == (1.0, 24.0, 2200.0)
    draws = sample_factor(ror, 50_000, np.random.default_rng(7))
    assert draws.max() <= 24.0
    assert np.median(draws) == pytest.approx(24.0, rel=0.02)


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
    assert out["intensity_median"] == pytest.approx(factors["B05"].median, rel=0.02)
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


# --------------------------------------------------------------------------
# One set of draws for every step (WE 6): what the warehouse stores in
# dim_factor_draw and int_intensity_interval computes with
# --------------------------------------------------------------------------
def test_shared_draws_are_the_priced_fuels_under_the_seed(factors):
    """The priced fuels in sorted order, each column drawn as factor_matrix
    draws it; the same seed gives the same draws, another seed others."""
    fuels, draws = shared_factor_draws(factors, 500, 11)
    assert fuels == sorted(p for p, f in factors.items() if f.priced)
    assert np.array_equal(draws, factor_matrix(fuels, factors, 500, np.random.default_rng(11)))
    assert np.array_equal(draws, shared_factor_draws(factors, 500, 11)[1])
    assert not np.array_equal(draws, shared_factor_draws(factors, 500, 12)[1])
    assert np.array_equal(shared_factor_draws(factors, 50)[1], shared_factor_draws(factors, 50, MC_SEED)[1])


def test_a_steps_interval_is_its_mix_under_the_shared_draws(factors):
    """Each row of step_intervals is what intensity_draws gives that step's
    mix under the same factor draws, however the steps are blocked; a step
    without priced energy gets no interval."""
    fuels, draws = shared_factor_draws(factors, 4000, 5)
    mixes = [{"B02": 300.0, "B04": 500.0, "B19": 900.0}, {"B14": 7000.0, "B12": 300.0, "B16": 50.0}, {}]
    energy = np.array([[m.get(p, 0.0) for p in fuels] for m in mixes])
    got = step_intervals(energy, draws, budget=4000)        # one step per block
    assert np.allclose(got, step_intervals(energy, draws), rtol=1e-12, atol=0, equal_nan=True)
    for m, row in zip(mixes[:2], got):
        w = np.array([m.get(p, 0.0) for p in fuels])
        assert row == pytest.approx(np.percentile(draws @ w / w.sum(), [5, 50, 95]), rel=1e-12)
    assert np.isnan(got[2]).all()


def test_a_shared_draw_keeps_a_years_interval_as_wide_as_its_errors(factors):
    """Prevents: drawing each step afresh. A factor's error is the same in
    every hour, so the mean of a hundred identical hours is exactly as
    uncertain as one of them. Drawn independently per hour, the errors
    average out and the interval shrinks about tenfold."""
    mix = {"B02": 300.0, "B04": 500.0, "B19": 900.0}
    fuels, draws = shared_factor_draws(factors, 4000)
    w = np.array([mix.get(p, 0.0) for p in fuels])
    one = step_intervals(w[None, :], draws)[0]
    year = step_intervals(np.tile(w, (100, 1)).sum(axis=0)[None, :], draws)[0]
    rng = np.random.default_rng(1)
    hourly = np.stack([intensity_draws(mix, factors, 4000, rng)[0] for _ in range(100)])
    width_independent = np.subtract(*np.percentile(hourly.mean(axis=0), [95, 5]))
    assert year == pytest.approx(one, rel=1e-12)
    assert width_independent < (one[2] - one[0]) / 5


def test_step_intervals_refuses_energy_and_draws_of_different_fuels(factors):
    fuels, draws = shared_factor_draws(factors, 10)
    with pytest.raises(ValueError):
        step_intervals(np.ones((2, len(fuels) - 1)), draws)
