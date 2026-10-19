"""Parse ENTSO-E A44 (Day-ahead Prices) into a tidy frame.

This is NOT a second pass of entsoe_parse.py. A44 is a different schema in a
different namespace, and four of its field names differ from A75:

    A75 (GL_MarketDocument)            A44 (Publication_MarketDocument)
    451-6:generationloaddocument:3:0   451-3:publicationdocument:7:3
    inBiddingZone_Domain.mRID          in_Domain.mRID
    outBiddingZone_Domain.mRID         out_Domain.mRID
    Point/quantity                     Point/price.amount
    quantity_Measure_Unit.name         price_Measure_Unit.name + currency_Unit.name
    MktPSRType/psrType                 (absent - prices have no fuel)

Until 17.10.2026, pointing the A75 parser at an A44 payload did not raise: it
returned zero rows, because findall() on the wrong namespace matches nothing. A
silent empty frame is the failure mode this module exists to prevent. Both
parsers now check the document before reading it and refuse an Acknowledgement,
a document of the wrong kind or one without TimeSeries (audit A13).

TRAP 5, the one that is specific to A44 and the reason this parser carries a
field the others do not:

    A single DE-LU 2025 payload contains 732 TimeSeries describing the same
    zone, the same year, the same businessType A62, the same contract A01 and
    the same auction A01. They are two complete and DISAGREEING price curves,
    366 days each, and the only field that tells them apart is

        classificationSequence_AttributeInstanceComponent.position

    Measured on raw/A44/10Y1001A1001A82H/2025/20261006T183150Z_9d48b590.xml
    (revision 1). These are
    STATED points; after A03 expansion (15,483 and 35,136 steps) the medians
    are 90.63 and 92.30 and the negative shares 4.7 % and 6.6 %:

        position 1   15,367 pts   PT60M 6,514 + PT15M 8,853
                     median 90.80   min -250.32   max  583.40   neg 4.5 %
        position 2   34,677 pts   PT15M 34,677
                     median 92.41   min -499.99   max  834.60   neg 6.5 %

    Sum both and every downstream mean is a weighted average of two different
    markets. Sum one at random and the answer changes between runs. So the
    column is emitted here, carried through the raw parquet, and the choice is
    made once, explicitly, in stg_entsoe__prices.sql. Position 1 is the
    day-ahead market's: it equals SMARD filter 4169 to the cent at every hour
    and quarter-hour of 2021-2025 (notebooks/price_curves.py, 19.10.2026).

    Not every zone publishes two curves. The field is optional in the schema,
    so it is emitted as None rather than defaulted - a default of 1 would make
    a single-curve zone indistinguishable from the first curve of a two-curve
    one, and the staging model needs to tell those apart.

Negative prices are real: 4.5 % of position 1's stated points and 6.5 % of
position 2's. Any
clamp, abs() or max(0, x) applied to this column is a bug, not cleaning.
"""
from __future__ import annotations

import datetime as dt
import re
import xml.etree.ElementTree as ET

# Resolutions seen in A44. PT15M became the German day-ahead MTU on
# 2025-10-01; payloads spanning that date carry both.
RES_HOURS = {"PT15M": 0.25, "PT30M": 0.5, "PT60M": 1.0, "PT1H": 1.0}

CS_FIELD = "classificationSequence_AttributeInstanceComponent.position"


def _iso(s: str) -> dt.datetime:
    """ENTSO-E time interval -> tz-aware UTC datetime.

    Identical contract to entsoe_parse._iso: accept both the 'YYYY-MM-DDTHH:MMZ'
    and the seconds-bearing form, and refuse a naive timestamp rather than let
    something downstream assume it is local time.
    """
    s = (s or "").strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        raise ValueError(f"timestamp carries no offset: {s!r}")
    return d.astimezone(dt.timezone.utc)


def _ns_of(root) -> dict:
    """Read the namespace off the root element instead of hardcoding it.

    xml_to_parquet.py carried the publication namespace as a literal ending
    ':7:0' while the payload on disk is ':7:3'. Nothing failed, because that
    constant was never used - but a hardcoded minor version is a trap waiting
    for the next schema bump. Derive it.
    """
    tag = root.tag
    uri = tag[1 : tag.index("}")] if tag.startswith("{") else ""
    return {"g": uri}


def _check_document(root, ns: dict) -> None:
    """Refuse anything that is not a publication document.

    ENTSO-E answers a query it cannot serve with HTTP 200 and an
    Acknowledgement_MarketDocument, which has no TimeSeries; this parser used
    to return [] for it.
    """
    local = root.tag.rsplit("}", 1)[-1]
    if local == "Acknowledgement_MarketDocument":
        reason = root.findtext("g:Reason/g:text", default="", namespaces=ns).strip()
        raise ValueError(
            "an Acknowledgement document, not data: " + (reason or "no reason stated")
        )
    if local != "Publication_MarketDocument":
        raise ValueError(
            f"parse_prices reads A44 Publication_MarketDocument; got {local}. "
            "A75 generation belongs in entsoe_parse.parse()."
        )


