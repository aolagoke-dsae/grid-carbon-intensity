"""The A65 load parser, on fixtures written before the first A65 pull.

The trap specific to A65: the actual total load (process A16) and the
day-ahead forecast (A01) are one document type, and nothing in a landed point
tells them apart. Read as each other they give plausible numbers, so the
parser takes the process type it expects and refuses any other.
"""
import datetime as dt

import pytest

from entsoe_load_parse import parse_load

NS = "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"
DE = "10Y1001A1001A82H"
UTC = dt.timezone.utc


def _doc(series, process="A01", doc_type="A65", root="GL_MarketDocument"):
    proc = f"<process.processType>{process}</process.processType>" if process else ""
    return (
        f'<?xml version="1.0" encoding="UTF-8"?><{root} xmlns="{NS}"><mRID>m</mRID>'
        f"<revisionNumber>1</revisionNumber><type>{doc_type}</type>{proc}{series}</{root}>"
    )


def _series(points, start="2025-06-01T22:00Z", end="2025-06-02T22:00Z", res="PT60M",
            curve="A01", domain="outBiddingZone_Domain.mRID"):
    pts = "".join(
        f"<Point><position>{p}</position><quantity>{q}</quantity></Point>"
        for p, q in points.items()
    )
    return (
        f"<TimeSeries><mRID>1</mRID><businessType>A04</businessType>"
        f'<{domain} codingScheme="A01">{DE}</{domain}>'
        "<quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>"
        f"<curveType>{curve}</curveType><Period><timeInterval><start>{start}</start>"
        f"<end>{end}</end></timeInterval><resolution>{res}</resolution>{pts}</Period></TimeSeries>"
    )


HOURS = {p: 40_000.0 + 100 * p for p in range(1, 25)}


def test_a_forecast_day_expands_to_one_row_per_hour():
    rows = parse_load(_doc(_series(HOURS)), "A01")
    assert len(rows) == 24
    assert rows[0]["ts_utc"] == dt.datetime(2025, 6, 1, 22, tzinfo=UTC)
    assert rows[-1]["ts_utc"] == dt.datetime(2025, 6, 2, 21, tzinfo=UTC)
    assert [r["mw"] for r in rows] == list(HOURS.values())
    assert {(r["zone_eic"], r["process_type"], r["unit"]) for r in rows} == {(DE, "A01", "MAW")}
    assert not any(r["was_carried"] for r in rows)


def test_a03_carries_the_last_stated_value_forward():
    """Prevents: a quarter-hour that A03 leaves out read as missing, or as zero."""
    rows = parse_load(_doc(_series({1: 100.0, 5: 200.0, 90: 300.0}, res="PT15M", curve="A03")), "A01")
    assert len(rows) == 96
    assert [r["mw"] for r in rows[:6]] == [100.0] * 4 + [200.0] * 2
    assert rows[88]["mw"] == 200.0 and rows[89]["mw"] == 300.0 and rows[-1]["mw"] == 300.0
    assert sum(r["was_carried"] for r in rows) == 93


def test_a01_leaves_a_missing_position_empty():
    """Prevents: an hour the forecast never stated filled with its neighbour's."""
    rows = parse_load(_doc(_series({p: q for p, q in HOURS.items() if p != 7})), "A01")
    assert rows[6]["mw"] is None and not rows[6]["was_carried"]
    assert sum(r["mw"] is None for r in rows) == 1


@pytest.mark.parametrize("start, end, hours", [
    ("2025-03-29T23:00Z", "2025-03-30T22:00Z", 23),
    ("2025-10-25T22:00Z", "2025-10-26T23:00Z", 25),
])
def test_the_clock_change_days_have_23_and_25_hours(start, end, hours):
    rows = parse_load(_doc(_series({p: 1.0 for p in range(1, hours + 1)}, start, end)), "A01")
    assert len(rows) == hours
    assert rows[-1]["ts_utc"] - rows[0]["ts_utc"] == dt.timedelta(hours=hours - 1)


ACK = (
    '<?xml version="1.0" encoding="UTF-8"?><Acknowledgement_MarketDocument '
    'xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0"><mRID>a</mRID>'
    "<Reason><code>999</code><text>No matching data found</text></Reason>"
    "</Acknowledgement_MarketDocument>"
)


@pytest.mark.parametrize("text, process, match", [
    (_doc(_series(HOURS), process="A16"), "A01", "A16, the actual total load"),
    (_doc(_series(HOURS), process="A01"), "A16", "A01, the day-ahead total load forecast"),
    (_doc(_series(HOURS), process=None), "A01", "process None"),
    (ACK, "A01", "No matching data found"),
    (_doc(_series(HOURS), doc_type="A75"), "A01", "A75 document"),
    (_doc(_series(HOURS), root="Publication_MarketDocument"), "A01", "GL_MarketDocument"),
    (_doc(_series({2: 1.0, 3: 2.0}, curve="A03")), "A01", "position 1"),
    (_doc(_series(HOURS, domain="inBiddingZone_Domain.mRID")), "A01", "outBiddingZone_Domain only"),
    (_doc(_series(HOURS, curve="A02")), "A01", "curveType"),
    (_doc(_series(HOURS)), "A31", "A16 or A01 only"),
], ids=["actual-read-as-forecast", "forecast-read-as-actual", "no-process", "acknowledgement", "generation",
        "price-document", "a03-without-position-1", "wrong-domain", "unknown-curve",
        "unknown-process"])
def test_what_is_not_the_expected_load_series_is_refused(text, process, match):
    with pytest.raises(ValueError, match=match):
        parse_load(text, process)
