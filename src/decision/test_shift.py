"""Tests for the decision model's core (docs/DECISION_MODEL.md).

They pin what the design fixes and what shift.py adds to it (R1-R5): which
starts a day offers, clock changes included; that the plant moves only for a
real gain; that perfect foresight bounds every other forecast; that the
naive forecast reads the same clock hour a week earlier; how the CO2 figures
relate; and that a withheld intensity hour empties a day's CO2 figures only
inside the window a shift can reach.
"""
import numpy as np
import pandas as pd
import pytest

from shift import (
    CO2_WINDOW,
    DEFAULT_START,
    K_HOURS,
    block_means,
    candidate_starts,
    choose,
    decide_day,
    decide_zone,
    hourly_energy_by_fuel,
    hourly_intensity,
    hourly_prices,
    intensity_draws,
    local_hours,
    naive_forecast,
    yearly,
)

DAY = list(range(24))
SPRING = [0, 1] + list(range(3, 24))          # 30.03.2025, Europe/Berlin
AUTUMN = [0, 1, 2, 2] + list(range(3, 24))    # 26.10.2025


def _utc_hours(start: str, end: str) -> pd.DataFrame:
    return pd.DataFrame({"hour_utc": pd.date_range(start, end, freq="h", inclusive="left")})


# --------------------------------------------------------------------------
# The plant: which starts a day offers
# --------------------------------------------------------------------------
@pytest.mark.parametrize("n, first, last", [(2, 6, 10), (4, 4, 12), (6, 2, 14)])
def test_an_ordinary_day_offers_every_start_within_n(n, first, last):
    s = candidate_starts(DAY, n=n)
    assert list(np.asarray(DAY)[s]) == list(range(first, last + 1))


def test_the_23_hour_day_offers_no_start_that_is_not_on_the_clock():
    labels = np.asarray(SPRING)
    s = candidate_starts(SPRING, n=6)
    assert 2 not in labels[s]
    assert list(labels[s]) == list(range(3, 15))


def test_the_25_hour_day_offers_the_repeated_hour_once_and_its_first_occurrence():
    s = candidate_starts(AUTUMN, n=6)
    assert list(np.asarray(AUTUMN)[s]).count(2) == 1
    assert s[0] == 2                            # the first 02:00, on summer time


def test_a_block_runs_k_real_hours_across_the_repeated_hour():
    """R2: a block from the first 02:00 covers 02, 02, 03, 04 on the clock."""
    price = np.arange(len(AUTUMN), dtype=float)
    s = candidate_starts(AUTUMN, n=6)
    assert block_means(price, s[:1])[0] == pytest.approx(np.mean([2, 3, 4, 5]))


def test_every_block_ends_inside_the_day():
    for labels in (DAY, SPRING, AUTUMN):
        assert all(i + K_HOURS <= len(labels) for i in candidate_starts(labels, n=6))


def test_a_day_without_the_default_start_is_refused():
    with pytest.raises(ValueError):
        candidate_starts(list(range(9, 24)))


# --------------------------------------------------------------------------
# The choice
# --------------------------------------------------------------------------
def test_flat_prices_keep_the_default():
    r = decide_day(DAY, np.full(24, 50.0), np.full(24, 50.0), np.full(24, 300.0))
    assert r.start == DEFAULT_START and r.eur_saving == 0.0


def test_float_noise_does_not_move_the_plant():
    f = np.full(24, 50.0)
    f[4:8] -= 1e-12
    assert decide_day(DAY, f, f, np.full(24, 300.0)).start == DEFAULT_START


def test_among_equal_alternatives_the_nearest_to_the_default_wins_then_the_earlier():
    labels = np.array([4, 5, 6, 7, 8, 9, 10, 11, 12])
    costs = np.array([1.0, 5, 5, 5, 9, 5, 5, 1.0, 5])
    assert labels[choose(costs, labels)] == 11
    costs = np.array([5, 5, 5, 1.0, 9, 1.0, 5, 5, 5])
    assert labels[choose(costs, labels)] == 7


def test_rising_prices_move_the_block_to_the_earliest_start():
    p = np.arange(24, dtype=float)
    r = decide_day(DAY, p, p, np.full(24, 300.0), n=4)
    assert r.start == 4
    assert r.eur_saving == pytest.approx(4.0)   # every hour 4 € cheaper


