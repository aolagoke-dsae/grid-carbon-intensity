/*  DORMANT until the marts layer lands a fact carrying both the deterministic
    intensity and the Monte Carlo band.

    What it will catch: a biased sampler. If the deterministic point estimate
    escapes the distribution it was drawn from, the propagation is wrong — not
    the estimate.

    The interval is produced by src/transform/intensity.py (lognormal for
    skewed factor bands, triangular otherwise). Point this test at the fact as
    soon as it exists, and delete the guard below.                             */
select 1 as placeholder
where false
