"""NRCS SNOTEL: hourly snow and weather at the four SNOTEL stations in the ring.

The AWDB REST API (wcc.sc.egov.usda.gov/awdbRestApi; robots.txt 404, so no
rules), one call per run for all four stations and every element they report
(elements=*): snow water equivalent, snow depth, precipitation, air
temperature, and at Mores Creek Summit also humidity, wind and radiation;
battery voltage everywhere. The stations, checked with one stations call on
Oct 7, 2026 (docs/sources/trails.md, "NRCS SNOTEL"; none of Oregon's 82 is in
the ring):

    978  Bogus Basin          Boise County    6,370 ft
    423  Cozy Cove            Valley County   5,410 ft  (the ring's north-east corner)
    637  Mores Creek Summit   Boise County    6,090 ft
    2029 Reynolds Creek       Owyhee County   5,590 ft

AWDB keeps decades of history, so this poller isn't racing a disappearing
window; it keeps the values as first published (NRCS edits them later in
quality control) and feeds live cards. Each run re-reads the last 48 hours,
so late and revised values are caught and a day of downtime loses nothing;
only new or changed versions are written.

AWDB gives times in the station's own standard time, without daylight saving
(dataTimeZone -8 for all four, matching the latest hourly value arriving
within the hour). One record per station and hour, `<triplet>@<UTC time>`:
{station, t (UTC), local (as published), utc_offset, values: {element: {v,
u, qc, qa}}}. An element is its code, plus `:<ordinal>` when not 1 and
`@<depth>` for soil sensors. An hour gains a version when a late element
arrives or a value or flag is revised.
"""

import json
import urllib.parse
from datetime import datetime, timedelta, timezone

from ingest import db, http

from ..common import iso, point, store_readings

API = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"
http.PACE_S.setdefault("wcc.sc.egov.usda.gov", 2.0)

# triplet: name, county, elevation (ft), latitude, longitude, data time zone (hours from UTC)
STATIONS = {
    "978:ID:SNTL": ("Bogus Basin", "Boise", 6370, 43.76377, -116.09685, -8.0),
    "423:ID:SNTL": ("Cozy Cove", "Valley", 5410, 44.28846, -115.65508, -8.0),
    "637:ID:SNTL": ("Mores Creek Summit", "Boise", 6090, 43.932, -115.66588, -8.0),
    "2029:ID:SNTL": ("Reynolds Creek", "Owyhee", 5590, 43.28863, -116.8431, -8.0),
}
WINDOW = timedelta(hours=48)

SOURCE = {
    "name": "nrcs_snotel",
    "title": "NRCS SNOTEL hourly snow and weather at the ring's four stations",
    "url": "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/stations?stationTriplets=*:ID:SNTL",
    "access": "open",
    "schedule": "1 hour",
    "license": "US government work (USDA NRCS); public domain assumed",
    "credit": "USDA Natural Resources Conservation Service (SNOTEL)",
    "notes": "One AWDB call per run for Bogus Basin, Cozy Cove, Mores Creek Summit and Reynolds Creek, every "
             "element, the last 48 hours; one raw.record per station and hour, new or revised versions only.",
}


def query_url(now, stations=STATIONS, window=WINDOW):
    """The last `window` of hourly values. AWDB reads the dates in the stations' own time."""
    local = now.astimezone(timezone.utc).replace(tzinfo=None) + timedelta(hours=min(s[5] for s in stations.values()))
    q = {"stationTriplets": ",".join(stations), "elements": "*", "duration": "HOURLY",
         "beginDate": (local - window).strftime("%Y-%m-%d %H:%M"),
         "endDate": (local + timedelta(hours=2)).strftime("%Y-%m-%d %H:%M"), "returnFlags": "true"}
    return API + "?" + urllib.parse.urlencode(q)


def element_key(se):
    """'TOBS'; 'SMS:2' for a second sensor; 'SMS@-8in' for one at a depth."""
    key = str(se.get("elementCode") or "?")
    if se.get("ordinal") not in (None, 1):
        key += f":{se['ordinal']}"
    depth = se.get("heightDepth")
    if isinstance(depth, dict) and depth.get("value") is not None:
        key += f"@{depth['value']}{depth.get('unitCode') or ''}"
    return key


def parse(data, stations=STATIONS):
    """{(triplet, UTC time): payload}, one per station and hour that has any value."""
    out = {}
    for block in data or []:
        triplet = block.get("stationTriplet")
        if triplet not in stations:
            continue
        offset = stations[triplet][5]
        tz = timezone(timedelta(hours=offset))
        for element in block.get("data") or []:
            se = element.get("stationElement") or {}
            key = element_key(se)
            for v in element.get("values") or []:
                if v.get("value") is None:
                    continue
                local = v.get("date")
                try:
                    t = iso(datetime.strptime(local, "%Y-%m-%d %H:%M").replace(tzinfo=tz))
                except (TypeError, ValueError):
                    continue
                rec = out.setdefault((triplet, t), {"station": triplet, "t": t, "local": local, "utc_offset": offset,
                                                    "values": {}})
                rec["values"][key] = {"v": v["value"], "u": se.get("storedUnitCode"), "qc": v.get("qcFlag"),
                                      "qa": v.get("qaFlag")}
    return out


def records(parsed, stations=STATIONS):
    return [(f"{triplet}@{t}", payload, point(stations[triplet][4], stations[triplet][3]))
            for (triplet, t), payload in sorted(parsed.items())]


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        f.http_status, body, f.robots = http.get(query_url(f.started_at), timeout=90, compressed=True)
        f.bytes = len(body)
        parsed = parse(json.loads(body))
        if not parsed:
            raise RuntimeError("AWDB returned no SNOTEL values for the last 48 hours")
        f.records = len(parsed)
        new, held = store_readings(conn, SOURCE["name"], records(parsed), f.id, f.started_at)
    return {"stations": len({k[0] for k in parsed}), "station hours": len(parsed), "versions new": new,
            "held": held}

