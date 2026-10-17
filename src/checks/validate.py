"""Stage checkpoints. Each returns (ok: bool, message: str).

The point of these is that you never build stage N+1 on an unproven stage N.
Run the relevant check, read the message, only then move on.

Each check has a test that makes it fail. A checkpoint that cannot fail is
worse than none: until 17.10.2026 the stage 2 direction check and the stage 5
bounds could not (audit A10).
"""
from __future__ import annotations
import datetime as dt
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict

RES_HOURS = {"PT15M": 0.25, "PT30M": 0.5, "PT60M": 1.0, "PT1H": 1.0}

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
    # period, which is why the tests never caught it. It must include the zone
    # too: two zones checked together share psr and period, and their rows
    # were counted against one zone's step count (audit A10).
    per_series = defaultdict(int)
    stated = {}
    for r in rows:
        k = (r.get("zone"), r["psr"], r["direction"], r.get("period_start_utc"))
        per_series[k] += 1
        stated[k] = r["n_steps_expanded"]
    wrong = {k: v for k, v in per_series.items() if v != stated[k]}
    if wrong:
        return False, f"series with wrong row count after expansion: {wrong}"
    return True, f"{len(rows)} rows across {len(per_series)} series, all fully expanded"


def _xml_steps(start: str, end: str, resolution: str) -> int:
    """Steps in one Period, from its interval: 92, 96 or 100 at PT15M."""
    def utc(s):
        s = s.strip()
        return dt.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith("Z") else s)
    hours = (utc(end) - utc(start)).total_seconds() / 3600
    return round(hours / RES_HOURS[resolution])


def check_stage2_direction(rows, xml_text: str) -> tuple[bool, str]:
    """Does every row carry the direction of the element its series came from?

    Read straight from the XML: a series named by inBiddingZone_Domain is
    generation, one named by outBiddingZone_Domain is consumption (pumping,
    battery charging). Per (zone, psr, direction), the steps its Periods
    declare must equal the parsed rows. A parser that summed a consumption
    leg into generation, dropped one, or swapped the two fails here.

    Until 17.10.2026 this checked only that B10 rows carried one of the two
    labels, which the parser could not fail to emit (audit A10). Before that
    it demanded both directions for B10, which a pump-only window does not
    have.
    """
    root = ET.fromstring(re.sub(r"<script[^>]*/>|<script.*?</script>", "", xml_text, flags=re.S))
    uri = root.tag[1:].partition("}")[0] if root.tag.startswith("{") else ""

    def q(*names):
        return "/".join(f"{{{uri}}}{n}" for n in names)

    expected = Counter()
    for ts in root.findall(q("TimeSeries")):
        psr = ts.findtext(q("MktPSRType", "psrType"))
        inz = ts.findtext(q("inBiddingZone_Domain.mRID"))
        outz = ts.findtext(q("outBiddingZone_Domain.mRID"))
        if (inz is None) == (outz is None):
            return False, f"{psr}: a series must name exactly one of in/outBiddingZone_Domain"
        key = (inz, psr, "generation") if inz is not None else (outz, psr, "consumption")
        for per in ts.findall(q("Period")):
            res = per.findtext(q("resolution"))
            if res not in RES_HOURS:
                return False, f"{psr}: unknown resolution {res!r} in the XML"
            expected[key] += _xml_steps(per.findtext(q("timeInterval", "start")),
                                        per.findtext(q("timeInterval", "end")), res)
    if not expected:
        return False, "the XML holds no TimeSeries"
    got = Counter((r.get("zone"), r["psr"], r["direction"]) for r in rows)
    if got != expected:
        diff = {f"{z} {p} {d}": f"{got.get((z, p, d), 0)} rows, XML {expected.get((z, p, d), 0)}"
                for (z, p, d) in sorted(set(got) | set(expected), key=str)
                if got.get((z, p, d), 0) != expected.get((z, p, d), 0)}
        return False, f"rows by direction differ from the XML elements: {diff}"
    legs = sorted(f"{z} {p}" for (z, p, d) in expected if d == "consumption")
    return True, (f"{len(expected)} series match the XML by direction; "
                  f"consumption legs: {', '.join(legs) or 'none'}")


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
    in config/sparse_series.csv); a missing step there is zero output.
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


def load_coverage_policy(sparse_csv=None, gaps_csv=None) -> tuple[frozenset, dict]:
    """(sparse, known) for check_stage3_coverage, from the two config files.

    sparse: series a zone publishes only while a unit runs, from
        config/sparse_series.csv.
    known: recorded source gaps, from config/source_gaps.csv.
    The dbt coverage test reads the same two files.
    """
    import csv
    from pathlib import Path
    config = Path(__file__).resolve().parents[2] / "config"
    with Path(sparse_csv or config / "sparse_series.csv").open(newline="", encoding="utf-8") as fh:
        sparse = frozenset((row["zone_eic"], row["psr"]) for row in csv.DictReader(fh))
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


