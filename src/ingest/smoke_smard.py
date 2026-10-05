"""Put one real file in raw/, tonight, without a token.

    python -m src.ingest.smoke_smard

Reads the index first to learn which weeks SMARD actually holds, then pulls the
most recent complete one. Two files land in raw/SMARD/ and two rows in
raw/manifest.csv.

UNTESTED AS WRITTEN. It could not be run from the machine it was written on,
because that sandbox cannot reach smard.de. The first run is the test. If the
field names differ from what is assumed below, the script says so rather than
guessing — which is the behaviour that matters.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.ingest.smard_client import FILTERS, REGION, RESOLUTION, index, week  # noqa: E402

FILTER_ID = 4169          # Grosshandelspreis DE-LU


def main() -> int:
    print(f"SMARD · filter {FILTER_ID} ({FILTERS.get(FILTER_ID, '?')}) · "
          f"{REGION} · {RESOLUTION}")

    try:
        stamps = index(FILTER_ID)
    except Exception as e:                          # noqa: BLE001
        print(f"  index request failed: {e}")
        print("  If this is a connection error, the machine has no route to "
              "smard.de. If it is a 404, the filter id or resolution is wrong.")
        return 1

    if not stamps:
        print("  index returned no timestamps — nothing to fetch")
        return 1

    first = dt.datetime.fromtimestamp(stamps[0] / 1000, dt.timezone.utc)
    last = dt.datetime.fromtimestamp(stamps[-1] / 1000, dt.timezone.utc)
    print(f"  {len(stamps)} weekly files available, "
          f"{first:%Y-%m-%d} to {last:%Y-%m-%d}")

    # the last entry is the week in progress; take the one before it
    target = stamps[-2] if len(stamps) > 1 else stamps[-1]
    when = dt.datetime.fromtimestamp(target / 1000, dt.timezone.utc)
    print(f"  fetching week beginning {when:%Y-%m-%d} ...")

    row = week(FILTER_ID, target)
    print(f"  HTTP {row['http_status']} · {row['bytes']:,} bytes")
    print(f"  file   {row['path']}")
    print(f"  sha256 {row['sha256'][:16]}...")

    doc = json.loads(Path(row["path"]).read_text(encoding="utf-8"))
    series = doc.get("series")
    if series is None:
        print(f"  no 'series' key. Top-level keys: {sorted(doc)}")
        print("  The response shape differs from the assumption. Inspect the "
              "file before writing a parser against it.")
        return 1

    values = [v for _, v in series if v is not None]
    print(f"\n  {len(series):,} rows, {len(values):,} with a value, "
          f"{len(series) - len(values):,} null")
    if values:
        print(f"  range {min(values):,.2f} to {max(values):,.2f} EUR/MWh")
    print(f"  168 rows is a full week at hourly resolution.")
    print(f"\n  Manifest: raw/manifest.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
