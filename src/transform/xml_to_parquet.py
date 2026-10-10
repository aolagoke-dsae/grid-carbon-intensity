"""Land ENTSO-E XML as raw parquet - stated points only, NO business logic.

Deliberate architecture note for the README:
  The A03 gap-filling, the generation/consumption split and the MW->MWh
  conversion all live in dbt, not here. The raw layer stays raw so the
  transformations are visible in the DAG and testable in the warehouse.
  src/transform/entsoe_parse.py keeps the Python implementation of the same
  logic for A75 and serves as the independent oracle the SQL is checked
  against; src/transform/entsoe_prices_parse.py does the same for A44.

One column is landed that is not a stated point: classification_sequence.
It is read straight off the TimeSeries without interpretation, and it has to
be here because it is the only field separating the two complete, disagreeing
day-ahead price curves a single A44 payload contains. See TRAP 5 in
entsoe_prices_parse.py. Dropping it is not a simplification - it makes the
payload unusable downstream.
"""
from __future__ import annotations

import datetime as dt
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
    text = re.sub(
        r"<script[^>]*/>|<script.*?</script>", "",
        xml_path.read_text(encoding="utf-8"), flags=re.S,
    )
    root = ET.fromstring(text)
    ns = _ns_of(root)
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
        zone_el = inz if inz is not None else outz
        if zone_el is None:
            # A44/A11 name the domains without the BiddingZone_ prefix.
            zone_el = ts.find("g:in_Domain.mRID", ns)
        if zone_el is None:
            zone_el = ts.find("g:out_Domain.mRID", ns)
        zone = zone_el.text if zone_el is not None else None
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
                    "zone_eic": zone,
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
    df = pd.DataFrame(rows)
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
                frames.append(land(xml))
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