def test_the_saving_is_per_mwh_of_the_block():
    p = np.zeros(24)
    p[8:12] = 100.0                              # the default block costs 100 €/MWh
    r = decide_day(DAY, p, p, np.full(24, 300.0))
    assert r.default_cost == pytest.approx(100.0)
    assert r.eur_saving == pytest.approx(100.0)


def test_perfect_foresight_bounds_every_other_forecast():
    rng = np.random.default_rng(1)
    for _ in range(500):
        p = rng.normal(80, 40, 24)
        f = p + rng.normal(0, 30, 24)
        perfect = decide_day(DAY, p, p, np.full(24, 1.0))
        other = decide_day(DAY, p, f, np.full(24, 1.0))
        assert perfect.eur_saving >= 0
        assert perfect.eur_saving >= other.eur_saving - 1e-12


def test_a_wrong_forecast_can_cost_money():
    p = np.full(24, 50.0)
    p[4:8] = 200.0
    f = np.full(24, 50.0)
    f[4:8] = 10.0
    r = decide_day(DAY, p, f, np.full(24, 1.0))
    assert r.start == 4 and r.eur_saving == pytest.approx(-150.0)


def test_a_start_without_a_whole_forecast_is_not_offered():
    p = np.arange(24, dtype=float)
    f = p.copy()
    f[4] = np.nan                                  # every block from 04:00 loses it
    r = decide_day(DAY, p, f, np.full(24, 1.0))
    assert r.start == 5 and r.forecast_whole


def test_no_forecast_keeps_the_default_and_says_so():
    p = np.arange(24, dtype=float)
    r = decide_day(DAY, p, np.full(24, np.nan), np.full(24, 1.0))
    assert r.start == DEFAULT_START and r.eur_saving == 0.0 and not r.forecast_whole


# --------------------------------------------------------------------------
# CO2
# --------------------------------------------------------------------------
def test_absolute_co2_is_relative_times_the_default_intensity():
    rng = np.random.default_rng(2)
    p = rng.normal(80, 40, 24)
    i = rng.uniform(50, 600, (200, 24))
    r = decide_day(DAY, p, p, i)
    np.testing.assert_allclose(r.co2_effect, r.co2_effect_rel * r.default_intensity)
    np.testing.assert_allclose(r.co2_potential, r.co2_potential_rel * r.default_intensity)


def test_the_potential_is_never_below_zero_nor_below_the_cost_driven_effect():
    rng = np.random.default_rng(3)
    for _ in range(100):
        p = rng.normal(80, 40, 24)
        i = rng.uniform(50, 600, (50, 24))
        r = decide_day(DAY, p, p, i)
        assert (r.co2_potential >= 0).all()
        assert (r.co2_potential >= r.co2_effect - 1e-12).all()


def test_the_carbon_optimal_start_is_taken_under_each_draw():
    i = np.full((2, 24), 300.0)
    i[0, 4:8] = 100.0
    i[1, 12:16] = 100.0
    r = decide_day(DAY, np.full(24, 50.0), np.full(24, 50.0), i)
    assert list(r.carbon_start) == [4, 12]
    np.testing.assert_allclose(r.co2_potential, [200.0, 200.0])
    np.testing.assert_allclose(r.co2_effect, [0.0, 0.0])   # cost did not move it


@pytest.mark.parametrize("hour, withheld", [(CO2_WINDOW[0], True), (CO2_WINDOW[1] - 1, True),
                                            (CO2_WINDOW[0] - 1, False), (CO2_WINDOW[1], False)])
def test_a_withheld_hour_empties_the_co2_figures_only_inside_the_window(hour, withheld):
    i = np.full(24, 300.0)
    i[hour] = np.nan
    r = decide_day(DAY, np.arange(24.0), np.arange(24.0), i)
    assert r.co2_withheld is withheld
    assert bool(np.isnan(r.co2_effect).all()) is withheld
    assert r.eur_saving == pytest.approx(4.0)      # € keeps every day


# --------------------------------------------------------------------------
# Hours from steps (R5)
# --------------------------------------------------------------------------
def test_quarter_hour_prices_average_to_the_hour_and_a_repeated_price_is_unchanged():
    ts = pd.date_range("2025-09-30 00:00", periods=8, freq="15min")
    s = pd.DataFrame({"ts_utc": ts, "step_hours": 0.25,
                      "price_eur_mwh": [10, 20, 30, 40, 55, 55, 55, 55]})
    h = hourly_prices(s)
    assert list(h["price_eur_mwh"]) == [25.0, 55.0]


