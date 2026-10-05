"""One request against the Transparency Platform, to prove the path works.

Run from the project root, outside any sandbox, on a machine with internet:

    python -m src.ingest.smoke

Reads ENTSOE_TOKEN from .env (no dependency on python-dotenv). Calls the real
client in entsoe_client.py, so a pass here means the production path works,
not a parallel one written for the test.

ENTSO-E answers a rejected query with HTTP 200 and an Acknowledgement document
rather than an error status. That is the outcome this script is mainly looking
for, because it is the one that fails silently.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.ingest.entsoe_client import day_ahead_prices  # noqa: E402

ZONE_KEY = "DE_LU"
ZONE_EIC = "10Y1001A1001A82H"      # config/zones.yml
YEAR = 2025


def read_token() -> str:
    env = ROOT / ".env"
    if not env.exists():
        sys.exit("No .env in the project root. Create it with:\n"
                 "    ENTSOE_TOKEN=<your token>")
    for line in env.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("ENTSOE_TOKEN"):
            tok = line.split("=", 1)[1].strip().strip('"').strip("'")
            if tok and "your" not in tok.lower():
                return tok
    sys.exit("ENTSOE_TOKEN missing or still a placeholder in .env")


def main() -> int:
    token = read_token()
    print(f"Requesting A44 day-ahead prices, {ZONE_KEY} ({ZONE_EIC}), {YEAR} ...")
    row = day_ahead_prices(ZONE_EIC, YEAR, token)

    print(f"  HTTP {row['http_status']}  ·  {row['bytes']:,} bytes")
    print(f"  file   {row['path']}")
    print(f"  sha256 {row['sha256'][:16]}...")
    print(f"  url    {row['url']}")          # token already redacted by the client

    body = Path(row["path"]).read_text(encoding="utf-8", errors="replace")

    if row["rejected"]:
        reason = re.search(r"<text>(.*?)</text>", body, re.S)
        print("\n  REJECTED — ENTSO-E returned an Acknowledgement document.")
        print(f"  reason: {reason.group(1).strip() if reason else 'not stated'}")
        print("  This is a 200. Nothing crashed. Exactly the failure the manifest exists to catch.")
        return 1

    points = body.count("<Point>")
    res = sorted(set(re.findall(r"<resolution>(.*?)</resolution>", body)))
    periods = body.count("<Period>")
    print(f"\n  ACCEPTED — Publication_MarketDocument")
    print(f"  {periods} periods, {points:,} points, resolution(s): {', '.join(res) or 'none found'}")
    print(f"  A full year at PT60M is about 8,760 points; at PT15M about 35,040.")
    print(f"\n  Manifest: raw/manifest.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
