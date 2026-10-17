"""Parser regression tests.

These were previously a print-based demo script with no assertions, while the
README claimed the four payload traps were "asserted in test_parse.py". They
now are. Each test names the failure it prevents, because every one of these
bugs produces a plausible number rather than a crash -- which is the only
reason they are worth testing at all.

Sample is lifted from a real DE-LU A75 payload (2026-08-07):
  TS 11 (B15, Other renewable): 5 stated points across 96 steps
  TS 17 (B10 as outBiddingZone): pumped-storage CONSUMPTION, not generation

The transition-day and PT60M fixtures further down are synthetic: one series
at constant power, so every expected count and total can be worked out by hand.
"""
import datetime as dt

import pytest

from entsoe_parse import parse
from validate import check_stage2_direction, check_stage2_parse, check_stage3_coverage

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
# TRAP 1: curveType A03 omits repeated values.
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
# TRAP 2: outBiddingZone_Domain is consumption.
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
# TRAP 3 on the transition days, at the parser itself.
# Prevents: a step count taken from a 24-hour day. Until 17.10.2026 every A75
# fixture was an ordinary day, so `n_steps = round(24 / step_h)` passed the
# whole suite (audit A7). A Period covers one local delivery day, in UTC.
# --------------------------------------------------------------------------
TZ = "Europe/Berlin"
NS_A75 = "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"

# 29 March 2026: clocks go forward, the local day has 23 hours.
# 25 October 2026: clocks go back, the local day has 25 hours.
SPRING_FORWARD = ("2026-03-28T23:00Z", "2026-03-29T22:00Z", 23)
FALL_BACK = ("2026-10-24T22:00Z", "2026-10-25T23:00Z", 25)
ORDINARY_DAY = ("2026-07-31T22:00Z", "2026-08-01T22:00Z", 24)


