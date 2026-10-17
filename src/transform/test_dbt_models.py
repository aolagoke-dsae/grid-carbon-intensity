"""The dbt models, executed on landed fixtures and checked against parse().

xml_to_parquet.py has long called entsoe_parse "the independent oracle the
SQL is checked against". Until 17.10.2026 no such check existed, and CI only
parsed the dbt project, so no model had ever run in CI (audit A8, B5). Here
fixture payloads are landed with xml_to_parquet, every enabled model is built
with dbt-duckdb, and the SQL is compared with the Python parser step by step.
A second build deletes one day and leaves one A01 position empty, and the two
tests written for those failures must fail.

The fixtures cover both transition days (92 steps at PT15M, 25 at PT60M),
A03 carry-forward, a pump-only series, a series published only while a unit
runs, and both A44 curves.

Needs dbt-core and dbt-duckdb (requirements.txt). Skipped where dbt cannot be
imported, unless REQUIRE_DBT=1, as in CI's dbt job.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import dbt.cli.main  # noqa: F401
except Exception as e:  # noqa: BLE001 - any import failure means no dbt here
    if os.environ.get("REQUIRE_DBT") == "1":
        raise
    pytest.skip(f"dbt cannot be imported here: {e}", allow_module_level=True)

import duckdb

import xml_to_parquet as X
from entsoe_parse import parse

REPO = Path(__file__).resolve().parents[2]
NS75 = "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"
NS44 = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
DE, FR = "10Y1001A1001A82H", "10YFR-RTE------C"

# Local delivery days, in UTC. Berlin springs forward on 29 March 2026 (23 h),
# Paris falls back on 25 October 2026 (25 h).
DE_DAYS = [("2026-03-28T23:00Z", "2026-03-29T22:00Z"), ("2026-03-29T22:00Z", "2026-03-30T22:00Z")]
FR_DAYS = [("2026-10-24T22:00Z", "2026-10-25T23:00Z"), ("2026-10-25T23:00Z", "2026-10-26T23:00Z")]
B15 = {1: 74.267, 19: 71.451, 43: 72.415, 68: 71.451, 89: 73.008}   # the trap 1 example


def _series(zone, psr, day, resolution, points, direction="generation", curve="A03"):
    domain = "inBiddingZone_Domain.mRID" if direction == "generation" else "outBiddingZone_Domain.mRID"
    stated = "".join(f"<Point><position>{p}</position><quantity>{q}</quantity></Point>"
                     for p, q in sorted(points.items()))
    return (
        f"<TimeSeries><mRID>{psr}-{direction}-{day[0]}</mRID>"
        f'<{domain} codingScheme="A01">{zone}</{domain}>'
        f"<quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name><curveType>{curve}</curveType>"
        f"<MktPSRType><psrType>{psr}</psrType></MktPSRType>"
        f"<Period><timeInterval><start>{day[0]}</start><end>{day[1]}</end></timeInterval>"
        f"<resolution>{resolution}</resolution>{stated}</Period></TimeSeries>"
    )


def _a75(series):
    return f'<?xml version="1.0" encoding="UTF-8"?><GL_MarketDocument xmlns="{NS75}">{"".join(series)}</GL_MarketDocument>'


def _de(broken=False):
    s = []
    for i, day in enumerate(DE_DAYS):
        s.append(_series(DE, "B19", day, "PT15M", {1: 1000.0, 40: 1200.0, 80: 900.0} if i == 0 else {1: 800.0, 50: 700.0}))
        if not (broken and i == 1):                       # broken: B04 loses its second day
            s.append(_series(DE, "B04", day, "PT15M", {1: 300.0}))
        s.append(_series(DE, "B15", day, "PT15M", B15))
        s.append(_series(DE, "B10", day, "PT15M", {1: 115.8, 2: 113.2}, direction="consumption"))
        if broken:                                        # broken: an A01 series misses position 7
            n = 92 if i == 0 else 96
            s.append(_series(DE, "B16", day, "PT15M",
                             {p: 50.0 for p in range(1, n + 1) if not (i == 0 and p == 7)}, curve="A01"))
    return _a75(s)


def _fr():
    s = []
    for i, day in enumerate(FR_DAYS):
        s.append(_series(FR, "B14", day, "PT60M", {1: 40000.0, 10: 38000.0} if i == 0 else {1: 41000.0}))
        s.append(_series(FR, "B10", day, "PT60M", {1: 200.0, 5: 0.0}))
        s.append(_series(FR, "B10", day, "PT60M", {1: 0.0, 5: 300.0}, direction="consumption"))
    # Hard coal while one unit runs, ten hours on the first day only: declared
    # in config/sparse_series.csv, so its short day and its absent day pass.
    s.append(_series(FR, "B05", ("2026-10-25T05:00Z", "2026-10-25T15:00Z"), "PT60M", {1: 500.0}))
    return _a75(s)


def _a44():
    def curve(cs, price):
        return (
            f"<TimeSeries><mRID>{cs}</mRID><in_Domain.mRID>{DE}</in_Domain.mRID>"
            f"<out_Domain.mRID>{DE}</out_Domain.mRID>"
            f"<{X.CS_FIELD}>{cs}</{X.CS_FIELD}><curveType>A03</curveType>"
            f"<Period><timeInterval><start>{DE_DAYS[1][0]}</start><end>{DE_DAYS[1][1]}</end>"
            f"</timeInterval><resolution>PT60M</resolution>"
            f"<Point><position>1</position><price.amount>{price}</price.amount></Point>"
            "</Period></TimeSeries>"
        )
    return (f'<?xml version="1.0" encoding="utf-8"?><Publication_MarketDocument xmlns="{NS44}">'
            f"<mRID>m</mRID><revisionNumber>1</revisionNumber><type>A44</type>"
            f"{curve(1, 90.0)}{curve(2, 92.0)}</Publication_MarketDocument>")


def _store(folder, text):
    folder.mkdir(parents=True, exist_ok=True)
    body = text.encode("utf-8")
    (folder / f"20261017T220000Z_{hashlib.sha256(body).hexdigest()[:8]}.xml").write_bytes(body)


def _project(root, payloads):
    """A GRID_ROOT: landed parquet, the real config, a warehouse, a profile."""
    for doc, zone, text in payloads:
        _store(root / "raw" / doc / zone / "2026", text)
    X.land_tree(root / "raw", root / "raw" / "parquet")
    shutil.copytree(REPO / "config", root / "config")
    (root / "warehouse").mkdir()
    (root / "profiles").mkdir()
    (root / "profiles" / "profiles.yml").write_text(
        "grid_intensity:\n  target: dev\n  outputs:\n    dev:\n      type: duckdb\n"
        f"      path: '{(root / 'warehouse' / 'grid.duckdb').as_posix()}'\n      threads: 1\n",
        encoding="utf-8",
    )


def _dbt(root, *command):
    """Run dbt in its own process against GRID_ROOT=root; return {node: (status, failures)}.

    A separate process, so that DuckDB's file is closed when dbt is done and
    nothing dbt keeps in memory carries over from one build to the next.
    """
    env = {**os.environ, "GRID_ROOT": root.as_posix(), "DO_NOT_TRACK": "1",
           "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    proc = subprocess.run(
        [sys.executable, "-c", "from dbt.cli.main import cli; cli()", *command,
         "--project-dir", str(REPO / "dbt"), "--profiles-dir", str(root / "profiles"),
         "--target-path", str(root / "target"), "--log-path", str(root / "logs")],
        env=env, capture_output=True, text=True, timeout=600,
    )
    results = root / "target" / "run_results.json"
    assert results.exists(), proc.stdout[-3000:] + proc.stderr[-3000:]
    out = {r["unique_id"].split(".")[2]: (r["status"], r.get("failures"))
           for r in json.loads(results.read_text(encoding="utf-8"))["results"]}
    results.unlink()
    return out, proc


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("grid")
    payloads = [("A75", DE, _de()), ("A75", FR, _fr()), ("A44", DE, _a44())]
    _project(root, payloads)
    results, proc = _dbt(root, "build")
    con = duckdb.connect(str(root / "warehouse" / "grid.duckdb"), read_only=True)
    yield results, con, payloads, proc
    con.close()


def test_every_model_and_test_passes_on_the_fixtures(built):
    results, _, _, proc = built
    assert {n: s for n, (s, _) in results.items() if s not in ("success", "pass")} == {}, proc.stdout[-3000:]
    assert proc.returncode == 0
    assert {"int_generation_gapfilled", "dim_date", "stg_entsoe__prices",
            "assert_step_count_per_local_day", "assert_no_consumption_in_generation_total"} <= set(results)


def test_the_gapfilled_model_matches_the_parser_step_by_step(built):
    """A03 carry-forward, both transition days, both resolutions."""
    _, con, payloads, _ = built
    want = {(r["zone"], r["psr"], r["direction"], r["ts_utc"].replace(tzinfo=None)): r["mw"]
            for doc, _, text in payloads if doc == "A75" for r in parse(text)}
    got = {(z, p, d, ts): mw for z, p, d, ts, mw in con.sql(
        "select zone_eic, psr_type, direction, ts_utc, mw from main_intermediate.int_generation_gapfilled"
    ).fetchall()}
    assert len(got) == len(want) == 92 * 3 + 96 * 3 + 92 + 96 + 25 * 3 + 24 * 3 + 10
    assert got.keys() == want.keys()
    assert all(got[k] == pytest.approx(want[k]) for k in want)


def test_a_pump_only_series_keeps_its_consumption(built):
    """B10 only pumps in the DE-LU fixture. The left join used until 17.10.2026
    gave it no rows at all (audit B1)."""
    _, con, payloads, _ = built
    want = sum(r["mwh"] for r in parse(payloads[0][2]) if r["psr"] == "B10")
    rows, cons, gen = con.sql(
        "select count(*), sum(consumption_mwh), sum(generation_mwh) from main_intermediate.int_generation_energy "
        f"where zone_eic = '{DE}' and psr_type = 'B10'"
    ).fetchone()
    assert rows == 92 + 96 and gen == 0
    assert cons == pytest.approx(want)


def test_energy_totals_match_the_parser(built):
    _, con, payloads, _ = built
    for doc, zone, text in payloads:
        if doc != "A75":
            continue
        rows = parse(text)
        gen = sum(r["mwh"] for r in rows if r["direction"] == "generation")
        cons = sum(r["mwh"] for r in rows if r["direction"] == "consumption")
        got = con.sql("select sum(generation_mwh), sum(consumption_mwh) from main_intermediate.int_generation_energy "
                      f"where zone_eic = '{zone}'").fetchone()
        assert got == (pytest.approx(gen), pytest.approx(cons))


def test_the_calendar_knows_the_transition_days(built):
    _, con, _, _ = built
    hours = dict(con.sql("select zone_eic || ' ' || local_date, hours_in_local_day from main_marts.dim_date").fetchall())
    assert hours == {f"{DE} 2026-03-29": 23, f"{DE} 2026-03-30": 24,
                     f"{FR} 2026-10-25": 25, f"{FR} 2026-10-26": 24}


def test_one_price_curve_survives_the_filter(built):
    _, con, _, _ = built
    assert con.sql("select distinct classification_sequence, price_eur_mwh from main_staging.stg_entsoe__prices").fetchall() == [(1, 90.0)]


def test_a_deleted_day_and_an_empty_a01_position_fail_their_tests(tmp_path):
    """RUNBOOK Checkpoint 7: break one on purpose. Until 17.10.2026 the
    coverage test could not see a deleted day (audit B3), and an empty A01
    position was filled with the last value (A6). run, then test, so that the
    first failure does not skip the second test."""
    _project(tmp_path, [("A75", DE, _de(broken=True)), ("A44", DE, _a44())])
    run, proc = _dbt(tmp_path, "run")
    assert {s for s, _ in run.values()} == {"success"}, proc.stdout[-3000:]
    tests, _ = _dbt(tmp_path, "test", "--store-failures")
    failed = {n: f for n, (s, f) in tests.items() if s != "pass"}
    assert failed == {"assert_step_count_per_local_day": 1, "not_null_int_generation_gapfilled_mw": 1}
    con = duckdb.connect(str(tmp_path / "warehouse" / "grid.duckdb"), read_only=True)
    try:
        row = con.sql("select zone_eic, psr_type, local_date, steps_present, steps_expected "
                      "from main_dbt_test__audit.assert_step_count_per_local_day").fetchone()
    finally:
        con.close()
    assert row == (DE, "B04", dt.date(2026, 3, 30), 0, 96)
