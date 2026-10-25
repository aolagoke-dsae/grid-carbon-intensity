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
runs, and both A44 curves. Since 18.10.2026 also a series stated net, one leg
per hour, a day that changes resolution, and a series exempt inside a window
only (config/sparse_series.csv from_date and to_date).

Since 25.10.2026 the three facts as well: fact_generation must hold exactly
the parser's rows, fact_intensity must pass the Python Checkpoint 5 check,
fact_price must be parse_prices' expansion of the selected curve, and every
fact row must resolve to a retrieval in the fixture's raw/manifest.csv.
Since the same day the Monte Carlo interval: dim_factor_draw must hold
intensity.py's draws for the project's seed, every reported step's interval
must be its parsed mix under them (check_stage6_marts), and a point moved out
of its interval must fail the acceptance test.

The payloads are built in src/transform/sample_data.py, which also writes the
synthetic curated/sample/ from them; the last test builds that sample with the
`sample` target, as a clone without a token would.

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
import numpy as np

import raw_store
import xml_to_parquet as X
from entsoe_parse import parse
from entsoe_prices_parse import parse_prices
from intensity import load_factors, shared_factor_draws
from sample_data import DE, FR, de_a44, de_a75, fr_a75
from validate import check_stage5_intensity, check_stage6_marts, load_coverage_policy

REPO = Path(__file__).resolve().parents[2]


def _store(folder, text):
    folder.mkdir(parents=True, exist_ok=True)
    body = text.encode("utf-8")
    path = folder / f"20261017T220000Z_{hashlib.sha256(body).hexdigest()[:8]}.xml"
    path.write_bytes(body)
    return path, body


def _project(root, payloads, unrecorded=()):
    """A GRID_ROOT: landed parquet, the real config, a warehouse, a profile,
    and a manifest row for every payload but those of the document types in
    `unrecorded`."""
    for doc, zone, text in payloads:
        path, body = _store(root / "raw" / doc / zone / "2026", text)
        if doc not in unrecorded:
            raw_store.append_manifest(root / "raw" / "manifest.csv", {
                "retrieved_at_utc": "2026-10-17T22:00:00+00:00",
                "path": path.relative_to(root).as_posix(), "url": f"fixture://{doc}/{zone}",
                "http_status": 200, "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(), "rejected": 0, "attempt": 1,
                "revision": "1",
            })
    X.land_tree(root / "raw", root / "raw" / "parquet")
    shutil.copytree(REPO / "config", root / "config")
    # The dbt Python models load src/transform/intensity.py from GRID_ROOT.
    shutil.copytree(REPO / "src", root / "src", ignore=shutil.ignore_patterns("__pycache__", "test_*.py"))
    with (root / "config" / "sparse_series.csv").open("a", encoding="utf-8", newline="") as fh:
        fh.write(f'{FR},B18,,2026-10-25,2026-10-18,"fixture: not published before 26.10.2026"\n')
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
    payloads = [("A75", DE, de_a75()), ("A75", FR, fr_a75()), ("A44", DE, de_a44())]
    _project(root, payloads)
    results, proc = _dbt(root, "build")
    con = duckdb.connect(str(root / "warehouse" / "grid.duckdb"), read_only=True)
    yield results, con, payloads, proc, root
    con.close()


def test_every_model_and_test_passes_on_the_fixtures(built):
    results, _, _, proc, _ = built
    assert {n: s for n, (s, _) in results.items() if s not in ("success", "pass")} == {}, proc.stdout[-3000:]
    assert proc.returncode == 0
    assert {"int_generation_gapfilled", "dim_date", "stg_entsoe__prices",
            "assert_step_count_per_local_day", "assert_no_consumption_in_generation_total",
            "fact_generation", "fact_intensity", "fact_price", "int_generation_partial_steps",
            "int_prices_gapfilled", "assert_intensity_recomputed_from_the_mix",
            "assert_every_fact_row_resolves_to_the_manifest", "assert_one_row_per_fact_grain",
            "dim_factor_draw", "int_intensity_interval", "assert_deterministic_within_mc_interval",
            "assert_every_factor_draw_inside_its_band"
            } <= set(results)


