# %% [markdown]
# # Cross-check against Electricity Maps, DE-LU 2024–2025
#
# RUNBOOK Checkpoint 5: cross-check against an independent published series,
# "Expect a difference … The difference comes from imports and from the
# factor sets. Document the difference and explain it."
#
# What is accessible. Electricity Maps sells its hourly series, and neither
# its free CSV allowance nor its academic access fits a public repository
# (RUNBOOK, 25.10.2026). Two things are public:
#
# - **Its method for Germany**, open source in electricitymaps-contrib
#   (AGPL-3.0; values cited here, no code copied). Germany's generation comes
#   from ENTSO-E, as ours does (`DATA_SOURCES.md`). Its ENTSO-E parser maps
#   each PsrType to a production mode, and `config/zones/DE.yaml`, with
#   `config/defaults.yaml` where DE has no entry, gives each mode's
#   life-cycle factor by year.
# - **Its results for Germany**, on the Grid in Review 2025 page: the mean
#   intensity of 2024 and 2025, production-based and flow-traced; the lowest
#   and highest hour and day of each year; and the peak and trough of each
#   season's mean day in 2025. Flow-traced figures count imports. The page
#   says neither which time zone its hours are in nor which factors it uses;
#   life-cycle is Electricity Maps' default.
#
# The like-for-like comparison is therefore with their production-based
# mean. Three versions of our intensity, hour by hour, from one parse:
#
# - **A, ours**: our median factors over the fuels we price, as Checkpoint 5
#   computes it;
# - **B, their factors**: their factors on the same fuels, so B − A is the
#   factor set;
# - **C, their factors and coverage**: their factors on everything their
#   parser counts as production, adding waste (as biomass), other and other
#   renewable (as unknown), oil and storage discharge, so C − B is the
#   coverage, and C is the counterpart of their production-based series.
#
# ## The rule, fixed on 25.10.2026, before anything here was run
#
# 1. **Hours.** Quarter-hours are summed to UTC hours. An hour enters only if
#    it is complete: no quarter-hour of it withheld (`incomplete_steps`), and
#    steps stated for the whole hour.
# 2. **Means.** A year's mean is the plain mean of its hourly intensities.
#    The energy-weighted mean is reported beside it, since the page does not
#    say which it uses.
# 3. **Like for like.** C agrees with their production-based mean if it lies
#    within ±2% of it, in 2024 and in 2025. Then our generation data and theirs
#    agree, and the gap between A and their flow-traced mean splits into the
#    factor set (B − A), the coverage (C − B), a residual (their
#    production-based mean − C) and imports (their flow-traced minus their
#    production-based mean, as they publish it). If C misses in either year,
#    the generation data disagree, and that is investigated before anything
#    is explained.
# 4. **The handful of hours.** For their extreme hours and days, and the
#    peaks and troughs of their 2025 seasonal days, A, B and C are reported
#    beside their value, each time read both as local time and as UTC. No
#    threshold: these figures are flow-traced, so imports are part of every
#    difference, which is explained, not tested.
#
# Run from the repository root: `python notebooks/em_crosscheck.py`. It needs
# the 2024 and 2025 DE-LU A75 payloads in `raw/`. No token, no account.

# %%
from __future__ import annotations

import datetime as dt
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
from src.transform.entsoe_parse import parse  # noqa: E402
from src.transform.intensity import energy_by_fuel, load_factors  # noqa: E402
from src.transform.xml_to_parquet import current_payloads  # noqa: E402

EIC = "10Y1001A1001A82H"                  # DE-LU; theirs is Germany, 10Y1001A1001A83F
YEARS = (2024, 2025)
UTC = dt.timezone.utc
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")
TOLERANCE = 0.02                          # rule 3

# Their mapping of PsrType to production mode: electricitymaps-contrib,
# electricitymap/contrib/parsers/ENTSOE.py, ENTSOE_PARAMETER_GROUPS, read on
# 25.10.2026. B10 and B25 are storage there; the generation leg is discharge.
MODE = {"B01": "biomass", "B17": "biomass",
        "B02": "coal", "B05": "coal", "B07": "coal", "B08": "coal",
        "B03": "gas", "B04": "gas", "B06": "oil", "B09": "geothermal",
        "B11": "hydro", "B12": "hydro", "B14": "nuclear", "B16": "solar",
        "B18": "wind", "B19": "wind", "B13": "unknown", "B15": "unknown", "B20": "unknown",
        "B10": "hydro discharge", "B25": "battery discharge"}

