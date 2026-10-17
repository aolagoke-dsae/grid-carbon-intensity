"""ENTSO-E ingestion: chunked pulls -> append-only raw layer + manifest.

Design notes that matter for the assurance story:
  * raw/ is append-only. Every response is written once, to a new file, and
    hashed; nothing is ever overwritten (src/ingest/raw_store.py). A response
    that is not data -- a non-200 status, an Acknowledgement document, a body
    that does not parse -- is kept under _failed/ and can never become the
    current version.
  * manifest.csv is the provenance record: URL (token redacted), status,
    bytes, SHA-256, retrieved_at, revisionNumber. This is what makes "data
    lineage" a control rather than a claim in a README.
  * A75 (Aggregated Generation per Type) permits a ONE-YEAR range per
    request, so we chunk by calendar year, not by day.
    https://transparencyplatform.zendesk.com/hc/en-us/articles/15854536354964
"""
from __future__ import annotations
import csv, hashlib, re, time, urllib.parse, zoneinfo, datetime as dt
import xml.etree.ElementTree as ET
from pathlib import Path
import requests

try:                        # run as a module from the repository root
    from src.ingest import raw_store
except ImportError:         # imported with src/ingest on sys.path (pytest)
    import raw_store

BASE = "https://web-api.tp.entsoe.eu/api"
RAW = Path("raw")
MANIFEST = RAW / "manifest.csv"
ZONES = Path(__file__).resolve().parents[2] / "config" / "zones.csv"

# Conservative default. Check the published rate limit before raising it:
# https://transparencyplatform.zendesk.com/hc/en-us/articles/12783148966036
SLEEP_SECONDS = 1.5
MAX_RETRIES = 4


def _fmt(d: dt.date | dt.datetime) -> str:
    return d.strftime("%Y%m%d%H%M")


def _zone_tz(zone_eic: str) -> str:
    """The bidding zone's IANA time zone, from config/zones.csv."""
    with ZONES.open(newline="", encoding="utf-8") as fh:
        for z in csv.DictReader(fh):
            if z["eic"] == zone_eic:
                return z["tz"]
    raise ValueError(f"{zone_eic} is not in config/zones.csv; add it with its time zone first")


def _local_year(zone_eic: str, year: int) -> tuple[dt.datetime, dt.datetime]:
    """UTC bounds of the zone's local calendar year, for periodStart/periodEnd.

    ENTSO-E reads both bounds as UTC and clips the answer to them. A UTC
    calendar year is not a delivery year: for DE-LU it cut the first hour off
    local 1 January 2025 (92 of 96 steps) and took the first hour of
    1 January 2026 -- found in the first A75 pull, 17.10.2026 (audit A5).
    Consecutive yearly pulls would then hold that hour twice. Local midnight to
    local midnight, converted to UTC, gives whole delivery days and years that
    meet without overlapping.
    """
    tz = zoneinfo.ZoneInfo(_zone_tz(zone_eic))
    start = dt.datetime(year, 1, 1, tzinfo=tz).astimezone(dt.timezone.utc)
    end = dt.datetime(year + 1, 1, 1, tzinfo=tz).astimezone(dt.timezone.utc)
    return start, end


def _redact(text: str, token: str) -> str:
    """Remove the token from any text, raw or percent-encoded.

    An empty token would otherwise splice the marker between every character.
    """
    if not token:
        return text
    for form in {token, urllib.parse.quote(token, safe="")}:
        text = text.replace(form, "***REDACTED***")
    return text


def _accepted(status: int, body: bytes) -> tuple[bool, str]:
    """Is this response data? Returns (accepted, revisionNumber or "").

    ENTSO-E answers a rejected query (bad range, no data) with HTTP 200 and an
    Acknowledgement document, and an expired or rotated token with a 401 page.
    Neither is data, and neither may stand in for the payload it would replace.
    """
    if status != 200:
        return False, ""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return False, ""
    if root.tag.endswith("Acknowledgement_MarketDocument"):
        return False, ""
    m = re.search(rb"<revisionNumber>\s*(\d+)\s*</revisionNumber>", body)
    return True, (m.group(1).decode() if m else "")


def fetch(params: dict, token: str, out_path: Path) -> dict:
    """One request -> one new raw file + one manifest row.

    out_path names the logical item, e.g. raw/A44/<eic>/2025.xml. The body is
    stored as a new file in raw/A44/<eic>/2025/ -- or in its _failed/ folder
    when it is not data -- and every earlier file is left untouched. Returns
    the manifest row: check row["rejected"] before reading row["path"].
    """
    raw_store.check_manifest(MANIFEST)      # fail before spending a request
    q = {**params, "securityToken": token}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(BASE, params=q, timeout=90)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            body = r.content
        except requests.RequestException as e:
            # Only transport failures are retried. A local error -- a manifest
            # with other columns, a file that would be overwritten -- stops at
            # once instead of sending the same request four more times.
            last_err = e
            time.sleep(min(2 ** attempt, 30))
            continue
        accepted, revision = _accepted(r.status_code, body)
        now = dt.datetime.now(dt.timezone.utc)
        path = raw_store.store(out_path, body, accepted, now)
        row = {
            "retrieved_at_utc": now.isoformat(timespec="seconds"),
            "path": path.as_posix(),
            "url": _redact(r.url, token),
            "http_status": r.status_code,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "rejected": int(not accepted),
            "attempt": attempt,
            "revision": revision,
        }
        raw_store.append_manifest(MANIFEST, row)
        time.sleep(SLEEP_SECONDS)
        return row
    # requests puts the full URL, query string included, into its exception
    # text, so `last_err` carries the securityToken. Unredacted, it reached
    # every traceback a failed connection printed -- smoke.py does not catch
    # it. Redact before raising, and drop the chain so nothing underneath
    # repeats the URL.
    raise RuntimeError(
        f"failed after {MAX_RETRIES} attempts: {_redact(str(last_err), token)}"
    ) from None


def generation_per_type(zone_eic: str, year: int, token: str) -> dict:
    """A75 / processType A16, one local calendar year (the documented limit)."""
    start, end = _local_year(zone_eic, year)
    params = {
        "documentType": "A75",
        "processType": "A16",
        "in_Domain": zone_eic,
        "periodStart": _fmt(start),
        "periodEnd": _fmt(end),
    }
    out = RAW / "A75" / zone_eic / f"{year}.xml"
    return fetch(params, token, out)


def day_ahead_prices(zone_eic: str, year: int, token: str) -> dict:
    """A44, one local calendar year."""
    start, end = _local_year(zone_eic, year)
    params = {
        "documentType": "A44",
        "in_Domain": zone_eic,
        "out_Domain": zone_eic,
        "periodStart": _fmt(start),
        "periodEnd": _fmt(end),
    }
    out = RAW / "A44" / zone_eic / f"{year}.xml"
    return fetch(params, token, out)


def actual_load(zone_eic: str, year: int, token: str) -> dict:
    """A65 / processType A16, one local calendar year."""
    start, end = _local_year(zone_eic, year)
    params = {
        "documentType": "A65",
        "processType": "A16",
        "outBiddingZone_Domain": zone_eic,
        "periodStart": _fmt(start),
        "periodEnd": _fmt(end),
    }
    out = RAW / "A65" / zone_eic / f"{year}.xml"
    return fetch(params, token, out)
