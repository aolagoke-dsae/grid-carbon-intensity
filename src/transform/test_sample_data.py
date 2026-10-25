"""The synthetic sample in curated/sample/: what is committed is what the
builder makes, nothing in it is real data, and the builder cannot be pointed
at the real raw/. The dbt build of the sample is tested in
test_dbt_models.py and run in CI's dbt job."""
import csv
from pathlib import Path

import pandas as pd
import pytest

import sample_data

REPO = Path(__file__).resolve().parents[2]
COMMITTED = REPO / "curated" / "sample" / "raw"

# The values test_parse.py lifted from a real DE-LU A75 payload (B15 and the
# B10 pumping leg), and their rounded forms, which the dbt fixtures carried
# until 25.10.2026.
REAL_VALUES = ("74.267", "71.451", "72.415", "73.008", "115.8084", "113.1906", "115.8", "113.2")


def test_the_committed_sample_is_what_the_builder_makes(tmp_path, monkeypatch):
    """Prevents: a sample that drifts from its builder, or from the dbt
    fixtures it is made of. Rebuilt from nothing, it must give the same
    payloads and manifest byte for byte and the same landed rows."""
    monkeypatch.chdir(tmp_path)
    counts = sample_data.build()
    fresh = tmp_path / "curated" / "sample" / "raw"
    files = sorted(p.relative_to(COMMITTED).as_posix() for p in COMMITTED.rglob("*") if p.is_file())
    assert files == sorted(p.relative_to(fresh).as_posix() for p in fresh.rglob("*") if p.is_file())
    for rel in files:
        if rel.endswith(".parquet"):
            pd.testing.assert_frame_equal(pd.read_parquet(COMMITTED / rel), pd.read_parquet(fresh / rel))
        else:
            assert (COMMITTED / rel).read_bytes() == (fresh / rel).read_bytes(), rel
    assert counts == {"A44": 2, "A75": 61}


def test_every_payload_is_synthetic_and_recorded():
    """Every payload has its manifest row, digest and synthetic URL, and none
    carries a value of the real payload test_parse.py quotes."""
    with (COMMITTED / "manifest.csv").open(newline="", encoding="utf-8") as fh:
        rows = {r["path"]: r for r in csv.DictReader(fh)}
    payloads = sorted(COMMITTED.rglob("*.xml"))
    assert len(payloads) == len(rows) == 3
    for xml in payloads:
        row = rows[xml.relative_to(REPO).as_posix()]
        assert row["url"].startswith("synthetic://") and row["rejected"] == "0"
        text = xml.read_text(encoding="utf-8")
        assert not [v for v in REAL_VALUES if f">{v}<" in text], xml.name


def test_the_builder_refuses_a_raw_that_is_not_a_sample(tmp_path, monkeypatch):
    """Prevents: `python -m src.transform.sample_data .` deleting the real raw/."""
    monkeypatch.chdir(tmp_path)
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "manifest.csv").write_text(
        "retrieved_at_utc,path,url,http_status,bytes,sha256,rejected,attempt,revision\n"
        "2026-10-17T21:26:39+00:00,raw/A75/x.xml,https://web-api.tp.entsoe.eu/api?x,200,1,ab,0,1,\n",
        encoding="utf-8")
    with pytest.raises(ValueError, match="refusing"):
        sample_data.build(Path("."))
    assert (raw / "manifest.csv").exists()
