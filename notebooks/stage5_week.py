# %% [markdown]
# # Stage 5: two weeks, looked at. DE-LU, 2025
#
# RUNBOOK Checkpoint 5 asks for one week to be plotted and looked at: "Sunny
# summer midday low, still winter evening high. An inverted shape means a join
# error." This draws two weeks of the deterministic intensity, a sunny summer
# week and a still winter one, computed exactly as Checkpoint 5 computes it,
# and states the shape in numbers before the picture is looked at.
#
# What a join error would look like. A quarter-hour's intensity joins every
# fuel's A75 series on the UTC timestamp, and every fuel to its factor. A fuel
# joined to the wrong factor, solar priced as coal say, puts a peak where the
# dip should be. A timestamp read in the wrong zone, or on a twelve-hour
# clock, moves the dip away from midday. The sun is a clock that neither error
# can move: German solar output peaks near solar noon, about 13:20 CEST in
# summer.
#
# ## The rule, fixed on 24.10.2026, before any week was plotted
#
# 1. **Weeks** run from Monday 00:00 to Monday 00:00, Berlin time. A week is a
#    candidate only if all seven of its days lie in the months named.
# 2. **The summer week** is the week of June–August 2025 with the most solar
#    generation (B16).
# 3. **The winter week** is the week of January, February or December 2025
#    with the least wind generation (B18 and B19).
# 4. **Midday low.** On at least five of the summer week's seven days, the
#    day's lowest quarter-hour is one of those from 10:00 to 15:45.
# 5. **Evening high.** On at least five of the winter week's seven days, the
#    day's highest quarter-hour is one of those from 16:00 to 21:45.
# 6. **The clock.** The summer week's solar output, averaged by quarter-hour
#    of the day, peaks in one of the quarter-hours from 12:30 to 13:45.
#
# Times are local, and a quarter-hour is named by its start. Rules 4 and 5 are
# the runbook's expectation. Rule 6 tells a timestamp error from a mix that
# behaves otherwise than expected: if it fails, the timestamps are wrong and
# nothing else is read; if it holds and rule 4 or 5 fails, the shape is the
# data's, and it is explained rather than fixed. Unlike the rules in
# `third_zone.py` and `price_curves.py`, this one was not committed before its
# first run, so the order rests on this note, not on the history.
#
# The values are `deterministic_intensity` at the median factors of
# `config/ipcc_ar5_factors.csv`, over the priced share of generation, with
# every partial step withheld (`incomplete_steps`). The whole year passes
# `check_stage5_intensity` before anything is drawn.
#
# Run from the repository root: `python notebooks/stage5_week.py`. It needs
# the 2025 DE-LU A75 payload in `raw/` and `requirements-figures.txt`, and it
# writes `docs/figures/stage5_week_de_lu_2025.png` with its table,
# `docs/figures/stage5_week_de_lu_2025.csv`. No token is needed.

# %%
from __future__ import annotations

import csv
import datetime as dt
import math
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

from src.checks.validate import (  # noqa: E402
    check_stage5_intensity, incomplete_steps, load_coverage_policy,
)
from src.transform.entsoe_parse import parse  # noqa: E402
from src.transform.intensity import (  # noqa: E402
    deterministic_intensity, energy_by_fuel, load_factors,
)
from src.transform.xml_to_parquet import current_payloads  # noqa: E402

EIC = "10Y1001A1001A82H"                       # DE-LU
YEAR = 2025
UTC = dt.timezone.utc
BERLIN = zoneinfo.ZoneInfo("Europe/Berlin")
SUMMER, WINTER = (6, 7, 8), (1, 2, 12)         # rules 2 and 3
SOLAR, WIND = ("B16",), ("B18", "B19")
MIDDAY = (dt.time(10, 0), dt.time(15, 45))     # rule 4: first and last quarter-hour
EVENING = (dt.time(16, 0), dt.time(21, 45))    # rule 5
NOON = (dt.time(12, 30), dt.time(13, 45))      # rule 6
DAYS = 5                                       # rules 4 and 5: days of seven
OUT = ROOT / "docs" / "figures"
STEM = "stage5_week_de_lu_2025"

# %%
A75 = ROOT / "raw" / "A75"
xml = [p for p in current_payloads(A75) if p.parent == A75 / EIC / str(YEAR)][0]
rows = parse(xml.read_text(encoding="utf-8"))
factors = load_factors(ROOT / "config" / "ipcc_ar5_factors.csv")
sparse, _ = load_coverage_policy()
mixes = energy_by_fuel(rows)
partial = incomplete_steps(rows, sparse)
values = {k: None if k in partial else deterministic_intensity(mix, factors)
          for k, mix in mixes.items()}
