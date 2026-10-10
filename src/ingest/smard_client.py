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
import time
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
