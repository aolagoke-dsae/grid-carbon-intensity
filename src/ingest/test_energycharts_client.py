"""The Energy-Charts backfill: which months a year needs, what counts as
data, and no month fetched twice. No network is used: the requests are
replaced."""
import json

import energycharts_client as E


def test_the_months_cover_the_year_from_first_to_last_day():
    """Prevents: a February that loses its leap day, or a year without its
    last day. The API reads an end day as its last minute, so months meet."""
    m24 = E.months(2024)
    assert [m for m, _, _ in m24] == list(range(1, 13))
    assert m24[0][1:] == ("2024-01-01", "2024-01-31")
    assert m24[1][2] == "2024-02-29"
    assert E.months(2025)[1][2] == "2025-02-28"
    assert m24[11][2] == "2024-12-31"


def _body(**doc) -> bytes:
    return json.dumps(doc).encode()


def test_only_a_json_object_with_data_and_series_is_data():
    """Prevents: an error page, a rate-limit answer or an empty month being
    read as the month's generation."""
    good = _body(series=[{"id": "solar", "name": "Solar"}],
                 data=[{"timestamp": "2025-01-01T00:00+01:00", "values": {"solar": 0.0}}])
    assert E._usable(200, good)
    assert not E._usable(429, good)
    assert not E._usable(200, _body(series=[{"id": "solar"}], data=[]))
    assert not E._usable(200, _body(data=[{"timestamp": "x", "values": {}}]))
    assert not E._usable(200, b"<html>Too Many Requests</html>")
    assert not E._usable(200, b"[]")


def test_requests_keep_to_the_documented_rate_limit():
    """Two requests a minute: one every 30 seconds at the most."""
    assert E.SLEEP_SECONDS >= 30


def _fake_pull(monkeypatch, tmp_path):
    monkeypatch.setattr(E, "RAW", tmp_path / "raw")
    fetched = []

    def fetch_month(year, month, country=E.COUNTRY):
        fetched.append(month)
        return {"rejected": 0}

    monkeypatch.setattr(E, "fetch_month", fetch_month)
    return fetched


def test_a_rerun_fetches_only_the_months_not_yet_stored(monkeypatch, tmp_path):
    """Prevents: every rerun downloading the year again into raw/."""
    fetched = _fake_pull(monkeypatch, tmp_path)
    stored = tmp_path / "raw" / "ENERGYCHARTS" / "public_power" / "de" / "2025-03"
    stored.mkdir(parents=True)
    (stored / "20261025T080000Z_00000000.json").write_text('{"data": [1], "series": [1]}')
    rows = E.backfill(2025)
    assert fetched == [m for m in range(1, 13) if m != 3]
    assert len(rows) == 11


def test_a_month_that_only_ever_failed_is_fetched_again(monkeypatch, tmp_path):
    """Prevents: a rate-limit page in _failed/ counting as the month."""
    fetched = _fake_pull(monkeypatch, tmp_path)
    failed = tmp_path / "raw" / "ENERGYCHARTS" / "public_power" / "de" / "2025-03" / "_failed"
    failed.mkdir(parents=True)
    (failed / "20261025T080000Z_00000000.json").write_text("<html>429</html>")
    E.backfill(2025)
    assert 3 in fetched


def test_a_month_is_asked_for_by_its_first_and_last_day(monkeypatch, tmp_path):
    seen = {}
    monkeypatch.setattr(E, "RAW", tmp_path / "raw")
    monkeypatch.setattr(E, "_get", lambda params, out: seen.update(params, out=out) or {})
    E.fetch_month(2024, 2)
    assert (seen["country"], seen["start"], seen["end"]) == ("de", "2024-02-01", "2024-02-29")
    assert seen["out"].as_posix().endswith("raw/ENERGYCHARTS/public_power/de/2024-02.json")
