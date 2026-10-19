"""SMARD weekly files -> prices keyed by UTC time, and their agreement with A44.

SMARD's chart_data files hold one week each,

    {"meta_data": {...}, "series": [[epoch_ms, value_or_null], ...]}

with the epoch at the start of each interval. raw_store keeps every retrieval
of a week in its own directory, raw/SMARD/<filter>/<resolution>/<week>/.

This is the independent side of trap 5. A DE-LU A44 payload carries two
disagreeing day-ahead price curves (entsoe_prices_parse.py), and SMARD filter
4169, the Bundesnetzagentur's day-ahead price for DE-LU, says which of them
is the market's. Reading it strictly matters for that reason: a document
without a series list, a malformed pair or a value that is not a number is
refused, never skipped, because a skipped week reads downstream as a week in
which nothing could be compared, and nothing compared looks like agreement.
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

UTC = dt.timezone.utc


def parse_week(text: str) -> list[tuple[dt.datetime, float | None]]:
    """One SMARD week -> [(UTC start, value or None)], in file order."""
    doc = json.loads(text)
    series = doc.get("series") if isinstance(doc, dict) else None
    if not isinstance(series, list):
        raise ValueError("not a SMARD week: no 'series' list")
    out = []
    for pair in series:
        if not (isinstance(pair, list) and len(pair) == 2
                and isinstance(pair[0], int) and not isinstance(pair[0], bool)):
            raise ValueError(f"not a SMARD [epoch_ms, value] pair: {pair!r}")
        ms, value = pair
        if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
            raise ValueError(f"not a number at {ms}: {value!r}")
        out.append((dt.datetime.fromtimestamp(ms / 1000, UTC),
                    None if value is None else float(value)))
    return out


def current_weeks(folder: Path) -> list[Path]:
    """The newest accepted retrieval of every week under folder.

    One directory per week, one file per retrieval named by its UTC time, so
    the newest sorts last; anything under _failed/ was not data.
    """
    groups: dict[Path, list[Path]] = {}
    for p in folder.rglob("*.json"):
        if "_failed" in p.relative_to(folder).parts:
            continue
        groups.setdefault(p.parent, []).append(p)
    return [max(files) for _, files in sorted(groups.items())]


def load_series(folder: Path) -> dict[dt.datetime, float | None]:
    """Every interval under folder, keyed by its UTC start.

    Weeks do not overlap. A time stated twice with two different values is
    refused rather than resolved by whichever week was read last.
    """
    out: dict[dt.datetime, float | None] = {}
    for path in current_weeks(folder):
        for t, v in parse_week(path.read_text(encoding="utf-8")):
            if t in out and out[t] != v:
                raise ValueError(f"{t:%Y-%m-%d %H:%M}Z is stated twice: {out[t]} and {v}")
            out[t] = v
    return out


def hourly_means(series: dict[dt.datetime, float | None], step_hours: float
                 ) -> dict[dt.datetime, float]:
    """The mean of every complete UTC hour of a sub-hourly series.

    An hour missing a step, or holding a step without a value, has no mean:
    three quarter-hours do not average to an hour's price.
    """
    per_hour = round(1 / step_hours)
    buckets: dict[dt.datetime, list] = defaultdict(list)
    for t, v in series.items():
        buckets[t.replace(minute=0, second=0, microsecond=0)].append(v)
    return {h: sum(vs) / per_hour for h, vs in buckets.items()
            if len(vs) == per_hour and None not in vs}


def agreement(reference: dict, candidate: dict, tolerance: float) -> dict:
    """How closely candidate reproduces reference where both state a value.

    n: the times both state; agree: those within tolerance (EUR/MWh); share:
    agree / n; mean_abs and max_abs: the absolute differences.
    """
    diffs = [abs(candidate[t] - v) for t, v in reference.items()
             if v is not None and candidate.get(t) is not None]
    agree = sum(1 for d in diffs if d <= tolerance + 1e-9)
    return {
        "n": len(diffs),
        "agree": agree,
        "share": agree / len(diffs) if diffs else None,
        "mean_abs": sum(diffs) / len(diffs) if diffs else None,
        "max_abs": max(diffs) if diffs else None,
    }
