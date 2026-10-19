# %% [markdown]
# # Third-zone diagnostic, 2025
#
# Master Plan §2.3. DE-LU and FR differ in two things at once: Germany is both
# higher-carbon and more variable within the day than France, so a result that
# differs between them cannot say which of the two caused it. A third zone is
# added to break that confound, and it is chosen on measurement. For each zone
# in `config/zones.csv`, calendar year 2025 (local), this reports
#
# - the **carbon level**: the mean intensity weighted by priced energy, gCO2e/kWh;
# - the **within-day coefficient of variation** of the hourly intensity, averaged
#   over complete local days. A coefficient of variation, not a standard
#   deviation: a standard deviation grows with the mean and would carry the
#   carbon level back into a measure meant to isolate variability;
# - the **priced share** of generation: a candidate qualifies only if its share
#   is comparable to DE-LU's, or the intensities rest on different fractions of
#   generation;
# - what the parser met: rows, PsrType codes, codes missing from the PSR map,
#   and any step stated twice (§2.3, half one).
#
# Read from `raw/` directly. The three candidates are not landed
# (`xml_to_parquet` skips zones outside the analysis), so nothing here touches
# the warehouse. Intensities use the median factors of
# `config/ipcc_ar5_factors.csv`, one table for every zone: Polish and Dutch coal
# carry Germany's lignite and hard-coal values, which Itten et al. (2023, Fig.
# 4.5) put close to Poland's own (1.09 and 1.12 against 1.06 and 1.04).
#
# An hour is complete when every series the zone states in at least 95% of its
# hours is stated for the whole hour; series stated less often count as zero
# when absent. All three numbers are computed over complete hours, and only
# complete local days enter the coefficient of variation.
#
# ## The choice rule, fixed on 19.10.2026, before PL, NL and IE-SEM were pulled
#
# 1. **Comparable coverage.** A candidate qualifies if its priced share is at
#    least DE-LU's minus 5 percentage points, and if at least 300 of its local
#    days are complete, so its coefficient of variation is a year's average and
#    not a season's. A candidate that misses the share on one fuel a cited
#    factor could price is reported as such rather than dropped (§2.3).
# 2. **The plane.** Each zone is placed relative to the pair:
#    u = (L − L_FR) / (L_DE − L_FR) for the level and
#    v = (C − C_FR) / (C_DE − C_FR) for the mean within-day CV, so FR sits at
#    (0, 0) and DE-LU at (1, 1). The confound is the diagonal u = v, on which
#    level and variability move together. A zone breaks it to the degree it sits
#    off that diagonal, |u − v|, which is twice the area of the triangle the
#    three zones span: zero when they are collinear and level and variability
#    cannot be told apart, larger the better a comparison of the three can
#    separate them. The qualifying candidate with the largest |u − v| is chosen.
#    u > v is the side §2.3 expected Poland on (dirtier than it is variable);
#    u < v is the other (more variable than it is dirty).
# 3. **Close calls.** If the two best qualifying scores differ by less than 0.1,
#    the rule does not separate them, and the one with the higher priced share
#    is chosen.
# 4. **Robustness.** The choice is recomputed with the median within-day CV in
#    place of the mean. If it changes, both are reported and the choice is not
#    final.
# 5. **Premise.** If DE-LU is not more variable than FR in CV terms
#    (C_DE ≤ C_FR), the confound does not exist as §2.3 states it, and no zone
#    is chosen until it is restated.
#
# Run from the repository root: `python notebooks/third_zone.py`, and with
# `--sensitivity` for the choice under other factor tables. No token is
# needed; the pulls are a separate step (Master Plan §2.3, RUNBOOK Stage 3).
# Zones not pulled yet are listed as such, and no zone is chosen until all
# three candidates are in. The result, 19.10.2026: `docs/THIRD_ZONE.md`.

# %%
from __future__ import annotations

