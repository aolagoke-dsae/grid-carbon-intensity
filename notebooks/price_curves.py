# %% [markdown]
# # Which A44 price curve is the market's? DE-LU, 2021–2025
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
# ## Extended on 19.10.2026 to 2021–2024, after their weeks were pulled
#
# Every earlier year had hourly MTU throughout, so it has one regime: the first
# regime of the rule above, applied unchanged to the whole year. SMARD's hourly
# series is set against curve 1's hours as published and against the means of
# curve 2's quarter-hours, with the same tolerances and the same thresholds,
# and each year gets its own verdict. Unlike the rule, this extension was
# written after the pull; it changes no threshold and no comparison.
#
# Run from the repository root: `python notebooks/price_curves.py`. It needs
# the DE-LU A44 payloads and the SMARD weeks of each year in `raw/`
# (`python -m src.ingest.smard_client <year>`). No token is needed.

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
UTC = dt.timezone.utc
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")
GO_LIVE = dt.datetime(2025, 9, 30, 22, tzinfo=UTC)     # 15-minute MTU
EXACT, MEAN = 0.005, 0.01                # rule 1
SHARE, COVER = 0.99, 0.90                # rule 3
SMARD = ROOT / "raw" / "SMARD" / "4169"
A44 = ROOT / "raw" / "A44"


def window(series: dict, lo: dt.datetime, hi: dt.datetime) -> dict:
    return {t: v for t, v in series.items() if lo <= t < hi}


def steps(lo: dt.datetime, hi: dt.datetime, step_hours: float) -> int:
    return round((hi - lo).total_seconds() / 3600 / step_hours)


def bounds(year: int) -> tuple[dt.datetime, dt.datetime]:
    """The year in German time, as UTC instants."""
    return (dt.datetime(year, 1, 1, tzinfo=BERLIN).astimezone(UTC),
            dt.datetime(year + 1, 1, 1, tzinfo=BERLIN).astimezone(UTC))


def curves_of(year: int) -> tuple[Path, dict]:
    """The newest accepted payload of the year: {curve: {resolution: {UTC start: price}}}."""
    y0, y1 = bounds(year)
    xml = [p for p in current_payloads(A44) if p.parent == A44 / EIC / str(year)][0]
    curves: dict = {}
    for r in parse_prices(xml.read_text(encoding="utf-8")):
        if y0 <= r["ts_utc"] < y1:
            curve = curves.setdefault(r["classification_sequence"], {})
            curve.setdefault(r["resolution"], {})[r["ts_utc"]] = r["price_eur_mwh"]
    return xml, curves


def reproduces(a: dict, expected: int) -> bool:
    return a["share"] is not None and a["n"] >= COVER * expected and a["share"] >= SHARE


# %%
YEARS = sorted(int(p.name) for p in (A44 / EIC).iterdir() if p.is_dir() and p.name.isdigit())
smard_h = load_series(SMARD / "hour")
has_q = (SMARD / "quarterhour").is_dir() and bool(current_weeks(SMARD / "quarterhour"))
smard_q = load_series(SMARD / "quarterhour") if has_q else {}

comparisons = []     # (year, regime, curve, compared as, agreement, steps in the regime)
loaded = {}
for year in YEARS:
    y0, y1 = bounds(year)
    xml, curves = curves_of(year)
    loaded[year] = curves
    cut = min(max(GO_LIVE, y0), y1)      # the go-live, or the year's end if it came later
    before_h = window(smard_h, y0, cut)
    print(f"{year}: A44 {xml.relative_to(ROOT).as_posix()}: curves "
          + ", ".join(f"{cs} ({', '.join(f'{res} {len(v):,}' for res, v in sorted(c.items()))})"
                      for cs, c in sorted(curves.items()))
          + f"; SMARD {len(window(smard_h, y0, y1)):,} hours"
          + (f", {len(window(smard_q, y0, y1)):,} quarter-hours" if has_q else ""))
    for cs, c in sorted(curves.items()):
        hours = window(c.get("PT60M", {}), y0, cut)
        if hours:
            a, how = agreement(before_h, hours, EXACT), "hours as published"
        else:
            means = hourly_means(window(c.get("PT15M", {}), y0, cut), 0.25)
            a, how = agreement(before_h, means, MEAN), "means of four quarter-hours"
        regime = "before go-live" if cut < y1 else "hourly MTU, all year"
        comparisons.append((year, regime, cs, how, a, steps(y0, cut, 1.0)))
    if cut < y1:
        for cs, c in sorted(curves.items()):
            quarters = window(c.get("PT15M", {}), cut, y1)
            if has_q:
                a, how = agreement(window(smard_q, cut, y1), quarters, EXACT), "quarter-hours"
                expected = steps(cut, y1, 0.25)
            else:
                a = agreement(window(smard_h, cut, y1), hourly_means(quarters, 0.25), MEAN)
                how, expected = "means of four quarter-hours, against SMARD's hours", steps(cut, y1, 1.0)
            comparisons.append((year, "from go-live", cs, how, a, expected))

