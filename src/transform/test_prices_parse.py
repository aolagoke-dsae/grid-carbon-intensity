"""A44 price parser regression tests.

Every test names the failure it prevents. That matters more here than usual,
because none of these bugs crash: each one returns a plausible number.

The synthetic fixtures run everywhere, CI included. The tests at the bottom read
the real 7.5 MB DE-LU payload and skip when it is absent, because raw/* is
gitignored - the payload is large and reproducible from the manifest, so CI has
no copy of it.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from entsoe_parse import parse as parse_generation
from entsoe_prices_parse import CS_FIELD, curve_summary, parse_prices

NS44 = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
ZONE = "10Y1001A1001A82H"


def _doc(timeseries: str, doc_type: str = "A44") -> str:
    return (
        f'<?xml version="1.0" encoding="utf-8"?>\n'
        f'<Publication_MarketDocument xmlns="{NS44}">'
        f"<mRID>deadbeef</mRID><revisionNumber>1</revisionNumber>"
        f"<type>{doc_type}</type>"
        f"{timeseries}"
        f"</Publication_MarketDocument>"
    )


def _series(
    mrid: str,
    cs: str | None,
    points: str,
    start: str = "2025-06-01T22:00Z",
    end: str = "2025-06-02T22:00Z",
    resolution: str = "PT60M",
    in_z: str = ZONE,
    out_z: str = ZONE,
) -> str:
    cs_el = f"<{CS_FIELD}>{cs}</{CS_FIELD}>" if cs is not None else ""
    return (
        f"<TimeSeries><mRID>{mrid}</mRID>"
        f"<auction.type>A01</auction.type><businessType>A62</businessType>"
        f'<in_Domain.mRID codingScheme="A01">{in_z}</in_Domain.mRID>'
        f'<out_Domain.mRID codingScheme="A01">{out_z}</out_Domain.mRID>'
        f"<contract_MarketAgreement.type>A01</contract_MarketAgreement.type>"
        f"<currency_Unit.name>EUR</currency_Unit.name>"
        f"<price_Measure_Unit.name>MWH</price_Measure_Unit.name>"
        f"{cs_el}<curveType>A03</curveType>"
        f"<Period><timeInterval><start>{start}</start><end>{end}</end></timeInterval>"
        f"<resolution>{resolution}</resolution>{points}</Period></TimeSeries>"
    )


def _pt(pos: int, amount: float) -> str:
    return f"<Point><position>{pos}</position><price.amount>{amount}</price.amount></Point>"


# --------------------------------------------------------------------------
# Trap 5: the two curves
# --------------------------------------------------------------------------

def test_the_two_curves_are_separable_and_must_not_be_summed():
    """Prevents: averaging two different markets into one number.

    Both series describe the same zone, year, businessType, contract and
    auction. classificationSequence is the only field that differs. Without it
    there is no key to group by, and every downstream mean silently becomes a
    weighted average of two disagreeing curves.
    """
    xml = _doc(
        _series("1", "1", _pt(1, 100.0))
        + _series("2", "2", _pt(1, 50.0))
    )
    rows = parse_prices(xml)
    seqs = {r["classification_sequence"] for r in rows}
    assert seqs == {1, 2}, "the discriminator was dropped; the curves are now indistinguishable"

    by_curve = curve_summary(rows)
    assert by_curve[1]["median"] == 100.0
    assert by_curve[2]["median"] == 50.0
    # The number you get by ignoring the discriminator -- wrong, and plausible.
    naive = sum(r["price_eur_mwh"] for r in rows) / len(rows)
    assert naive == 75.0
    assert naive not in (100.0, 50.0)


def test_classification_sequence_is_an_int_not_a_string():
    """Prevents: a dbt filter `where classification_sequence = 1` matching nothing."""
    rows = parse_prices(_doc(_series("1", "2", _pt(1, 10.0))))
    assert rows[0]["classification_sequence"] == 2
    assert isinstance(rows[0]["classification_sequence"], int)


def test_a_single_curve_zone_yields_none_not_a_defaulted_one():
    """Prevents: a zone that publishes one curve being mistaken for curve 1 of two.

    The field is optional in the schema. Defaulting it to 1 would make the
    staging model unable to tell 'this zone has one curve' from 'this is the
    first of two', which is exactly the distinction it needs to pick safely.
    """
    rows = parse_prices(_doc(_series("1", None, _pt(1, 10.0))))
    assert rows[0]["classification_sequence"] is None


# --------------------------------------------------------------------------
# Why this module exists at all
# --------------------------------------------------------------------------

def test_the_a75_parser_returns_silence_on_an_a44_payload():
    """Prevents: reusing entsoe_parse.parse() for prices and getting zero rows.

    Different namespace, so findall() matches nothing. No exception, no warning,
    an empty frame -- and an empty frame looks like 'no data for that day'.
    This is the failure that made a separate parser necessary.
    """
    xml = _doc(_series("1", "1", _pt(1, 42.0)))
    assert parse_generation(xml) == []
    assert len(parse_prices(xml)) == 24


def test_price_amount_is_read_not_quantity():
    """Prevents: float(None) from reading <quantity>, which A44 does not have.

    The real payload contains 50,044 <price.amount> elements and zero
    <quantity> elements.
    """
    rows = parse_prices(_doc(_series("1", "1", _pt(1, 123.45))))
    assert rows[0]["price_eur_mwh"] == 123.45
    assert "<quantity>" not in _doc(_series("1", "1", _pt(1, 1.0)))


def test_a_generation_document_is_refused():
    """Prevents: an A75 payload being parsed as prices and producing None prices."""
    with pytest.raises(ValueError, match="only reads A44"):
        parse_prices(_doc(_series("1", "1", _pt(1, 1.0)), doc_type="A75"))


# --------------------------------------------------------------------------
# Values
# --------------------------------------------------------------------------

def test_negative_prices_survive_unchanged():
    """Prevents: a clamp, abs() or max(0, x) treating a real market outcome as dirt.

    4.5 % of curve 1 and 6.5 % of curve 2 are negative, down to -499.99, which
    is the technical floor. Clipping them removes precisely the hours a
    load-shift analysis exists to find.
    """
    rows = parse_prices(
        _doc(_series("1", "1", _pt(1, -45.6) + _pt(2, -499.99) + _pt(3, 0.0)))
    )
    assert rows[0]["price_eur_mwh"] == -45.6
    assert rows[1]["price_eur_mwh"] == -499.99
    assert rows[2]["price_eur_mwh"] == 0.0
    assert min(r["price_eur_mwh"] for r in rows) == -499.99


def test_a03_omitted_positions_carry_the_last_value_forward():
    """Prevents: a 24-hour day arriving as 3 rows because A03 omits repeats."""
    rows = parse_prices(_doc(_series("1", "1", _pt(1, 10.0) + _pt(5, 20.0) + _pt(20, 30.0))))
    assert len(rows) == 24, "the step curve was not expanded to the full interval"
    assert [r["price_eur_mwh"] for r in rows[0:4]] == [10.0] * 4
    assert [r["price_eur_mwh"] for r in rows[4:19]] == [20.0] * 15
    assert [r["price_eur_mwh"] for r in rows[19:24]] == [30.0] * 5
    assert rows[0]["n_points_stated"] == 3
    assert rows[0]["n_steps_expanded"] == 24


def test_a_gap_at_position_one_is_refused_not_silently_shifted():
    """Prevents: every timestamp in a series sliding by the length of the gap."""
    with pytest.raises(ValueError, match="position 1"):
        parse_prices(_doc(_series("1", "1", _pt(2, 10.0) + _pt(3, 20.0))))


def test_timestamps_step_by_the_resolution_from_the_period_start():
    rows = parse_prices(
        _doc(
            _series(
                "1", "1", _pt(1, 10.0),
                start="2025-06-01T22:00Z", end="2025-06-01T23:00Z", resolution="PT15M",
            )
        )
    )
    assert len(rows) == 4
    assert rows[0]["ts_utc"] == dt.datetime(2025, 6, 1, 22, 0, tzinfo=dt.timezone.utc)
    assert rows[3]["ts_utc"] == dt.datetime(2025, 6, 1, 22, 45, tzinfo=dt.timezone.utc)
    assert rows[0]["step_hours"] == 0.25


# --------------------------------------------------------------------------
# Transition days -- derived from the interval, never assumed to be 24
# --------------------------------------------------------------------------

@pytest.mark.parametrize(
    "start,end,resolution,expected",
    [
        ("2025-03-29T23:00Z", "2025-03-30T22:00Z", "PT60M", 23),   # DST start
        ("2025-10-25T22:00Z", "2025-10-26T23:00Z", "PT60M", 25),   # DST end
        ("2025-03-29T23:00Z", "2025-03-30T22:00Z", "PT15M", 92),
        ("2025-10-25T22:00Z", "2025-10-26T23:00Z", "PT15M", 100),
    ],
)
def test_transition_days_expand_to_the_interval_not_to_twenty_four_hours(
    start, end, resolution, expected
):
    """Prevents: a hardcoded 24 (or 96) shifting every timestamp after a DST change.

    Both transitions are present in the real 2025 payload and both curves carry
    them: curve 1 as 23 steps in March (still hourly) and 100 in October
    (quarter-hourly by then), curve 2 as 92 and 100.
    """
    rows = parse_prices(
        _doc(_series("1", "1", _pt(1, 10.0), start=start, end=end, resolution=resolution))
    )
    assert len(rows) == expected
    assert rows[0]["n_steps_expanded"] == expected


# --------------------------------------------------------------------------
# Structural refusals
# --------------------------------------------------------------------------

def test_a_cross_border_series_is_refused():
    """Prevents: a transit price being averaged into a zone's own day-ahead price."""
    with pytest.raises(ValueError, match="not a single-zone"):
        parse_prices(
            _doc(_series("1", "1", _pt(1, 10.0), in_z=ZONE, out_z="10YFR-RTE------C"))
        )


