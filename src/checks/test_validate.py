"""Regression tests for the stage checkpoints.

All three failures below were live on 2026-10-07 and none was caught by the
existing suite, because every fixture was single-period and single-zone. A
checkpoint that cannot fail on correct data is worse than no checkpoint: it
sends you debugging a parser that works.
"""
import datetime as dt

import pytest

from intensity import Factor
from validate import (
    check_stage2_parse,
    check_stage3_coverage,
    check_stage4_factors,
    check_stage5_intensity,
    incomplete_steps,
    load_coverage_policy,
)

UTC = dt.timezone.utc


def _rows(zone="DE", days=(1, 2), steps=96, step_h=0.25, psr="B16"):
    out = []
    for d in days:
        start = dt.datetime(2026, 1, d, tzinfo=UTC)
        for pos in range(steps):
            out.append({
                "psr": psr, "direction": "generation", "zone": zone, "mw": 1.0,
                "ts_utc": start + dt.timedelta(hours=step_h * pos),
                "period_start_utc": start,
                "step_hours": step_h, "n_steps_expanded": steps,
            })
    return out


def test_stage2_accepts_a_series_spanning_many_periods():
    """A yearly A75 carries one Period per day.

    Keying on (psr, direction) alone compared 365 days of rows against one
    day's step count, so the check failed on every correct full-year parse.
    """
    ok, msg = check_stage2_parse(_rows(days=(1, 2, 3)))
    assert ok, msg
    assert "3 series" in msg


def test_stage2_does_not_merge_zones():
    """Two zones checked together share psr and period. Keyed without the
    zone, both zones' rows were counted against one step count, and a
    correct parse failed (audit A10)."""
    ok, msg = check_stage2_parse(_rows(zone="DE", days=(1,)) + _rows(zone="FR", days=(1,)))
    assert ok, msg
    assert "2 series" in msg, msg


def test_stage2_still_catches_a_short_period():
    rows = _rows(days=(1,))
    del rows[-1]                      # 95 of 96 steps
    ok, msg = check_stage2_parse(rows)
    assert not ok and "wrong row count" in msg


def test_stage3_does_not_merge_zones():
    """Two zones share timestamps. Without zone in the key they collapse,
    and a zone missing a whole day hides behind a zone that has it."""
    rows = _rows(zone="DE", days=(5,), steps=24, step_h=1.0) \
         + _rows(zone="FR", days=(5,), steps=24, step_h=1.0)
    ok, msg = check_stage3_coverage(rows, "UTC")
    assert ok, msg
    assert "2 day-series" in msg, msg


def test_stage3_reports_the_zone_that_is_short():
    rows = _rows(zone="DE", days=(5,), steps=24, step_h=1.0) \
         + _rows(zone="FR", days=(5,), steps=24, step_h=1.0)[:-1]
    ok, msg = check_stage3_coverage(rows, "UTC")
    assert not ok
    assert "FR" in msg and "23/24" in msg, msg


def test_stage3_sees_a_day_with_no_rows_at_all():
    """Until 17.10.2026 only days holding at least one row were checked, so a
    whole missing day passed, and the RUNBOOK's "break one on purpose" would
    not have broken anything."""
    rows = _rows(zone="DE", days=(1, 3), steps=24, step_h=1.0)
    ok, msg = check_stage3_coverage(rows, "UTC")
    assert not ok
    assert "DE 2026-01-02 B16: 0/24" in msg, msg


def test_stage3_exempts_a_series_reported_only_while_running():
    """French coal in the 2025 pull: present on some days, absent on others,
    part of a day when a unit starts or stops."""
    rows = (_rows(zone="FR", days=(1, 2, 3), steps=24, step_h=1.0, psr="B04")
            + _rows(zone="FR", days=(1,), steps=24, step_h=1.0, psr="B05")
            + _rows(zone="FR", days=(3,), steps=10, step_h=1.0, psr="B05"))
    assert not check_stage3_coverage(rows, "UTC")[0]
    ok, msg = check_stage3_coverage(rows, "UTC", sparse={("FR", "B05")})
    assert ok, msg
    assert "2 day-series short in series exempted by sparse_series.csv" in msg, msg


def test_stage3_accepts_a_recorded_source_gap_of_the_same_size_only():
    rows = _rows(zone="FR", days=(1,), steps=24, step_h=1.0, psr="B18")[:-4]   # 20 of 24
    day = dt.date(2026, 1, 1)
    ok, msg = check_stage3_coverage(rows, "UTC", known={("FR", day, "B18"): 4})
    assert ok and "recorded source gaps (4 steps)" in msg, msg
    ok, msg = check_stage3_coverage(rows, "UTC", known={("FR", day, "B18"): 3})
    assert not ok and "FR 2026-01-01 B18: 20/24" in msg, msg