def test_the_gapfilled_model_matches_the_parser_step_by_step(built):
    """A03 carry-forward, both transition days, both resolutions."""
    _, con, payloads, _, _ = built
    want = {(r["zone"], r["psr"], r["direction"], r["ts_utc"].replace(tzinfo=None)): r["mw"]
            for doc, _, text in payloads if doc == "A75" for r in parse(text)}
    got = {(z, p, d, ts): mw for z, p, d, ts, mw in con.sql(
        "select zone_eic, psr_type, direction, ts_utc, mw from main_intermediate.int_generation_gapfilled"
    ).fetchall()}
    # DE: three series and a pumping leg over 23 + 24 h. FR, 25 + 24 h: B14, B10 both
    # legs and B12 on the first day; B10 both legs, B12 (20 + 4 net) and B18 on the
    # second, where B14 has one hourly step and 92 quarter-hours; B05 ten hours.
    assert len(got) == len(want) == 92 * 3 + 96 * 3 + 92 + 96 + 25 * 4 + 24 * 4 + 1 + 92 + 10
    assert got.keys() == want.keys()
    assert all(got[k] == pytest.approx(want[k]) for k in want)


def test_a_pump_only_series_keeps_its_consumption(built):
    """B10 only pumps in the DE-LU fixture. The left join used until 17.10.2026
    gave it no rows at all (audit B1)."""
    _, con, payloads, _, _ = built
    want = sum(r["mwh"] for r in parse(payloads[0][2]) if r["psr"] == "B10")
    # fetchall(), not fetchone(): DuckDB 2.0 (21.10.2026) removed fetchone()
    # from relations, and fetchall() reads the same in 1.x. Unpacking the list
    # also fails if the query returns more than the one row it should.
    [(rows, cons, gen)] = con.sql(
        "select count(*), sum(consumption_mwh), sum(generation_mwh) from main_intermediate.int_generation_energy "
        f"where zone_eic = '{DE}' and psr_type = 'B10'"
    ).fetchall()
    assert rows == 92 + 96 and gen == 0
    assert cons == pytest.approx(want)


def test_energy_totals_match_the_parser(built):
    _, con, payloads, _, _ = built
    for doc, zone, text in payloads:
        if doc != "A75":
            continue
        rows = parse(text)
        gen = sum(r["mwh"] for r in rows if r["direction"] == "generation")
        cons = sum(r["mwh"] for r in rows if r["direction"] == "consumption")
        [got] = con.sql("select sum(generation_mwh), sum(consumption_mwh) from main_intermediate.int_generation_energy "
                        f"where zone_eic = '{zone}'").fetchall()
        assert got == (pytest.approx(gen), pytest.approx(cons))


def test_the_calendar_knows_the_transition_days(built):
    _, con, _, _, _ = built
    hours = dict(con.sql("select zone_eic || ' ' || local_date, hours_in_local_day from main_marts.dim_date").fetchall())
    assert hours == {f"{DE} 2026-03-29": 23, f"{DE} 2026-03-30": 24,
                     f"{FR} 2026-10-25": 25, f"{FR} 2026-10-26": 24}


def test_one_price_curve_survives_the_filter(built):
    _, con, _, _, _ = built
    assert con.sql("select distinct classification_sequence, price_eur_mwh from main_staging.stg_entsoe__prices").fetchall() == [(1, 90.0)]


def test_the_generation_fact_holds_exactly_the_parsed_rows(built):
    """RUNBOOK Checkpoint 6: the mart's rows are the parser's rows, one for one,
    with energy in MWh and emissions at the median factor for priced
    generation only. A consumption leg carries no emissions."""
    _, con, payloads, _, _ = built
    factors = load_factors(REPO / "config" / "ipcc_ar5_factors.csv")
    want = {(r["zone"], r["psr"], r["direction"], r["ts_utc"].replace(tzinfo=None)): r
            for doc, _, text in payloads if doc == "A75" for r in parse(text)}
    got = {(z, p, d, ts): (mwh, kg) for z, p, d, ts, mwh, kg in con.sql(
        "select zone_eic, psr_type, direction, ts_utc, mwh, emissions_kg from main_marts.fact_generation"
    ).fetchall()}
    assert got.keys() == want.keys()
    for key, r in want.items():
        mwh, kg = got[key]
        assert mwh == pytest.approx(r["mwh"])
        if r["direction"] == "generation" and factors[r["psr"]].priced:
            assert kg == pytest.approx(r["mwh"] * factors[r["psr"]].median)
        else:
            assert kg is None