def test_an_unknown_resolution_is_refused_not_defaulted():
    """Prevents: a KeyError being swallowed upstream, or a silent 1.0 step."""
    with pytest.raises(ValueError, match="unknown resolution"):
        parse_prices(_doc(_series("1", "1", _pt(1, 10.0), resolution="PT5M")))


def test_a_naive_timestamp_is_refused():
    """Prevents: an offset-less time being assumed local somewhere downstream."""
    with pytest.raises(ValueError, match="no offset"):
        parse_prices(
            _doc(_series("1", "1", _pt(1, 10.0), start="2025-06-01T22:00", end="2025-06-02T22:00"))
        )


# --------------------------------------------------------------------------
# The real payload. Skipped where raw/* is not present, i.e. in CI.
# --------------------------------------------------------------------------

REAL = Path(__file__).resolve().parents[2] / "raw" / "A44" / ZONE / "2025.xml"
needs_real = pytest.mark.skipif(
    not REAL.exists(), reason=f"{REAL} absent; raw/* is gitignored and not shipped to CI"
)


@pytest.fixture(scope="module")
def real_rows():
    return parse_prices(REAL.read_text(encoding="utf-8"))


@needs_real
def test_real_payload_reproduces_the_measured_curve_split(real_rows):
    """Locks in the 07.10.2026 measurement of raw/A44/.../2025.xml revision 1."""
    s = curve_summary(real_rows)
    assert set(s) == {1, 2}, "the real payload must carry exactly two curves"
    assert s[1]["resolutions"] == {"PT60M": 6551, "PT15M": 8932}
    assert s[2]["resolutions"] == {"PT15M": 35136}
    assert s[1]["min"] == -250.32 and s[1]["max"] == 583.40
    assert s[2]["min"] == -499.99 and s[2]["max"] == 834.60
    # Curve 2 clears at the technical floor and more often below zero. That is
    # the fingerprint of genuine 15-minute clearing, not an hourly average.
    assert s[2]["negative_share"] > s[1]["negative_share"]