ok, message = check_stage5_intensity(rows, factors, values, sparse)
print(f"A75 {xml.relative_to(ROOT).as_posix()}: {len(rows):,} rows")
print(f"check_stage5_intensity: {ok}; {message}")
if not ok:
    raise SystemExit("the values fail Checkpoint 5, so nothing is drawn")

step_hours = {(r["zone"], r["ts_utc"]): r["step_hours"]
              for r in rows if r["direction"] == "generation"}
del rows


def priced(mix: dict) -> float:
    return sum(e for p, e in mix.items() if p in factors and factors[p].priced)


steps = []          # one per generation step, in time order
for key in sorted(mixes, key=lambda k: k[1]):
    mix, hours = mixes[key], step_hours[key]
    solar = sum(mix.get(p, 0.0) for p in SOLAR)
    wind = sum(mix.get(p, 0.0) for p in WIND)
    steps.append({
        "key": key,
        "ts_utc": key[1],
        "local": key[1].astimezone(BERLIN),
        "intensity": values[key],
        "priced_mwh": priced(mix),
        "total_mwh": sum(mix.values()),
        "solar_mwh": solar,
        "wind_mwh": wind,
        "solar_gw": solar / hours / 1000,
        "wind_gw": wind / hours / 1000,
    })


# %%
def monday_of(local: dt.datetime) -> dt.date:
    return local.date() - dt.timedelta(days=local.weekday())


def inside(monday: dt.date, months: tuple) -> bool:
    """Rule 1: all seven days lie in the year and in the months named."""
    days = [monday + dt.timedelta(days=d) for d in range(7)]
    return all(d.year == YEAR and d.month in months for d in days)


def gwh(week: dt.date, field: str) -> float:
    return sum(s[field] for s in by_week[week]) / 1000


def span(monday: dt.date) -> str:
    return f"{monday:%d.%m.}–{monday + dt.timedelta(days=6):%d.%m.%Y}"


by_week = defaultdict(list)
for s in steps:
    by_week[monday_of(s["local"])].append(s)

summer_weeks = sorted((w for w in by_week if inside(w, SUMMER)), key=lambda w: -gwh(w, "solar_mwh"))
winter_weeks = sorted((w for w in by_week if inside(w, WINTER)), key=lambda w: gwh(w, "wind_mwh"))
SUMMER_WEEK, WINTER_WEEK = summer_weeks[0], winter_weeks[0]

year_hours = sum(step_hours[s["key"]] for s in steps)
print(f"\nRule 2: {len(summer_weeks)} summer weeks, most solar first")
for w in summer_weeks[:3]:
    print(f"  {span(w)}  solar {gwh(w, 'solar_mwh'):,.0f} GWh, wind {gwh(w, 'wind_mwh'):,.0f} GWh")
print(f"Rule 3: {len(winter_weeks)} winter weeks, least wind first")
for w in winter_weeks[:3]:
    print(f"  {span(w)}  wind {gwh(w, 'wind_mwh'):,.0f} GWh, solar {gwh(w, 'solar_mwh'):,.0f} GWh")
print(f"  2025 as a whole: wind {sum(s['wind_mwh'] for s in steps) / year_hours / 1000:.1f} GW "
      f"on average, against {gwh(WINTER_WEEK, 'wind_mwh') / 168:.1f} GW in the winter week")


# %%
def within(t: dt.time, window: tuple) -> bool:
    return window[0] <= t <= window[1]


def daily_extremes(week: dt.date, pick) -> list:
    """Each local day's lowest (pick=min) or highest (pick=max) quarter-hour."""
    days = defaultdict(list)
    for s in by_week[week]:
        if s["intensity"] is not None:
            days[s["local"].date()].append(s)
    return [pick(day, key=lambda s: s["intensity"]) for _, day in sorted(days.items())]


lows = daily_extremes(SUMMER_WEEK, min)
highs = daily_extremes(WINTER_WEEK, max)
rule4 = sum(within(s["local"].time(), MIDDAY) for s in lows)
rule5 = sum(within(s["local"].time(), EVENING) for s in highs)
profile = defaultdict(list)
for s in by_week[SUMMER_WEEK]:
    profile[s["local"].time()].append(s["solar_gw"])
peak = max(profile, key=lambda t: statistics.fmean(profile[t]))
rule6 = within(peak, NOON)

