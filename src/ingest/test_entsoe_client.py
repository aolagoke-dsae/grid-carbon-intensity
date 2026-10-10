"""Token redaction regression tests.

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