@needs_real
def test_real_payload_stated_points_match_the_element_count(real_rows):
    """50,044 <price.amount> elements in the file; none may be lost or invented."""
    stated = {
        (r["series_mrid"], r["period_start_utc"]): r["n_points_stated"] for r in real_rows
    }
    assert sum(stated.values()) == 50_044
    assert len(stated) == 732, "366 days x 2 curves"


@needs_real
def test_real_payload_covers_exactly_366_days_on_both_curves(real_rows):
    """Prevents a dropped or duplicated day going unnoticed in a 50k-row frame."""
    import collections

    steps = collections.defaultdict(dict)
    for r in real_rows:
        steps[r["classification_sequence"]][r["period_start_utc"]] = r["n_steps_expanded"]
    for cs in (1, 2):
        assert len(steps[cs]) == 366, f"curve {cs} is not a complete year"
    assert collections.Counter(steps[1].values()) == {24: 272, 96: 92, 23: 1, 100: 1}
    assert collections.Counter(steps[2].values()) == {96: 364, 92: 1, 100: 1}


@needs_real
def test_real_payload_switches_resolution_at_the_german_mtu_go_live(real_rows):
    """1 October 2025 00:00 CEST = 2025-09-30T22:00Z. Curve 1 only; curve 2 is PT15M throughout."""
    by_period = {
        r["period_start_utc"]: r["resolution"]
        for r in real_rows
        if r["classification_sequence"] == 1
    }
    changes = [
        s
        for prev, s in zip(sorted(by_period), sorted(by_period)[1:])
        if by_period[s] != by_period[prev]
    ]
    assert len(changes) == 1, "curve 1 must change resolution exactly once"
    assert changes[0] == dt.datetime(2025, 9, 30, 22, 0, tzinfo=dt.timezone.utc)
