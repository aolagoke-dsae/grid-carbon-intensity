"""SMARD (Bundesnetzagentur) ingestion — no token required.

Why this exists: the plan names SMARD as the independent second source for the
dbt reconciliation test. ENTSO-E and SMARD publish the same German quantities
through different pipelines, so a disagreement between them is a real finding
rather than a rounding artefact. Having both is the point.

Same discipline as entsoe_client.py and the SAME manifest, so there is one
provenance record for the project rather than two:
  * raw/ is append-only: every response is a new file, never an overwrite
    (src/ingest/raw_store.py); a response that is not usable JSON is kept
    under _failed/ and never read as data
  * every response is hashed and recorded with its URL, status, size and time

SMARD serves data in weekly files. The index endpoint lists which week-start
timestamps exist; the data endpoint returns one of them. Always read the index
first — the available range moves, and guessing a timestamp returns a 404 that
is easy to mistake for "no data".

    https://www.smard.de/home/downloadcenter/download-marktdaten/
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
import zoneinfo
from pathlib import Path

import requests

try:                        # run as a module from the repository root
    from src.ingest import raw_store
except ImportError:         # imported with src/ingest on sys.path (pytest)
    import raw_store

BASE = "https://www.smard.de/app/chart_data"
RAW = Path("raw")
MANIFEST = RAW / "manifest.csv"
SLEEP_SECONDS = 1.0
MAX_RETRIES = 4

# Filter IDs are SMARD's own series identifiers. Verify any addition against
# the download centre before trusting it; the names are not self-describing.
FILTERS = {
    4169: "Grosshandelspreis DE-LU",
}
REGION = "DE"
RESOLUTION = "hour"          # hour | quarterhour | day | week | month | year
# SMARD weeks run from Monday 00:00 to Monday 00:00, German time.
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")


def _is_json_object(body: bytes) -> bool:
    try:
        return isinstance(json.loads(body), dict)
    except ValueError:
        return False


def _get(url: str, out_path: Path) -> dict:
    """One request -> one new raw file + one manifest row (see raw_store)."""
    raw_store.check_manifest(MANIFEST)
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            body = r.content
        except requests.RequestException as e:
            last_err = e
            time.sleep(min(2 ** attempt, 30))
            continue
        # A 404 is an HTML page, not an empty week, and must never replace one.
        accepted = r.status_code == 200 and _is_json_object(body)
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


def index(filter_id: int, region: str = REGION,
          resolution: str = RESOLUTION) -> list[int]:
    """Week-start timestamps (epoch ms) that SMARD actually holds."""
    url = f"{BASE}/{filter_id}/{region}/index_{resolution}.json"
    out = RAW / "SMARD" / str(filter_id) / f"index_{resolution}.json"
    row = _get(url, out)
    if row["rejected"]:
        raise RuntimeError(
            f"SMARD index not usable: HTTP {row['http_status']}; the response is "
            f"kept at {row['path']} and the previous index is unchanged"
        )
    return json.loads(Path(row["path"]).read_text(encoding="utf-8"))["timestamps"]


def week(filter_id: int, timestamp_ms: int, region: str = REGION,
         resolution: str = RESOLUTION) -> dict:
    """One weekly file. Returns the manifest row; check row["rejected"]."""
    name = f"{filter_id}_{region}_{resolution}_{timestamp_ms}.json"
    url = f"{BASE}/{filter_id}/{region}/{name}"
    out = RAW / "SMARD" / str(filter_id) / resolution / name
    return _get(url, out)


def weeks_in_year(stamps: list[int], year: int) -> list[int]:
    """The week-start stamps whose week overlaps the German calendar year.

    The first and last weeks of a year usually straddle New Year: 2025 needs
    the week of Monday 30 December 2024 and the week of Monday 29 December
    2025, 53 in all. A week that ends exactly at local midnight on 1 January
    belongs to the year before.
    """
    lo = dt.datetime(year, 1, 1, tzinfo=BERLIN)
    hi = dt.datetime(year + 1, 1, 1, tzinfo=BERLIN)
    picked = []
    for t in stamps:
        start = dt.datetime.fromtimestamp(t / 1000, BERLIN)
        end = start + dt.timedelta(days=7)      # wall clock: the next Monday 00:00
        if start < hi and end > lo:
            picked.append(t)
    return picked


def backfill(filter_id: int, year: int, region: str = REGION,
             resolution: str = RESOLUTION) -> list[dict]:
    """Every week of a calendar year that SMARD holds, one request for each
    week not already stored. Reads the index first, as every pull must.

    A week with an accepted retrieval on disk is skipped, so a rerun after a
    failure repeats only what failed; a week whose only retrieval sits in
    _failed/ is fetched again. Returns the manifest rows of the requests made.
    """
    rows = []
    for t in weeks_in_year(index(filter_id, region, resolution), year):
        name = f"{filter_id}_{region}_{resolution}_{t}.json"
        if raw_store.current_version(RAW / "SMARD" / str(filter_id) / resolution / name):
            continue
        rows.append(week(filter_id, t, region, resolution))
    return rows


def main(argv: list[str]) -> int:
    """python -m src.ingest.smard_client <year> [resolution ...]

    Filter 4169, the DE-LU day-ahead price, for every week of <year>, at each
    resolution named; by default hour and quarterhour. A resolution SMARD does
    not hold is reported and its index response kept under _failed/.
    """
    if not argv or not argv[0].isdigit():
        print(main.__doc__)
        return 2
    year, resolutions = int(argv[0]), argv[1:] or ["hour", "quarterhour"]
    status = 0
    for res in resolutions:
        try:
            rows = backfill(4169, year, resolution=res)
        except RuntimeError as e:
            print(f"{res}: {e}")
            status = 1
            continue
        rejected = [r for r in rows if r["rejected"]]
        print(f"{res}: {len(rows)} week(s) fetched, {len(rejected)} rejected")
        for r in rejected:
            print(f"   HTTP {r['http_status']}: {r['url']} -> {r['path']}")
        status = status or int(bool(rejected))
    return status


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