def _a75_day(start, end, resolution, mw=1000.0, psr="B19", curve="A03", points=None):
    """One generation series. By default it states a single A03 point: constant
    power all day. `points`, {position: MW}, states more."""
    stated = "".join(
        f"<Point><position>{p}</position><quantity>{q}</quantity></Point>"
        for p, q in sorted((points or {1: mw}).items())
    )
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<GL_MarketDocument xmlns="{NS_A75}">
<TimeSeries><mRID>1</mRID>
<inBiddingZone_Domain.mRID codingScheme="A01">10Y1001A1001A82H</inBiddingZone_Domain.mRID>
<quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name><curveType>{curve}</curveType>
<MktPSRType><psrType>{psr}</psrType></MktPSRType>
<Period><timeInterval><start>{start}</start><end>{end}</end></timeInterval>
<resolution>{resolution}</resolution>
{stated}
</Period></TimeSeries>
</GL_MarketDocument>"""


def _utc(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


@pytest.mark.parametrize(
    "day, resolution, steps",
    [
        (SPRING_FORWARD, "PT15M", 92),
        (FALL_BACK, "PT15M", 100),
        (SPRING_FORWARD, "PT60M", 23),
        (FALL_BACK, "PT60M", 25),
    ],
    ids=["spring-PT15M", "fall-PT15M", "spring-PT60M", "fall-PT60M"],
)
def test_transition_day_expands_to_its_real_length(day, resolution, steps):
    start, end, hours = day
    rows = parse(_a75_day(start, end, resolution))
    assert len(rows) == steps
    assert {r["n_steps_expanded"] for r in rows} == {steps}
    last_end = rows[-1]["ts_utc"] + dt.timedelta(hours=rows[-1]["step_hours"])
    assert last_end == _utc(end), "the last step must end where the period ends"
    assert sum(r["mwh"] for r in rows) == pytest.approx(1000.0 * hours)
    ok, msg = check_stage3_coverage(rows, TZ)
    assert ok, msg


# --------------------------------------------------------------------------
# TRAP 4 across resolutions.
# Prevents: energy computed with a hard-coded quarter-hour. FR publishes at
# PT60M. A day at a constant 1000 MW is 24,000 MWh at either resolution,
# while the sum of the MW column differs fourfold.
# --------------------------------------------------------------------------
def test_energy_is_power_times_step_hours_at_pt60m():
    rows = parse(_a75_day(*ORDINARY_DAY[:2], "PT60M"))
    assert len(rows) == 24
    assert {r["step_hours"] for r in rows} == {1.0}
    assert all(r["mwh"] == pytest.approx(r["mw"]) for r in rows)


def test_energy_agrees_across_resolutions_where_power_sums_do_not():
    quarter = parse(_a75_day(*ORDINARY_DAY[:2], "PT15M"))
    hourly = parse(_a75_day(*ORDINARY_DAY[:2], "PT60M"))
    assert sum(r["mwh"] for r in quarter) == pytest.approx(24_000.0)
    assert sum(r["mwh"] for r in hourly) == pytest.approx(24_000.0)
    assert sum(r["mw"] for r in quarter) == pytest.approx(4 * sum(r["mw"] for r in hourly))


# --------------------------------------------------------------------------
# Curve types: only A03 omits repeats.
# Prevents: a missing A01 position being filled with the last value, which
# turns missing data into plausible generation (audit A6).
# --------------------------------------------------------------------------
A01_GAP = {p: 500.0 + p for p in range(1, 97) if not 10 <= p <= 42}   # 63 of 96


def test_a01_gaps_stay_empty_and_fail_stage_2():
    rows = parse(_a75_day(*ORDINARY_DAY[:2], "PT15M", curve="A01", points=A01_GAP))
    assert len(rows) == 96
    assert [i + 1 for i, r in enumerate(rows) if r["mw"] is None] == list(range(10, 43))
    assert all(r["mwh"] is None for r in rows[9:42])
    assert rows[8]["mw"] == 509.0 and rows[42]["mw"] == 543.0
    ok, msg = check_stage2_parse(rows)
    assert not ok and "33 rows with null mw" in msg, msg


def test_the_same_points_under_a03_are_carried_forward():
    rows = parse(_a75_day(*ORDINARY_DAY[:2], "PT15M", curve="A03", points=A01_GAP))
    assert {r["mw"] for r in rows[9:42]} == {509.0}
    ok, msg = check_stage2_parse(rows)
    assert ok, msg


def test_an_unknown_curve_type_is_refused():
    with pytest.raises(ValueError, match="curveType 'A02'"):
        parse(_a75_day(*ORDINARY_DAY[:2], "PT60M", curve="A02"))


# --------------------------------------------------------------------------
# What is not data is refused, not parsed into nothing (audit A13).
# Prevents: an empty result that reads downstream as "no generation that year".
# --------------------------------------------------------------------------
ACK = """<?xml version="1.0" encoding="UTF-8"?>
<Acknowledgement_MarketDocument xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0">
<mRID>4f1c</mRID><createdDateTime>2026-10-17T21:00:00Z</createdDateTime>
<Reason><code>999</code><text>No matching data found for Data item ACTUAL_GENERATION_PER_PRODUCTION_TYPE [16.1.B&amp;C]</text></Reason>
</Acknowledgement_MarketDocument>"""


def test_an_acknowledgement_is_refused_with_its_reason():
    with pytest.raises(ValueError, match="Acknowledgement.*No matching data found"):
        parse(ACK)


def test_a_document_without_timeseries_is_refused():
    head = SAMPLE.split("<TimeSeries>", 1)[0]
    with pytest.raises(ValueError, match="no TimeSeries"):
        parse(head + "</GL_MarketDocument>")


def test_another_schema_version_is_refused_not_read_as_empty():
    """The namespace is fixed in NS. A schema bump would match no element."""
    bumped = SAMPLE.replace("generationloaddocument:3:0", "generationloaddocument:3:1")
    with pytest.raises(ValueError, match="generationloaddocument:3:1"):
        parse(bumped)


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
