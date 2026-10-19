"""The SMARD backfill: which weeks a calendar year needs, and no week fetched
twice. No network is used: the index and the week requests are replaced."""
import datetime as dt
import zoneinfo

import smard_client as S

BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")


def _mondays(first: dt.date, n: int) -> list[int]:
    """Epoch-ms stamps of n consecutive Mondays 00:00 German time, as SMARD's
    index lists them; across a clock change they are 167 or 169 hours apart."""
    days = [first + dt.timedelta(weeks=i) for i in range(n)]
    return [int(dt.datetime(d.year, d.month, d.day, tzinfo=BERLIN).timestamp() * 1000)
            for d in days]


def _day(stamp: int) -> dt.date:
    return dt.datetime.fromtimestamp(stamp / 1000, BERLIN).date()


def test_2025_needs_53_weeks_from_30_december_2024_to_29_december_2025():
    """Prevents: a year that loses its first days or its last week. 1 January
    2025 is a Wednesday, so the year starts inside the week of 30 December."""
    picked = S.weeks_in_year(_mondays(dt.date(2024, 12, 16), 60), 2025)
    assert _day(picked[0]) == dt.date(2024, 12, 30)
    assert _day(picked[-1]) == dt.date(2025, 12, 29)
    assert len(picked) == 53


def test_a_week_that_ends_at_new_year_belongs_to_the_year_before():
    """1 January 2024 is a Monday: the week of 25 December 2023 ends exactly at
    the year's first instant and must not be fetched for 2024."""
    picked = S.weeks_in_year(_mondays(dt.date(2023, 12, 11), 60), 2024)
    assert _day(picked[0]) == dt.date(2024, 1, 1)
    assert _day(picked[-1]) == dt.date(2024, 12, 30)


def test_the_weeks_of_both_clock_changes_are_kept():
    """A week of 167 or 169 hours is still one week."""
    picked = {_day(t) for t in S.weeks_in_year(_mondays(dt.date(2024, 12, 16), 60), 2025)}
    assert {dt.date(2025, 3, 24), dt.date(2025, 10, 20)} <= picked


def _fake_pull(monkeypatch, tmp_path, stamps):
    monkeypatch.setattr(S, "RAW", tmp_path / "raw")
    monkeypatch.setattr(S, "index", lambda f, region, resolution: stamps)
    fetched = []

    def week(f, t, region, resolution):
        fetched.append(t)
        return {"rejected": 0}

    monkeypatch.setattr(S, "week", week)
    return fetched


def _week_dir(tmp_path, stamp):
    return tmp_path / "raw" / "SMARD" / "4169" / "hour" / f"4169_DE_hour_{stamp}"


def test_a_rerun_fetches_only_the_weeks_not_yet_stored(monkeypatch, tmp_path):
    """Prevents: every rerun downloading the whole year again into raw/."""
    stamps = _mondays(dt.date(2025, 1, 6), 3)
    fetched = _fake_pull(monkeypatch, tmp_path, stamps)
    stored = _week_dir(tmp_path, stamps[1])
    stored.mkdir(parents=True)
    (stored / "20261019T210000Z_00000000.json").write_text('{"series": []}')
    rows = S.backfill(4169, 2025)
    assert fetched == [stamps[0], stamps[2]]
    assert len(rows) == 2


def test_a_week_that_only_ever_failed_is_fetched_again(monkeypatch, tmp_path):
    """Prevents: an HTML error page in _failed/ counting as the week."""
    stamps = _mondays(dt.date(2025, 1, 6), 1)
    fetched = _fake_pull(monkeypatch, tmp_path, stamps)
    failed = _week_dir(tmp_path, stamps[0]) / "_failed"
    failed.mkdir(parents=True)
    (failed / "20261019T210000Z_00000000.json").write_text("<html>404</html>")
    S.backfill(4169, 2025)
    assert fetched == stamps