def incomplete_steps(rows, sparse=frozenset()) -> set:
    """(zone, ts_utc) steps at which a series the zone publishes is missing.

    A series counts once it appears anywhere in the rows. Series in `sparse`,
    published only while a unit runs, are exempt, as in stage 3: their absence
    is zero output. At any other missing series the mix is partial -- a
    recorded source gap, say -- and an intensity computed from it is biased by
    whatever is absent, so it is withheld.
    """
    present, series = defaultdict(set), defaultdict(set)
    for r in rows:
        if r["direction"] != "generation":
            continue
        present[(r.get("zone"), r["ts_utc"])].add(r["psr"])
        series[r.get("zone")].add(r["psr"])
    need = {z: {p for p in ps if (z, p) not in sparse} for z, ps in series.items()}
    return {k for k, ps in present.items() if not need[k[0]] <= ps}


def check_stage5_intensity(rows, factors: dict, values: dict,
                           sparse=frozenset(), rel_tol: float = 1e-9) -> tuple[bool, str]:
    """Is every reported intensity the energy-weighted mean of a complete mix?

    values: {(zone, ts_utc): gCO2e/kWh, or None where withheld}, one entry per
    generation step of `rows`. The check recomputes each step here, from the
    rows and the median factors, and fails on
      - a step without an entry, or an entry without a step;
      - a reported value at an incomplete step (see incomplete_steps), or a
        withheld value at a complete step with priced energy;
      - a value that differs from the recomputed mean: MWh on one side of
        the ratio and MW on the other, a consumption leg in the mix, a
        factor other than the median;
      - negative or missing generation energy, and series at different
        resolutions sharing a step, where a per-step mix would put a whole
        hour of energy into one quarter-hour.

    It replaces check_stage5_plausibility. Its 0-1000 bounds could not see a
    units error: a weighted mean is unchanged when every weight is scaled,
    and MWh on one side only scales the result by the step length, which at
    PT15M lands well inside 0-1000 (audit A10).
    """
    mixes, steps, bad_energy = defaultdict(dict), defaultdict(set), 0
    for r in rows:
        if r["direction"] != "generation":
            continue
        if r["mwh"] is None or r["mwh"] < 0:
            bad_energy += 1
            continue
        k = (r.get("zone"), r["ts_utc"])
        mixes[k][r["psr"]] = mixes[k].get(r["psr"], 0.0) + r["mwh"]
        steps[k].add(r["step_hours"])
    problems = []
    if bad_energy:
        problems.append(f"{bad_energy} generation rows with negative or missing energy")
    mixed = sorted(k for k, s in steps.items() if len(s) > 1)
    if mixed:
        problems.append(f"{len(mixed)} steps where series of different resolution meet, "
                        f"first {mixed[0]}; resample before mixing")
    missing = sorted(set(mixes) - set(values))
    extra = sorted(set(values) - set(mixes))
    if missing:
        problems.append(f"{len(missing)} steps without a value, first {missing[0]}")
    if extra:
        problems.append(f"{len(extra)} values for steps the rows do not have, first {extra[0]}")

    partial = incomplete_steps(rows, sparse)
    reported_partial = sorted(k for k in partial if values.get(k) is not None)
    if reported_partial:
        problems.append(f"{len(reported_partial)} values reported from a partial mix, "
                        f"first {reported_partial[0]}; withhold them")
    wrong, withheld, priced_tot, energy_tot = [], [], defaultdict(float), defaultdict(float)
    for k in sorted(set(mixes) & set(values)):
        mix = mixes[k]
        priced = {p: e for p, e in mix.items() if p in factors and factors[p].priced}
        energy_tot[k[0]] += sum(mix.values())
        priced_tot[k[0]] += sum(priced.values())
        if k in partial:
            continue
        tot = sum(priced.values())
        want = sum(e * factors[p].median for p, e in priced.items()) / tot if tot > 0 else None
        got = values[k]
        if want is None and got is not None:
            wrong.append((k, got, "no priced energy"))
        elif want is not None and got is None:
            withheld.append(k)
        elif want is not None and not math.isclose(got, want, rel_tol=rel_tol, abs_tol=1e-9):
            wrong.append((k, got, round(want, 3)))
    if withheld:
        problems.append(f"{len(withheld)} complete steps withheld, first {withheld[0]}")
    if wrong:
        problems.append(f"{len(wrong)} values differ from the median-factor mean of their mix, "
                        f"first {wrong[0]} (got, expected)")
    if problems:
        return False, "; ".join(problems)
    shown = [v for v in values.values() if v is not None]
    share = ", ".join(f"{z} {priced_tot[z] / energy_tot[z]:.1%}" for z in sorted(energy_tot, key=str)
                      if energy_tot[z] > 0)
    rng = f"range {min(shown):.0f}-{max(shown):.0f} gCO2e/kWh; " if shown else ""
    return True, (f"{len(shown)} steps equal the median-factor mean of a complete mix; "
                  f"{len(partial)} withheld from a partial mix; {rng}priced share of energy: {share}")
