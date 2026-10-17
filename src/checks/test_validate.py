"""Regression tests for the stage checkpoints.

All three failures below were live on 2026-10-07 and none was caught by the
existing suite, because every fixture was single-period and single-zone. A
checkpoint that cannot fail on correct data is worse than no checkpoint: it
sends you debugging a parser that works.
"""
import datetime as dt

from intensity import Factor
from validate import (
    check_stage2_parse,
    check_stage3_coverage,
    check_stage4_factors,
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
    assert "2 day-series short in series reported only while running" in msg, msg


def test_stage3_accepts_a_recorded_source_gap_of_the_same_size_only():
    rows = _rows(zone="FR", days=(1,), steps=24, step_h=1.0, psr="B18")[:-4]   # 20 of 24
    day = dt.date(2026, 1, 1)
    ok, msg = check_stage3_coverage(rows, "UTC", known={("FR", day, "B18"): 4})
    assert ok and "recorded source gaps (4 steps)" in msg, msg
    ok, msg = check_stage3_coverage(rows, "UTC", known={("FR", day, "B18"): 3})
    assert not ok and "FR 2026-01-01 B18: 20/24" in msg, msg


def test_the_coverage_policy_files_load():
    sparse, known = load_coverage_policy()
    assert {("10YFR-RTE------C", "B05"), ("10YFR-RTE------C", "B25")} <= sparse
    assert not any(zone == "10Y1001A1001A82H" for zone, _ in sparse), "DE-LU declares none"
    assert known and all(n > 0 for n in known.values())


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


def test_stage4_still_fails_on_a_fuel_with_no_row_at_all():
    factors = {"B02": Factor(psr_type="B02", fuel="Lignite", median=820,
                             lo=740, hi=910, confidence="high", source="AR5")}
    rows = [{"psr": "B08", "direction": "generation"}]   # Peat, as in IE-SEM
    ok, msg = check_stage4_factors(rows, factors)
    assert not ok and "B08" in msg