for title, week, marks, window, held in (
        ("Rule 4, midday low: each day's lowest quarter-hour", SUMMER_WEEK, lows, MIDDAY,
         rule4 >= DAYS),
        ("Rule 5, evening high: each day's highest quarter-hour", WINTER_WEEK, highs, EVENING,
         rule5 >= DAYS)):
    inn = sum(within(s["local"].time(), window) for s in marks)
    gaps = defaultdict(int)
    for s in by_week[week]:
        gaps[s["local"].date()] += s["intensity"] is None
    print(f"\n{title}, {span(week)}")
    for s in marks:
        where = "" if within(s["local"].time(), window) else \
            f"   outside {window[0]:%H:%M}–{window[1]:%H:%M}"
        if gaps[s["local"].date()]:
            where += f"; {gaps[s['local'].date()]} quarter-hours withheld that day"
        print(f"  {s['local']:%a %d.%m. %H:%M}  {s['intensity']:4.0f} gCO2e/kWh{where}")
    print(f"  {inn} of {len(marks)} days: {'holds' if held else 'fails'}")
print(f"\nRule 6, the clock: the summer week's mean solar output peaks at {peak:%H:%M} "
      f"({statistics.fmean(profile[peak]):.1f} GW): {'holds' if rule6 else 'fails'}")

if not rule6:
    print("\nVerdict: the timestamps are wrong (rule 6), and nothing else is read.")
elif rule4 >= DAYS and rule5 >= DAYS:
    print("\nVerdict: the shape is the expected one, and no join error shows.")
else:
    print("\nVerdict: the timestamps are right (rule 6), but the shape departs from the "
          "runbook's expectation (rules 4 and 5). Explain it from the mix.")


# %%
def describe(week: dt.date) -> dict:
    shown = [s for s in by_week[week] if s["intensity"] is not None]
    vals = [s["intensity"] for s in shown]
    return {
        "mean": sum(s["intensity"] * s["priced_mwh"] for s in shown)
        / sum(s["priced_mwh"] for s in shown),
        "lo": min(vals), "hi": max(vals),
        "share": sum(s["priced_mwh"] for s in shown) / sum(s["total_mwh"] for s in shown),
        "withheld": sum(s["intensity"] is None for s in by_week[week]),
        "steps": len(by_week[week]),
    }


SUMMARY = {"summer": describe(SUMMER_WEEK), "winter": describe(WINTER_WEEK)}
print()
for name, week in (("summer", SUMMER_WEEK), ("winter", WINTER_WEEK)):
    d = SUMMARY[name]
    print(f"{name} {span(week)}: {d['lo']:.0f}–{d['hi']:.0f} gCO2e/kWh, mean {d['mean']:.0f} "
          f"weighted by priced energy; priced share {100 * d['share']:.1f}%; "
          f"{d['withheld']} of {d['steps']} quarter-hours withheld")

# %% [markdown]
# ## Beyond the rule, descriptive only
#
# The mean intensity by local hour in both weeks, and the winter week's
# generation by fuel and hour: what moves when its intensity moves.

# %%
GROUPS = (("lignite", ("B02",)), ("hard coal", ("B05",)), ("gas", ("B04",)),
          ("biomass", ("B01",)), ("wind", WIND), ("solar", SOLAR))
grouped = {p for _, ps in GROUPS for p in ps}

for name, week in (("summer", SUMMER_WEEK), ("winter", WINTER_WEEK)):
    by_hour = defaultdict(list)
    for s in by_week[week]:
        if s["intensity"] is not None:
            by_hour[s["local"].hour].append(s["intensity"])
    print(f"{name}, mean by local hour: "
          + " ".join(f"{h:02d}h {statistics.fmean(v):.0f}" for h, v in sorted(by_hour.items())))


def by_group(s: dict) -> dict:
    """A quarter-hour's output in GW by fuel group, the rest, and the total."""
    mix, hours = mixes[s["key"]], step_hours[s["key"]]
    out = {name: sum(mix.get(p, 0.0) for p in ps) / hours / 1000 for name, ps in GROUPS}
    out["other"] = sum(e for p, e in mix.items() if p not in grouped) / hours / 1000
    out["total"] = sum(mix.values()) / hours / 1000
    return out


columns = [name for name, _ in GROUPS] + ["other", "total"]
table = defaultdict(list)
for s in by_week[WINTER_WEEK]:
    if s["intensity"] is not None:
        table[s["local"].hour].append((s["intensity"], by_group(s)))
print("\nwinter, mean by local hour: intensity in gCO2e/kWh, output in GW")
print("hour  intensity" + "".join(f"{c:>11}" for c in columns))
for hour, recs in sorted(table.items()):
    print(f"{hour:02d}h   {statistics.fmean(i for i, _ in recs):9.0f}"
          + "".join(f"{statistics.fmean(g[c] for _, g in recs):11.1f}" for c in columns))