def parse_prices(xml_text: str) -> list[dict]:
    """A44 XML -> one row per expanded step.

    Expansion follows the A75 parser: curveType A03 is a step curve whose
    omitted positions repeat the last stated value. A01 states every position,
    so a missing one stays None rather than being carried forward (audit A6).
    Any other curve type is refused.
    """
    # strip anything a browser extension injected before parsing
    xml_text = re.sub(r"<script[^>]*/>|<script.*?</script>", "", xml_text, flags=re.S)
    root = ET.fromstring(xml_text)
    ns = _ns_of(root)
    _check_document(root, ns)

    doc_type = root.findtext("g:type", default=None, namespaces=ns)
    if doc_type and doc_type != "A44":
        raise ValueError(
            f"parse_prices got a {doc_type} document; it only reads A44. "
            "A75 generation belongs in entsoe_parse.parse()."
        )
    revision = root.findtext("g:revisionNumber", default=None, namespaces=ns)

    series_elements = root.findall("g:TimeSeries", ns)
    if not series_elements:
        raise ValueError("an A44 document with no TimeSeries: nothing to parse")

    rows: list[dict] = []
    for ts in series_elements:
        series_mrid = ts.findtext("g:mRID", default=None, namespaces=ns)
        in_z = ts.findtext("g:in_Domain.mRID", default=None, namespaces=ns)
        out_z = ts.findtext("g:out_Domain.mRID", default=None, namespaces=ns)
        # For a day-ahead price both domains are the same zone. A differing
        # pair is a transit/border series and must not be averaged in with
        # a zone's own prices, so refuse rather than silently pick one.
        if in_z and out_z and in_z != out_z:
            raise ValueError(
                f"TimeSeries {series_mrid}: in_Domain {in_z} != out_Domain {out_z}; "
                "this is not a single-zone day-ahead price series"
            )
        zone = in_z or out_z

        # TRAP 5. Optional in the schema, so None is a real value here.
        cs_raw = ts.findtext(f"g:{CS_FIELD}", default=None, namespaces=ns)
        classification_sequence = int(cs_raw) if cs_raw is not None else None

        curve = ts.findtext("g:curveType", default=None, namespaces=ns)
        if curve not in ("A01", "A03"):
            raise ValueError(
                f"TimeSeries {series_mrid}: curveType {curve!r} is neither A01 nor "
                "A03; how its omitted positions read is unknown, so it is not guessed"
            )
        currency = ts.findtext("g:currency_Unit.name", default=None, namespaces=ns)
        unit = ts.findtext("g:price_Measure_Unit.name", default=None, namespaces=ns)
        auction = ts.findtext("g:auction.type", default=None, namespaces=ns)
        business = ts.findtext("g:businessType", default=None, namespaces=ns)
        contract = ts.findtext(
            "g:contract_MarketAgreement.type", default=None, namespaces=ns
        )

        for per in ts.findall("g:Period", ns):
            start = _iso(per.findtext("g:timeInterval/g:start", namespaces=ns))
            end = _iso(per.findtext("g:timeInterval/g:end", namespaces=ns))
            res = per.findtext("g:resolution", namespaces=ns)
            if res not in RES_HOURS:
                raise ValueError(f"unknown resolution {res!r} in TimeSeries {series_mrid}")
            step_h = RES_HOURS[res]
            # Derived from the interval, not assumed: a transition day is 23 or
            # 25 hours and a hardcoded 24 would shift every later timestamp.
            n_steps = round((end - start).total_seconds() / 3600 / step_h)

            pts = {
                int(p.findtext("g:position", namespaces=ns)): float(
                    p.findtext("g:price.amount", namespaces=ns)
                )
                for p in per.findall("g:Point", ns)
            }

            if curve == "A03":
                # A step curve has nothing to carry forward from before its
                # first point. Starting the series late would shift every
                # timestamp in it, so refuse instead.
                if 1 not in pts:
                    raise ValueError(
                        f"TimeSeries {series_mrid} {start:%Y-%m-%d}: no point at "
                        "position 1; a curveType A03 series cannot be expanded "
                        "from a gap"
                    )
                last, series = None, []
                for pos in range(1, n_steps + 1):
                    if pos in pts:
                        last = pts[pos]
                    series.append((pos, last))
            else:
                # A01: every position is stated, so a missing one is a missing
                # price. A carried-forward price would be an invented one.
                series = [(pos, pts.get(pos)) for pos in range(1, n_steps + 1)]

            for pos, price in series:
                rows.append(
                    {
                        "ts_utc": start + dt.timedelta(hours=step_h * (pos - 1)),
                        "period_start_utc": start,
                        "zone_eic": zone,
                        "classification_sequence": classification_sequence,
                        "position": pos,
                        "resolution": res,
                        "step_hours": step_h,
                        # No MW->MWh conversion: a price is already per MWh.
                        # Negative values are real and are left alone.
                        "price_eur_mwh": price,
                        "currency": currency,
                        "unit": unit,
                        "curve_type": curve,
                        "auction_type": auction,
                        "business_type": business,
                        "contract_type": contract,
                        "series_mrid": series_mrid,
                        "revision_number": revision,
                        "n_points_stated": len(pts),
                        "n_steps_expanded": n_steps,
                    }
                )
    return rows


def curve_summary(rows: list[dict]) -> dict:
    """Per classificationSequence: how many rows, which resolutions, the median.

    The diagnostic that makes trap 5 visible instead of theoretical. Used by the
    tests and worth running by hand on any new zone before trusting its prices.
    """
    import statistics
    from collections import Counter, defaultdict

    agg: dict = defaultdict(lambda: {"rows": 0, "resolutions": Counter(), "prices": []})
    for r in rows:
        a = agg[r["classification_sequence"]]
        a["rows"] += 1
        a["resolutions"][r["resolution"]] += 1
        if r["price_eur_mwh"] is not None:
            a["prices"].append(r["price_eur_mwh"])
    out = {}
    for cs, a in agg.items():
        p = a["prices"]
        out[cs] = {
            "rows": a["rows"],
            "resolutions": dict(a["resolutions"]),
            "median": statistics.median(p) if p else None,
            "min": min(p) if p else None,
            "max": max(p) if p else None,
            "negative_share": (sum(1 for x in p if x < 0) / len(p)) if p else None,
        }
    return out
