"""raw/ is append-only: regression tests for src/ingest/raw_store.py and for
the clients and smoke scripts that write through it.

Every test names the failure it prevents, and each of those failures was live
until 10.10.2026: the first A44 pull was overwritten by the second, an expired
token's 401 page would have replaced a year of data, and smoke.py would have
called it ACCEPTED. No network is used.
"""
import datetime as dt
import json

import pytest
import requests

import entsoe_client as C
import raw_store as R
import smard_client as S
import smoke

UTC = dt.timezone.utc
TOKEN = "t" * 36
A44_OK = (
    b'<?xml version="1.0" encoding="utf-8"?><Publication_MarketDocument '
    b'xmlns="urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"><mRID>m</mRID>'
    b"<revisionNumber>%s</revisionNumber><type>A44</type></Publication_MarketDocument>"
)
ACK = (
    b'<?xml version="1.0" encoding="utf-8"?><Acknowledgement_MarketDocument '
    b'xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0"><mRID>x</mRID>'
    b"<Reason><code>999</code><text>No matching data found</text></Reason>"
    b"</Acknowledgement_MarketDocument>"
)
PAGE_401 = b"<html><body>401 Unauthorized</body></html>"


class Resp:
    def __init__(self, status, content, url="https://web-api.tp.entsoe.eu/api?documentType=A44"):
        self.status_code, self.content, self.url = status, content, url


@pytest.fixture
def raw(monkeypatch, tmp_path):
    """Point both clients at an empty raw/ and skip their sleeps."""
    root = tmp_path / "raw"
    for mod in (C, S):
        monkeypatch.setattr(mod, "RAW", root)
        monkeypatch.setattr(mod, "MANIFEST", root / "manifest.csv")
    monkeypatch.setattr(C.time, "sleep", lambda s: None)
    return root


def _serve(monkeypatch, *responses):
    queue = iter(responses)
    monkeypatch.setattr(requests, "get", lambda *a, **k: next(queue))


def test_a_failed_pull_never_replaces_the_current_payload(raw, monkeypatch):
    """Prevents: an expired token's 401 page overwriting a year of data."""
    _serve(monkeypatch, Resp(200, A44_OK % b"1"), Resp(401, PAGE_401))
    item = raw / "A44" / "Z" / "2025.xml"
    good = C.fetch({}, TOKEN, item)
    bad = C.fetch({}, TOKEN, item)
    assert (good["rejected"], bad["rejected"], bad["http_status"]) == (0, 1, 401)
    assert "/_failed/" in bad["path"]
    assert R.current_version(item).as_posix() == good["path"]
    assert R.current_version(item).read_bytes() == A44_OK % b"1"


def test_an_acknowledgement_is_kept_but_never_becomes_current(raw, monkeypatch):
    """Prevents: "No matching data found" being read as an empty year."""
    _serve(monkeypatch, Resp(200, ACK))
    item = raw / "A75" / "Z" / "2025.xml"
    row = C.fetch({}, TOKEN, item)
    assert (row["rejected"], row["http_status"]) == (1, 200)
    assert "/_failed/" in row["path"]
    assert R.current_version(item) is None


def test_a_body_that_does_not_parse_is_not_data(raw, monkeypatch):
    """Prevents: a truncated download becoming the current version."""
    _serve(monkeypatch, Resp(200, (A44_OK % b"1")[:-40]))
    assert C.fetch({}, TOKEN, raw / "A44" / "Z" / "2025.xml")["rejected"] == 1


def test_a_new_retrieval_is_added_and_the_old_one_kept(tmp_path):
    """Prevents: a re-pull destroying the payload behind an earlier manifest row."""
    item = tmp_path / "A44" / "Z" / "2025.xml"
    first = R.store(item, b"<a>1</a>", True, dt.datetime(2026, 10, 6, 16, 30, 47, tzinfo=UTC))
    second = R.store(item, b"<a>2</a>", True, dt.datetime(2026, 10, 6, 18, 31, 50, tzinfo=UTC))
    assert first != second and first.read_bytes() == b"<a>1</a>"
    assert R.current_version(item) == second


def test_store_refuses_to_overwrite_different_bytes(tmp_path):
    """Prevents: any code path writing new content over an existing file."""
    item = tmp_path / "A44" / "Z" / "2025.xml"
    when = dt.datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC)
    path = R.store(item, b"<a>1</a>", True, when)
    assert R.store(item, b"<a>1</a>", True, when) == path      # same bytes: no-op
    path.write_bytes(b"tampered")
    with pytest.raises(FileExistsError):
        R.store(item, b"<a>1</a>", True, when)


def test_a_manifest_with_other_columns_is_refused_before_any_request(raw, monkeypatch):
    """Prevents: rows appended under a header they do not match, and a request
    spent before finding out."""
    raw.mkdir(parents=True)
    (raw / "manifest.csv").write_text("retrieved_at_utc,path\n2026-10-06,x\n", encoding="utf-8")
    calls = []
    monkeypatch.setattr(requests, "get", lambda *a, **k: calls.append(1))
    with pytest.raises(ValueError, match="migrate"):
        C.fetch({}, TOKEN, raw / "A44" / "Z" / "2025.xml")
    assert calls == []


def test_the_revision_is_recorded(raw, monkeypatch):
    """Prevents: not knowing which revision of a closed period is on disk."""
    _serve(monkeypatch, Resp(200, A44_OK % b"2"))
    assert C.fetch({}, TOKEN, raw / "A44" / "Z" / "2025.xml")["revision"] == "2"
    header = (raw / "manifest.csv").read_text(encoding="utf-8").splitlines()[0]
    assert header.split(",") == R.MANIFEST_FIELDS


def test_a_failed_smard_index_raises_and_keeps_the_previous_index(raw, monkeypatch):
    """Prevents: a 404 page overwriting the index, then crashing json.loads."""
    _serve(
        monkeypatch,
        Resp(200, json.dumps({"timestamps": [1, 2]}).encode()),
        Resp(404, b"<html>404</html>"),
    )
    assert S.index(4169) == [1, 2]
    with pytest.raises(RuntimeError, match="HTTP 404"):
        S.index(4169)
    current = R.current_version(raw / "SMARD" / "4169" / "index_hour.json")
    assert json.loads(current.read_text(encoding="utf-8")) == {"timestamps": [1, 2]}


@pytest.mark.parametrize(
    "status, body, rejected, verdict",
    [
        (401, PAGE_401, 1, 1),
        # a 401 the client somehow failed to flag: smoke must catch it alone
        (401, PAGE_401, 0, 1),
        (400, ACK, 1, 1),
        (200, A44_OK % b"1", 0, 0),
    ],
)
def test_smoke_reports_the_status_it_actually_got(
    monkeypatch, tmp_path, capsys, status, body, rejected, verdict
):
    """Prevents: smoke.py printing ACCEPTED for a 401, or "This is a 200" for a 400."""
    f = tmp_path / "response.xml"
    f.write_bytes(body)
    row = {
        "http_status": status, "bytes": len(body), "path": str(f),
        "sha256": "0" * 64, "url": "https://x/api?securityToken=***REDACTED***",
        "rejected": rejected,
    }
    monkeypatch.setattr(smoke, "read_token", lambda: TOKEN)
    monkeypatch.setattr(smoke, "day_ahead_prices", lambda *a: row)
    assert smoke.main() == verdict
    out = capsys.readouterr().out
    assert ("ACCEPTED — Publication_MarketDocument" in out) is (verdict == 0)
    assert "This is a 200" not in out
