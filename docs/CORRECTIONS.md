# Corrections

Dated corrections to the intensity method and to the check that guards it,
moved here word for word from the README on 10 November 2026. Each was
committed when it was made, and the commit history is the record.

Other dated corrections stay beside what they correct: the four changes of a
factor value, each with its evidence and its own commit, in
[`FACTOR_CHECK.md`](FACTOR_CHECK.md) (decisions 1, 2 and 5); the dbt row of
**What is not built** in the README (08.10.2026); and the daylight-saving fix
under **Tests** in the README (17.09.2026).

## The acceptance criterion

The criterion that governs the whole build: the deterministic point estimate
must fall inside the sampled 90% interval (README, **Stack**).

> Corrected 7 October 2026. The test behind this criterion used to compare the
> sampled median against the sampled percentiles, which is true by definition
> and could never fail. The headline control was vacuous for seven weeks.
>
> Corrected 17 October 2026. Once the test was real, it held for coal- and
> gas-heavy mixes and failed for nuclear-heavy French ones, because the sampler
> moved the median of every skewed factor band. The sampler now keeps each
> published median, and the criterion holds on all of 729 French-like test
> mixes (see **The interval is the deliverable** in the README).

## The factor sampler, method 2.0.0

> Changed 17 October 2026 (method 2.0.0). Until then the default was a
> triangular with the published median as its mode. For a skewed band that
> moves the median — nuclear's came out at 37.7 instead of 12 — so French,
> nuclear-heavy hours came out too dirty and their deterministic point fell
> outside its own interval. Hydro already had a lognormal, but with an open
> upper tail that ran past AR5's maximum. A triangular over the hydro range
> would put the median near 650 gCO₂e/kWh, dirtier than gas.