# Their life-cycle factors for Germany, gCO2eq/kWh, read on 25.10.2026 from
# config/zones/DE.yaml, and from config/defaults.yaml for geothermal, unknown
# and battery discharge. Their sources: coal, gas and oil "EU-ETS 2025,
# ENTSO-E {year}; IPCC 2014"; hydro and nuclear "UNECE 2022"; solar "INCER
# ACV"; wind "UNECE 2022, WindEurope"; biomass "BEIS 2021; IPCC 2014";
# geothermal "IPCC 2014"; unknown "assumes thermal"; hydro discharge
# "Electricity Maps, {year} zone average"; battery discharge, the
# consumption-weighted mean across their zones in charging hours.
EM_FACTORS = {
    2024: {"coal": 1140.4, "gas": 520.79, "oil": 1113.31,
           "hydro discharge": 250.83, "battery discharge": 382.58},
    2025: {"coal": 1112.69, "gas": 502.97, "oil": 1070.11,
           "hydro discharge": 246.07, "battery discharge": 358.44},
}
for _f in EM_FACTORS.values():
    _f.update({"biomass": 230.0, "geothermal": 38.0, "hydro": 10.7, "nuclear": 5.13,
               "solar": 35.11666667, "wind": 12.62, "unknown": 700.0})

# Their published figures for Germany, gCO2eq/kWh: Electricity Maps, Grid in
# Review 2025: Germany, read on 25.10.2026. Times as printed there.
EM_MEAN = {2024: {"production-based": 367.8, "flow-traced": 334.5},
           2025: {"production-based": 362.5, "flow-traced": 335.4}}
EM_HOURS = [("lowest hour", "2024-08-23 10:00", 112.2), ("highest hour", "2024-12-28 01:00", 651.1),
            ("lowest hour", "2025-10-26 09:00", 97.0), ("highest hour", "2025-03-24 02:00", 632.7)]
EM_DAYS = [("lowest day", "2024-09-27", 145.5), ("highest day", "2024-01-11", 589.1),
           ("lowest day", "2025-10-04", 111.3), ("highest day", "2025-02-02", 559.6)]
EM_SEASONS = {"winter": ((12, 1, 2), (408, 15), (349, 11)),     # (months, peak @ h, trough @ h)
              "spring": ((3, 4, 5), (410, 2), (198, 11)),
              "summer": ((6, 7, 8), (376, 20), (155, 11)),
              "fall": ((9, 10, 11), (376, 17), (257, 11))}

OURS = {p: f.median for p, f in load_factors(ROOT / "config" / "ipcc_ar5_factors.csv").items()
        if f.priced}
SPARSE, _ = load_coverage_policy()


# %%
def complete_hours(year: int, eic: str = EIC) -> tuple[Path, dict, int]:
    """The year's complete UTC hours, {hour: {psr: MWh}}, and how many hours
    the payload states at all (rule 1)."""
    a75 = ROOT / "raw" / "A75"
    xml = [p for p in current_payloads(a75) if p.parent == a75 / eic / str(year)][0]
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
    unmapped = {p for m in energy.values() for p in m} - set(MODE)
    assert not unmapped, f"PsrTypes their parser does not map: {unmapped}"
    hours = {h: dict(m) for h, m in energy.items()
             if h not in withheld and abs(stated[h] - 1.0) < 1e-9}
    return xml, hours, len(energy)


def weighted(mix: dict, ef: dict) -> tuple[float | None, float, float]:
    """(intensity, emissions in kg, energy in MWh) over the fuels ef prices."""
    e = {p: v for p, v in mix.items() if p in ef}
    mwh = sum(e.values())
    kg = sum(v * ef[p] for p, v in e.items())
    return (kg / mwh if mwh > 0 else None), kg, mwh


def versions(year: int) -> dict:
    """The factor sets of A, B and C for one year."""
    em = EM_FACTORS[year]
    return {"A": OURS,
            "B": {p: em[MODE[p]] for p in OURS},
            "C": {p: em[m] for p, m in MODE.items()}}


DATA = {}
for year in YEARS:
    xml, hours, stated = complete_hours(year)
    sets = versions(year)
    per_hour = {v: {h: weighted(m, ef) for h, m in hours.items()} for v, ef in sets.items()}
    DATA[year] = {"hours": hours, "per_hour": per_hour, "sets": sets}
    print(f"{year}: {xml.relative_to(ROOT).as_posix()}, {len(hours):,} complete hours of "
          f"{stated:,} stated")


# %%
def plain(series: dict) -> float:
    return statistics.fmean(i for i, _, _ in series.values() if i is not None)


def energy_weighted(series: dict) -> float:
    return sum(kg for _, kg, _ in series.values()) / sum(mwh for _, _, mwh in series.values())


