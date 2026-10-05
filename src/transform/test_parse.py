"""Parser regression tests.

These were previously a print-based demo script with no assertions, while the
README claimed the four payload traps were "asserted in test_parse.py". They
now are. Each test names the failure it prevents, because every one of these
bugs produces a plausible number rather than a crash -- which is the only
reason they are worth testing at all.

Sample is lifted from a real DE-LU A75 payload (2026-08-07):
  TS 11 (B15, Other renewable): 5 stated points across 96 steps
  TS 17 (B10 as outBiddingZone): pumped-storage CONSUMPTION, not generation
"""
import datetime as dt

import pytest

from entsoe_parse import parse
from validate import check_stage2_direction, check_stage2_parse

SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0">
<TimeSeries><mRID>11</mRID>
<inBiddingZone_Domain.mRID codingScheme="A01">10Y1001A1001A82H</inBiddingZone_Domain.mRID>
<quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name><curveType>A03</curveType>
<MktPSRType><psrType>B15</psrType></MktPSRType>
<Period><timeInterval><start>2026-08-01T00:00Z</start><end>2026-08-02T00:00Z</end></timeInterval>
<resolution>PT15M</resolution>
<Point><position>1</position><quantity>74.267</quantity></Point>
<Point><position>19</position><quantity>71.451</quantity></Point>
<Point><position>43</position><quantity>72.415</quantity></Point>
<Point><position>68</position><quantity>71.451</quantity></Point>
<Point><position>89</position><quantity>73.008</quantity></Point>
</Period></TimeSeries>
<TimeSeries><mRID>17</mRID>
<outBiddingZone_Domain.mRID codingScheme="A01">10Y1001A1001A82H</outBiddingZone_Domain.mRID>
<quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name><curveType>A03</curveType>
<MktPSRType><psrType>B10</psrType></MktPSRType>
<Period><timeInterval><start>2026-08-01T00:00Z</start><end>2026-08-02T00:00Z</end></timeInterval>
<resolution>PT15M</resolution>
<Point><position>1</position><quantity>115.8084</quantity></Point>
<Point><position>2</position><quantity>113.1906</quantity></Point>
</Period></TimeSeries>
</GL_MarketDocument>"""


@pytest.fixture(scope="module")
def rows():
    return parse(SAMPLE)


def _b15(rows):
    return [r for r in rows if r["psr"] == "B15"]


# --------------------------------------------------------------------------
# TRAP 1/2: curveType A03 omits repeated values.
# Prevents: a naive loop emitting 5 rows for a 96-step day and losing 95% of
# it with no error raised. The daily total would look merely "low", not wrong.
# --------------------------------------------------------------------------
def test_a03_gaps_expand_to_full_step_count(rows):
    b15 = _b15(rows)
    assert b15[0]["n_points_stated"] == 5, "sample should state only 5 points"
    assert len(b15) == 96, f"expected 96 quarter-hourly steps, got {len(b15)}"


def test_a03_carries_last_stated_value_forward(rows):
    b15 = _b15(rows)
    # positions 1..18 all carry position 1's value; 19 introduces a new one
    assert b15[0]["mw"] == pytest.approx(74.267)
    assert b15[17]["mw"] == pytest.approx(74.267), "position 18 must carry pos 1 forward"
    assert b15[18]["mw"] == pytest.approx(71.451), "position 19 states a new value"


def test_a03_series_without_position_one_is_rejected():
    """A step curve has nothing to carry forward from before its first point."""
    broken = SAMPLE.replace("<position>1</position>", "<position>3</position>", 1)
    with pytest.raises(ValueError, match="position 1"):
        parse(broken)


# --------------------------------------------------------------------------
# TRAP 3: outBiddingZone_Domain is consumption.
# Prevents: pumped storage being counted twice -- once generating, once
# pumping -- which inflates the mix and corrupts the intensity denominator.
# --------------------------------------------------------------------------
def test_out_bidding_zone_is_classified_as_consumption(rows):
    b10 = [r for r in rows if r["psr"] == "B10"]
    assert b10, "sample contains a B10 series"
    assert {r["direction"] for r in b10} == {"consumption"}


def test_in_bidding_zone_is_classified_as_generation(rows):
    assert {r["direction"] for r in _b15(rows)} == {"generation"}


def test_direction_check_accepts_a_pump_only_window(rows):
    """Regression: the old check demanded BOTH directions and failed here."""
    ok, msg = check_stage2_direction(rows)
    assert ok, msg


# --------------------------------------------------------------------------
# TRAP 4: the unit is MAW -- power, not energy.
# Prevents: summing MW as if it were MWh, which overstates a PT15M zone
# fourfold and silently breaks any comparison across resolutions.
# --------------------------------------------------------------------------
def test_energy_is_power_times_step_hours(rows):
    b15 = _b15(rows)
    assert b15[0]["step_hours"] == 0.25
    assert b15[0]["mwh"] == pytest.approx(b15[0]["mw"] * 0.25)
    naive_sum_of_mw = sum(r["mw"] for r in b15)
    true_energy = sum(r["mwh"] for r in b15)
    assert true_energy == pytest.approx(naive_sum_of_mw * 0.25)
    assert true_energy == pytest.approx(1736.635, abs=1e-3)


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------
def test_timestamps_are_utc_aware_and_quarter_hourly(rows):
    b15 = _b15(rows)
    assert b15[0]["ts_utc"] == dt.datetime(2026, 8, 1, 0, 0, tzinfo=dt.timezone.utc)
    assert b15[-1]["ts_utc"] == dt.datetime(2026, 8, 1, 23, 45, tzinfo=dt.timezone.utc)
    assert all(r["ts_utc"].tzinfo is not None for r in rows), "no naive timestamps"
    assert (b15[1]["ts_utc"] - b15[0]["ts_utc"]) == dt.timedelta(minutes=15)


def test_timestamps_with_seconds_are_accepted():
    """Some document types emit HH:MM:SS; a fixed strptime pattern broke on it."""
    with_seconds = SAMPLE.replace("T00:00Z", "T00:00:00Z").replace(
        "T00:00Z", "T00:00:00Z"
    )
    out = parse(with_seconds)
    assert out, "payload with seconds in the interval must still parse"


def test_stage2_parse_gate_passes(rows):
    ok, msg = check_stage2_parse(rows)
    assert ok, msg
