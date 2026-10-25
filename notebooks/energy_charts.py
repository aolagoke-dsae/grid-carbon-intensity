# %% [markdown]
# # Hour by hour against Energy-Charts, Germany 2024–2025
#
# RUNBOOK Checkpoint 5 asks for our series to be set against an independent
# one. Electricity Maps' hourly series is not open to a public repository
# (docs/EM_CROSSCHECK.md); Fraunhofer ISE's Energy-Charts is, under CC BY 4.0.
# It publishes Germany's public net electricity generation by source every
# quarter-hour, compiled from ENTSO-E, EEX transparency data and its own
# estimates. It publishes no carbon intensity, so both mixes are priced with
# our factors, and any difference is the generation data's.
#
# Energy-Charts covers Germany alone, so it is set against our ENTSO-E parse of
# Germany alone, `10Y1001A1001A83F`, pulled for this and for rule 5 of
# `em_crosscheck.py`. "Public net" leaves out what industry generates for its
# own use, which ENTSO-E may count; the energy by fuel shows where they part.
#
# ## The rule, fixed on 25.10.2026, before either source was pulled
#
# 1. **Hours.** Both are summed to UTC hours. An hour enters only if it is
#    complete in both. On the ENTSO-E side, no quarter-hour of it is withheld
#    (`incomplete_steps`) and steps are stated for the whole hour. On the
#    Energy-Charts side, every series that states at least 95% of the year's
#    quarter-hours states all four; a series stated less often counts as zero
#    where it is absent.
# 2. **One factor set.** Each hour's intensity is computed from each source's
#    mix with our median factors over the fuels we price, as Checkpoint 5
#    computes it, so the factors cannot make a difference.
# 3. **Verdict, per year.** The two hourly series agree if they correlate at
#    r ≥ 0.98, correlate best unshifted (against shifts of one and two hours
#    either way), and their plain means differ by at most 3%. A series
#    shifted by one hour against itself still correlates at about 0.98, as a
#    test on our own data showed before the pull, so the correlation alone
#    cannot see a misjoined hour; the shift can. If they align and correlate
#    but the means differ by more, they have the same shape at a different
#    level, and the energy by fuel says which fuels make the difference.
#    Otherwise they disagree hour by hour, and nothing built on our hours is
#    trusted until that is explained.
#
# Translating Energy-Charts' series names into PsrTypes is not part of the
# rule. A name the map below does not know stops the run, and the map is
# completed from the first response, before any comparison is made.
#
# Run from the repository root: `python notebooks/energy_charts.py`, after
# `python -m src.ingest.energycharts_client 2024 2025` and the A75 pull of
# `10Y1001A1001A83F` (RUNBOOK, Checkpoint 5). Data: Energy-Charts.info,
# Fraunhofer ISE, CC BY 4.0.

# %%
from __future__ import annotations

import datetime as dt
import json
import os
import statistics
import sys
import zoneinfo
from collections import defaultdict
from pathlib import Path

ROOT = Path.cwd()
if ROOT.name == "notebooks":
    ROOT = ROOT.parent
    os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from src.checks.validate import incomplete_steps, load_coverage_policy  # noqa: E402
from src.ingest import raw_store  # noqa: E402
from src.transform.entsoe_parse import parse  # noqa: E402
from src.transform.intensity import energy_by_fuel, load_factors  # noqa: E402
from src.transform.xml_to_parquet import current_payloads  # noqa: E402

DE_ALONE = "10Y1001A1001A83F"
YEARS = (2024, 2025)
UTC = dt.timezone.utc
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")
R_MIN, MEAN_GAP = 0.98, 0.03        # rule 3
SHIFTS = (-2, -1, 0, 1, 2)          # rule 3, hours
REGULAR = 0.95                      # rule 1, Energy-Charts side
A75 = ROOT / "raw" / "A75"
EC = ROOT / "raw" / "ENERGYCHARTS" / "public_power" / "de"

