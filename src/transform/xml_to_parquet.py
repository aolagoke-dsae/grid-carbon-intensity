"""Land ENTSO-E XML as raw parquet - stated points only, NO business logic.

Deliberate architecture note for the README:
  The A03 gap-filling, the generation/consumption split and the MW->MWh
  conversion all live in dbt, not here. The raw layer stays raw so the
  transformations are visible in the DAG and testable in the warehouse.
  src/transform/entsoe_parse.py keeps the Python implementation of the same
  logic for A75 and serves as the independent oracle the SQL is checked
  against: src/transform/test_dbt_models.py builds the models on landed
  fixtures and compares them with parse() step by step (since 17.10.2026;
  until then no such check existed). entsoe_prices_parse.py is the A44 twin.

One column is landed that is not a stated point: classification_sequence.
It is read straight off the TimeSeries without interpretation, and it has to
be here because it is the only field separating the two complete, disagreeing
day-ahead price curves a single A44 payload contains. See TRAP 5 in
entsoe_prices_parse.py. Dropping it is not a simplification - it makes the
payload unusable downstream.

Both domains are landed, as in_domain_eic and out_domain_eic. A cross-border
flow (A11) is defined by the pair, and until 17.10.2026 only one of them
survived (audit A9). zone_eic is the in-domain where there is one, else the
out-domain: a convenience for the single-zone documents.

Every row carries its provenance: source_file and source_sha256, the SHA-256
of the stored bytes, which is the key of that retrieval's row in
raw/manifest.csv (audit B6). land_tree refuses a file whose bytes no longer
match the digest in its name.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pandas as pd

RES_HOURS = {"PT15M": 0.25, "PT30M": 0.5, "PT60M": 1.0, "PT1H": 1.0}

CS_FIELD = "classificationSequence_AttributeInstanceComponent.position"

# The value element differs by document type and there is no overlap: the real
# DE-LU A44 payload contains 50,044 <price.amount> and zero <quantity>.
# Reading only 'quantity' made float(None) raise on every A44 point, which
# land_tree then printed as "! skipped" and walked past.
VALUE_ELEMENTS = ("quantity", "price.amount")

# raw_store names every retrieval <UTC time>_<first 8 hex digits of sha256>.
STORED_NAME = re.compile(r"^\d{8}T\d{6}Z_([0-9a-f]{8})\.xml$")

DTYPES = {
    "classification_sequence": "Int64",   # nullable: None where a zone has one curve
    # Microseconds, the resolution of DuckDB's TIMESTAMP. Left to inference,
    # pandas 2 picked nanoseconds and pandas 3 picks microseconds, so the
    # parquet schema depended on the pandas version installed.
    "period_start_utc": "datetime64[us]",
    "period_end_utc": "datetime64[us]",
    "step_hours": "float64",
    "n_steps": "int64",
    "position": "int64",
    "quantity": "float64",
}


def _iso(s: str) -> dt.datetime:
    """Accept both the minute and the seconds-bearing ENTSO-E forms.

    strptime with a single fixed pattern breaks silently on the second form.
    """
    s = (s or "").strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        raise ValueError(f"timestamp carries no offset: {s!r}")
    return d.astimezone(dt.timezone.utc)


def _ns_of(root) -> dict:
    """Read the namespace off the root element.

    A hardcoded namespace is a trap: A75 is 451-6:generationloaddocument:3:0,
    A44 is 451-3:publicationdocument:7:3, and this module previously carried a
    constant for ':7:0' - a minor version that does not match the payload on
    disk. It was dead code, because this function already did the right thing,
    but it was dead code that looked authoritative.
    """
    tag = root.tag
    uri = tag[1 : tag.index("}")] if tag.startswith("{") else ""
    return {"g": uri}


def _point_value(pt, ns) -> float:
    for name in VALUE_ELEMENTS:
        txt = pt.findtext(f"g:{name}", namespaces=ns)
        if txt is not None:
            return float(txt)
    raise ValueError(
        "Point carries none of " + "/".join(VALUE_ELEMENTS) + "; "
        "the document type is probably not handled here"
    )


def land(xml_path: Path, out_path: Path | None = None) -> pd.DataFrame:
    body = xml_path.read_bytes()
    sha256 = hashlib.sha256(body).hexdigest()
    text = re.sub(
        r"<script[^>]*/>|<script.*?</script>", "", body.decode("utf-8"), flags=re.S,
    )
    root = ET.fromstring(text)
    ns = _ns_of(root)
    if root.tag.endswith("Acknowledgement_MarketDocument"):
        reason = root.findtext("g:Reason/g:text", default="", namespaces=ns).strip()
        raise ValueError(
            f"{xml_path.name}: an Acknowledgement document, not data: "
            + (reason or "no reason stated")
        )
    doc_type = root.findtext("g:type", default="", namespaces=ns) or ""
    revision = root.findtext("g:revisionNumber", default=None, namespaces=ns)
    rows = []
    for ts in root.findall("g:TimeSeries", ns):
        psr = ts.findtext("g:MktPSRType/g:psrType", default=None, namespaces=ns)
        inz = ts.find("g:inBiddingZone_Domain.mRID", ns)
        outz = ts.find("g:outBiddingZone_Domain.mRID", ns)
        # direction is recorded, not acted upon - the split happens in dbt.
        # Only a BiddingZone_Domain carries a direction. A44 names its domains
        # in_Domain/out_Domain and has no direction at all, so None is the
        # honest value: `if inz is not None else "consumption"` labelled all
        # 50,044 DE-LU price rows as consumption, which puts them in the wrong
        # bucket for anything that filters the raw layer on this column.
        if inz is not None:
            direction = "generation"
        elif outz is not None:
            direction = "consumption"
        else:
            direction = None
        # A44 and A11 name their domains without the BiddingZone_ prefix.
        # Both are kept: an A11 flow runs from out_Domain to in_Domain, and a
        # single zone column loses the border (audit A9).
        in_domain = (ts.findtext("g:inBiddingZone_Domain.mRID", default=None, namespaces=ns)
                     or ts.findtext("g:in_Domain.mRID", default=None, namespaces=ns))
        out_domain = (ts.findtext("g:outBiddingZone_Domain.mRID", default=None, namespaces=ns)
                      or ts.findtext("g:out_Domain.mRID", default=None, namespaces=ns))
        zone = in_domain or out_domain
        curve = ts.findtext("g:curveType", default=None, namespaces=ns)
        # A75 states the unit as quantity_..., A44 as price_... . Keep one
        # column so the raw layer stays document-type agnostic.
        unit = ts.findtext("g:quantity_Measure_Unit.name", default=None, namespaces=ns)
        if unit is None:
            unit = ts.findtext("g:price_Measure_Unit.name", default=None, namespaces=ns)
        cs_raw = ts.findtext(f"g:{CS_FIELD}", default=None, namespaces=ns)
        # Left as None where the zone publishes a single curve. A default of 1
        # would make a one-curve zone indistinguishable from the first curve of
        # a two-curve one, which is the distinction stg_entsoe__prices.sql
        # needs in order to filter safely.
        classification_sequence = int(cs_raw) if cs_raw is not None else None
        for per in ts.findall("g:Period", ns):
            p_start = _iso(per.findtext("g:timeInterval/g:start", namespaces=ns))
            p_end = _iso(per.findtext("g:timeInterval/g:end", namespaces=ns))
            res = per.findtext("g:resolution", namespaces=ns)
            if res not in RES_HOURS:
                raise ValueError(f"unknown resolution {res!r} in {xml_path.name}")
            step_h = RES_HOURS[res]
            n_steps = round((p_end - p_start).total_seconds() / 3600 / step_h)
            for pt in per.findall("g:Point", ns):
                rows.append({
                    "document_type": doc_type,
                    "revision_number": revision,
                    # which retrieval this row came from: raw/ keeps every one
                    "source_file": xml_path.as_posix(),
                    "source_sha256": sha256,
                    "zone_eic": zone,
                    "in_domain_eic": in_domain,
                    "out_domain_eic": out_domain,
                    "psr_type": psr,
                    "direction": direction,
                    "classification_sequence": classification_sequence,
                    "curve_type": curve,
                    "unit_name": unit,
                    "period_start_utc": p_start.replace(tzinfo=None),
                    "period_end_utc": p_end.replace(tzinfo=None),
                    "resolution": res,
                    "step_hours": step_h,
                    "n_steps": n_steps,
                    "position": int(pt.findtext("g:position", namespaces=ns)),
                    "quantity": _point_value(pt, ns),
                })
    if not rows:
        # An empty frame here means the namespace or the element names did not
        # match, not that the platform returned nothing: the caller only ever
        # passes files that were landed with content. Fail instead of writing
        # an empty parquet that reads downstream as "no data for that period".
        raise ValueError(
            f"{xml_path.name}: parsed 0 points. Root is {root.tag!r}; "
            "check the namespace and the Point value element."
        )
    df = pd.DataFrame(rows).astype(DTYPES)
    # out_path is optional: land_tree concatenates in memory and writes once per
    # document type. It previously passed a scratch '_tmp.parquet' and deleted
    # it afterwards, which wrote and removed one file per payload for nothing.
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(out_path, index=False)
    return df


def current_payloads(doc_dir: Path) -> list[Path]:
    """The newest accepted retrieval of every logical item under doc_dir.

    raw/ is append-only (src/ingest/raw_store.py): each document type, zone
    and year is a directory with one file per retrieval, and responses that
    were not data sit in its _failed/ folder. Landing every file would count a
    re-pulled year twice; landing a failure would land an error page. File
    names start with the UTC retrieval time, so the newest sorts last.
    """
    groups: dict[Path, list[Path]] = {}
    for xml in doc_dir.rglob("*.xml"):
        if "_failed" in xml.relative_to(doc_dir).parts:
            continue
        groups.setdefault(xml.parent, []).append(xml)
    return [max(files) for _, files in sorted(groups.items())]


def _check_stored_name(xml: Path, frame: pd.DataFrame) -> None:
    """The bytes must still hash to the digest raw_store put in the name.

    A file edited after it was stored, or copied in by hand, would otherwise
    land under a provenance it no longer has.
    """
    m = STORED_NAME.match(xml.name)
    if m is None:
        raise ValueError(f"{xml.name}: not a raw_store name (<UTC time>_<sha8>.xml)")
    digest = frame["source_sha256"].iat[0]
    if not digest.startswith(m.group(1)):
        raise ValueError(
            f"{xml.name}: its bytes hash to {digest[:8]}, not to the digest in its "
            "name; the file changed after it was stored"
        )


def land_tree(raw_root: Path, parquet_root: Path, strict: bool = True) -> dict:
    """Land the newest accepted retrieval of every raw/<DOCTYPE>/<EIC>/<year>/
    item into raw/parquet/<doctype>.parquet.

    strict=True re-raises after reporting. The previous bare `except Exception:
    print(...)` meant a document type that failed on EVERY file produced no
    parquet, no non-zero exit and no test failure - which is how the A44
    landing stayed broken while the pipeline looked green.
    """
    counts: dict[str, int] = {}
    failures: list[tuple[Path, Exception]] = []
    for doc_dir in sorted(
        p for p in raw_root.iterdir()
        if p.is_dir() and p.name != "parquet" and not p.name.startswith("_")
    ):
        frames = []
        xmls = current_payloads(doc_dir)
        for xml in xmls:
            try:
                frame = land(xml)
                _check_stored_name(xml, frame)
                frames.append(frame)
            except Exception as e:  # noqa: BLE001
                print(f"  ! {xml}: {e}")
                failures.append((xml, e))
        if frames:
            df = pd.concat(frames, ignore_index=True)
            out = parquet_root / f"{doc_dir.name.lower()}.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(out, index=False)
            counts[doc_dir.name] = len(df)
        elif xmls:
            print(f"  ! {doc_dir.name}: all {len(xmls)} file(s) failed; no parquet written")
    if failures and strict:
        raise RuntimeError(
            f"{len(failures)} payload(s) failed to land: "
            + ", ".join(str(p) for p, _ in failures)
        )
    return counts


if __name__ == "__main__":
    import sys

    c = land_tree(Path("raw"), Path("raw/parquet"), strict="--keep-going" not in sys.argv)
    for k, v in c.items():
        print(f"{k}: {v:,} stated points")