def test_stage3_counts_a_step_reported_only_as_consumption():
    """RTE's hourly A75 states pumped storage net until December 2024: an hour
    carries the generation leg or the consumption leg, never both. Counted on
    generation rows alone, the 3,840 pumping hours of 2021 were gaps, and 44 %
    of French hours were withheld as partial mixes. Found 18.10.2026."""
    gen = _rows(zone="FR", days=(1,), steps=24, step_h=1.0, psr="B10")
    pumping = {gen[i]["ts_utc"] for i in (2, 3, 4)}
    rows = ([r for r in gen if r["ts_utc"] not in pumping]
            + [{**r, "direction": "consumption"} for r in gen if r["ts_utc"] in pumping])
    ok, msg = check_stage3_coverage(rows, "UTC")
    assert ok, msg
    ok, msg = check_stage3_coverage([r for r in rows if r["direction"] == "generation"], "UTC")
    assert not ok and "FR 2026-01-01 B10: 21/24" in msg, msg


def test_stage3_does_not_check_a_series_published_only_as_consumption():
    """A fuel that only ever consumes is not a generation series."""
    rows = (_rows(zone="DE", days=(1,), steps=24, step_h=1.0, psr="B04")
            + [{**r, "direction": "consumption"}
               for r in _rows(zone="DE", days=(1,), steps=5, step_h=1.0, psr="B10")])
    ok, msg = check_stage3_coverage(rows, "UTC")
    assert ok and "1 day-series" in msg, msg


def test_stage3_measures_a_change_of_resolution_in_time():
    """France moved from PT60M to PT15M on 19.12.2024: one hourly stamp, then
    92 quarter-hours. Counting stamps called the complete day 93 of 96."""
    hour = _rows(zone="FR", days=(1,), steps=1, step_h=1.0, psr="B01")
    quarters = [{**r, "ts_utc": r["ts_utc"] + dt.timedelta(hours=1)}
                for r in _rows(zone="FR", days=(1,), steps=92, step_h=0.25, psr="B01")]
    ok, msg = check_stage3_coverage(hour + quarters, "UTC")
    assert ok, msg
    ok, msg = check_stage3_coverage(hour + quarters[:-1], "UTC")
    assert not ok and "FR 2026-01-01 B01: 95/96" in msg, msg


def test_stage3_exempts_a_series_only_inside_its_window():
    """German nuclear ended on 15.04.2023; after that a missing quarter-hour is
    zero output. Before the window opens, a missing step is still a gap."""
    rows = (_rows(zone="DE", days=(1, 2, 3), steps=24, step_h=1.0, psr="B04")
            + _rows(zone="DE", days=(1,), steps=24, step_h=1.0, psr="B14")
            + _rows(zone="DE", days=(2,), steps=20, step_h=1.0, psr="B14"))
    from_day3 = {("DE", "B14", dt.datetime(2026, 1, 3, tzinfo=UTC), None)}
    ok, msg = check_stage3_coverage(rows, "UTC", sparse=from_day3)
    assert not ok and "DE 2026-01-02 B14: 20/24" in msg and "B14: 0/24" not in msg, msg
    from_day2 = {("DE", "B14", dt.datetime(2026, 1, 2, tzinfo=UTC), None)}
    ok, msg = check_stage3_coverage(rows, "UTC", sparse=from_day2)
    assert ok and "2 day-series short" in msg, msg
    until_day1 = {("DE", "B14", None, dt.datetime(2026, 1, 2, tzinfo=UTC))}
    assert not check_stage3_coverage(rows, "UTC", sparse=until_day1)[0]


def test_stage3_sizes_an_absent_day_in_the_zone_step_of_that_day():
    """French offshore wind was absent on whole days in June 2023, when France
    published hourly, and its latest rows are quarter-hours. Sized by those,
    the absent day was 0/96 over all years and 0/24 over 2023 alone."""
    rows = (_rows(zone="FR", days=(1, 2), steps=24, step_h=1.0, psr="B01")
            + _rows(zone="FR", days=(2,), steps=96, step_h=0.25, psr="B18"))
    ok, msg = check_stage3_coverage(rows, "UTC")
    assert not ok and "FR 2026-01-01 B18: 0/24" in msg, msg
    ok, msg = check_stage3_coverage(rows, "UTC", known={("FR", dt.date(2026, 1, 1), "B18"): 24})
    assert ok and "1 recorded source gaps (24 steps)" in msg, msg