import csv
import dataclasses
import datetime as dt
import os
import statistics
import sys
import zoneinfo
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path.cwd()
if ROOT.name == "notebooks":
    ROOT = ROOT.parent
    os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

from src.transform.entsoe_parse import PSR, parse  # noqa: E402
from src.transform.intensity import load_factors  # noqa: E402
from src.transform.xml_to_parquet import current_payloads  # noqa: E402

YEAR = 2025
REGULAR = 0.95          # a series stated in at least this share of hours must be there
SHARE_TOLERANCE = 0.05  # rule 1: priced share at least DE-LU's minus 5 points
MIN_DAYS = 300          # rule 1: complete local days
CLOSE_CALL = 0.1        # rule 3
PAIR = ("DE_LU", "FR")
FACTORS = load_factors(ROOT / "config" / "ipcc_ar5_factors.csv")
with (ROOT / "config" / "zones.csv").open(newline="", encoding="utf-8") as fh:
    ZONES = list(csv.DictReader(fh))


# %%
def payload(eic: str, year: int = YEAR) -> Path | None:
    """The newest accepted A75 retrieval of the zone's year, or None."""
    doc_dir = ROOT / "raw" / "A75"
    item = doc_dir / eic / str(year)
    if not item.is_dir():
        return None
    hits = [p for p in current_payloads(doc_dir) if p.parent == item]
    return hits[0] if hits else None


def by_hour(rows: list[dict]):
    """Per UTC hour: generation MWh by fuel, and how much of the hour each
    series states in either leg, so a partial hour can be told apart."""
    energy: dict = defaultdict(lambda: defaultdict(float))
    stated: dict = defaultdict(lambda: defaultdict(float))
    seen = set()
    for r in rows:
        if r["mw"] is None:
            continue
        hour = r["ts_utc"].replace(minute=0, second=0, microsecond=0)
        if (r["psr"], r["ts_utc"]) not in seen:     # a step counts once, either leg
            seen.add((r["psr"], r["ts_utc"]))
            stated[hour][r["psr"]] += r["step_hours"]
        if r["direction"] == "generation":
            energy[hour][r["psr"]] += r["mwh"]
    return energy, stated


def num(x, spec: str, scale: float = 1.0) -> str:
    """Format a measurement, or a dash where the zone has none."""
    return "–" if x is None else format(scale * x, spec)


def load(zone: dict) -> dict:
    """Parse the zone's payload once: the hourly mix over its complete hours,
    and what the parser met. Nothing here depends on the factors."""
    xml = payload(zone["eic"])
    if xml is None:
        return {"zone": zone["key"], "file": None}
    try:
        rows = parse(xml.read_text(encoding="utf-8"))
    except (ValueError, KeyError) as e:     # §2.3, half one: a payload the parser refuses
        return {"zone": zone["key"], "file": xml.relative_to(ROOT).as_posix(),
                "error": f"{type(e).__name__}: {e}"}
    twice = Counter((r["psr"], r["direction"], r["ts_utc"]) for r in rows if r["mw"] is not None)
    energy, stated = by_hour(rows)
    hours = sorted(stated)
    tz = zoneinfo.ZoneInfo(zone["tz"])
    y0 = dt.datetime(YEAR, 1, 1, tzinfo=tz).astimezone(dt.timezone.utc)
    y1 = dt.datetime(YEAR + 1, 1, 1, tzinfo=tz).astimezone(dt.timezone.utc)
    expected = round((y1 - y0).total_seconds() / 3600)     # hours in the local year
    outside = sum(1 for h in hours if not y0 <= h < y1)

    full = defaultdict(int)
    for h in hours:
        for psr, cover in stated[h].items():
            if cover >= 0.999:
                full[psr] += 1
    regular = {p for p, n in full.items() if n >= REGULAR * expected}
    complete = {h for h in hours
                if y0 <= h < y1 and all(stated[h].get(p, 0.0) >= 0.999 for p in regular)}

    codes = sorted({r["psr"] for r in rows})
    return {
        "zone": zone["key"],
        "file": xml.relative_to(ROOT).as_posix(),
        "tz": tz,
        "rows": len(rows),
        "codes": codes,
        "not_in_psr_map": [c for c in codes if c not in PSR],
        "stated_twice": sum(1 for n in twice.values() if n > 1),
        "resolutions": sorted({r["resolution"] for r in rows}),
        "hours": expected,
        "stated_hours": len(hours),
        "outside": outside,
        "complete_hours": len(complete),
        "sparse": sorted(set(full) - regular),
        "twh": sum(sum(energy[h].values()) for h in hours if y0 <= h < y1) / 1e6,
        "mix": {h: dict(energy.get(h, {})) for h in sorted(complete)},
    }


