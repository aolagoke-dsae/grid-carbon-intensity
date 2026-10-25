"""The Monte Carlo draws of every priced emission factor, one row per draw
and fuel: the same draws for every step.

A factor's error is the same in every hour, so a day, a year or the saving of
a load shift must take its interval from the same draw at every step it
spans. These rows are those draws. int_intensity_interval reads them for each
step's interval, and any total can take its own interval in SQL: weight each
draw's factors by the total's energy by fuel, then take the percentiles over
draw_id.

The sampling stays in one place: src/transform/intensity.py,
shared_factor_draws(), the two-piece lognormal of method 2.0.0, applied to
config/ipcc_ar5_factors.csv, the file dim_production_type reads. The draw
count and the seed are the project vars mc_draws and mc_seed; the rule that
fixed the count is in RUNBOOK Stage 6.

Every path hangs off GRID_ROOT, the repository root, as in the SQL models.
intensity.py is loaded from there by its path, so nothing is added to
sys.path: the repository root holds a folder named dbt.
"""
import importlib.util
import os
import sys
from pathlib import Path

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
    n_draws = int(dbt.config.get("mc_draws"))
    seed = int(dbt.config.get("mc_seed"))
    intensity = _intensity()
    factors = intensity.load_factors(
        Path(os.environ.get("GRID_ROOT", "..")).resolve() / "config" / "ipcc_ar5_factors.csv")
    fuels, draws = intensity.shared_factor_draws(factors, n_draws, seed)
    return pd.DataFrame({
        "draw_id": [d + 1 for _ in fuels for d in range(n_draws)],
        "psr_type": [p for p in fuels for _ in range(n_draws)],
        "ef_g_kwh": draws.T.reshape(-1),
        "mc_seed": seed,
        "method_version": intensity.METHOD_VERSION,
    })