# %% [markdown]
# ## The figure
#
# Small multiples, never a second y-axis: one column per week, one row per
# measure, and each row on one scale, so the two weeks compare directly.
# Intensity on top, with each day's lowest quarter-hour (summer) or highest
# (winter) marked and the window the rule expects it in shaded; solar and wind
# output below. Gaps in a line are withheld quarter-hours. The table beside the
# PNG holds every value drawn.

# %%
import matplotlib  # noqa: E402

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

INK, INK_2, MUTED = "#0b0b0b", "#52514e", "#898781"
GRID, BASELINE, SURFACE, WASH = "#e1e0d9", "#c3c2b7", "#fcfcfb", "#f0efec"
HUE = {"intensity": "#2a78d6", "solar": "#eb6834", "wind": "#1baf7a"}
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Segoe UI", "Inter", "DejaVu Sans", "Arial"],
    "font.size": 9,
    "axes.unicode_minus": False,
})


def ceiling(x: float, step: float) -> float:
    return step * math.ceil(x / step)


MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")


def dates(monday: dt.date) -> str:
    """'16–22 June', or '27 January–2 February' for a week across two months."""
    sunday = monday + dt.timedelta(days=6)
    if monday.month == sunday.month:
        return f"{monday.day}–{sunday.day} {MONTHS[sunday.month - 1]}"
    return f"{monday.day} {MONTHS[monday.month - 1]}–{sunday.day} {MONTHS[sunday.month - 1]}"


def draw(columns: list, path: Path, title: str, notes: str, source: str) -> None:
    """One column per week: dicts with title, line, steps, marks, window, labels."""
    fig = plt.figure(figsize=(10, 6.8), facecolor=SURFACE)
    grid = fig.add_gridspec(2, 2, height_ratios=(1.3, 1), left=0.07, right=0.985,
                            top=0.745, bottom=0.135, hspace=0.14, wspace=0.05)
    top = max(s["intensity"] or 0 for c in columns for s in c["steps"])
    power = max(max(s["solar_gw"], s["wind_gw"]) for c in columns for s in c["steps"])
    axes = []
    for col, c in enumerate(columns):
        ss, marks, window = c["steps"], c["marks"], c["window"]
        a = fig.add_subplot(grid[0, col], sharey=axes[0][0] if axes else None)
        b = fig.add_subplot(grid[1, col], sharex=a, sharey=axes[0][1] if axes else None)
        axes.append((a, b))
        t0 = dt.datetime.combine(monday_of(ss[0]["local"]), dt.time(0), tzinfo=BERLIN)
        x = [s["local"] for s in ss]
        for d in range(7):
            day = t0 + dt.timedelta(days=d)
            a.axvspan(day.replace(hour=window[0].hour, minute=window[0].minute),
                      day.replace(hour=window[1].hour, minute=window[1].minute)
                      + dt.timedelta(minutes=15), color=WASH, lw=0, zorder=0)
        a.plot(x, [math.nan if s["intensity"] is None else s["intensity"] for s in ss],
               color=HUE["intensity"], lw=1.4, solid_joinstyle="round", zorder=3)
        a.plot([s["local"] for s in marks], [s["intensity"] for s in marks], "o", ms=5.5,
               mfc=HUE["intensity"], mec=SURFACE, mew=1.3, zorder=4, clip_on=False)
        for name in ("solar", "wind"):
            b.plot(x, [s[f"{name}_gw"] for s in ss], color=HUE[name], lw=1.4, zorder=3)
            if c["labels"]:          # direct labels, beside the legend in column 1
                at = max(ss, key=lambda s: s[f"{name}_gw"])
                b.annotate(name.capitalize(), (at["local"], at[f"{name}_gw"]),
                           xytext=(0, 5), textcoords="offset points", ha="center",
                           va="bottom", color=INK_2, size=8.5)
        a.text(0, 1.13, c["title"], transform=a.transAxes, color=INK, size=10.5,
               weight="semibold", va="bottom")
        a.text(0, 1.035, c["line"], transform=a.transAxes, color=INK_2, size=8.5,
               va="bottom")
        for ax in (a, b):
            ax.set_facecolor(SURFACE)
            ax.set_xlim(t0, t0 + dt.timedelta(days=7))
            ax.grid(axis="both", which="major", color=GRID, lw=0.8)
            ax.set_axisbelow(True)
            for side in ("top", "right", "left"):
                ax.spines[side].set_visible(False)
            ax.spines["bottom"].set_color(BASELINE)
            ax.spines["bottom"].set_linewidth(0.8)
            ax.xaxis.set_major_locator(mdates.DayLocator(tz=BERLIN))
            ax.xaxis.set_major_formatter(plt.NullFormatter())
            ax.xaxis.set_minor_locator(mdates.HourLocator(byhour=[12], tz=BERLIN))
            ax.xaxis.set_minor_formatter(mdates.DateFormatter("%a\n%d", tz=BERLIN))
            ax.tick_params(which="both", length=0, colors=MUTED, labelsize=8.5)
        a.tick_params(axis="x", which="minor", labelbottom=False)
        if col:
            a.tick_params(axis="y", labelleft=False)
            b.tick_params(axis="y", labelleft=False)
    a0, b0 = axes[0]
    a0.set_ylim(0, ceiling(top, 100))
    b0.set_ylim(0, ceiling(power, 10))
    a0.set_ylabel("Intensity, gCO₂e/kWh", color=INK_2, size=8.5)
    b0.set_ylabel("Output, GW", color=INK_2, size=8.5)
    b0.legend(handles=[Line2D([], [], color=HUE["solar"], lw=2),
                       Line2D([], [], color=HUE["wind"], lw=2)],
              labels=["Solar", "Wind, onshore and offshore"], loc="upper left",
              bbox_to_anchor=(0, 1.0), ncol=2, frameon=False, fontsize=8.5,
              labelcolor=INK_2, handlelength=1.6, borderaxespad=0.2)
    fig.text(0.07, 0.965, title, color=INK, size=13.5, weight="semibold", va="top")
    fig.text(0.07, 0.915, notes, color=INK_2, size=9, va="top", linespacing=1.5)
    fig.text(0.07, 0.022, source, color=MUTED, size=7.5, va="bottom", linespacing=1.5)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=200, facecolor=SURFACE)
    plt.close(fig)


