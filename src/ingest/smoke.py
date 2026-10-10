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
    """Read ENTSOE_TOKEN from .env, tolerating how Windows shells write files.

    PowerShell 5.1 writes UTF-16LE by default when you redirect with '>', and
    writes UTF-8 with a BOM with Set-Content. cmd.exe keeps any space you leave
    before the '>' inside the value. All three produce a token that looks right
    and is not, so handle them here rather than in a troubleshooting session.
    """
    env = ROOT / ".env"
    if not env.exists():
        sys.exit("No .env in the project root. Create it with one line:\n"
                 "    ENTSOE_TOKEN=<paste the token, no quotes, no spaces>")

    raw = env.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "utf-8", "latin-1"):
        try:
            txt = raw.decode(enc)
            if "ENTSOE_TOKEN" in txt:
                break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        sys.exit(".env could not be decoded. Re-save it as plain UTF-8 text.")

    for line in txt.splitlines():
        line = line.lstrip("\ufeff").strip()
        if not line.startswith("ENTSOE_TOKEN"):
            continue
        tok = line.split("=", 1)[1].strip().strip('"').strip("'").strip()
        if not tok or "your" in tok.lower() or "<" in tok:
            sys.exit("ENTSOE_TOKEN is still a placeholder in .env")
        if len(tok) < 20:
            sys.exit(f"ENTSOE_TOKEN looks too short ({len(tok)} characters). "
                     "A Transparency Platform token is a 36-character UUID.")
        return tok
    sys.exit("No ENTSOE_TOKEN line found in .env")


def main() -> int:
    token = read_token()
    print(f"Requesting A44 day-ahead prices, {ZONE_KEY} ({ZONE_EIC}), {YEAR} ...")
    row = day_ahead_prices(ZONE_EIC, YEAR, token)

    print(f"  HTTP {row['http_status']}  ·  {row['bytes']:,} bytes")
    print(f"  file   {row['path']}")
    print(f"  sha256 {row['sha256'][:16]}...")
    print(f"  url    {row['url']}")          # token already redacted by the client

    body = Path(row["path"]).read_text(encoding="utf-8", errors="replace")

    # Both conditions, independently: a non-200 response is never a pass, even
    # if something upstream failed to flag it. This script used to check only
    # `rejected`, so a 401 page without an Acknowledgement printed ACCEPTED.
    if row["rejected"] or row["http_status"] != 200:
        print(f"\n  NOT ACCEPTED — HTTP {row['http_status']}.")
        if "Acknowledgement_MarketDocument" in body:
            reason = re.search(r"<text>(.*?)</text>", body, re.S)
            print("  ENTSO-E returned an Acknowledgement document instead of data.")
            print(f"  reason: {reason.group(1).strip() if reason else 'not stated'}")
        elif row["http_status"] == 401:
            print("  The token was refused. Check .env, and whether it was rotated.")
        else:
            print("  The response is not a parseable ENTSO-E document.")
        print("  It is kept in the _failed/ folder for inspection. Nothing in raw/ was")
        print("  replaced: the previous payload, if any, is still the current one.")
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