def score(z: dict, factors: dict = FACTORS) -> dict:
    """Level, within-day CV and priced share over the complete hours, under
    one factor table; z as load() returned it, with those added."""
    def priced(psr: str) -> bool:
        return psr in factors and factors[psr].priced

    total = priced_mwh = emissions = 0.0
    unpriced: dict = defaultdict(float)
    hourly: dict = {}
    for h, mix in z["mix"].items():
        p = sum(e for f, e in mix.items() if priced(f))
        em = sum(e * factors[f].median for f, e in mix.items() if priced(f))
        total += sum(mix.values())
        priced_mwh += p
        emissions += em
        for f, e in mix.items():
            if not priced(f):
                unpriced[f] += e
        if p > 0:
            hourly[h] = em / p

    tz = z["tz"]
    days: dict = defaultdict(list)
    for h, v in hourly.items():
        days[h.astimezone(tz).date()].append(v)
    cvs, sds = {}, {}
    for d, vals in days.items():
        start = dt.datetime(d.year, d.month, d.day, tzinfo=tz)
        length = (start + dt.timedelta(days=1)).astimezone(dt.timezone.utc) - start.astimezone(dt.timezone.utc)
        if len(vals) == round(length.total_seconds() / 3600):
            sds[d] = statistics.pstdev(vals)
            cvs[d] = sds[d] / statistics.fmean(vals)
    summer = [c for d, c in cvs.items() if 4 <= d.month <= 9]
    winter = [c for d, c in cvs.items() if not 4 <= d.month <= 9]

    return {
        **z,
        "days": len(cvs),
        "level": emissions / priced_mwh if priced_mwh else None,
        "cv_mean": statistics.fmean(cvs.values()) if cvs else None,
        "cv_median": statistics.median(cvs.values()) if cvs else None,
        "priced_share": priced_mwh / total if total else None,
        "unpriced": sorted(((f, e / total) for f, e in unpriced.items()), key=lambda t: -t[1]),
        "unknown": sorted(f for f in unpriced if f not in factors),
        "sd_mean": statistics.fmean(sds.values()) if sds else None,
        "cv_summer": statistics.fmean(summer) if summer else None,
        "cv_winter": statistics.fmean(winter) if winter else None,
    }


def measure(zone: dict, factors: dict = FACTORS) -> dict:
    z = load(zone)
    return score(z, factors) if "mix" in z else z


# %%
def place(results: dict, cv: str) -> dict:
    """Rule 2: (u, v) relative to the pair, FR at (0, 0) and DE-LU at (1, 1)."""
    de, fr = results[PAIR[0]], results[PAIR[1]]
    span_l, span_c = de["level"] - fr["level"], de[cv] - fr[cv]
    return {
        k: ((r["level"] - fr["level"]) / span_l, (r[cv] - fr[cv]) / span_c)
        for k, r in results.items()
        if r.get("level") is not None and r.get(cv) is not None
    }


