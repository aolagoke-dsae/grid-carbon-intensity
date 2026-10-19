"""SMARD weekly files, read strictly, and the agreement measure used to test
the two A44 price curves against them (trap 5). Fixtures only."""
import datetime as dt
import json

import pytest

import smard_parse as P

UTC = dt.timezone.utc


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
