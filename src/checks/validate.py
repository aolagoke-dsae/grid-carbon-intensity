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


def find_gaps(rows, tz: str, sparse=frozenset()) -> tuple[list, int, list, int]:
    """Every (zone, local day, psr) whose step count differs from the calendar.

    Each series is checked on every day of its zone's span, so a day with no
    rows at all counts as a gap. Until 17.10.2026 only days holding at least
    one row were looked at, and a whole missing day passed unseen.

    Returns (gaps, checked, dst_days, exempt): gaps as
    (zone, day, psr, got, expected); exempt counts the day-series of `sparse`
    series, {(zone, psr)} that a zone publishes only while a unit runs, where
    a missing step is zero output rather than a gap.
    """
    import zoneinfo
    z = zoneinfo.ZoneInfo(tz)
    stamps = defaultdict(set)
    step_of_day, step_of_series = {}, {}
    span, series = {}, defaultdict(set)
    for r in rows:
        if r["direction"] != "generation":
            continue
        # Zone belongs in the key. Without it two zones with the same
        # timestamps collapse into one set, and a zone missing a whole day is
        # invisible as long as another zone has it.
        zone, psr = r.get("zone"), r["psr"]
        day = r["ts_utc"].astimezone(z).date()
        stamps[(zone, day, psr)].add(r["ts_utc"])
        step_of_day[(zone, day, psr)] = r["step_hours"]
        step_of_series[(zone, psr)] = r["step_hours"]
        lo, hi = span.get(zone, (day, day))
        span[zone] = (min(lo, day), max(hi, day))
        series[zone].add(psr)
    gaps, dst, checked, exempt = [], set(), 0, 0
    for zone in sorted(span, key=str):
        lo, hi = span[zone]
        days = [lo + dt.timedelta(days=n) for n in range((hi - lo).days + 1)]
        for psr in sorted(series[zone]):
            for day in days:
                checked += 1
                step = step_of_day.get((zone, day, psr), step_of_series[(zone, psr)])
                exp = expected_steps(day, tz, step)
                got = len(stamps.get((zone, day, psr), ()))
                if got == exp:
                    if exp != int(round(24 / step)):
                        dst.add(f"{day} ({exp} steps)")
                elif got < exp and (zone, psr) in sparse:
                    exempt += 1
                else:
                    gaps.append((zone, day, psr, got, exp))
    return gaps, checked, sorted(dst), exempt


def check_stage3_coverage(rows, tz: str, sparse=frozenset(), known=None) -> tuple[bool, str]:
    """Per local day, per series: does the step count match the calendar?

    `sparse`: {(zone, psr)} series published only while a unit runs (declared
    in config/zones.yml); a missing step there is zero output.
    `known`: {(zone, local_date, psr): missing_steps}, source gaps recorded in
    config/source_gaps.csv after inspection. A gap of exactly the recorded
    size is reported, not failed. Any other gap fails, including a recorded
    one whose size has changed.
    """
    known = known or {}
    gaps, checked, dst, exempt = find_gaps(rows, tz, sparse)
    recorded = [g for g in gaps if g[3] < g[4] and known.get((g[0], g[1], g[2])) == g[4] - g[3]]
    problems = [f"{zone} {day} {psr}: {got}/{exp}" for zone, day, psr, got, exp in gaps
                if (zone, day, psr, got, exp) not in recorded]
    msg = f"{checked} day-series checked"
    if dst:
        msg += f"; DST days handled correctly: {dst}"
    if exempt:
        msg += f"; {exempt} day-series short in series reported only while running (zero output)"
    if recorded:
        msg += f"; {len(recorded)} recorded source gaps ({sum(g[4] - g[3] for g in recorded)} steps)"
    if problems:
        return False, msg + f"; MISMATCHES ({len(problems)}): {problems[:10]}"
    return True, msg


def load_coverage_policy(zones_yml=None, gaps_csv=None) -> tuple[frozenset, dict]:
    """(sparse, known) for check_stage3_coverage, from the two config files.

    sparse: series a zone publishes only while a unit runs, from
        `reported_only_while_running` in config/zones.yml.
    known: recorded source gaps, from config/source_gaps.csv.
    """
    import csv
    from pathlib import Path
    import yaml
    config = Path(__file__).resolve().parents[2] / "config"
    zones = yaml.safe_load(Path(zones_yml or config / "zones.yml").read_text(encoding="utf-8"))["zones"]
    sparse = frozenset((z["eic"], psr) for z in zones for psr in z.get("reported_only_while_running", []))
    known = {}
    with Path(gaps_csv or config / "source_gaps.csv").open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            key = (row["zone_eic"], dt.date.fromisoformat(row["local_date"]), row["psr"])
            known[key] = int(row["missing_steps"])
    return sparse, known


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