# %%
def heading(d: dict) -> str:
    line = (f"{d['lo']:.0f}–{d['hi']:.0f}, mean {d['mean']:.0f} gCO₂e/kWh; "
            f"priced share {100 * d['share']:.1f}%")
    if d["withheld"]:
        line += f"; {d['withheld']} withheld"
    return line


retrieved = f"{xml.name[:4]}-{xml.name[4:6]}-{xml.name[6:8]}"
draw([{"title": f"Summer: the sunniest week, {dates(SUMMER_WEEK)}",
       "line": heading(SUMMARY["summer"]), "steps": by_week[SUMMER_WEEK], "marks": lows,
       "window": MIDDAY, "labels": False},
      {"title": f"Winter: the stillest week, {dates(WINTER_WEEK)}",
       "line": heading(SUMMARY["winter"]), "steps": by_week[WINTER_WEEK], "marks": highs,
       "window": EVENING, "labels": True}],
     OUT / f"{STEM}.png",
     title="Midday lows in summer, night-time highs in a still winter week",
     notes=(f"Carbon intensity of generation, DE-LU, {YEAR}: life-cycle gCO₂e per kWh at the "
            "median IPCC AR5 factors, over the priced share of generation.\n"
            "Quarter-hours, local time. Dots: each day's lowest quarter-hour in summer, its "
            "highest in winter. Shading: where the check expects them."),
     source=("Source: ENTSO-E Transparency Platform, actual generation per production type "
             f"(A75), retrieved {retrieved}. Factors: config/ipcc_ar5_factors.csv.\n"
             "Gaps: quarter-hours withheld at a recorded source gap. "
             f"Values: {STEM}.csv; rule and check: notebooks/stage5_week.py."))

with (OUT / f"{STEM}.csv").open("w", newline="", encoding="utf-8") as fh:
    out = csv.writer(fh, lineterminator="\n")
    out.writerow(["week", "ts_utc", "ts_local", "intensity_g_kwh", "withheld",
                  "priced_share_pct", "solar_gw", "wind_gw", "marked"])
    for name, week, marks in (("summer", SUMMER_WEEK, lows), ("winter", WINTER_WEEK, highs)):
        marked = {s["ts_utc"] for s in marks}
        for s in by_week[week]:
            out.writerow([
                name, f"{s['ts_utc']:%Y-%m-%dT%H:%MZ}", s["local"].isoformat(timespec="minutes"),
                "" if s["intensity"] is None else f"{s['intensity']:.1f}",
                int(s["intensity"] is None),
                "" if s["intensity"] is None
                else f"{100 * s['priced_mwh'] / s['total_mwh']:.2f}",
                f"{s['solar_gw']:.3f}", f"{s['wind_gw']:.3f}", int(s["ts_utc"] in marked),
            ])
print(f"\nwrote {(OUT / STEM).relative_to(ROOT).as_posix()}.png and .csv")