print("\nMean intensity, gCO2eq/kWh: plain mean of hours (energy-weighted in brackets)\n")
print("| Year | A, ours | B, their factors | C, their factors and coverage "
      "| Theirs, production-based | C against it | Theirs, flow-traced |")
print("|---|---:|---:|---:|---:|---:|---:|")
verdict = {}
for year in YEARS:
    ph = DATA[year]["per_hour"]
    m = {v: (plain(ph[v]), energy_weighted(ph[v])) for v in "ABC"}
    prod, flow = EM_MEAN[year]["production-based"], EM_MEAN[year]["flow-traced"]
    rel = m["C"][0] / prod - 1
    verdict[year] = abs(rel) <= TOLERANCE
    DATA[year]["means"] = m
    print(f"| {year} | " + " | ".join(f"{m[v][0]:.1f} ({m[v][1]:.1f})" for v in "ABC")
          + f" | {prod} | {100 * rel:+.1f}% | {flow} |")

print()
for year in YEARS:
    m, em = DATA[year]["means"], EM_MEAN[year]
    print(f"{year}, plain means: A {m['A'][0]:.1f} → factor set {m['B'][0] - m['A'][0]:+.1f} → "
          f"coverage {m['C'][0] - m['B'][0]:+.1f} → residual {em['production-based'] - m['C'][0]:+.1f} "
          f"→ their production-based {em['production-based']} → imports "
          f"{em['flow-traced'] - em['production-based']:+.1f} → their flow-traced {em['flow-traced']}")
print("\nRule 3: " + "; ".join(f"{y} {'within' if ok else 'outside'} ±{100 * TOLERANCE:.0f}%"
                              for y, ok in verdict.items())
      + (". Our generation data and theirs agree." if all(verdict.values())
         else ". The generation data disagree; investigate before explaining."))


# %% [markdown]
# ## Where the factor set and the coverage come from
#
# Energy-weighted, the differences split exactly by fuel: B − A is the sum of
# each priced fuel's share times the difference of the factors, and C − B the
# sum, over what only they price, of its share of all generation times the
# distance of its factor from B.

# %%
for year in YEARS:
    hours, sets = DATA[year]["hours"], DATA[year]["sets"]
    total = defaultdict(float)
    for mix in hours.values():
        for p, v in mix.items():
            total[p] += v
    all_mwh = sum(total.values())
    priced_mwh = sum(v for p, v in total.items() if p in OURS)
    b_w = DATA[year]["means"]["B"][1]
    print(f"\n{year}: {all_mwh / 1e6:,.1f} TWh generated in complete hours, "
          f"{100 * priced_mwh / all_mwh:.1f}% priced by us")
    print("| PsrType | Share of generation | Ours | Theirs | Mode | Contribution |")
    print("|---|---:|---:|---:|---|---:|")
    for p in sorted(total, key=lambda p: -total[p]):
        theirs = sets["C"][p]
        if p in OURS:
            part = total[p] * (theirs - OURS[p]) / priced_mwh          # to B − A
            ours = f"{OURS[p]:g}"
        else:
            part = total[p] * (theirs - b_w) / all_mwh                 # to C − B
            ours = "unpriced"
        print(f"| {p} | {100 * total[p] / all_mwh:.2f}% | {ours} | {theirs:g} | {MODE[p]} "
              f"| {part:+.1f} |")


# %% [markdown]
# ## The handful of hours and days
#
# Their figures here are flow-traced; ours are not. Each time is read as
# local time and as UTC, since the page does not say which it is.

# %%
def at(year: int, when_utc: dt.datetime) -> dict:
    ph = DATA[year]["per_hour"]
    return {v: (ph[v][when_utc][0] if when_utc in ph[v] else None) for v in "ABC"}


def fmt(x) -> str:
    return "–" if x is None else f"{x:.0f}"


print("| Their figure | As printed | Read as | UTC hour | A | B | C | Theirs | Theirs − C |")
print("|---|---|---|---|---:|---:|---:|---:|---:|")
for label, stamp, value in EM_HOURS:
    naive = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    for zone_name, tz in (("local", BERLIN), ("UTC", UTC)):
        hour = naive.replace(tzinfo=tz).astimezone(UTC)
        got = at(naive.year, hour)
        gap = "–" if got["C"] is None else f"{value - got['C']:+.0f}"
        print(f"| {label} {naive.year} | {stamp} | {zone_name} | {hour:%m-%d %H:%M} | "
              + " | ".join(fmt(got[v]) for v in "ABC") + f" | {value} | {gap} |")


