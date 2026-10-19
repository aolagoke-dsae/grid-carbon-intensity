"""SMARD weekly files, read strictly, and the agreement measure used to test
the two A44 price curves against them (trap 5). Fixtures only."""
import datetime as dt
import json
import zoneinfo

import pytest

import smard_parse as P

UTC = dt.timezone.utc
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")


def _ms(*args) -> int:
    return int(dt.datetime(*args, tzinfo=UTC).timestamp() * 1000)


def _week(pairs) -> str:
    return json.dumps({"meta_data": {"version": 1, "created": 0}, "series": pairs})


def test_a_week_reads_as_utc_starts_with_nulls_kept():
    rows = P.parse_week(_week([[_ms(2024, 12, 29, 23), 120.5], [_ms(2024, 12, 30, 0), None]]))
    assert rows == [(dt.datetime(2024, 12, 29, 23, tzinfo=UTC), 120.5),
                    (dt.datetime(2024, 12, 30, 0, tzinfo=UTC), None)]


@pytest.mark.parametrize("text", [
    "{}",                                                    # no series
    json.dumps({"series": {"1": 2}}),                        # series not a list
    _week([["1735513200000", 1.0]]),                         # epoch as a string
    _week([[_ms(2025, 1, 1), 1.0, 2.0]]),                    # not a pair
    _week([[_ms(2025, 1, 1), "94.50"]]),                     # price as a string
    json.dumps([[0, 1.0]]),                                  # a bare list
])
def test_anything_that_is_not_a_smard_week_is_refused(text):
    """Prevents: a malformed week skipped, then read as a week with no prices."""
    with pytest.raises(ValueError):
        P.parse_week(text)


