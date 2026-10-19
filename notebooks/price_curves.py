# %% [markdown]
# # Which A44 price curve is the market's? DE-LU, 2025
#
# Trap 5 (`src/transform/entsoe_prices_parse.py`). The DE-LU A44 payload carries
# two complete, disagreeing day-ahead price curves, told apart only by
# `classificationSequence`. Curve 1 is hourly until the 15-minute market time
# unit went live (2025-09-30T22:00Z, 1 October 00:00 CEST) and 15-minute after.
# Curve 2 is 15-minute all year, and in 2021–2024 too. `stg_entsoe__prices.sql`
# keeps curve 1 by default, for continuity and without proof.
#
# SMARD filter 4169, the Bundesnetzagentur's day-ahead price for
# Germany/Luxembourg, is the independent check. It comes through a different
# pipeline, so it should reproduce the market's curve to the cent and the
# other curve not at all.
#
# ## The rule, fixed on 19.10.2026, before the 2025 SMARD weeks were pulled
#
# 1. **Agreement.** A step agrees when SMARD and the curve differ by at most
#    0.005 €/MWh, that is, when they are equal to the cent. Where an hourly SMARD
#    value is set against the mean of four quarter-hours, the tolerance is
#    0.01, since a mean of cent prices need not be one.
# 2. **Two regimes, compared separately.** Before 2025-09-30T22:00Z, SMARD's
#    hourly series is set against each curve's hours: curve 1's as published,
#    curve 2's as the means of its four quarter-hours. From then on, SMARD's
#    quarter-hour series is set against each curve's quarter-hours. If SMARD
#    holds no quarter-hour series, its hourly series is set against the means of
#    each curve's quarter-hours instead.
# 3. **Reproduces.** A curve reproduces SMARD in a regime if it agrees in at
#    least 99% of the steps both state, and those steps cover at least 90% of
#    the regime.
# 4. **Verdict.** The curve that reproduces SMARD in both regimes is the
#    market's, and the default in `stg_entsoe__prices.sql` follows it. If both
#    curves or neither do, the question stays open and the default stays as it
#    is.
#
# Run from the repository root: `python notebooks/price_curves.py`. It needs
# the 2025 DE-LU A44 payload and the 2025 SMARD weeks in `raw/`
# (`python -m src.ingest.smard_client 2025`). No token is needed.

# %%
from __future__ import annotations

import datetime as dt
import os
import statistics
import sys
import zoneinfo
from pathlib import Path

ROOT = Path.cwd()
if ROOT.name == "notebooks":
    ROOT = ROOT.parent
    os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from src.transform.entsoe_prices_parse import parse_prices  # noqa: E402
from src.transform.smard_parse import (  # noqa: E402
    agreement, current_weeks, hourly_means, load_series,
)
from src.transform.xml_to_parquet import current_payloads  # noqa: E402

EIC = "10Y1001A1001A82H"                 # DE-LU
YEAR = 2025
UTC = dt.timezone.utc
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")
Y0 = dt.datetime(YEAR, 1, 1, tzinfo=BERLIN).astimezone(UTC)
Y1 = dt.datetime(YEAR + 1, 1, 1, tzinfo=BERLIN).astimezone(UTC)
GO_LIVE = dt.datetime(2025, 9, 30, 22, tzinfo=UTC)     # 15-minute MTU
EXACT, MEAN = 0.005, 0.01                # rule 1
SHARE, COVER = 0.99, 0.90                # rule 3
SMARD = ROOT / "raw" / "SMARD" / "4169"


def window(series: dict, lo: dt.datetime, hi: dt.datetime) -> dict:
    return {t: v for t, v in series.items() if lo <= t < hi}


def steps(lo: dt.datetime, hi: dt.datetime, step_hours: float) -> int:
    return round((hi - lo).total_seconds() / 3600 / step_hours)


# %%
doc_dir = ROOT / "raw" / "A44"
xml = [p for p in current_payloads(doc_dir) if p.parent == doc_dir / EIC / str(YEAR)][0]
curves: dict = {}
for r in parse_prices(xml.read_text(encoding="utf-8")):
    if Y0 <= r["ts_utc"] < Y1:
        curve = curves.setdefault(r["classification_sequence"], {})
        curve.setdefault(r["resolution"], {})[r["ts_utc"]] = r["price_eur_mwh"]

