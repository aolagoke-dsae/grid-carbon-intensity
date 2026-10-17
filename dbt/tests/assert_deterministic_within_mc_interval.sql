{{ config(enabled = false) }}

/*  DISABLED until the marts layer lands a fact carrying both the deterministic
    intensity and the Monte Carlo band. Until 17.10.2026 this file was a
    `select ... where false` guard, which dbt reported as a PASS although it
    tested nothing (audit B7). Disabled, it says what it is.

    What it will catch: a biased sampler. If the deterministic point estimate
    escapes the interval built around it, the propagation is wrong — not the
    estimate. In Python the same criterion is already tested, including on
    729 French-like mixes (src/transform/test_intensity.py).

    The interval is produced by src/transform/intensity.py (two-piece
    lognormal, method 2.0.0). When the fact exists: point the query at it,
    return the rows whose point lies outside [p05, p95], and remove the config
    line above.                                                                */
select 1 as placeholder
where false