print("\nSMARD against each curve, by year; 2025 split at "
      f"{GO_LIVE:%Y-%m-%d %H:%M}Z\n")
print("| Year | Regime | Curve | Compared as | Steps compared, of the regime's | Equal to the cent "
      "| Mean abs. difference, €/MWh | Max abs. difference | Reproduces |")
print("|---|---|---|---|---:|---:|---:|---:|---|")
for year, regime, cs, how, a, expected in comparisons:
    share = "–" if a["share"] is None else f"{100 * a['share']:.2f}%"
    mean = "–" if a["mean_abs"] is None else f"{a['mean_abs']:.3f}"
    top = "–" if a["max_abs"] is None else f"{a['max_abs']:.2f}"
    print(f"| {year} | {regime} | {cs} | {how} | {a['n']:,} of {expected:,} | {share} | {mean} "
          f"| {top} | {'yes' if reproduces(a, expected) else 'no'} |")

print()
verdicts = {}
for year in YEARS:
    rows = [(cs, a, e) for y, _, cs, _, a, e in comparisons if y == year]
    winners = [cs for cs in sorted(loaded[year])
               if all(reproduces(a, e) for c, a, e in rows if c == cs)]
    verdicts[year] = winners[0] if len(winners) == 1 else None
    print(f"Verdict, {year} (rule 4): " + (f"curve {winners[0]} is the market's."
          if len(winners) == 1 else f"open; curves reproducing SMARD: {winners or 'none'}."))
same = set(verdicts.values())
if len(same) == 1 and None not in same:
    print(f"\nEvery year, {YEARS[0]}–{YEARS[-1]}: curve {same.pop()} is the market's.")

# %% [markdown]
# ## Beyond the rule, descriptive only
#
# What SMARD's quarter-hour series holds: before the go-live, is it curve 1's
# hourly price repeated, or curve 2? After it, do SMARD's hours average the
# market's quarter-hours?

# %%
for year in YEARS:
    y0, y1 = bounds(year)
    cut = min(max(GO_LIVE, y0), y1)
    c1, c2 = loaded[year].get(1, {}), loaded[year].get(2, {})
    if has_q:
        q = window(smard_q, y0, cut)
        repeated = {t: c1.get("PT60M", {}).get(t.replace(minute=0)) for t in q}
        a1 = agreement(q, repeated, EXACT)
        a2 = agreement(q, c2.get("PT15M", {}), EXACT)
        if a1["n"]:
            print(f"{year}, before the go-live: SMARD's quarter-hours equal curve 1's hour "
                  f"repeated in {100 * a1['share']:.2f}% of {a1['n']:,}, curve 2's quarter-hours "
                  f"in {100 * (a2['share'] or 0):.2f}%")
    if cut < y1:
        after_h = window(smard_h, cut, y1)
        for cs, c in sorted(loaded[year].items()):
            a = agreement(after_h, hourly_means(window(c.get("PT15M", {}), cut, y1), 0.25), MEAN)
            share = "–" if a["share"] is None else f"{100 * a['share']:.2f}%"
            print(f"{year}, from the go-live: SMARD's hours against the means of curve {cs}'s "
                  f"quarter-hours, {a['n']:,} hours, {share} within 0.01 €/MWh")

for year in YEARS:
    for cs, c in sorted(loaded[year].items()):
        prices = [v for res in c.values() for v in res.values() if v is not None]
        print(f"{year}, curve {cs}: median {statistics.median(prices):.2f}, min {min(prices):.2f}, "
              f"max {max(prices):.2f}, negative {100 * sum(v < 0 for v in prices) / len(prices):.1f}% "
              f"of {len(prices):,} steps")
