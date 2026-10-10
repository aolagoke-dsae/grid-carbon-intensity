"""land_tree lands exactly one retrieval per logical item.

raw/ is append-only since 10.10.2026, so a re-pulled year is two files on
disk. Landing both would double every row; landing a _failed/ response would
land an error page.
"""
import pandas as pd

import xml_to_parquet as X

NS = "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:3"


def _a44(price: float) -> str:
    return (
        f'<?xml version="1.0" encoding="utf-8"?><Publication_MarketDocument xmlns="{NS}">'
        "<mRID>m</mRID><revisionNumber>1</revisionNumber><type>A44</type><TimeSeries>"
        "<mRID>1</mRID><in_Domain.mRID>Z</in_Domain.mRID><out_Domain.mRID>Z</out_Domain.mRID>"
        "<curveType>A03</curveType><Period><timeInterval><start>2025-06-01T22:00Z</start>"
        "<end>2025-06-01T23:00Z</end></timeInterval><resolution>PT60M</resolution>"
        f"<Point><position>1</position><price.amount>{price}</price.amount></Point>"
        "</Period></TimeSeries></Publication_MarketDocument>"
    )


def test_only_the_newest_accepted_retrieval_is_landed(tmp_path):
    item = tmp_path / "raw" / "A44" / "Z" / "2025"
    (item / "_failed").mkdir(parents=True)
    (item / "20261006T163047Z_d9687790.xml").write_text(_a44(10.0), encoding="utf-8")
    newest = item / "20261006T183150Z_9d48b590.xml"
    newest.write_text(_a44(20.0), encoding="utf-8")
    (item / "_failed" / "20261010T090000Z_00000000.xml").write_text(
        "<html>401</html>", encoding="utf-8"
    )
    counts = X.land_tree(tmp_path / "raw", tmp_path / "raw" / "parquet")
    df = pd.read_parquet(tmp_path / "raw" / "parquet" / "a44.parquet")
    assert counts == {"A44": 1}
    assert df["quantity"].tolist() == [20.0]
    assert df["source_file"].tolist() == [newest.as_posix()]
