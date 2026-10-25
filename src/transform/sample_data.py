"""The payloads of the dbt fixture tests, and the synthetic sample in
curated/sample/ that lets a clone build the warehouse without a token.

ENTSO-E's Terms of Use open neither A75 nor A44 for re-use (README, Licence),
so the sample is made, not pulled. It is the payloads
src/transform/test_dbt_models.py builds the dbt models on, stored as
raw_store stores a retrieval, each with its manifest row, and landed by
xml_to_parquet: two local days in each zone that carry the traps the pipeline
exists for -- both daylight-saving transitions (92 quarter-hours in DE-LU, 25
hours in France), A03 carry-forward, a pump-only series, a series stated net,
a day that changes resolution, a series published only while a unit runs,
and an A44 payload with two price curves. Every number is invented, nothing
comes from ENTSO-E, and the sample is MIT like the code. Until 25.10.2026 the
DE-LU fixture carried five B15 points and two pumping values lifted from a
real payload (test_parse.py); they are invented here as well.

From the repository root:

    python -m src.transform.sample_data        # rewrites curated/sample/raw/
    GRID_ROOT=. dbt build --project-dir dbt --profiles-dir dbt --target sample

The `sample` target of dbt/profiles.example.yml reads curated/sample/raw/ in
place of raw/ and builds warehouse/sample.duckdb, so it never touches the
real warehouse. The sample shows that the code runs from a clean clone; it
reproduces no figure.
"""
from __future__ import annotations

import csv
import datetime as dt
import hashlib
import shutil
import sys
from pathlib import Path

try:                        # run as a module from the repository root
    from src.ingest import raw_store
    from src.transform import xml_to_parquet
except ImportError:         # imported with src/ingest and src/transform on sys.path (pytest)
    import raw_store
    import xml_to_parquet

NS75 = "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"
NS44 = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
DE, FR = "10Y1001A1001A82H", "10YFR-RTE------C"

# Local delivery days, in UTC. Berlin springs forward on 29 March 2026 (23 h),
# Paris falls back on 25 October 2026 (25 h).
DE_DAYS = [("2026-03-28T23:00Z", "2026-03-29T22:00Z"), ("2026-03-29T22:00Z", "2026-03-30T22:00Z")]
FR_DAYS = [("2026-10-24T22:00Z", "2026-10-25T23:00Z"), ("2026-10-25T23:00Z", "2026-10-26T23:00Z")]
# Trap 1: five stated points across a day of A03, the rest carried forward.
B15 = {1: 70.0, 19: 72.5, 43: 71.5, 68: 72.5, 89: 73.0}

SAMPLE = Path("curated") / "sample"
STORED_AT = dt.datetime(2026, 10, 17, 22, 0, tzinfo=dt.timezone.utc)   # names every stored payload


def series(zone, psr, day, resolution, points, direction="generation", curve="A03"):
    """One A75 TimeSeries of one Period, stating `points` {position: MW}."""
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


def a75(series_list):
    return (f'<?xml version="1.0" encoding="UTF-8"?><GL_MarketDocument xmlns="{NS75}">'
            f'{"".join(series_list)}</GL_MarketDocument>')


def de_a75(broken=False):
    """DE-LU over the spring transition, quarter-hourly. broken: B04 loses
    its second day, and an A01 series misses one position."""
    s = []
    for i, day in enumerate(DE_DAYS):
        s.append(series(DE, "B19", day, "PT15M", {1: 1000.0, 40: 1200.0, 80: 900.0} if i == 0 else {1: 800.0, 50: 700.0}))
        if not (broken and i == 1):
            s.append(series(DE, "B04", day, "PT15M", {1: 300.0}))
        s.append(series(DE, "B15", day, "PT15M", B15))
        s.append(series(DE, "B10", day, "PT15M", {1: 120.0, 2: 110.0}, direction="consumption"))
        if broken:
            n = 92 if i == 0 else 96
            s.append(series(DE, "B16", day, "PT15M",
                            {p: 50.0 for p in range(1, n + 1) if not (i == 0 and p == 7)}, curve="A01"))
    return a75(s)


