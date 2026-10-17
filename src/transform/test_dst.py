"""Daylight-saving regression tests.

The DST handling already existed in `validate.expected_steps` and in the
T-SQL DQ views (now archived in `archive/azure-excursion/`), but nothing
proved it. Since a local calendar day has
23, 24 or 25 hours -- 92, 96 or 100 steps at PT15M -- a hard-coded "= 96" rule
reports two false failures a year AND hides real gaps on those same two days.
That is the bug these tests exist to prevent.

They also pin the design decision: timestamps are stored in UTC and converted
to local only for calendar reasoning. Normalising the warehouse to a fixed
CET offset would be wrong for Germany, which observes CEST from late March to
late October.

EU transitions in 2026: 29 March (spring forward), 25 October (fall back).
"""
import datetime as dt

import pytest

from validate import check_stage3_coverage, expected_steps

TZ = "Europe/Berlin"
SPRING_FORWARD = dt.date(2026, 3, 29)  # 23-hour local day
FALL_BACK = dt.date(2026, 10, 25)  # 25-hour local day
ORDINARY = dt.date(2026, 8, 1)  # 24-hour local day


@pytest.mark.parametrize(
    "day, step_hours, expected",
    [
        (ORDINARY, 0.25, 96),
        (SPRING_FORWARD, 0.25, 92),
        (FALL_BACK, 0.25, 100),
        (ORDINARY, 1.0, 24),
        (SPRING_FORWARD, 1.0, 23),
        (FALL_BACK, 1.0, 25),
    ],
)
def test_expected_steps_follows_the_local_calendar(day, step_hours, expected):
    assert expected_steps(day, TZ, step_hours) == expected


def test_a_fixed_96_rule_would_be_wrong_twice_a_year():
    """The assumption this project refuses to make."""
    assert expected_steps(SPRING_FORWARD, TZ, 0.25) != 96
    assert expected_steps(FALL_BACK, TZ, 0.25) != 96


def _day_of_rows(local_date: str | dt.date, tz: str, step_hours: float, psr="B19"):
    """Build one full local day of UTC-stamped generation rows."""
    import zoneinfo

    z = zoneinfo.ZoneInfo(tz)
    if isinstance(local_date, str):
        local_date = dt.date.fromisoformat(local_date)
    # Step in real elapsed time from local midnight, not in wall-clock hours:
    # adding a timedelta to an aware datetime does naive arithmetic, so on a
    # fall-back day wall-clock stepping would skip the repeated hour.
    start_utc = dt.datetime.combine(local_date, dt.time(0), tzinfo=z).astimezone(
        dt.timezone.utc
    )
    n = expected_steps(local_date, tz, step_hours)
    rows = []
    for i in range(n):
        ts_utc = start_utc + dt.timedelta(hours=step_hours * i)
        rows.append(
            {
                "ts_utc": ts_utc,
                "zone": "10Y1001A1001A82H",
                "psr": psr,
                "fuel": "Wind Onshore",
                "direction": "generation",
                "resolution": "PT15M",
                "step_hours": step_hours,
                "mw": 1000.0,
                "mwh": 1000.0 * step_hours,
                "n_points_stated": n,
                "n_steps_expanded": n,
            }
        )
    return rows


@pytest.mark.parametrize("day", [ORDINARY, SPRING_FORWARD, FALL_BACK])
def test_complete_local_day_passes_coverage(day):
    ok, msg = check_stage3_coverage(_day_of_rows(day, TZ, 0.25), TZ)
    assert ok, msg


def test_fall_back_day_is_recognised_as_dst_not_as_duplicates():
    """25 hours is correct on 25 October, not a duplicate-row bug."""
    ok, msg = check_stage3_coverage(_day_of_rows(FALL_BACK, TZ, 0.25), TZ)
    assert ok
    assert "DST days handled correctly" in msg


def test_short_day_is_still_detected_when_steps_are_actually_missing():
    """The DST allowance must not become a blanket excuse for gaps."""
    rows = _day_of_rows(FALL_BACK, TZ, 0.25)
    ok, msg = check_stage3_coverage(rows[:-4], TZ)
    assert not ok, "dropping four steps from a 100-step day must fail"
    assert "MISMATCHES" in msg


def test_utc_storage_survives_the_repeated_local_hour():
    """02:00-03:00 local occurs twice on fall-back day; UTC keeps them distinct."""
    import zoneinfo

    z = zoneinfo.ZoneInfo(TZ)
    rows = _day_of_rows(FALL_BACK, TZ, 1.0)
    stamps = [r["ts_utc"] for r in rows]
    assert len(set(stamps)) == len(stamps) == 25, "25 distinct UTC instants"
    local_hours = [s.astimezone(z).strftime("%H") for s in stamps]
    assert local_hours.count("02") == 2, "local hour 02 is genuinely repeated"
