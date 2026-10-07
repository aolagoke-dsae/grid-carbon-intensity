"""Stage checkpoints. Each returns (ok: bool, message: str).

The point of these is that you never build stage N+1 on an unproven stage N.
Run the relevant check, read the message, only then move on.
"""
from __future__ import annotations
import datetime as dt
from collections import Counter, defaultdict

# Expected steps in a LOCAL day, by resolution. DST days are the interesting ones.
def expected_steps(local_date, tz, step_hours: float) -> int:
    """Hours in the local calendar day (23, 24 or 25) divided by the step.

    The .astimezone(utc) calls are load-bearing and were missing until
    2026-09-17. Python subtracts two aware datetimes that share a tzinfo
    object by ignoring the offset entirely -- "No time zone adjustments are
    done in this case", per the datetime docs -- so the previous version
    returned 24 hours for every day of the year, including both transition
    days. It read as correct DST handling and asserted nothing, which is the
    precise failure mode this project is otherwise built to avoid: a wrong
    number that looks reasonable. Converting to UTC first forces the real
    elapsed time.
    """
    import zoneinfo
    z = zoneinfo.ZoneInfo(tz)
    utc = dt.timezone.utc
    start = dt.datetime.combine(local_date, dt.time(0), tzinfo=z).astimezone(utc)
    nxt = dt.datetime.combine(
        local_date + dt.timedelta(days=1), dt.time(0), tzinfo=z
    ).astimezone(utc)
    hours = (nxt - start).total_seconds() / 3600
    return int(round(hours / step_hours))


def check_stage2_parse(rows) -> tuple[bool, str]:
    """Every (series, period) must expand to its full step count, no nulls."""
    if not rows:
        return False, "no rows parsed"
    bad = [r for r in rows if r["mw"] is None]
    if bad:
        return False, f"{len(bad)} rows with null mw"
    # The key must include the period. A yearly payload carries one Period per
    # day, so keying on the series alone compares 365 days of rows against one
    # day's step count and fails on every correct parse. Fixtures are single-
    # period, which is why the tests never caught it.
    per_series = defaultdict(int)
    stated = {}
    for r in rows:
        k = (r["psr"], r["direction"], r.get("period_start_utc"))
        per_series[k] += 1
        stated[k] = r["n_steps_expanded"]
    wrong = {k: v for k, v in per_series.items() if v != stated[k]}
    if wrong:
        return False, f"series with wrong row count after expansion: {wrong}"
    return True, f"{len(rows)} rows across {len(per_series)} series, all fully expanded"


def check_stage2_direction(rows) -> tuple[bool, str]:
    """Pumped storage must be carried with an explicit direction.

    Earlier versions demanded BOTH directions be present and failed otherwise.
    That is wrong for any window in which the unit only pumps (or only
    generates) -- a common overnight payload -- and it produced a false
    failure on the very sample in test_parse.py. What actually matters is
    that every B10 row is classified, so the consumption leg can be excluded
    from the generation mix rather than silently summed into it.
    """
    dirs = {(r["psr"], r["direction"]) for r in rows}
    if "B10" not in {p for (p, _) in dirs}:
        return True, "no B10 in this payload (fine)"
    found = {d for (p, d) in dirs if p == "B10"}
    unexpected = found - {"generation", "consumption"}
    if unexpected:
        return False, f"B10 rows with unclassified direction: {sorted(unexpected)}"
    return True, f"B10 present and directionally split: {sorted(found)}"


def check_stage3_coverage(rows, tz: str) -> tuple[bool, str]:
    """Per local day, per series: does the step count match the calendar?"""
    import zoneinfo
    z = zoneinfo.ZoneInfo(tz)
    by_day = defaultdict(set)
    steps = {}
    for r in rows:
        if r["direction"] != "generation":
            continue
        local = r["ts_utc"].astimezone(z).date()
        # Zone belongs in the key. Without it two zones with the same
        # timestamps collapse into one set, and a zone missing a whole day is
        # invisible as long as another zone has it.
        k = (r.get("zone"), local, r["psr"])
        by_day[k].add(r["ts_utc"])
        steps[k] = r["step_hours"]
    problems, dst = [], []
    for (zone, day, psr), tss in sorted(by_day.items(), key=lambda kv: (str(kv[0][0]), kv[0][1], kv[0][2])):
        k = (zone, day, psr)
        exp = expected_steps(day, tz, steps[k])
        got = len(tss)
        if got != exp:
            problems.append(f"{zone} {day} {psr}: {got}/{exp}")
        elif exp != int(round(24 / steps[k])):
            dst.append(f"{day} ({exp} steps)")
    msg = f"{len(by_day)} day-series checked"
    if dst:
        msg += f"; DST days handled correctly: {sorted(set(dst))}"
    if problems:
        return False, msg + f"; MISMATCHES: {problems[:10]}"
    return True, msg


def check_stage4_factors(rows, factors: dict) -> tuple[bool, str]:
    """Every generating psrType must map to a factor or be explicitly flagged."""
    seen = {r["psr"] for r in rows if r["direction"] == "generation"}
    missing = [p for p in sorted(seen) if p not in factors]
    # load_factors() returns Factor dataclasses, not csv.DictReader rows, so
    # .get() raised AttributeError here. Factor.priced is the same test: a
    # median AND a band.
    unpriced = [p for p in sorted(seen)
                if p in factors and not factors[p].priced]
    if missing:
        return False, f"psrTypes with no row in the factor table at all: {missing}"
    return True, (f"{len(seen)} psrTypes present; "
                  f"{len(unpriced)} deliberately unpriced and flagged: {unpriced}")


def check_stage5_plausibility(intensity_g_kwh) -> tuple[bool, str]:
    """Sanity bounds. Anything outside these means a units or join error."""
    vals = [v for v in intensity_g_kwh if v is not None]
    if not vals:
        return False, "no intensity values"
    lo, hi = min(vals), max(vals)
    if lo < 0:
        return False, f"negative intensity ({lo:.1f}) - check the consumption filter"
    if hi > 1000:
        return False, f"intensity {hi:.1f} exceeds the dirtiest single fuel - check MWh weighting"
    return True, f"range {lo:.0f}-{hi:.0f} gCO2e/kWh across {len(vals)} steps - plausible"
