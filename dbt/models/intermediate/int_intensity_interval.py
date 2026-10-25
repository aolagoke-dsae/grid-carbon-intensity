"""Each generation step's Monte Carlo interval: the 5th, 50th and 95th
percentiles of its mix under the draws of dim_factor_draw.

The mix is the step's priced generation energy by fuel, MW times step_hours
from int_generation_gapfilled; the fuels are those dim_factor_draw draws,
which intensity.py prices by the rule dim_production_type uses, a median and
a band. Every step takes the same draws, so the intervals of steps that are
summed later stay consistent with each other. A step without priced energy
gets no row. fact_intensity sets these beside its point, and withholds them
wherever it withholds the point.

The arithmetic is src/transform/intensity.py's step_intervals(), loaded by
its path under GRID_ROOT as in dim_factor_draw. src/checks/validate.py,
check_stage6_marts, recomputes every interval from the parser's rows.
"""
import importlib.util
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd


def _intensity():
    """src/transform/intensity.py under GRID_ROOT, loaded as a module."""
    path = Path(os.environ.get("GRID_ROOT", "..")).resolve() / "src" / "transform" / "intensity.py"
    spec = importlib.util.spec_from_file_location("grid_intensity", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module          # dataclasses look their module up here
    spec.loader.exec_module(module)
    return module


def model(dbt, session):
    dbt.config(materialized="table")
    intensity = _intensity()

    d = dbt.ref("dim_factor_draw").query(
        "d", "select psr_type, draw_id, ef_g_kwh from d order by psr_type, draw_id").fetchnumpy()
    fuels = list(dict.fromkeys(d["psr_type"]))
    n_draws = len(d["draw_id"]) // len(fuels)
    ids = np.asarray(d["draw_id"]).reshape(len(fuels), n_draws)
    if fuels != sorted(fuels) or not (ids == np.arange(1, n_draws + 1)).all():
        raise ValueError("dim_factor_draw is not one row per draw 1..n for every fuel")
    draws = np.asarray(d["ef_g_kwh"], dtype=float).reshape(len(fuels), n_draws).T

    columns = ", ".join(
        f"coalesce(sum(mw * step_hours) filter (where psr_type = '{p}'), 0) as \"{p}\"" for p in fuels)
    e = dbt.ref("int_generation_gapfilled").query(
        "g", f"select zone_eic, ts_utc, {columns} from g where direction = 'generation' group by all"
    ).fetchnumpy()
    energy = np.column_stack([np.asarray(e[p], dtype=float) for p in fuels])

    q = intensity.step_intervals(energy, draws)
    keep = ~np.isnan(q[:, 0])
    return pd.DataFrame({
        "zone_eic": np.asarray(e["zone_eic"], dtype=object)[keep],
        "ts_utc": np.asarray(e["ts_utc"]).astype("datetime64[us]")[keep],
        "intensity_p05_g_kwh": q[keep, 0],
        "intensity_p50_g_kwh": q[keep, 1],
        "intensity_p95_g_kwh": q[keep, 2],
        "mc_draws": n_draws,
    })