# Energy-Charts series name, in lower case -> PsrType.
EC_PSR = {
    "biomass": "B01", "fossil brown coal / lignite": "B02", "fossil coal-derived gas": "B03",
    "fossil gas": "B04", "fossil hard coal": "B05", "fossil oil": "B06", "geothermal": "B09",
    "hydro pumped storage": "B10", "hydro run-of-river": "B11", "hydro water reservoir": "B12",
    "nuclear": "B14", "solar": "B16", "waste": "B17", "wind offshore": "B18",
    "wind onshore": "B19", "others": "B20",
}
# Series that are not generation by fuel.
EC_IGNORE = {"hydro pumped storage consumption", "cross border electricity trading",
             "load", "load (incl. self-consumption)", "residual load",
             "renewable share of generation", "renewable share of load"}
OURS = {p: f.median for p, f in load_factors(ROOT / "config" / "ipcc_ar5_factors.csv").items()
        if f.priced}
SPARSE, _ = load_coverage_policy()

missing = [f"A75 {DE_ALONE} {y}" for y in YEARS if not (A75 / DE_ALONE / str(y)).is_dir()]
missing += [f"Energy-Charts {y}-{m:02d}" for y in YEARS for m in range(1, 13)
            if raw_store.current_version(EC / f"{y}-{m:02d}.json") is None]
if missing:
    print(f"Not pulled yet: {', '.join(missing[:4])}{' …' if len(missing) > 4 else ''} "
          f"({len(missing)} items). The rule waits for them.")
    raise SystemExit(0)


# %%
def entsoe_hours(year: int) -> dict:
    """Complete UTC hours of our A75 parse of Germany alone: {hour: {psr: MWh}}."""
    xml = [p for p in current_payloads(A75) if p.parent == A75 / DE_ALONE / str(year)][0]
    rows = parse(xml.read_text(encoding="utf-8"))
    partial = incomplete_steps(rows, SPARSE)
    length = {(r["zone"], r["ts_utc"]): r["step_hours"] for r in rows if r["direction"] == "generation"}
    energy, stated, withheld = defaultdict(lambda: defaultdict(float)), defaultdict(float), set()
    for key, mix in energy_by_fuel(rows).items():
        hour = key[1].replace(minute=0)
        stated[hour] += length[key]
        if key in partial:
            withheld.add(hour)
        for psr, mwh in mix.items():
            energy[hour][psr] += mwh
    print(f"ENTSO-E {year}: {xml.relative_to(ROOT).as_posix()}")
    return {h: dict(m) for h, m in energy.items()
            if h not in withheld and abs(stated[h] - 1.0) < 1e-9}


def ec_hours(year: int) -> dict:
    """Complete UTC hours of Energy-Charts' public net generation (rule 1)."""
    energy = defaultdict(lambda: defaultdict(float))
    stated = defaultdict(lambda: defaultdict(set))     # hour -> psr -> intervals stated
    per_series, quarters, unknown, units = defaultdict(set), set(), set(), set()
    for month in range(1, 13):
        path = raw_store.current_version(EC / f"{year}-{month:02d}.json")
        doc = json.loads(path.read_text(encoding="utf-8"))
        names = {s["id"]: s["name"] for s in doc["series"]}
        units.add((doc.get("unit"), doc.get("interval_minutes")))
        step = doc["interval_minutes"] / 60
        for point in doc["data"]:
            t = dt.datetime.fromisoformat(point["timestamp"]).astimezone(UTC)
            if t.astimezone(BERLIN).year != year:
                continue                # outside the local year, at either end
            quarters.add(t)
            for sid, mw in point["values"].items():
                name = names.get(sid, sid).strip().lower()
                if name in EC_IGNORE:
                    continue
                psr = EC_PSR.get(name)
                if psr is None:
                    unknown.add(names.get(sid, sid))
                    continue
                if mw is None:
                    continue
                energy[t.replace(minute=0)][psr] += mw * step
                stated[t.replace(minute=0)][psr].add(t)
                per_series[psr].add(t)
    if unknown:
        raise SystemExit(f"Energy-Charts series the map does not know: {sorted(unknown)}")
    intervals = {i for _, i in units}
    assert len(intervals) == 1 and {u for u, _ in units} <= {"MW", None}, units
    print(f"Energy-Charts {year}: {len(quarters):,} intervals of {intervals.pop()} minutes, MW")
    regular = {p for p, ts in per_series.items() if len(ts) >= REGULAR * len(quarters)}
    per_hour = round(1 / step)          # intervals in an hour
    return {h: dict(m) for h, m in energy.items()
            if all(len(stated[h].get(p, ())) == per_hour for p in regular)}