def fr_a75(offshore_from_day=1):
    """France over the autumn transition, hourly, moving to quarter-hours on
    its second day. Offshore wind (B18) is published from day
    `offshore_from_day`: 1 for the fixture tests, which declare its window in
    config/sparse_series.csv, 0 for the sample, which reads the real config."""
    s = []
    for i, day in enumerate(FR_DAYS):
        if i == 0:
            s.append(series(FR, "B14", day, "PT60M", {1: 40000.0, 10: 38000.0}))
        else:   # RTE's move to PT15M, as on 19.12.2024: one hourly step, then 92 quarter-hours
            s.append(series(FR, "B14", (day[0], "2026-10-26T00:00Z"), "PT60M", {1: 41000.0}))
            s.append(series(FR, "B14", ("2026-10-26T00:00Z", day[1]), "PT15M", {1: 41000.0}))
        s.append(series(FR, "B10", day, "PT60M", {1: 200.0, 5: 0.0}))
        s.append(series(FR, "B10", day, "PT60M", {1: 0.0, 5: 300.0}, direction="consumption"))
    # Reservoir hydro stated net, as in RTE's hourly A75: on the second day 20
    # generating hours, then four pumping hours that carry only the
    # consumption leg. A01, so every hour is stated and nothing is carried.
    s.append(series(FR, "B12", FR_DAYS[0], "PT60M", {1: 900.0}))
    s.append(series(FR, "B12", (FR_DAYS[1][0], "2026-10-26T19:00Z"), "PT60M",
                    {p: 800.0 for p in range(1, 21)}, curve="A01"))
    s.append(series(FR, "B12", ("2026-10-26T19:00Z", FR_DAYS[1][1]), "PT60M",
                    {p: 150.0 for p in range(1, 5)}, direction="consumption", curve="A01"))
    for day in FR_DAYS[offshore_from_day:]:
        s.append(series(FR, "B18", day, "PT60M", {1: 30.0}))
    # Hard coal while one unit runs, ten hours on the first day only: declared
    # in config/sparse_series.csv, so its short day and its absent day pass.
    s.append(series(FR, "B05", ("2026-10-25T05:00Z", "2026-10-25T15:00Z"), "PT60M", {1: 500.0}))
    return a75(s)


def de_a44():
    """One DE-LU day of day-ahead prices with two curves, as a real A44
    payload carries them (trap 5); only classificationSequence tells them apart."""
    def curve(cs, price):
        return (
            f"<TimeSeries><mRID>{cs}</mRID><in_Domain.mRID>{DE}</in_Domain.mRID>"
            f"<out_Domain.mRID>{DE}</out_Domain.mRID>"
            f"<{xml_to_parquet.CS_FIELD}>{cs}</{xml_to_parquet.CS_FIELD}><curveType>A03</curveType>"
            f"<Period><timeInterval><start>{DE_DAYS[1][0]}</start><end>{DE_DAYS[1][1]}</end>"
            f"</timeInterval><resolution>PT60M</resolution>"
            f"<Point><position>1</position><price.amount>{price}</price.amount></Point>"
            "</Period></TimeSeries>"
        )
    return (f'<?xml version="1.0" encoding="utf-8"?><Publication_MarketDocument xmlns="{NS44}">'
            f"<mRID>m</mRID><revisionNumber>1</revisionNumber><type>A44</type>"
            f"{curve(1, 90.0)}{curve(2, 92.0)}</Publication_MarketDocument>")


def sample_payloads():
    """(document type, zone, XML) of the sample: the fixtures, with offshore
    wind from the first day."""
    return [("A75", DE, de_a75()), ("A75", FR, fr_a75(offshore_from_day=0)), ("A44", DE, de_a44())]


def _is_sample(raw: Path) -> bool:
    """Only a raw/ whose every manifest row is synthetic may be rewritten."""
    manifest = raw / "manifest.csv"
    if not raw.exists():
        return True
    if not manifest.exists():
        return not any(raw.iterdir())
    with manifest.open(newline="", encoding="utf-8") as fh:
        return all(row["url"].startswith("synthetic://") for row in csv.DictReader(fh))


def build(out: Path = SAMPLE) -> dict:
    """Write the sample under `out`/raw and land it; returns {doc: stated points}.

    Run from the repository root with a relative `out`: the paths in the
    manifest and in the parquet are taken as given. A raw/ that holds anything
    but an earlier sample is refused, so the real raw/ can never be rewritten.
    """
    raw = Path(out) / "raw"
    if not _is_sample(raw):
        raise ValueError(f"{raw} holds more than an earlier sample; refusing to rewrite it")
    if raw.exists():
        shutil.rmtree(raw)
    for doc, zone, text in sample_payloads():
        body = text.encode("utf-8")
        sha = hashlib.sha256(body).hexdigest()
        path = raw / doc / zone / "2026" / f"{STORED_AT:%Y%m%dT%H%M%SZ}_{sha[:8]}.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(body)
        raw_store.append_manifest(raw / "manifest.csv", {
            "retrieved_at_utc": STORED_AT.isoformat(timespec="seconds"),
            "path": path.as_posix(), "url": f"synthetic://{doc}/{zone}/2026",
            "http_status": 200, "bytes": len(body), "sha256": sha,
            "rejected": 0, "attempt": 1, "revision": "1",
        })
    return xml_to_parquet.land_tree(raw, raw / "parquet")


if __name__ == "__main__":
    counts = build(Path(sys.argv[1]) if len(sys.argv) > 1 else SAMPLE)
    for doc, n in counts.items():
        print(f"{doc}: {n:,} stated points")
