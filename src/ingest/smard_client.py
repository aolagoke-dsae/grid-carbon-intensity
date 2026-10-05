"""SMARD (Bundesnetzagentur) ingestion — no token required.

Why this exists: the plan names SMARD as the independent second source for the
dbt reconciliation test. ENTSO-E and SMARD publish the same German quantities
through different pipelines, so a disagreement between them is a real finding
rather than a rounding artefact. Having both is the point.

Same discipline as entsoe_client.py and the SAME manifest, so there is one
provenance record for the project rather than two:
  * raw/ is written once, never mutated
  * every response is hashed and recorded with its URL, status, size and time

SMARD serves data in weekly files. The index endpoint lists which week-start
timestamps exist; the data endpoint returns one of them. Always read the index
first — the available range moves, and guessing a timestamp returns a 404 that
is easy to mistake for "no data".

    https://www.smard.de/home/downloadcenter/download-marktdaten/
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import json
import time
from pathlib import Path

import requests

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


def _append_manifest(row: dict) -> None:
    """Append to the shared manifest, tolerating the ENTSO-E column set."""
    RAW.mkdir(parents=True, exist_ok=True)
    fields = ["retrieved_at_utc", "path", "url", "http_status", "bytes",
              "sha256", "rejected", "attempt"]
    new = not MANIFEST.exists()
    with MANIFEST.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in fields})


def _get(url: str, out_path: Path) -> dict:
    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 429 or 500 <= r.status_code < 600:
                raise requests.HTTPError(f"HTTP {r.status_code}")
            body = r.content
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(body)
            row = {
                "retrieved_at_utc": dt.datetime.now(dt.timezone.utc)
                                      .isoformat(timespec="seconds"),
                "path": str(out_path),
                "url": r.url,
                "http_status": r.status_code,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
                "rejected": int(r.status_code != 200),
                "attempt": attempt,
            }
            _append_manifest(row)
            time.sleep(SLEEP_SECONDS)
            return row
        except Exception as e:                     # noqa: BLE001
            last_err = e
            time.sleep(min(2 ** attempt, 30))
    raise RuntimeError(f"failed after {MAX_RETRIES} attempts: {last_err}")


def index(filter_id: int, region: str = REGION,
          resolution: str = RESOLUTION) -> list[int]:
    """Week-start timestamps (epoch ms) that SMARD actually holds."""
    url = f"{BASE}/{filter_id}/{region}/index_{resolution}.json"
    out = RAW / "SMARD" / str(filter_id) / f"index_{resolution}.json"
    row = _get(url, out)
    return json.loads(out.read_text(encoding="utf-8"))["timestamps"]


def week(filter_id: int, timestamp_ms: int, region: str = REGION,
         resolution: str = RESOLUTION) -> dict:
    """One weekly file. Returns the manifest row."""
    name = f"{filter_id}_{region}_{resolution}_{timestamp_ms}.json"
    url = f"{BASE}/{filter_id}/{region}/{name}"
    out = RAW / "SMARD" / str(filter_id) / resolution / name
    return _get(url, out)