def test_the_coverage_policy_files_load():
    sparse, known = load_coverage_policy()
    assert {("10YFR-RTE------C", "B05"), ("10YFR-RTE------C", "B25")} <= sparse
    assert known and all(n > 0 for n in known.values())


def test_a_window_in_the_policy_file_turns_at_local_midnight(tmp_path):
    """from_date and to_date are local days, both inclusive: the window opens
    or closes at the zone's midnight, 22:00 UTC in summer time."""
    f = tmp_path / "sparse_series.csv"
    f.write_text("zone_eic,psr,from_date,to_date,decided,note\n"
                 "10Y1001A1001A82H,B14,2023-04-16,,2026-10-18,ended\n"
                 "10YFR-RTE------C,B18,,2023-05-31,2026-10-18,not yet published\n"
                 "10YFR-RTE------C,B05,,,2026-10-17,only while a unit runs\n", encoding="utf-8")
    sparse, _ = load_coverage_policy(sparse_csv=f)
    assert sparse == {
        ("10YFR-RTE------C", "B05"),
        ("10Y1001A1001A82H", "B14", dt.datetime(2023, 4, 15, 22, tzinfo=UTC), None),
        ("10YFR-RTE------C", "B18", None, dt.datetime(2023, 5, 31, 22, tzinfo=UTC)),
    }


def test_every_zone_in_the_policy_files_is_a_known_zone():
    """A typo in an EIC would exempt nothing and fail nowhere."""
    import csv
    from pathlib import Path
    config = Path(__file__).resolve().parents[2] / "config"
    with (config / "zones.csv").open(newline="", encoding="utf-8") as fh:
        zones = {row["eic"]: row for row in csv.DictReader(fh)}
    sparse, known = load_coverage_policy()
    assert {e[0] for e in sparse} <= set(zones)
    assert {z for z, _, _ in known} <= set(zones)
    assert {z["key"] for z in zones.values() if z["in_analysis"] == "yes"} == {"DE_LU", "FR"}


def test_stage4_accepts_factor_dataclasses():
    """load_factors() returns Factor objects; the check called dict.get()
    and raised AttributeError. The two modules had never been run together."""
    factors = {
        "B02": Factor(psr_type="B02", fuel="Lignite", median=820, lo=740,
                      hi=910, confidence="high", source="AR5"),
        "B15": Factor(psr_type="B15", fuel="Other renewable", median=None,
                      lo=None, hi=None, confidence="n/a", source="unpriced"),
    }
    rows = [{"psr": "B02", "direction": "generation"},
            {"psr": "B15", "direction": "generation"}]
    ok, msg = check_stage4_factors(rows, factors)
    assert ok, msg
    assert "B15" in msg


# --------------------------------------------------------------------------
# Stage 5. The old check bounded the values to 0-1000 and could not fail on
# a units error (audit A10). This one recomputes every step.
# --------------------------------------------------------------------------
FACTORS = {
    "B04": Factor(psr_type="B04", fuel="Gas", median=490, lo=410, hi=650,
                  confidence="high", source="AR5"),
    "B19": Factor(psr_type="B19", fuel="Wind Onshore", median=11, lo=7, hi=56,
                  confidence="high", source="AR5"),
    "B10": Factor(psr_type="B10", fuel="Hydro Pumped Storage", median=None, lo=None,
                  hi=None, confidence="excluded", source="storage"),
}


def _mix_rows(steps=4, step_h=0.25, drop=()):
    """Gas 300 MW, wind 900 MW and pumped storage 50 MW, quarter-hourly.
    `drop` removes (psr, step) rows to make a step incomplete."""
    out, start = [], dt.datetime(2026, 1, 5, tzinfo=UTC)
    for i in range(steps):
        for psr, mw in (("B04", 300.0), ("B19", 900.0), ("B10", 50.0)):
            if (psr, i) in drop:
                continue
            out.append({"zone": "DE", "psr": psr, "direction": "generation",
                        "ts_utc": start + dt.timedelta(hours=step_h * i),
                        "step_hours": step_h, "mw": mw, "mwh": mw * step_h})
    return out


def _values(rows, numerator="mwh", denominator="mwh", skip=frozenset()):
    """What a pipeline would report: the median-factor mean per step."""
    num, den = {}, {}
    for r in rows:
        k = (r["zone"], r["ts_utc"])
        f = FACTORS[r["psr"]]
        if f.priced:
            num[k] = num.get(k, 0.0) + r[numerator] * f.median
            den[k] = den.get(k, 0.0) + r[denominator]
    return {k: None if k in skip else num[k] / den[k] for k in num}


