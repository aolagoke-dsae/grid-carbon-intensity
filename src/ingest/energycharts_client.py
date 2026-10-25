"""Energy-Charts (Fraunhofer ISE) ingestion — no token required.

Why this exists: Electricity Maps' hourly series is not open to a public
repository (docs/EM_CROSSCHECK.md), so the hour-by-hour check of our German
generation data runs against the independent compilation that is: Fraunhofer
ISE's public net electricity generation, licensed CC BY 4.0 with attribution
to Energy-Charts.info. It is built from ENTSO-E, EEX transparency data and
Fraunhofer's own estimates, so where it disagrees with our ENTSO-E parse, one
of the two is wrong or they count different things.

Same discipline and the same manifest as entsoe_client.py and smard_client.py:
  * raw/ is append-only: every response is a new file, never an overwrite
    (src/ingest/raw_store.py); a response that is not usable JSON is kept
    under _failed/ and never read as data
  * every response is hashed and recorded with its URL, status, size and time

One request per calendar month, first day to last day, in the API's day
format: it reads a day in the country's time zone and an end day as that day's
last minute, so consecutive months meet at local midnight. The documented
limit is 2 requests a minute with a burst of 4, so requests are spaced 31
seconds apart, and a 429 waits for its Retry-After before the next attempt.

    https://api.energy-charts.info/
"""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import requests

try:                        # run as a module from the repository root
    from src.ingest import raw_store
except ImportError:         # imported with src/ingest on sys.path (pytest)
    import raw_store

BASE = "https://api.energy-charts.info/v2/public_power"
RAW = Path("raw")
MANIFEST = RAW / "manifest.csv"
COUNTRY = "de"
SLEEP_SECONDS = 31.0        # the documented limit: 2 requests a minute
MAX_RETRIES = 4


def months(year: int) -> list[tuple[int, str, str]]:
    """(month, first day, last day) of each month of the year, as the API's
    day format."""
    return [(m, f"{year}-{m:02d}-01", f"{year}-{m:02d}-{calendar.monthrange(year, m)[1]:02d}")
            for m in range(1, 13)]


def _usable(status: int, body: bytes) -> bool:
    """HTTP 200 and a JSON object that holds data points and the series they
    name. An error page, a rate-limit answer or an empty month is not data."""
    if status != 200:
        return False
    try:
        doc = json.loads(body)
    except ValueError:
        return False
    return isinstance(doc, dict) and bool(doc.get("data")) and bool(doc.get("series"))


def _retry_after(response: requests.Response) -> float:
    try:
        return float(response.headers.get("Retry-After", 60))
    except ValueError:      # an HTTP date rather than seconds
        return 60.0


def _get(params: dict, out_path: Path) -> dict:
    """One request -> one new raw file + one manifest row (see raw_store)."""
    raw_store.check_manifest(MANIFEST)
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(BASE, params=params, timeout=120)
            if r.status_code == 429:
                time.sleep(_retry_after(r))
                raise requests.HTTPError("HTTP 429")
            if 500 <= r.status_code < 600:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            body = r.content
        except requests.RequestException as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
            continue
        accepted = _usable(r.status_code, body)
        now = dt.datetime.now(dt.timezone.utc)
        path = raw_store.store(out_path, body, accepted, now)
        row = {
            "retrieved_at_utc": now.isoformat(timespec="seconds"),
            "path": path.as_posix(),
            "url": r.url,
            "http_status": r.status_code,
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
            "rejected": int(not accepted),
            "attempt": attempt,
            "revision": "",
        }
        raw_store.append_manifest(MANIFEST, row)
        time.sleep(SLEEP_SECONDS)
        return row
    raise RuntimeError(f"failed after {MAX_RETRIES} attempts: {last_err}") from None


def logical(year: int, month: int, country: str = COUNTRY) -> Path:
    """raw/ENERGYCHARTS/public_power/de/2025-01.json, the month's logical item."""
    return RAW / "ENERGYCHARTS" / "public_power" / country / f"{year}-{month:02d}.json"


def fetch_month(year: int, month: int, country: str = COUNTRY) -> dict:
    """One month of public net generation. Returns the manifest row; check
    row["rejected"] before reading row["path"]."""
    _, first, last = months(year)[month - 1]
    return _get({"country": country, "start": first, "end": last},
                logical(year, month, country))


def backfill(year: int, country: str = COUNTRY) -> list[dict]:
    """Every month of the year not already stored, one request each. A month
    whose only retrieval sits in _failed/ is fetched again. Returns the
    manifest rows of the requests made."""
    rows = []
    for month, _, _ in months(year):
        if raw_store.current_version(logical(year, month, country)):
            continue
        rows.append(fetch_month(year, month, country))
    return rows


def main(argv: list[str]) -> int:
    """python -m src.ingest.energycharts_client <year> [<year> ...]

    Public net generation for Germany from Energy-Charts, one request per
    month not yet stored. About half a minute per month: the API allows two
    requests a minute.
    """
    if not argv or not all(a.isdigit() for a in argv):
        print(main.__doc__)
        return 2
    status = 0
    for year in map(int, argv):
        try:
            rows = backfill(year)
        except RuntimeError as e:
            print(f"{year}: {e}")
            status = 1
            continue
        rejected = [r for r in rows if r["rejected"]]
        print(f"{year}: {len(rows)} month(s) fetched, {len(rejected)} rejected")
        for r in rejected:
            print(f"   HTTP {r['http_status']}: {r['url']} -> {r['path']}")
        status = status or int(bool(rejected))
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
