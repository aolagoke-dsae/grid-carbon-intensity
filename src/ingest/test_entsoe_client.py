"""Token redaction and request-window tests.

The ENTSO-E security token travels in the query string, and requests puts the
full URL into its exception text. Unredacted, a failed connection printed the
token into a traceback -- the kind of output that gets pasted into a chat,
which is how the previous token was exposed on 06.10.2026. These tests pin the
token out of everything the client raises or writes. No network is used.
"""
import urllib.parse

import pytest
import requests

import entsoe_client as C

TOKEN = "00000000-0000-4000-8000-000000000000"  # UUID-shaped, like a real token


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    monkeypatch.setattr(C, "RAW", tmp_path / "raw")
    monkeypatch.setattr(C, "MANIFEST", tmp_path / "raw" / "manifest.csv")


def _failing_get(url, params, timeout):
    # The shape of the message urllib3 produces on an unresolvable or refused
    # connection: the request path with its full query string, token included.
    query = urllib.parse.urlencode(params)
    raise requests.ConnectionError(
        "HTTPSConnectionPool(host='web-api.tp.entsoe.eu', port=443): "
        f"Max retries exceeded with url: /api?{query} "
        "(Caused by NameResolutionError(...))"
    )


def test_a_failed_connection_does_not_put_the_token_in_the_exception(monkeypatch, tmp_path):
    """Prevents: the token printed into every traceback of a failed pull."""
    monkeypatch.setattr(C.requests, "get", _failing_get)
    with pytest.raises(RuntimeError) as exc:
        C.fetch({"documentType": "A44"}, TOKEN, tmp_path / "x.xml")
    assert TOKEN not in str(exc.value)
    assert "***REDACTED***" in str(exc.value)
    # nothing token-bearing chained underneath, either
    assert exc.value.__cause__ is None and exc.value.__suppress_context__


def test_the_manifest_row_never_carries_the_token(monkeypatch, tmp_path):
    """Prevents: a committed manifest.csv that publishes the token."""

    class Response:
        status_code = 200
        content = b"<Publication_MarketDocument/>"
        url = f"https://web-api.tp.entsoe.eu/api?documentType=A44&securityToken={TOKEN}"

    monkeypatch.setattr(C.requests, "get", lambda url, params, timeout: Response())
    row = C.fetch({"documentType": "A44"}, TOKEN, tmp_path / "x.xml")
    assert TOKEN not in row["url"]
    assert TOKEN not in C.MANIFEST.read_text(encoding="utf-8")


def test_redaction_leaves_text_alone_when_there_is_no_token():
    """Prevents: an empty token splicing the marker between every character."""
    assert C._redact("https://x/api?a=1", "") == "https://x/api?a=1"


# --------------------------------------------------------------------------
# Request windows (audit A5, seen in the first A75 pull on 17.10.2026)
# --------------------------------------------------------------------------
def _capture(monkeypatch):
    seen = {}
    monkeypatch.setattr(C, "fetch", lambda params, token, out: seen.update(params) or {})
    return seen


@pytest.mark.parametrize(
    "fn, doc",
    [(C.generation_per_type, "A75"), (C.day_ahead_prices, "A44"), (C.actual_load, "A65")],
)
def test_a_yearly_request_covers_the_local_year_not_the_utc_year(monkeypatch, fn, doc):
    """Prevents: local 1 January losing its first hour (92 of 96 steps in the
    first DE-LU pull) and the next year's first hour arriving twice."""
    seen = _capture(monkeypatch)
    fn("10Y1001A1001A82H", 2025, TOKEN)
    assert seen["documentType"] == doc
    assert (seen["periodStart"], seen["periodEnd"]) == ("202412312300", "202512312300")


def test_each_zone_gets_its_own_local_midnight(monkeypatch):
    """IE-SEM keeps GMT in winter, so its year starts at 00:00 UTC."""
    seen = _capture(monkeypatch)
    C.generation_per_type("10Y1001A1001A59C", 2025, TOKEN)
    assert (seen["periodStart"], seen["periodEnd"]) == ("202501010000", "202601010000")


def test_consecutive_years_meet_without_overlapping(monkeypatch):
    seen = _capture(monkeypatch)
    C.generation_per_type("10YFR-RTE------C", 2025, TOKEN)
    end_2025 = seen["periodEnd"]
    C.generation_per_type("10YFR-RTE------C", 2026, TOKEN)
    assert seen["periodStart"] == end_2025


def test_an_unknown_zone_is_refused_before_any_request(monkeypatch):
    seen = _capture(monkeypatch)
    with pytest.raises(ValueError, match="zones.yml"):
        C.generation_per_type("10YXX-UNKNOWN--1", 2025, TOKEN)
    assert not seen
