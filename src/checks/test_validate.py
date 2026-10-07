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
