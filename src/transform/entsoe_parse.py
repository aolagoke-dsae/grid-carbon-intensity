"""Parse ENTSO-E A75 (Aggregated Generation per Type) into a tidy frame.

Handles the four traps in the real payload:
  1. resolution is PT15M for DE-LU, not hourly  -> 96 points/day
  2. curveType A03 omits repeated values        -> gaps must be carried forward
  3. outBiddingZone_Domain = consumption        -> must not be summed as generation
  4. unit is MAW (power)                        -> energy = MW * hours_per_step
"""
import re, datetime as dt
import xml.etree.ElementTree as ET

NS = {"g": "urn:iec62325.351:tc57wg16:451-6:generationloaddocument:3:0"}
RES = {"PT15M": 0.25, "PT30M": 0.5, "PT60M": 1.0, "PT1H": 1.0}

PSR = {  # ENTSO-E PsrType -> readable
 "B01":"Biomass","B02":"Fossil Brown coal/Lignite","B03":"Fossil Coal-derived gas",
 "B04":"Fossil Gas","B05":"Fossil Hard coal","B06":"Fossil Oil","B09":"Geothermal",
 "B10":"Hydro Pumped Storage","B11":"Hydro Run-of-river","B12":"Hydro Water Reservoir",
 "B14":"Nuclear","B15":"Other renewable","B16":"Solar","B17":"Waste",
 "B18":"Wind Offshore","B19":"Wind Onshore","B20":"Other",
 "B25":"Energy storage"}

def _iso(s):
    """ENTSO-E time interval -> tz-aware UTC datetime.

    The platform normally emits 'YYYY-MM-DDTHH:MMZ', but seconds appear in
    some document types. strptime with a fixed pattern silently breaks on the
    second form, so parse both and fail loudly on a naive timestamp: an
    offset-less time here would be assumed local somewhere downstream, which
    is exactly the class of bug that produces a 23- or 25-hour day.
    """
    s = (s or "").strip()
    if s.endswith(("Z", "z")):
        s = s[:-1] + "+00:00"
    d = dt.datetime.fromisoformat(s)
    if d.tzinfo is None:
        raise ValueError(f"timestamp carries no offset: {s!r}")
    return d.astimezone(dt.timezone.utc)

def parse(xml_text):
    # strip anything a browser extension injected before parsing
    xml_text = re.sub(r"<script[^>]*/>|<script.*?</script>", "", xml_text, flags=re.S)
    root = ET.fromstring(xml_text)
    rows = []
    for ts in root.findall("g:TimeSeries", NS):
        psr = ts.find("g:MktPSRType/g:psrType", NS).text
        inz  = ts.find("g:inBiddingZone_Domain.mRID", NS)
        outz = ts.find("g:outBiddingZone_Domain.mRID", NS)
        # TRAP 3: an outBiddingZone series is consumption (e.g. pumping), not generation
        direction = "generation" if inz is not None else "consumption"
        zone = (inz if inz is not None else outz).text
        curve = ts.find("g:curveType", NS).text
        unit  = ts.find("g:quantity_Measure_Unit.name", NS).text

        for per in ts.findall("g:Period", NS):
            start = _iso(per.find("g:timeInterval/g:start", NS).text)
            end   = _iso(per.find("g:timeInterval/g:end", NS).text)
            res   = per.find("g:resolution", NS).text
            step_h = RES[res]
            n_steps = round((end - start).total_seconds() / 3600 / step_h)

            pts = {int(p.find("g:position", NS).text): float(p.find("g:quantity", NS).text)
                   for p in per.findall("g:Point", NS)}

            # TRAP 2: A03 = "step" curve. Missing positions repeat the last stated value.
            # A01 would be dense. Expanding both the same way is safe.
            #
            # Position 1 must exist: a step curve has nothing to carry forward
            # from before its first point. Silently starting the series late
            # would shift every timestamp in it, so refuse instead.
            if 1 not in pts:
                raise ValueError(
                    f"{psr}/{direction} {start:%Y-%m-%d}: no point at position 1; "
                    "a curveType A03 series cannot be expanded from a gap"
                )
            last, series = None, []
            for pos in range(1, n_steps + 1):
                if pos in pts:
                    last = pts[pos]
                series.append((pos, last))

            for pos, mw in series:
                rows.append({
                    "ts_utc": start + dt.timedelta(hours=step_h * (pos - 1)),
                    # The period a row came from. Without it a series cannot be
                    # told apart from the sum of its periods, and a yearly
                    # payload carries one Period per day.
                    "period_start_utc": start,
                    "zone": zone, "psr": psr, "fuel": PSR.get(psr, psr),
                    "direction": direction,
                    "resolution": res, "step_hours": step_h,
                    "mw": mw,
                    # TRAP 4: MAW is power. Energy for the step:
                    "mwh": mw * step_h,
                    "curve_type": curve, "unit": unit,
                    "n_points_stated": len(pts), "n_steps_expanded": n_steps,
                })
    return rows
