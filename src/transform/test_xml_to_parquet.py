"""The raw landing: stated points only, both domains, provenance on every row.

Until 17.10.2026 this file held one test and every other behaviour of
xml_to_parquet.py could change unnoticed, including a reversion of the A44
fix (audit A8). The dbt models are checked against parse() on landed
fixtures in test_dbt_models.py.

raw/ is append-only since 10.10.2026, so a re-pulled year is two files on
disk. Landing both would double every row; landing a _failed/ response would
land an error page.
"""
import datetime as dt
import hashlib

import pandas as pd
import pytest

import xml_to_parquet as X
from entsoe_parse import parse
from test_parse import SAMPLE

NS44 = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"
DE, FR = "10Y1001A1001A82H", "10YFR-RTE------C"

COLUMNS = [
    "document_type", "revision_number", "source_file", "source_sha256",
    "zone_eic", "in_domain_eic", "out_domain_eic", "psr_type", "direction",
    "classification_sequence", "curve_type", "unit_name",
    "period_start_utc", "period_end_utc", "resolution", "step_hours", "n_steps",
    "position", "quantity",
]


def _publication(doc_type, series):
    return (
        f'<?xml version="1.0" encoding="utf-8"?><Publication_MarketDocument xmlns="{NS44}">'
        f"<mRID>m</mRID><revisionNumber>1</revisionNumber><type>{doc_type}</type>"
        f"{series}</Publication_MarketDocument>"
    )


def _a44_series(price, cs=None, zone="Z"):
    cs_el = f"<{X.CS_FIELD}>{cs}</{X.CS_FIELD}>" if cs is not None else ""
    return (
        f"<TimeSeries><mRID>1</mRID><in_Domain.mRID>{zone}</in_Domain.mRID>"
        f"<out_Domain.mRID>{zone}</out_Domain.mRID>{cs_el}"
        "<curveType>A03</curveType><Period><timeInterval><start>2025-06-01T22:00Z</start>"
        "<end>2025-06-01T23:00Z</end></timeInterval><resolution>PT60M</resolution>"
        f"<Point><position>1</position><price.amount>{price}</price.amount></Point>"
        "</Period></TimeSeries>"
    )


def _a44(price):
    return _publication("A44", _a44_series(price))


def _store(folder, when, text):
    """Write text the way raw_store does: <UTC time>_<sha8>.xml."""
    folder.mkdir(parents=True, exist_ok=True)
    body = text.encode("utf-8")
    path = folder / f"{when}_{hashlib.sha256(body).hexdigest()[:8]}.xml"
    path.write_bytes(body)
    return path


@pytest.fixture
def a75(tmp_path):
    path = _store(tmp_path, "20261017T212639Z", SAMPLE)
    return path, X.land(path)


def test_a75_lands_stated_points_only(a75):
    """5 stated B15 points and 2 B10 points, not 96 + 96 expanded steps:
    the carry-forward belongs to the SQL, where the lineage graph shows it."""
    _, df = a75
    assert list(df.columns) == COLUMNS
    assert len(df) == 7
    assert df.groupby("psr_type").size().to_dict() == {"B10": 2, "B15": 5}
    assert set(df["n_steps"]) == {96}
    assert df.loc[df["psr_type"] == "B15", "position"].tolist() == [1, 19, 43, 68, 89]


def test_a75_keeps_both_domains_and_the_direction(a75):
    _, df = a75
    b15, b10 = df[df["psr_type"] == "B15"], df[df["psr_type"] == "B10"]
    assert set(b15["direction"]) == {"generation"} and set(b10["direction"]) == {"consumption"}
    assert set(b15["in_domain_eic"]) == {DE} and b15["out_domain_eic"].isna().all()
    assert set(b10["out_domain_eic"]) == {DE} and b10["in_domain_eic"].isna().all()
    assert set(df["zone_eic"]) == {DE}


def test_landed_points_agree_with_the_parser(a75):
    """Every stated point, placed at its timestamp, carries the value parse()
    gives that step."""
    _, df = a75
    parsed = {(r["psr"], r["direction"], r["ts_utc"]): r["mw"] for r in parse(SAMPLE)}
    for row in df.itertuples():
        ts = (row.period_start_utc.to_pydatetime().replace(tzinfo=dt.timezone.utc)
              + dt.timedelta(hours=row.step_hours * (row.position - 1)))
        assert parsed[(row.psr_type, row.direction, ts)] == pytest.approx(row.quantity)


def test_dtypes_and_naive_utc_timestamps(a75):
    _, df = a75
    assert str(df["classification_sequence"].dtype) == "Int64"
    assert df["classification_sequence"].isna().all(), "A75 has no curve id"
    assert str(df["position"].dtype) == "int64" and str(df["quantity"].dtype) == "float64"
    # Fixed, not inferred: pandas 2 inferred nanoseconds, pandas 3 microseconds.
    assert str(df["period_start_utc"].dtype) == "datetime64[us]"
    assert str(df["period_end_utc"].dtype) == "datetime64[us]"
    assert df["period_start_utc"].iat[0] == pd.Timestamp("2026-08-01 00:00")