def qualifies(r: dict, de: dict) -> list[str]:
    """Rule 1. The reasons a candidate does not qualify; empty if it does."""
    why = []
    share = r["priced_share"]
    if share is None:
        why.append("no generation in complete hours")
    elif share < de["priced_share"] - SHARE_TOLERANCE:
        why.append(f"priced share {100 * share:.1f}% against DE-LU's "
                   f"{100 * de['priced_share']:.1f}%")
    if r["days"] < MIN_DAYS:
        why.append(f"{r['days']} complete days")
    return why


def choose(results: dict, cv: str):
    """Rules 1 to 3 for one CV statistic. Returns (zone or None, scores, note)."""
    de, fr = results[PAIR[0]], results[PAIR[1]]
    if de[cv] <= fr[cv]:
        return None, {}, (f"premise fails: DE-LU's {cv} ({de[cv]:.3f}) is not above "
                          f"FR's ({fr[cv]:.3f}); restate §2.3 before choosing")
    uv = place(results, cv)
    scores = {k: abs(u - v) for k, (u, v) in uv.items() if k not in PAIR}
    eligible = sorted((k for k in scores if not qualifies(results[k], de)),
                      key=lambda k: (-scores[k], k))
    if not eligible:
        return None, scores, "no candidate qualifies"
    best = eligible[0]
    note = ""
    if len(eligible) > 1 and scores[best] - scores[eligible[1]] < CLOSE_CALL:
        runner = eligible[1]
        best = max(best, runner, key=lambda k: results[k]["priced_share"])
        note = (f"close call ({scores[eligible[0]]:.2f} against {scores[eligible[1]]:.2f}); "
                "the higher priced share decides (rule 3)")
    return best, scores, note


# %%
loaded = {z["key"]: load(z) for z in ZONES}
results = {k: score(z) if "mix" in z else z for k, z in loaded.items()}
pulled = [k for k, r in results.items() if r["file"] and "error" not in r]
missing = [z["key"] for z in ZONES if z["key"] not in PAIR and z["key"] not in pulled]

print(f"Third-zone diagnostic, {YEAR}, median factors, complete hours and local days only\n")
print("| Zone | Resolution | Generation in the year, TWh | Complete hours | Days | Level, gCO2e/kWh "
      "| Within-day CV, mean (median) | Priced share | Largest unpriced |")
print("|---|---|---:|---:|---:|---:|---:|---:|---|")
for k, r in results.items():
    if r["file"] is None:
        print(f"| {k} | not pulled | | | | | | | |")
        continue
    if "error" in r:
        print(f"| {k} | parse failed | | | | | | | |")
        continue
    top = ", ".join(f"{f} {100 * s:.1f}%" for f, s in r["unpriced"][:3])
    print(
        f"| {k} | {'/'.join(r['resolutions'])} | {r['twh']:.1f} "
        f"| {100 * r['complete_hours'] / r['hours']:.1f}% of {r['hours']:,} "
        f"| {r['days']} | {num(r['level'], '.0f')} "
        f"| {num(r['cv_mean'], '.3f')} ({num(r['cv_median'], '.3f')}) "
        f"| {num(r['priced_share'], '.1f', 100)}% | {top} |"
    )

print("\nWhat the parser met (§2.3, half one):\n")
for k, r in results.items():
    if "error" in r:
        print(f"- {k}: parse() refused {r['file']}: {r['error']}")
for k in pulled:
    r = results[k]
    print(f"- {k}: {r['rows']:,} rows from {r['file']}; PsrType {', '.join(r['codes'])}; "
          f"not in the PSR map: {', '.join(r['not_in_psr_map']) or 'none'}; "
          f"without a factor row: {', '.join(r['unknown']) or 'none'}; "
          f"stated in under {100 * REGULAR:.0f}% of hours: {', '.join(r['sparse']) or 'none'}; "
          f"hours with any value {r['stated_hours']:,} of {r['hours']:,}, "
          f"outside the local year {r['outside']}; steps stated twice: {r['stated_twice']}")