def test_stage5_accepts_the_median_factor_mean():
    """(300 x 490 + 900 x 11) / 1200 = 130.75; storage is 50 of 1250 MW unpriced."""
    rows = _mix_rows()
    ok, msg = check_stage5_intensity(rows, FACTORS, _values(rows))
    assert ok, msg
    assert "4 steps equal the median-factor mean" in msg and "DE 96.0%" in msg, msg


def test_stage5_catches_mwh_on_one_side_of_the_ratio():
    """MW in the denominator scales every value by the step length. The
    result, a quarter of the true intensity, stays inside the old 0-1000."""
    rows = _mix_rows()
    scaled = _values(rows, denominator="mw")
    assert all(0 <= v <= 1000 for v in scaled.values())
    ok, msg = check_stage5_intensity(rows, FACTORS, scaled)
    assert not ok and "differ from the median-factor mean" in msg, msg


def test_stage5_requires_a_partial_mix_to_be_withheld():
    """Wind missing at one step: the mean of what is left is gas-heavy and wrong."""
    rows = _mix_rows(drop={("B19", 2)})
    gap = (("DE", dt.datetime(2026, 1, 5, 0, 30, tzinfo=UTC)),)
    assert incomplete_steps(rows) == set(gap)
    ok, msg = check_stage5_intensity(rows, FACTORS, _values(rows))
    assert not ok and "partial mix" in msg, msg
    ok, msg = check_stage5_intensity(rows, FACTORS, _values(rows, skip=set(gap)))
    assert ok and "1 withheld" in msg, msg


def test_stage5_exempts_a_series_reported_only_while_running():
    rows = _mix_rows(drop={("B10", 1)})
    assert incomplete_steps(rows, sparse={("DE", "B10")}) == set()
    ok, msg = check_stage5_intensity(rows, FACTORS, _values(rows), sparse={("DE", "B10")})
    assert ok, msg


def test_stage5_counts_the_consumption_leg_and_respects_a_window():
    """A pumping step carries only the consumption leg: the mix is complete,
    with zero generation from storage. A window exempts only inside itself."""
    rows = _mix_rows(drop={("B10", 1)})
    step = dt.datetime(2026, 1, 5, 0, 15, tzinfo=UTC)
    pumping = [{"zone": "DE", "psr": "B10", "direction": "consumption", "ts_utc": step,
                "step_hours": 0.25, "mw": 80.0, "mwh": 20.0}]
    assert incomplete_steps(rows) == {("DE", step)}
    assert incomplete_steps(rows + pumping) == set()
    ok, msg = check_stage5_intensity(rows + pumping, FACTORS, _values(rows))
    assert ok and "0 withheld" in msg, msg
    assert incomplete_steps(rows, sparse={("DE", "B10", step, None)}) == set()
    assert incomplete_steps(rows, sparse={("DE", "B10", None, step)}) == {("DE", step)}


@pytest.mark.parametrize("change", ["missing", "extra", "withheld"])
def test_stage5_accounts_for_every_step(change):
    rows = _mix_rows()
    values = _values(rows)
    first = min(values)
    if change == "missing":
        del values[first]
    elif change == "extra":
        values[("FR", first[1])] = 50.0
    else:
        values[first] = None
    ok, msg = check_stage5_intensity(rows, FACTORS, values)
    assert not ok, msg


def test_stage5_refuses_resolutions_meeting_at_one_step():
    """An hourly series beside quarter-hours would put an hour of energy into
    the first quarter-hour of the per-step mix."""
    rows = _mix_rows(steps=4) + [{"zone": "DE", "psr": "B04", "direction": "generation",
                                  "ts_utc": dt.datetime(2026, 1, 5, tzinfo=UTC),
                                  "step_hours": 1.0, "mw": 10.0, "mwh": 10.0}]
    ok, msg = check_stage5_intensity(rows, FACTORS, _values(rows))
    assert not ok and "different resolution" in msg, msg


def test_stage4_still_fails_on_a_fuel_with_no_row_at_all():
    factors = {"B02": Factor(psr_type="B02", fuel="Lignite", median=820,
                             lo=740, hi=910, confidence="high", source="AR5")}
    rows = [{"psr": "B08", "direction": "generation"}]   # Peat, as in IE-SEM
    ok, msg = check_stage4_factors(rows, factors)
    assert not ok and "B08" in msg