def test_every_row_carries_its_provenance(a75):
    path, df = a75
    assert set(df["source_file"]) == {path.as_posix()}
    assert set(df["source_sha256"]) == {hashlib.sha256(path.read_bytes()).hexdigest()}


def test_a44_lands_both_curves_without_a_direction(tmp_path):
    """The A44 fix of 08.10.2026: price.amount is read, the curve id kept,
    and no direction is invented for a document that has none."""
    xml = _publication("A44", _a44_series(10.5, cs=1) + _a44_series(-3.0, cs=2))
    df = X.land(_store(tmp_path, "20261006T183150Z", xml))
    assert df["classification_sequence"].tolist() == [1, 2]
    assert df["quantity"].tolist() == [10.5, -3.0]
    assert df["direction"].isna().all()
    assert set(df["in_domain_eic"]) == set(df["out_domain_eic"]) == {"Z"}


def test_a11_keeps_the_border(tmp_path):
    """A cross-border flow runs from out_Domain to in_Domain. Landed with one
    zone column, it lost the border (audit A9)."""
    series = (
        f"<TimeSeries><mRID>1</mRID><in_Domain.mRID>{FR}</in_Domain.mRID>"
        f"<out_Domain.mRID>{DE}</out_Domain.mRID><curveType>A01</curveType>"
        "<quantity_Measure_Unit.name>MAW</quantity_Measure_Unit.name>"
        "<Period><timeInterval><start>2025-06-01T22:00Z</start><end>2025-06-01T23:00Z</end>"
        "</timeInterval><resolution>PT60M</resolution>"
        "<Point><position>1</position><quantity>1234</quantity></Point></Period></TimeSeries>"
    )
    df = X.land(_store(tmp_path, "20261017T220000Z", _publication("A11", series)))
    assert (df["out_domain_eic"].iat[0], df["in_domain_eic"].iat[0]) == (DE, FR)


def test_an_acknowledgement_is_refused(tmp_path):
    ack = ('<?xml version="1.0" encoding="UTF-8"?><Acknowledgement_MarketDocument '
           'xmlns="urn:iec62325.351:tc57wg16:451-1:acknowledgementdocument:7:0"><mRID>a</mRID>'
           "<Reason><code>999</code><text>No matching data found</text></Reason>"
           "</Acknowledgement_MarketDocument>")
    with pytest.raises(ValueError, match="No matching data found"):
        X.land(_store(tmp_path, "20261017T220000Z", ack))


def test_only_the_newest_accepted_retrieval_is_landed(tmp_path):
    item = tmp_path / "raw" / "A44" / "Z" / "2025"
    _store(item, "20261006T163047Z", _a44(10.0))
    newest = _store(item, "20261006T183150Z", _a44(20.0))
    _store(item / "_failed", "20261010T090000Z", "<html>401</html>")
    counts = X.land_tree(tmp_path / "raw", tmp_path / "raw" / "parquet")
    df = pd.read_parquet(tmp_path / "raw" / "parquet" / "a44.parquet")
    assert counts == {"A44": 1}
    assert df["quantity"].tolist() == [20.0]
    assert df["source_file"].tolist() == [newest.as_posix()]


def test_a_file_whose_bytes_no_longer_match_its_name_is_refused(tmp_path):
    item = tmp_path / "raw" / "A44" / "Z" / "2025"
    path = _store(item, "20261006T183150Z", _a44(20.0))
    path.write_text(_a44(99.0), encoding="utf-8")      # edited after it was stored
    with pytest.raises(RuntimeError, match="1 payload"):
        X.land_tree(tmp_path / "raw", tmp_path / "raw" / "parquet")


def test_strict_mode_raises_and_keep_going_lands_the_rest(tmp_path, capsys):
    """A document type that failed on every file used to produce no parquet,
    no non-zero exit and no test failure."""
    raw = tmp_path / "raw"
    _store(raw / "A44" / "Z" / "2025", "20261006T183150Z", _a44(20.0))
    _store(raw / "A44" / "Y" / "2025", "20261006T183151Z", "<not xml")
    with pytest.raises(RuntimeError, match="1 payload"):
        X.land_tree(raw, raw / "parquet")
    counts = X.land_tree(raw, raw / "parquet", strict=False)
    assert counts == {"A44": 1}
    assert "! " in capsys.readouterr().out


def test_zones_outside_the_analysis_stay_in_raw(tmp_path):
    """The third-zone diagnostic pulls PL, NL and IE-SEM into raw/ (Master
    Plan, 2.3). They are measured there and not landed, so the warehouse, its
    dbt tests and every intensity figure stay on the two analysis zones."""
    raw = tmp_path / "raw"
    _store(raw / "A44" / "Z" / "2025", "20261006T183150Z", _a44(20.0))
    _store(raw / "A44" / "Y" / "2025", "20261006T183151Z", _a44(30.0))
    counts = X.land_tree(raw, raw / "parquet", skip_zones=frozenset({"Y"}))
    df = pd.read_parquet(raw / "parquet" / "a44.parquet")
    assert counts == {"A44": 1}
    assert df["quantity"].tolist() == [20.0]


def test_the_command_line_skips_exactly_the_zones_outside_the_analysis():
    assert X.zones_outside_analysis() == {
        "10YNL----------L", "10YPL-AREA-----S", "10Y1001A1001A59C",
    }