def test_an_hour_its_steps_do_not_cover_has_no_price():
    ts = pd.date_range("2025-10-01 00:00", periods=3, freq="15min")
    h = hourly_prices(pd.DataFrame({"ts_utc": ts, "step_hours": 0.25, "price_eur_mwh": 10.0}))
    assert h["price_eur_mwh"].isna().all()


def test_intensity_is_energy_weighted_to_the_hour_not_averaged():
    ts = pd.date_range("2025-06-01 00:00", periods=4, freq="15min")
    s = pd.DataFrame({"ts_utc": ts, "step_hours": 0.25,
                      "priced_mwh": [100.0, 100.0, 100.0, 700.0],
                      "emissions_kg": [100e3, 100e3, 100e3, 70e3]})
    s["intensity_g_kwh"] = s["emissions_kg"] / s["priced_mwh"]
    h = hourly_intensity(s)
    assert h["intensity_g_kwh"].iloc[0] == pytest.approx(370e3 / 1000)
    assert h["intensity_g_kwh"].iloc[0] != pytest.approx(s["intensity_g_kwh"].mean())


def test_a_withheld_step_withholds_its_hour():
    ts = pd.date_range("2025-06-01 00:00", periods=4, freq="15min")
    s = pd.DataFrame({"ts_utc": ts, "step_hours": 0.25, "priced_mwh": 100.0,
                      "emissions_kg": 30e3, "intensity_g_kwh": [300, 300, None, 300]})
    assert hourly_intensity(s)["intensity_g_kwh"].isna().all()


def test_draws_at_the_median_factors_return_the_point():
    gen = pd.DataFrame({
        "ts_utc": pd.date_range("2025-06-01", periods=8, freq="15min").repeat(2),
        "psr_type": ["B02", "B16"] * 8, "direction": "generation",
        "mwh": [50.0, 25.0] * 4 + [10.0, 90.0] * 4,
    })
    medians = np.array([[1060.0, 41.0]])
    e = hourly_energy_by_fuel(gen, ["B02", "B16"])
    i = intensity_draws(e.to_numpy(), medians)[0]
    expected = (e["B02"] * 1060 + e["B16"] * 41) / e.sum(axis=1)
    np.testing.assert_allclose(i, expected.to_numpy())


def test_consumption_and_unpriced_fuels_leave_the_energy():
    gen = pd.DataFrame({"ts_utc": pd.Timestamp("2025-06-01"), "psr_type": ["B02", "B10", "B02"],
                        "direction": ["generation", "generation", "consumption"],
                        "mwh": [10.0, 99.0, 99.0]})
    e = hourly_energy_by_fuel(gen, ["B02", "B16"])
    assert e.loc[pd.Timestamp("2025-06-01")].tolist() == [10.0, 0.0]


@pytest.mark.parametrize("date, n_hours", [("2025-03-30", 23), ("2025-10-26", 25), ("2025-06-01", 24)])
def test_local_days_have_23_24_or_25_hours(date, n_hours):
    h = local_hours(_utc_hours("2025-03-29", "2025-10-28"), "Europe/Berlin")
    day = h[h["local_date"] == pd.Timestamp(date).date()]
    assert len(day) == n_hours
    assert day["occurrence"].sum() == (1 if n_hours == 25 else 0)


def test_a_missing_hour_becomes_an_empty_row_so_no_block_jumps_a_gap():
    h = _utc_hours("2025-06-01 22:00", "2025-06-02 22:00")
    h["intensity_g_kwh"] = 300.0
    h["price_eur_mwh"] = 50.0
    gap = h.drop(index=[12, 13, 14]).reset_index(drop=True)    # 10:00-12:59 UTC
    day = local_hours(gap, "Europe/Berlin")
    assert len(day) == 24 and day["intensity_g_kwh"].isna().sum() == 3
    r = decide_day(day["local_hour"], day["price_eur_mwh"], day["price_eur_mwh"],
                   day["intensity_g_kwh"])
    assert r.co2_withheld                       # 12:00-14:59 local lie in the window


# --------------------------------------------------------------------------
# The naive forecast (R3)
# --------------------------------------------------------------------------
def _hours_with_prices(start, end, tz="Europe/Berlin", fn=None):
    h = local_hours(_utc_hours(start, end), tz)
    h["price_eur_mwh"] = fn(h) if fn else np.arange(len(h), dtype=float)
    return h


