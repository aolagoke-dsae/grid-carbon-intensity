"""ENTSO-E ingestion: chunked pulls -> immutable raw layer + manifest.

Design notes that matter for the assurance story:
  * raw/ is never mutated. Every response is written once and hashed.
  * manifest.csv is the provenance record: URL (token redacted), status,
    bytes, SHA-256, retrieved_at. This is what makes "data lineage" a
    control rather than a claim in a README.
  * A75 (Aggregated Generation per Type) permits a ONE-YEAR range per
    request, so we chunk by calendar year, not by day.
    https://transparencyplatform.zendesk.com/hc/en-us/articles/15854536354964
"""
from __future__ import annotations
import csv, hashlib, os, time, urllib.parse, datetime as dt
from pathlib import Path
import requests

BASE = "https://web-api.tp.entsoe.eu/api"
RAW = Path("raw")
MANIFEST = RAW / "manifest.csv"

# Conservative default. Check the published rate limit before raising it:
# https://transparencyplatform.zendesk.com/hc/en-us/articles/12783148966036
SLEEP_SECONDS = 1.5
MAX_RETRIES = 4


def _fmt(d: dt.date | dt.datetime) -> str:
    return d.strftime("%Y%m%d%H%M")


def _redact(text: str, token: str) -> str:
    """Remove the token from any text, raw or percent-encoded.

    An empty token would otherwise splice the marker between every character.
    """
    if not token:
        return text
    for form in {token, urllib.parse.quote(token, safe="")}:
        text = text.replace(form, "***REDACTED***")
    return text


def _append_manifest(row: dict) -> None:
    RAW.mkdir(parents=True, exist_ok=True)
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)


def fetch(params: dict, token: str, out_path: Path) -> dict:
    """One request -> raw file + manifest row. Returns the manifest row."""
    q = {**params, "securityToken": token}
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(BASE, params=q, timeout=90)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            body = r.content
            # ENTSO-E returns 200 with an Acknowledgement doc when a query is
            # rejected (bad range, no data). Treat that as a first-class outcome.
            rejected = b"Acknowledgement_MarketDocument" in body
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(body)
            row = {
                "retrieved_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "path": str(out_path),
                "url": _redact(r.url, token),
                "http_status": r.status_code,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "rejected": int(rejected),
                "attempt": attempt,
            }
            _append_manifest(row)
            time.sleep(SLEEP_SECONDS)
            return row
        except Exception as e:      # noqa: BLE001
            last_err = e
            time.sleep(min(2 ** attempt, 30))
    # requests puts the full URL, query string included, into its exception
    # text, so `last_err` carries the securityToken. Unredacted, it reached
    # every traceback a failed connection printed -- smoke.py does not catch
    # it. Redact before raising, and drop the chain so nothing underneath
    # repeats the URL.
    raise RuntimeError(
        f"failed after {MAX_RETRIES} attempts: {_redact(str(last_err), token)}"
    ) from None


def generation_per_type(zone_eic: str, year: int, token: str) -> dict:
    """A75 / processType A16, one calendar year (within the documented limit)."""
    start = dt.datetime(year, 1, 1)
    end = dt.datetime(year + 1, 1, 1)
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
    """A44, one calendar year."""
    params = {
        "documentType": "A44",
        "in_Domain": zone_eic,
        "out_Domain": zone_eic,
        "periodStart": _fmt(dt.datetime(year, 1, 1)),
        "periodEnd": _fmt(dt.datetime(year + 1, 1, 1)),
    }
    out = RAW / "A44" / zone_eic / f"{year}.xml"
    return fetch(params, token, out)


def actual_load(zone_eic: str, year: int, token: str) -> dict:
    """A65 / processType A16, one calendar year."""
    params = {
        "documentType": "A65",
        "processType": "A16",
        "outBiddingZone_Domain": zone_eic,
        "periodStart": _fmt(dt.datetime(year, 1, 1)),
        "periodEnd": _fmt(dt.datetime(year + 1, 1, 1)),
    }
    out = RAW / "A65" / zone_eic / f"{year}.xml"
    return fetch(params, token, out)