smard_h = window(load_series(SMARD / "hour"), Y0, Y1)
has_q = (SMARD / "quarterhour").is_dir() and bool(current_weeks(SMARD / "quarterhour"))
smard_q = window(load_series(SMARD / "quarterhour"), Y0, Y1) if has_q else {}

print(f"A44 {xml.relative_to(ROOT).as_posix()}: curves "
      + ", ".join(f"{cs} ({', '.join(f'{res} {len(v):,}' for res, v in sorted(c.items()))})"
                  for cs, c in sorted(curves.items())))
print(f"SMARD 4169: {len(smard_h):,} hours"
      + (f", {len(smard_q):,} quarter-hours" if has_q else ", no quarter-hour series")
      + f" in {YEAR}")

# %%
comparisons = []     # (regime, curve, compared as, agreement, steps in the regime)
before_h = window(smard_h, Y0, GO_LIVE)
for cs, c in sorted(curves.items()):
    hours = window(c.get("PT60M", {}), Y0, GO_LIVE)
    if hours:
        a, how = agreement(before_h, hours, EXACT), "hours as published"
    else:
        means = hourly_means(window(c.get("PT15M", {}), Y0, GO_LIVE), 0.25)
        a, how = agreement(before_h, means, MEAN), "means of four quarter-hours"
    comparisons.append(("before", cs, how, a, steps(Y0, GO_LIVE, 1.0)))

for cs, c in sorted(curves.items()):
    quarters = window(c.get("PT15M", {}), GO_LIVE, Y1)
    if has_q:
        a, how = agreement(window(smard_q, GO_LIVE, Y1), quarters, EXACT), "quarter-hours"
        expected = steps(GO_LIVE, Y1, 0.25)
    else:
        a = agreement(window(smard_h, GO_LIVE, Y1), hourly_means(quarters, 0.25), MEAN)
        how, expected = "means of four quarter-hours, against SMARD's hours", steps(GO_LIVE, Y1, 1.0)
    comparisons.append(("from go-live", cs, how, a, expected))


def reproduces(a: dict, expected: int) -> bool:
    return a["share"] is not None and a["n"] >= COVER * expected and a["share"] >= SHARE


print(f"\nSMARD against each curve, {YEAR}; regimes split at {GO_LIVE:%Y-%m-%d %H:%M}Z\n")
print("| Regime | Curve | Compared as | Steps compared, of the regime's | Equal to the cent "
      "| Mean abs. difference, €/MWh | Max abs. difference | Reproduces |")
print("|---|---|---|---:|---:|---:|---:|---|")
for regime, cs, how, a, expected in comparisons:
    share = "–" if a["share"] is None else f"{100 * a['share']:.2f}%"
    mean = "–" if a["mean_abs"] is None else f"{a['mean_abs']:.3f}"
    top = "–" if a["max_abs"] is None else f"{a['max_abs']:.2f}"
    print(f"| {regime} | {cs} | {how} | {a['n']:,} of {expected:,} | {share} | {mean} | {top} "
          f"| {'yes' if reproduces(a, expected) else 'no'} |")

winners = [cs for cs in sorted(curves)
           if all(reproduces(a, e) for _, c, _, a, e in comparisons if c == cs)]
if len(winners) == 1:
    print(f"\nVerdict (rule 4): curve {winners[0]} is the market's.")
else:
    print(f"\nVerdict (rule 4): open; curves reproducing SMARD in both regimes: {winners or 'none'}.")

# %% [markdown]
# ## Beyond the rule, descriptive only
#
# SMARD's hourly series after the go-live, set against the hourly means of each
# curve's quarter-hours: does SMARD's hour average the market's quarter-hours?

# %%
if has_q:
    after_h = window(smard_h, GO_LIVE, Y1)
    for cs, c in sorted(curves.items()):
        a = agreement(after_h, hourly_means(window(c.get("PT15M", {}), GO_LIVE, Y1), 0.25), MEAN)
        share = "–" if a["share"] is None else f"{100 * a['share']:.2f}%"
        print(f"curve {cs}: SMARD hours against means of quarter-hours, {a['n']:,} hours, "
              f"{share} within 0.01 €/MWh")

for cs, c in sorted(curves.items()):
    prices = [v for res in c.values() for v in res.values() if v is not None]
    print(f"curve {cs}: median {statistics.median(prices):.2f}, min {min(prices):.2f}, "
          f"max {max(prices):.2f}, negative {100 * sum(v < 0 for v in prices) / len(prices):.1f}% "
          f"of {len(prices):,} steps")