def _store(folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")


def test_the_newest_accepted_retrieval_of_each_week_is_read(tmp_path):
    """Prevents: an older retrieval, or a failure in _failed/, read as data."""
    w1, w2 = tmp_path / "4169_DE_hour_1", tmp_path / "4169_DE_hour_2"
    _store(w1, "20261006T000000Z_aaaaaaaa.json", _week([[_ms(2025, 1, 6), 1.0]]))
    _store(w1, "20261019T000000Z_bbbbbbbb.json", _week([[_ms(2025, 1, 6), 2.0]]))
    _store(w2, "20261019T000000Z_cccccccc.json", _week([[_ms(2025, 1, 13), 3.0]]))
    _store(w2 / "_failed", "20261020T000000Z_dddddddd.json", "<html>404</html>")
    series = P.load_series(tmp_path)
    assert series == {dt.datetime(2025, 1, 6, tzinfo=UTC): 2.0,
                      dt.datetime(2025, 1, 13, tzinfo=UTC): 3.0}


def test_a_time_stated_twice_with_two_values_is_refused(tmp_path):
    _store(tmp_path / "a", "20261019T000000Z_aaaaaaaa.json", _week([[_ms(2025, 1, 6), 1.0]]))
    _store(tmp_path / "b", "20261019T000000Z_bbbbbbbb.json", _week([[_ms(2025, 1, 6), 1.5]]))
    with pytest.raises(ValueError, match="stated twice"):
        P.load_series(tmp_path)


def test_only_complete_hours_have_a_mean():
    """Three quarter-hours, or four with one missing value, are not an hour."""
    q = {dt.datetime(2025, 10, 1, 0, m, tzinfo=UTC): v for m, v in
         [(0, 10.0), (15, 20.0), (30, 30.0), (45, 40.0)]}
    q |= {dt.datetime(2025, 10, 1, 1, m, tzinfo=UTC): 5.0 for m in (0, 15, 30)}
    q |= {dt.datetime(2025, 10, 1, 2, m, tzinfo=UTC): (None if m == 30 else 5.0)
          for m in (0, 15, 30, 45)}
    assert P.hourly_means(q, 0.25) == {dt.datetime(2025, 10, 1, 0, tzinfo=UTC): 25.0}


def test_agreement_counts_only_the_times_both_state():
    t = [dt.datetime(2025, 1, 1, h, tzinfo=UTC) for h in range(5)]
    ref = {t[0]: 50.0, t[1]: 60.0, t[2]: None, t[3]: 80.0, t[4]: 90.0}
    cand = {t[0]: 50.0, t[1]: 60.004, t[2]: 70.0, t[3]: 81.0}
    a = P.agreement(ref, cand, tolerance=0.005)
    assert (a["n"], a["agree"]) == (3, 2)
    assert a["share"] == pytest.approx(2 / 3)
    assert a["max_abs"] == pytest.approx(1.0)
    assert P.agreement(ref, {}, 0.005)["share"] is None


# --------------------------------------------------------------------------
# The real data. Skipped where raw/* is absent, as in CI. These lock in the
# verdict of notebooks/price_curves.py of 19.10.2026: SMARD filter 4169 against
# the 2025 DE-LU A44 payload. A newer retrieval that changes it fails here on
# purpose: rerun the notebook and re-decide.
# --------------------------------------------------------------------------

from pathlib import Path  # noqa: E402

from entsoe_prices_parse import parse_prices  # noqa: E402

_RAW = Path(__file__).resolve().parents[2] / "raw"
_A44 = sorted((_RAW / "A44" / "10Y1001A1001A82H" / "2025").glob("*.xml"))
_SMARD = _RAW / "SMARD" / "4169"
needs_real = pytest.mark.skipif(
    not (_A44 and (_SMARD / "hour").is_dir() and (_SMARD / "quarterhour").is_dir()),
    reason="needs the 2025 DE-LU A44 payload and the 2025 SMARD weeks; raw/* is not in CI",
)
Y0 = dt.datetime(2024, 12, 31, 23, tzinfo=UTC)       # 2025, German time
Y1 = dt.datetime(2025, 12, 31, 23, tzinfo=UTC)
GO_LIVE = dt.datetime(2025, 9, 30, 22, tzinfo=UTC)   # 15-minute MTU


def _window(series, lo=Y0, hi=Y1):
    return {t: v for t, v in series.items() if lo <= t < hi}


@pytest.fixture(scope="module")
def real():
    curves: dict = {}
    for r in parse_prices(_A44[-1].read_text(encoding="utf-8")):
        if Y0 <= r["ts_utc"] < Y1:
            curves.setdefault(r["classification_sequence"], {})[r["ts_utc"]] = r["price_eur_mwh"]
    return (curves, _window(P.load_series(_SMARD / "hour")),
            _window(P.load_series(_SMARD / "quarterhour")))


@needs_real
def test_curve_1_is_smard_to_the_cent_before_and_after_the_15_minute_go_live(real):
    """Prevents: the dbt default drifting to a curve that is not the market's,
    or a re-pulled payload whose curve 1 no longer matches SMARD."""
    curves, hours, quarters = real
    before = P.agreement(_window(hours, Y0, GO_LIVE), _window(curves[1], Y0, GO_LIVE), 0.005)
    after = P.agreement(_window(quarters, GO_LIVE, Y1), _window(curves[1], GO_LIVE, Y1), 0.005)
    assert (before["n"], before["agree"]) == (6551, 6551)
    assert (after["n"], after["agree"]) == (8836, 8836)


@needs_real
def test_curve_2_is_not_smard(real):
    """The other curve is a different market, not a rounding of the same one."""
    curves, _, quarters = real
    a = P.agreement(quarters, curves[2], 0.005)
    assert a["n"] == 35040
    assert a["share"] < 0.01


def _a44(year: int) -> list:
    return sorted((_RAW / "A44" / "10Y1001A1001A82H" / str(year)).glob("*.xml"))


@pytest.fixture(scope="module")
def smard_hours():
    return P.load_series(_SMARD / "hour")


@needs_real
@pytest.mark.parametrize("year, hours", [(2021, 8760), (2022, 8760), (2023, 8760), (2024, 8784)])
def test_curve_1_is_smard_at_every_hour_of_2021_to_2024(year, hours, smard_hours):
    """Hourly MTU throughout: curve 1's hours are SMARD's to the cent, and the
    means of curve 2's quarter-hours are not (checked 19.10.2026)."""
    if not _a44(year):
        pytest.skip(f"no {year} DE-LU A44 payload in raw/")
    lo = dt.datetime(year, 1, 1, tzinfo=BERLIN).astimezone(UTC)
    hi = dt.datetime(year + 1, 1, 1, tzinfo=BERLIN).astimezone(UTC)
    curves: dict = {}
    for r in parse_prices(_a44(year)[-1].read_text(encoding="utf-8")):
        if lo <= r["ts_utc"] < hi:
            curves.setdefault(r["classification_sequence"], {})[r["ts_utc"]] = r["price_eur_mwh"]
    reference = _window(smard_hours, lo, hi)
    one = P.agreement(reference, curves[1], 0.005)
    two = P.agreement(reference, P.hourly_means(curves[2], 0.25), 0.01)
    assert (one["n"], one["agree"]) == (hours, hours)
    assert two["n"] == hours and two["share"] < 0.01
