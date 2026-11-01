"""Parse ENTSO-E A65 (Total Load) into one row per expanded step.

A65 carries two different series under one document type, told apart only by
the document's process type:

    process A16   the actual total load (Transparency Regulation, 6.1.A)
    process A01   the day-ahead total load forecast (6.1.B)

The decision model uses the forecast: it is due two hours before the
day-ahead gate closure (Reg. 543/2013, Art. 6(2)(b)), so a plant deciding at
10:00 the day before can rely on it (docs/DECISION_MODEL.md). The actual load
is pulled to check the forecast against. Read one as the other and every figure
built on it is plausible and wrong. So parse_load() takes the process type it
expects and refuses any other, and raw/ keeps the two in separate folders,
A65/ and A65_A01/, which xml_to_parquet.land_tree checks against every
payload's process type.

The schema is the generation-and-load document A75 uses (GL_MarketDocument),
with the zone in outBiddingZone_Domain.mRID: load is what the zone takes out
of the grid. There is no fuel and no inBiddingZone_Domain. Expansion follows
the other two parsers: curveType A03 repeats the last stated value over the
positions it omits, and A01 states every position, so a missing one stays
empty rather than invented.

Written on fixtures on 01.11.2026, before the first A65 payload was pulled.
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET

RES_HOURS = {"PT15M": 0.25, "PT30M": 0.5, "PT60M": 1.0, "PT1H": 1.0}
PROCESSES = {"A16": "actual total load", "A01": "day-ahead total load forecast"}


def _iso(s: str) -> dt.datetime:
    """ENTSO-E time interval -> tz-aware UTC datetime; a naive one is refused."""
    s = (s or "").strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        raise ValueError(f"timestamp carries no offset: {s!r}")
    return d.astimezone(dt.timezone.utc)


def _ns_of(root) -> dict:
    tag = root.tag
    uri = tag[1 : tag.index("}")] if tag.startswith("{") else ""
    return {"g": uri}


def parse_load(xml_text: str, process: str) -> list[dict]:
    """A65 XML -> one row per expanded step of the series `process` names.

    `process` is A16 (actual) or A01 (day-ahead forecast) and must match the
    document's own process type. A document without one is refused too: it
    cannot say which of the two series it holds.
    """
    if process not in PROCESSES:
        raise ValueError(f"process {process!r}: A65 is read as A16 or A01 only")
    xml_text = re.sub(r"<script[^>]*/>|<script.*?</script>", "", xml_text, flags=re.S)
    root = ET.fromstring(xml_text)
    ns = _ns_of(root)
    local = root.tag.rsplit("}", 1)[-1]
    if local == "Acknowledgement_MarketDocument":
        reason = root.findtext("g:Reason/g:text", default="", namespaces=ns).strip()
        raise ValueError("an Acknowledgement document, not data: " + (reason or "no reason stated"))
    if local != "GL_MarketDocument":
        raise ValueError(f"parse_load reads the A65 GL_MarketDocument; got {local}")
    doc_type = root.findtext("g:type", default=None, namespaces=ns)
    if doc_type != "A65":
        raise ValueError(f"parse_load reads A65 total load; got a {doc_type} document")
    stated = root.findtext("g:process.processType", default=None, namespaces=ns)
    if stated != process:
        raise ValueError(
            f"the document holds process {stated}"
            + (f", the {PROCESSES[stated]}," if stated in PROCESSES else "")
            + f" not {process}, the {PROCESSES[process]}"
        )
    revision = root.findtext("g:revisionNumber", default=None, namespaces=ns)

    series_elements = root.findall("g:TimeSeries", ns)
    if not series_elements:
        raise ValueError("an A65 document with no TimeSeries: nothing to parse")

    rows: list[dict] = []
    for ts in series_elements:
        series_mrid = ts.findtext("g:mRID", default=None, namespaces=ns)
        zone = ts.findtext("g:outBiddingZone_Domain.mRID", default=None, namespaces=ns)
        if zone is None or ts.find("g:inBiddingZone_Domain.mRID", ns) is not None:
            raise ValueError(
                f"TimeSeries {series_mrid}: a load series names its zone in "
                "outBiddingZone_Domain only"
            )
        curve = ts.findtext("g:curveType", default=None, namespaces=ns)
        if curve not in ("A01", "A03"):
            raise ValueError(
                f"TimeSeries {series_mrid}: curveType {curve!r} is neither A01 nor "
                "A03; how its omitted positions read is unknown, so it is not guessed"
            )
        unit = ts.findtext("g:quantity_Measure_Unit.name", default=None, namespaces=ns)
        business = ts.findtext("g:businessType", default=None, namespaces=ns)

        for per in ts.findall("g:Period", ns):
            start = _iso(per.findtext("g:timeInterval/g:start", namespaces=ns))
            end = _iso(per.findtext("g:timeInterval/g:end", namespaces=ns))
            res = per.findtext("g:resolution", namespaces=ns)
            if res not in RES_HOURS:
                raise ValueError(f"unknown resolution {res!r} in TimeSeries {series_mrid}")
            step_h = RES_HOURS[res]
            # From the interval, not assumed: a clock-change day is 23 or 25 hours.
            n_steps = round((end - start).total_seconds() / 3600 / step_h)
            pts = {
                int(p.findtext("g:position", namespaces=ns)): float(
                    p.findtext("g:quantity", namespaces=ns)
                )
                for p in per.findall("g:Point", ns)
            }
            if curve == "A03" and 1 not in pts:
                raise ValueError(
                    f"TimeSeries {series_mrid} {start:%Y-%m-%d}: no point at position 1; "
                    "a curveType A03 series cannot be expanded from a gap"
                )
            last = None
            for pos in range(1, n_steps + 1):
                if pos in pts:
                    last = pts[pos]
                    value, carried = last, False
                elif curve == "A03":
                    value, carried = last, True
                else:
                    value, carried = None, False
                rows.append({
                    "ts_utc": start + dt.timedelta(hours=step_h * (pos - 1)),
                    "zone_eic": zone,
                    "process_type": stated,
                    "resolution": res,
                    "step_hours": step_h,
                    "mw": value,
                    "was_carried": carried,
                    "curve_type": curve,
                    "unit": unit,
                    "business_type": business,
                    "position": pos,
                    "period_start_utc": start,
                    "series_mrid": series_mrid,
                    "revision_number": revision,
                })
    return rows