def test_naive_is_the_same_clock_hour_a_week_earlier():
    h = _hours_with_prices("2025-06-01", "2025-06-20")
    f = naive_forecast(h)
    for date in ("2025-06-10", "2025-06-15"):
        d = pd.Timestamp(date).date()
        w = (pd.Timestamp(date) - pd.Timedelta(days=7)).date()
        np.testing.assert_array_equal(f[h["local_date"] == d].to_numpy(),
                                      h.loc[h["local_date"] == w, "price_eur_mwh"].to_numpy())


def test_the_first_week_has_no_naive_forecast():
    h = _hours_with_prices("2025-06-01", "2025-06-20")
    assert naive_forecast(h)[h["local_date"] < pd.Timestamp("2025-06-08").date()].isna().all()


def test_naive_across_the_clock_changes():
    h = _hours_with_prices("2025-03-20", "2025-04-10", fn=lambda x: x["local_hour"] * 1.0)
    f = naive_forecast(h)
    week_after = h["local_date"] == pd.Timestamp("2025-04-06").date()   # 30.03 + 7
    hour2 = week_after & (h["local_hour"] == 2)
    assert f[hour2].isna().all()                  # 30.03 had no 02:00
    assert f[week_after & ~hour2].notna().all()
    h = _hours_with_prices("2025-10-15", "2025-11-05", fn=lambda x: x["local_hour"] * 1.0)
    f = naive_forecast(h)
    autumn = h["local_date"] == pd.Timestamp("2025-10-26").date()
    assert f[autumn & (h["local_hour"] == 2)].tolist() == [2.0, 2.0]


# --------------------------------------------------------------------------
# A zone
# --------------------------------------------------------------------------
def _zone(days=60, seed=4, tz="Europe/Berlin"):
    rng = np.random.default_rng(seed)
    h = local_hours(_utc_hours("2024-12-31 23:00", pd.Timestamp("2024-12-31 23:00")
                                + pd.Timedelta(days=days)), tz)
    shape = np.sin((h["local_hour"] - 8) / 24 * 2 * np.pi)
    h["price_eur_mwh"] = 80 + 30 * shape + rng.normal(0, 10, len(h))
    h["intensity_g_kwh"] = 350 + 90 * shape + rng.normal(0, 20, len(h))
    return h


def test_a_zone_is_decided_day_by_day_and_perfect_bounds_naive():
    h = _zone()
    perfect, acc_p = decide_zone(h, "perfect")
    naive, acc_n = decide_zone(h, "naive")
    assert len(perfect) == len(naive) == 60
    assert (perfect["eur_saving_per_mwh"] >= naive["eur_saving_per_mwh"] - 1e-12).all()
    assert (~naive["forecast_whole"]).sum() == 7
    assert (naive.loc[~naive["forecast_whole"], "eur_saving_per_mwh"] == 0).all()


def test_yearly_figures_follow_from_the_days():
    h = _zone()
    days, acc = decide_zone(h, "perfect")
    y = yearly(acc).iloc[0]
    assert y["eur_saving_per_mwh"] == pytest.approx(days["eur_saving_per_mwh"].mean())
    assert y["co2_effect_kg_mwh"] == pytest.approx(days["co2_effect_kg_mwh"].mean())
    rel = days["co2_effect_kg_mwh"].sum() / days["default_intensity_g_kwh"].sum()
    assert y["co2_effect_rel"] == pytest.approx(rel)


def test_under_draws_the_point_lies_inside_its_interval():
    """The design's rule for the saving: every input at its centre must lie in
    the interval (Checkpoint 8). Here the draws scatter around the point."""
    h = _zone()
    rng = np.random.default_rng(5)
    draws = h["intensity_g_kwh"].to_numpy() * rng.lognormal(0, 0.1, (400, 1))
    days, acc = decide_zone(h, "perfect", intensity=draws)
    y = yearly(acc).iloc[0]
    _, acc0 = decide_zone(h, "perfect")
    p = yearly(acc0).iloc[0]
    for name in ("co2_effect_kg_mwh", "co2_potential_kg_mwh"):
        assert y[f"{name}_p05"] <= p[name] <= y[f"{name}_p95"]
    assert {"co2_effect_p05_kg_mwh", "co2_potential_p95_kg_mwh"} <= set(days.columns)