print("\nBeyond the rule, descriptive only: the absolute spread, and the CV by half-year\n")
print("| Zone | Mean within-day SD, gCO2e/kWh | CV, April–September | CV, October–March |")
print("|---|---:|---:|---:|")
for k in pulled:
    r = results[k]
    print(f"| {k} | {num(r['sd_mean'], '.1f')} | {num(r['cv_summer'], '.3f')} "
          f"| {num(r['cv_winter'], '.3f')} |")

# %%
if all(k in pulled for k in PAIR):
    uv = place(results, "cv_mean")
    print("\nThe plane (rule 2), mean CV: FR at (0, 0), DE-LU at (1, 1)\n")
    print("| Zone | u, level | v, variability | abs(u − v) | Qualifies |")
    print("|---|---:|---:|---:|---|")
    for k, (u, v) in uv.items():
        why = "pair" if k in PAIR else ("; ".join(qualifies(results[k], results[PAIR[0]])) or "yes")
        print(f"| {k} | {u:.2f} | {v:.2f} | {abs(u - v):.2f} | {why} |")
    for k in pulled:
        if k not in uv:
            print(f"| {k} | – | – | – | no complete hours or days to place |")

    if missing:
        print(f"\nNo choice yet: {', '.join(missing)} not pulled or not parsed.")
    else:
        best, _, note = choose(results, "cv_mean")
        check, _, check_note = choose(results, "cv_median")
        print(f"\nChoice (rules 1 to 3, mean CV): {best or 'none'}{'; ' + note if note else ''}")
        print(f"Robustness (rule 4, median CV): {check or 'none'}{'; ' + check_note if check_note else ''}")
        if best != check:
            print("The two disagree: report both; the choice is not final.")

# %% [markdown]
# ## Sensitivity to the factors (run with `--sensitivity`)
#
# The same rule under three other factor tables: every priced factor at the
# low end of its band, every one at the high end, and PL's lignite and hard
# coal at Poland's own values in Itten et al. (2023, Fig. 4.5), read off the
# figure like Germany's (`docs/FACTOR_CHECK.md`, decision 1). The band ends
# move every zone at once, so they test the plane, not one zone.

# %%
POLAND = {"B02": 1094.0, "B05": 1115.0}     # Itten et al. 2023, Fig. 4.5, Poland


def swapped(pick) -> dict:
    """The factor table with every priced median replaced by pick(psr, factor)."""
    return {k: dataclasses.replace(f, median=pick(k, f)) if f.priced else f
            for k, f in FACTORS.items()}


if "--sensitivity" in sys.argv and all(k in pulled for k in PAIR) and not missing:
    low, high = swapped(lambda k, f: f.lo), swapped(lambda k, f: f.hi)
    poland = swapped(lambda k, f: POLAND.get(k, f.median))
    variants = {
        "medians (the result)": lambda key: FACTORS,
        "every factor at its band minimum": lambda key: low,
        "every factor at its band maximum": lambda key: high,
        "PL's coal at Poland's own values": lambda key: poland if key == "PL" else FACTORS,
    }
    candidates = [k for k in pulled if k not in PAIR]
    print("\nSensitivity: the rule under other factor tables\n")
    print("| Factors | " + " | ".join(f"{k}: level, CV, abs(u − v)" for k in candidates)
          + " | Choice, mean CV | Choice, median CV |")
    print("|---|" + "---:|" * len(candidates) + "---|---|")
    for name, table in variants.items():
        res = {k: score(z, table(k)) for k, z in loaded.items() if k in pulled}
        uv = place(res, "cv_mean")
        cells = [f"{num(res[k]['level'], '.0f')}, {num(res[k]['cv_mean'], '.3f')}, "
                 f"{abs(uv[k][0] - uv[k][1]):.2f}" if k in uv else "–" for k in candidates]
        print(f"| {name} | " + " | ".join(cells)
              + f" | {choose(res, 'cv_mean')[0] or 'none'} | {choose(res, 'cv_median')[0] or 'none'} |")