def intensity(mix: dict) -> tuple[float | None, float, float]:
    """(gCO2e/kWh, kg, MWh) at our median factors over the fuels we price."""
    e = {p: v for p, v in mix.items() if p in OURS}
    mwh = sum(e.values())
    kg = sum(v * OURS[p] for p, v in e.items())
    return (kg / mwh if mwh > 0 else None), kg, mwh


def shifted_r(pairs_a: dict, pairs_b: dict, shift: int) -> float:
    """r between our hour h and Energy-Charts' hour h + shift."""
    hours = [h for h in pairs_a if h + dt.timedelta(hours=shift) in pairs_b]
    return statistics.correlation([pairs_a[h] for h in hours],
                                  [pairs_b[h + dt.timedelta(hours=shift)] for h in hours])


# %%
RESULT = {}
for year in YEARS:
    ours, theirs = entsoe_hours(year), ec_hours(year)
    both = sorted(h for h in set(ours) & set(theirs)
                  if intensity(ours[h])[0] is not None and intensity(theirs[h])[0] is not None)
    a = [intensity(ours[h])[0] for h in both]
    b = [intensity(theirs[h])[0] for h in both]
    r = statistics.correlation(a, b)
    gap = statistics.fmean(b) / statistics.fmean(a) - 1
    by_shift = {k: shifted_r(dict(zip(both, a)), dict(zip(both, b)), k) for k in SHIFTS}
    aligned = max(by_shift, key=by_shift.get) == 0
    if aligned and r >= R_MIN and abs(gap) <= MEAN_GAP:
        verdict = "agree"
    elif aligned and r >= R_MIN:
        verdict = "same shape, different level"
    else:
        verdict = "disagree hour by hour"
    RESULT[year] = {"ours": ours, "theirs": theirs, "both": both, "a": a, "b": b}
    print(f"\n{year}: {len(both):,} hours complete in both ({len(ours):,} ENTSO-E, "
          f"{len(theirs):,} Energy-Charts); mean {statistics.fmean(a):.1f} ENTSO-E, "
          f"{statistics.fmean(b):.1f} Energy-Charts, {100 * gap:+.1f}%; r = {r:.4f}; "
          f"mean absolute difference {statistics.fmean(abs(x - y) for x, y in zip(a, b)):.1f} "
          f"gCO2e/kWh; r by shift " + ", ".join(f"{k:+d} h {v:.4f}" for k, v in by_shift.items())
          + f". Rule 3: {verdict}.")


# %% [markdown]
# ## Beyond the rule, descriptive only
#
# Where the two sources part: energy by fuel over the hours complete in both.

# %%
for year in YEARS:
    res = RESULT[year]
    tot = {s: defaultdict(float) for s in ("ours", "theirs")}
    for h in res["both"]:
        for s in tot:
            for p, v in res[s][h].items():
                tot[s][p] += v
    print(f"\n{year}, energy over the hours complete in both, TWh")
    print("| PsrType | Priced by us | ENTSO-E | Energy-Charts | Difference |")
    print("|---|---|---:|---:|---:|")
    for p in sorted(set(tot["ours"]) | set(tot["theirs"]), key=lambda p: -tot["ours"].get(p, 0.0)):
        x, y = tot["ours"].get(p, 0.0) / 1e6, tot["theirs"].get(p, 0.0) / 1e6
        diff = f"{100 * (y / x - 1):+.1f}%" if x > 0.01 else "–"
        print(f"| {p} | {'yes' if p in OURS else 'no'} | {x:,.2f} | {y:,.2f} | {diff} |")