def test_the_intensity_fact_passes_checkpoint_5(built):
    """The SQL intensity, handed to the Python Checkpoint 5 check: every value
    the median-factor mean of a complete mix, every partial step withheld, no
    step missing and none extra. FR's offshore wind is exempt before its
    first day, as _project declares; DE's B15 is never exempt."""
    _, con, payloads, _, root = built
    rows = [r for doc, _, text in payloads if doc == "A75" for r in parse(text)]
    values = {(z, ts.replace(tzinfo=dt.timezone.utc)): v for z, ts, v in con.sql(
        "select zone_eic, ts_utc, intensity_g_kwh from main_marts.fact_intensity").fetchall()}
    factors = load_factors(root / "config" / "ipcc_ar5_factors.csv")
    sparse, _ = load_coverage_policy(sparse_csv=root / "config" / "sparse_series.csv",
                                     gaps_csv=root / "config" / "source_gaps.csv")
    ok, message = check_stage5_intensity(rows, factors, values, sparse)
    assert ok, message
    assert any(v is not None for v in values.values())


def test_the_price_fact_is_the_selected_curve_expanded(built):
    """Trap 1 for prices: A03's repeated prices carried forward, as
    parse_prices expands them, on the curve trap 5 selects. The fixture states
    position 1 of a 24-hour day; the other 23 hours repeat it."""
    _, con, payloads, _, _ = built
    want = {(r["zone_eic"], r["ts_utc"].replace(tzinfo=None)): r["price_eur_mwh"]
            for doc, _, text in payloads if doc == "A44"
            for r in parse_prices(text) if r["classification_sequence"] == 1}
    got = {(z, ts): price for z, ts, price in con.sql(
        "select zone_eic, ts_utc, price_eur_mwh from main_marts.fact_price").fetchall()}
    assert got == want
    assert len(got) == 24
    assert con.sql("select count(*) from main_marts.fact_price where was_carried").fetchall() == [(23,)]


def _mc_vars():
    """(mc_draws, mc_seed), the project vars of dbt/dbt_project.yml."""
    import yaml
    v = yaml.safe_load((REPO / "dbt" / "dbt_project.yml").read_text(encoding="utf-8"))["vars"]
    return int(v["mc_draws"]), int(v["mc_seed"])


def test_the_factor_draws_are_the_samplers_with_the_projects_seed(built):
    """dim_factor_draw holds intensity.shared_factor_draws for the project's
    mc_draws and mc_seed, one row per draw and priced fuel: the sampling
    stays in Python, and the warehouse stores what it drew."""
    _, con, _, _, root = built
    n, seed = _mc_vars()
    fuels, want = shared_factor_draws(load_factors(root / "config" / "ipcc_ar5_factors.csv"), n, seed)
    got = con.sql("select psr_type, draw_id, ef_g_kwh, mc_seed from main_marts.dim_factor_draw "
                  "order by psr_type, draw_id").fetchall()
    assert len(got) == n * len(fuels)
    assert [p for p, *_ in got[::n]] == fuels
    assert {s for *_, s in got} == {seed}
    assert np.allclose(np.array([e for _, _, e, _ in got]).reshape(len(fuels), n).T, want,
                       rtol=1e-12, atol=0)


def test_the_marts_pass_checkpoint_6_with_the_interval(built):
    """The whole Checkpoint 6 check on the fixture warehouse: the generation
    fact against the parser, the point against Checkpoint 5, and each
    reported step's interval against its parsed mix under the stored draws,
    the point inside it, no interval where the point is withheld."""
    _, con, payloads, _, root = built
    factors = load_factors(root / "config" / "ipcc_ar5_factors.csv")
    sparse, _ = load_coverage_policy(sparse_csv=root / "config" / "sparse_series.csv",
                                     gaps_csv=root / "config" / "source_gaps.csv")
    ok, message = check_stage6_marts(
        con, [(zone, 2026, parse(text)) for doc, zone, text in payloads if doc == "A75"], factors, sparse)
    assert ok, message
    n, seed = _mc_vars()
    assert f"{n:,} stored draws of seed {seed}" in message, message
    [(banded, withheld)] = con.sql(
        "select count(intensity_p05_g_kwh), count(*) filter (where intensity_g_kwh is null) "
        "from main_marts.fact_intensity").fetchall()
    assert banded > 0 and withheld > 0