print("\n| Their figure | Day | Read as | A | B | C | Theirs | Theirs − C |")
print("|---|---|---|---:|---:|---:|---:|---:|")
for label, day, value in EM_DAYS:
    d = dt.date.fromisoformat(day)
    for zone_name, tz in (("local", BERLIN), ("UTC", UTC)):
        start = dt.datetime.combine(d, dt.time(0), tzinfo=tz).astimezone(UTC)
        end = dt.datetime.combine(d + dt.timedelta(days=1), dt.time(0), tzinfo=tz).astimezone(UTC)
        ph = DATA[d.year]["per_hour"]
        got = {}
        for v in "ABC":
            vals = [i for h, (i, _, _) in ph[v].items() if start <= h < end and i is not None]
            got[v] = statistics.fmean(vals) if vals else None
        gap = "–" if got["C"] is None else f"{value - got['C']:+.0f}"
        print(f"| {label} {d.year} | {day} | {zone_name} | "
              + " | ".join(fmt(got[v]) for v in "ABC") + f" | {value} | {gap} |")


# %% [markdown]
# ## The 2025 seasonal days
#
# The mean of each hour of the day over a season's complete hours, with the
# season's peak and trough, read in local time and in UTC.

# %%
print("| Season | Read as | Theirs: peak @ hour | C: peak @ hour | A: peak @ hour "
      "| Theirs: trough @ hour | C: trough @ hour | A: trough @ hour |")
print("|---|---|---|---|---|---|---|---|")
for season, (months, (peak, peak_h), (trough, trough_h)) in EM_SEASONS.items():
    for zone_name, tz in (("local", BERLIN), ("UTC", UTC)):
        cells = []
        for v in ("C", "A"):
            by_hour = defaultdict(list)
            for h, (i, _, _) in DATA[2025]["per_hour"][v].items():
                local = h.astimezone(tz)
                if local.year == 2025 and local.month in months and i is not None:
                    by_hour[local.hour].append(i)
            means = {hh: statistics.fmean(x) for hh, x in by_hour.items()}
            top, low = max(means, key=means.get), min(means, key=means.get)
            cells.append((f"{means[top]:.0f} @ {top:02d}", f"{means[low]:.0f} @ {low:02d}"))
        print(f"| {season} | {zone_name} | {peak} @ {peak_h:02d} | {cells[0][0]} | {cells[1][0]} "
              f"| {trough} @ {trough_h:02d} | {cells[0][1]} | {cells[1][1]} |")


# %% [markdown]
# ## After the first run, 25.10.2026: what rule 3 asks to investigate
#
# Written after the result above, and changing nothing in it: rule 3 failed
# on the plain means, C 7.2% above their production-based mean in 2024 and
# 4.8% in 2025. Three things are looked at, all descriptive.
#
# 1. **Which mean.** The energy-weighted means stand in brackets above. The
#    page does not say which mean it reports, and neither does the
#    methodology page.
# 2. **Which clock.** Read as UTC, seven of their eight seasonal peaks and
#    troughs fall on the hour where C has its own, and the eighth, the spring
#    peak, one hour away (03:00 against 02:00). Read as local time, none
#    does. Their times are taken as UTC.
# 3. **Which hours.** If their series and ours were joined to different
#    hours, their extreme hours would be ordinary ones in ours. Where do
#    their extreme hours and days rank in our series?
# 4. **Which factors.** The page does not say whether its figures are
#    life-cycle. C on their direct factors shows which reading fits:
#    `DE.yaml` direct entries, `defaults.yaml` for battery discharge and
#    unknown, and zero for biomass, hydro, nuclear, solar, wind and
#    geothermal, as they set them.

# %%
for year in YEARS:
    m, em = DATA[year]["means"], EM_MEAN[year]["production-based"]
    print(f"{year}, energy-weighted: A {m['A'][1]:.1f} → factor set {m['B'][1] - m['A'][1]:+.1f} → "
          f"coverage {m['C'][1] - m['B'][1]:+.1f} → C {m['C'][1]:.1f}, "
          f"{100 * (m['C'][1] / em - 1):+.1f}% against their production-based {em}")

print("\n| Their figure | Their time, as UTC | Rank in our A, of complete hours | Rank in C | A | C |")
print("|---|---|---:|---:|---:|---:|")
for label, stamp, value in EM_HOURS:
    hour = dt.datetime.strptime(stamp, "%Y-%m-%d %H:%M").replace(tzinfo=UTC)
    ranks = []
    for v in "AC":
        series = {h: i for h, (i, _, _) in DATA[hour.year]["per_hour"][v].items() if i is not None}
        order = sorted(series, key=series.get, reverse=label.startswith("highest"))
        ranks.append((order.index(hour) + 1, series[hour], len(order)))
    print(f"| {label} {hour.year} | {hour:%m-%d %H:%M} | {ranks[0][0]} of {ranks[0][2]:,} "
          f"| {ranks[1][0]} | {ranks[0][1]:.0f} | {ranks[1][1]:.0f} |")

