"""Land ENTSO-E XML as raw parquet — stated points only, NO business logic.

Deliberate architecture note for the README:
  The A03 gap-filling, the generation/consumption split and the MW->MWh
  conversion all live in dbt, not here. The raw layer stays raw so the
  transformations are visible in the DAG and testable in the warehouse.
  src/transform/entsoe_parse.py keeps the Python implementation of the same
  logic and serves as the independent oracle the SQL is checked against.
"""
from __future__ import annotations
import re, datetime as dt
from pathlib import Path
import xml.etree.ElementTree as ET
import pandas as pd

NS = {"g": "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0",
      "p": "urn:iec62325.351:tc57wg16:451-3:publicationdocument:7:0"}
RES_HOURS = {"PT15M": 0.25, "PT30M": 0.5, "PT60M": 1.0, "PT1H": 1.0}


def _iso(s: str) -> dt.datetime:
    return dt.datetime.strptime(s.replace("Z", "+0000"), "%Y-%m-%dT%H:%M%z")


def _ns_of(root) -> dict:
    tag = root.tag
    uri = tag[1:tag.index("}")] if tag.startswith("{") else ""
    return {"g": uri}


def land(xml_path: Path, out_path: Path) -> pd.DataFrame:
    text = re.sub(r"<script[^>]*/>|<script.*?</script>", "",
                  xml_path.read_text(encoding="utf-8"), flags=re.S)
    root = ET.fromstring(text)
    ns = _ns_of(root)
    doc_type = (root.findtext("g:type", default="", namespaces=ns) or "")
    rows = []
    for ts in root.findall("g:TimeSeries", ns):
        psr_el = ts.find("g:MktPSRType/g:psrType", ns)
        psr = psr_el.text if psr_el is not None else None
        inz = ts.find("g:inBiddingZone_Domain.mRID", ns)
        outz = ts.find("g:outBiddingZone_Domain.mRID", ns)
        # direction is recorded, not acted upon - the split happens in dbt
        direction = "generation" if inz is not None else "consumption"
        zone_el = inz if inz is not None else outz
        if zone_el is None:
            zone_el = ts.find("g:in_Domain.mRID", ns)
        zone = zone_el.text if zone_el is not None else None
        curve = ts.findtext("g:curveType", default=None, namespaces=ns)
        unit = ts.findtext("g:quantity_Measure_Unit.name", default=None, namespaces=ns)
        for per in ts.findall("g:Period", ns):
            p_start = _iso(per.findtext("g:timeInterval/g:start", namespaces=ns))
            p_end = _iso(per.findtext("g:timeInterval/g:end", namespaces=ns))
            res = per.findtext("g:resolution", namespaces=ns)
            step_h = RES_HOURS[res]
            n_steps = round((p_end - p_start).total_seconds() / 3600 / step_h)
            for pt in per.findall("g:Point", ns):
                rows.append({
                    "document_type": doc_type,
                    "zone_eic": zone,
                    "psr_type": psr,
                    "direction": direction,
                    "curve_type": curve,
                    "unit_name": unit,
                    "period_start_utc": p_start.replace(tzinfo=None),
                    "period_end_utc": p_end.replace(tzinfo=None),
                    "resolution": res,
                    "step_hours": step_h,
                    "n_steps": n_steps,
                    "position": int(pt.findtext("g:position", namespaces=ns)),
                    "quantity": float(pt.findtext("g:quantity", namespaces=ns)),
                })
    df = pd.DataFrame(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return df


def land_tree(raw_root: Path, parquet_root: Path) -> dict:
    """Walk raw/<DOCTYPE>/<EIC>/<year>.xml -> raw/parquet/<doctype>.parquet"""
    counts = {}
    for doc_dir in sorted(p for p in raw_root.iterdir() if p.is_dir() and p.name != "parquet"):
        frames = []
        for xml in sorted(doc_dir.rglob("*.xml")):
            try:
                frames.append(land(xml, parquet_root / "_tmp.parquet"))
            except Exception as e:                       # noqa: BLE001
                print(f"  ! skipped {xml}: {e}")
        if frames:
            df = pd.concat(frames, ignore_index=True)
            out = parquet_root / f"{doc_dir.name.lower()}.parquet"
            out.parent.mkdir(parents=True, exist_ok=True)
            df.to_parquet(out, index=False)
            counts[doc_dir.name] = len(df)
    tmp = parquet_root / "_tmp.parquet"
    if tmp.exists():
        tmp.unlink()
    return counts


if __name__ == "__main__":
    c = land_tree(Path("raw"), Path("raw/parquet"))
    for k, v in c.items():
        print(f"{k}: {v:,} stated points")