def test_a_point_outside_its_interval_fails_the_acceptance_test(tmp_path):
    """RUNBOOK Checkpoint 7, break one on purpose, for the criterion the whole
    build answers to: move one reported step's 5th percentile above its point
    and assert_deterministic_within_mc_interval must fail on that step."""
    _project(tmp_path, [("A75", DE, de_a75()), ("A75", FR, fr_a75()), ("A44", DE, de_a44())])
    run, proc = _dbt(tmp_path, "run")
    assert {s for s, _ in run.values()} == {"success"}, proc.stdout[-3000:]
    con = duckdb.connect(str(tmp_path / "warehouse" / "grid.duckdb"))
    try:
        con.sql("update main_marts.fact_intensity set intensity_p05_g_kwh = intensity_g_kwh + 1 "
                "where ts_utc = (select min(ts_utc) from main_marts.fact_intensity "
                "where intensity_g_kwh is not null)")
    finally:
        con.close()
    tests, proc = _dbt(tmp_path, "test", "--select", "assert_deterministic_within_mc_interval")
    assert tests == {"assert_deterministic_within_mc_interval": ("fail", 1)}, proc.stdout[-3000:]


def test_a_deleted_day_and_an_empty_a01_position_fail_their_tests(tmp_path):
    """RUNBOOK Checkpoint 7: break one on purpose. Until 17.10.2026 the
    coverage test could not see a deleted day (audit B3), and an empty A01
    position was filled with the last value (A6). run, then test, so that the
    first failure does not skip the second test. Since 25.10.2026 the price
    payload also has no manifest row, so its fact rows have no provenance, and
    the empty position reaches fact_generation as well."""
    _project(tmp_path, [("A75", DE, de_a75(broken=True)), ("A44", DE, de_a44())], unrecorded=("A44",))
    run, proc = _dbt(tmp_path, "run")
    assert {s for s, _ in run.values()} == {"success"}, proc.stdout[-3000:]
    tests, _ = _dbt(tmp_path, "test", "--store-failures")
    failed = {n: f for n, (s, f) in tests.items() if s != "pass"}
    assert failed == {"assert_step_count_per_local_day": 1, "not_null_int_generation_gapfilled_mw": 1,
                      "not_null_fact_generation_mw": 1,
                      "assert_every_fact_row_resolves_to_the_manifest": 1}
    con = duckdb.connect(str(tmp_path / "warehouse" / "grid.duckdb"), read_only=True)
    try:
        rows = con.sql("select zone_eic, psr_type, local_date, steps_present, steps_expected "
                       "from main_dbt_test__audit.assert_step_count_per_local_day").fetchall()
    finally:
        con.close()
    assert rows == [(DE, "B04", dt.date(2026, 3, 30), 0, 96)]


def test_the_committed_sample_builds_with_the_sample_target(tmp_path):
    """README: a clone without a token builds the warehouse from the synthetic
    sample in curated/sample/. The `sample` target reads it in place of raw/
    and writes a file of its own; every node must pass, with GRID_ROOT the
    repository itself, as on a reader's clone."""
    (tmp_path / "profiles").mkdir()
    (tmp_path / "profiles" / "profiles.yml").write_text(
        "grid_intensity:\n  target: sample\n  outputs:\n    sample:\n      type: duckdb\n"
        f"      path: '{(tmp_path / 'sample.duckdb').as_posix()}'\n      threads: 1\n",
        encoding="utf-8",
    )
    env = {**os.environ, "GRID_ROOT": REPO.as_posix(), "DO_NOT_TRACK": "1",
           "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
    proc = subprocess.run(
        [sys.executable, "-c", "from dbt.cli.main import cli; cli()", "build", "--target", "sample",
         "--project-dir", str(REPO / "dbt"), "--profiles-dir", str(tmp_path / "profiles"),
         "--target-path", str(tmp_path / "target"), "--log-path", str(tmp_path / "logs")],
        env=env, capture_output=True, text=True, timeout=600,
    )
    results = json.loads((tmp_path / "target" / "run_results.json").read_text(encoding="utf-8"))["results"]
    status = {r["unique_id"].split(".")[2]: r["status"] for r in results}
    assert proc.returncode == 0 and set(status.values()) <= {"success", "pass"}, proc.stdout[-3000:]
    assert {"fact_generation", "fact_intensity", "fact_price", "assert_deterministic_within_mc_interval",
            "assert_every_fact_row_resolves_to_the_manifest"} <= set(status)
    con = duckdb.connect(str(tmp_path / "sample.duckdb"), read_only=True)
    try:
        [(sources,)] = con.sql("select count(distinct source_sha256) from main_marts.fact_generation").fetchall()
        [(banded,)] = con.sql("select count(intensity_p05_g_kwh) from main_marts.fact_intensity").fetchall()
    finally:
        con.close()
    assert sources == 2 and banded > 0