print("\n| Their figure | Day | Rank in our A, of days | Rank in C |")
print("|---|---|---:|---:|")
for label, day, value in EM_DAYS:
    d = dt.date.fromisoformat(day)
    ranks = []
    for v in "AC":
        daily = defaultdict(list)
        for h, (i, _, _) in DATA[d.year]["per_hour"][v].items():
            if i is not None and h.year == d.year:
                daily[h.date()].append(i)
        means = {k: statistics.fmean(x) for k, x in daily.items() if len(x) >= 20}
        order = sorted(means, key=means.get, reverse=label.startswith("highest"))
        ranks.append((order.index(d) + 1 if d in means else None, len(order)))
    print(f"| {label} {d.year} | {day} | {ranks[0][0]} of {ranks[0][1]} | {ranks[1][0]} |")


# %%
EM_DIRECT = {
    2024: {"coal": 1080.4, "gas": 400.79, "oil": 869.31,
           "hydro discharge": 240.13, "battery discharge": 317.53},
    2025: {"coal": 1052.69, "gas": 382.97, "oil": 826.11,
           "hydro discharge": 235.37, "battery discharge": 297.68},
}
for _f in EM_DIRECT.values():
    _f.update({"biomass": 0.0, "geothermal": 0.0, "hydro": 0.0, "nuclear": 0.0,
               "solar": 0.0, "wind": 0.0, "unknown": 575.0})
print()
for year in YEARS:
    ef = {p: EM_DIRECT[year][m] for p, m in MODE.items()}
    direct = {h: weighted(mix, ef) for h, mix in DATA[year]["hours"].items()}
    print(f"{year}, C on their direct factors: plain {plain(direct):.1f}, energy-weighted "
          f"{energy_weighted(direct):.1f}, against their production-based "
          f"{EM_MEAN[year]['production-based']}")


# %% [markdown]
# ## Extended on 25.10.2026, before the pull of Germany alone
#
# 5. **Germany alone.** Their area is Germany alone, `10Y1001A1001A83F`; ours
#    is DE-LU. Prediction, stated before the pull: Luxembourg's generation is
#    small, so C on Germany alone differs from C on DE-LU by less than 1% in
#    each year, on both means. Rule 3 is then applied to Germany alone,
#    unchanged. If the area moves C by 1% or more, it is a cause of the gap,
#    by that much.
#
# The pull: `generation_per_type("10Y1001A1001A83F", year, token)` for 2024 and
# 2025 (RUNBOOK, Checkpoint 5). Until it is in, this cell says so.

# %%
DE_ALONE = "10Y1001A1001A83F"
if not all((ROOT / "raw" / "A75" / DE_ALONE / str(y)).is_dir() for y in YEARS):
    print(f"\n{DE_ALONE} is not pulled yet for {YEARS}; rule 5 waits for it.")
else:
    print("\n| Year | Mean | C, DE-LU | C, Germany alone | Change | Theirs, production-based "
          "| Germany alone against it |")
    print("|---|---|---:|---:|---:|---:|---:|")
    held, within = [], []
    for year in YEARS:
        xml, hours, stated = complete_hours(year, DE_ALONE)
        alone = {h: weighted(m, versions(year)["C"]) for h, m in hours.items()}
        prod = EM_MEAN[year]["production-based"]
        for label, value, dl in (("plain", plain(alone), DATA[year]["means"]["C"][0]),
                                 ("energy-weighted", energy_weighted(alone), DATA[year]["means"]["C"][1])):
            change = value / dl - 1
            held.append(abs(change) < 0.01)
            if label == "plain":
                within.append(abs(value / prod - 1) <= TOLERANCE)
            print(f"| {year} | {label} | {dl:.1f} | {value:.1f} | {100 * change:+.2f}% | {prod} "
                  f"| {100 * (value / prod - 1):+.1f}% |")
        print(f"   {xml.relative_to(ROOT).as_posix()}: {len(hours):,} complete hours of {stated:,}")
    print(f"\nRule 5, the area moves C by less than 1%: {'holds' if all(held) else 'fails'}.")
    print(f"Rule 3 on Germany alone: {'within' if all(within) else 'outside'} "
          f"±{100 * TOLERANCE:.0f}% of their production-based mean "
          f"{'in both years' if all(within) else 'in at least one year'}.")
