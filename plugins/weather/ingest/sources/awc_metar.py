"""Aviation Weather Center METARs and SPECIs for the regional ring's airports.

One request to AWC's Data API per run, by bounding box over the regional
ring, in JSON: every routine report (METAR) and special (SPECI) observed
there in the last few hours. On Oct 7, 2026 the box held five reporting
airports: Boise (KBOI), Nampa (KMAN, an AWOS reporting every 20 minutes),
Caldwell (KEUL), Mountain Home AFB (KMUO) and Ontario, Oregon (KONO). The
box picks up any airport AWC adds later.

AWC keeps 30 days, so history exists only if we poll (IEM holds the long
archive). Each report is versioned in raw.record by station and observation
time ("KBOI 2026-10-07T13:53Z"); the polls aren't snapshots. An unchanged
report only moves last_seen; a corrected one (COR) adds a version. The
payload is AWC's decoded record as returned, raw text (`rawOb`) included,
minus the station's display name; the point goes in geom.

The lookback covers the time since the last good fetch plus 6 hours for
reports that reach AWC late (on Oct 7 Mountain Home AFB's 11:55Z report
arrived at 14:18Z), at most 24 hours: a day is about 200 reports, half of
AWC's 400-entry cap. An empty answer (HTTP 204) fails the fetch, since
Boise's ASOS reports every hour; the next run then asks for the whole gap.

Docs: https://aviationweather.gov/data/api/ (at most 100 requests a minute;
keep requests limited; set a custom User-Agent). robots.txt: 404, no rules
(re-read Oct 7). A US Government work with no license stated, so public
domain is assumed (docs/sources/weather.md, "Aviation Weather Center Data API").
"""

import json
import math
import re
import urllib.error
import urllib.parse
from datetime import datetime, timezone

from ingest import db, http

API = "https://aviationweather.gov/api/data/metar"

# The regional ring (west, south, east, north): proposed in docs/DECISIONS.md ("How far the
# study area reaches"), and the box the source catalogs in docs/sources/ use.
RING = (-117.30, 42.90, -115.60, 44.30)

MIN_HOURS = 6        # every poll looks back at least this far
LATE_HOURS = 6       # added to the time since the last good fetch, for reports that arrive late
MAX_HOURS = 24       # after a longer outage the oldest reports are left to IEM's archive
MAX_ENTRIES = 400    # AWC's cap on one answer
STATION = re.compile(r"^[A-Z0-9]{3,4}$")
LATEST_OBS = 4102444800   # 2100-01-01: a larger obsTime is garbage, not a time
DROP = ("name",)     # the station's display name: presentation only, the same on every report

SOURCE = {
    "name": "awc_metar",
    "title": "Aviation Weather Center METARs and SPECIs (regional ring airports)",
    "url": "https://aviationweather.gov/data/api/",
    "access": "open",
    "schedule": "10 minutes",
    "license": "US Government work; no license stated (public domain assumed)",
    "credit": "NOAA National Weather Service, Aviation Weather Center",
    "notes": "One bounding-box request over the regional ring per run, looking back over the time since the "
             "last good fetch plus 6 h (6 to 24 h). Each report versioned in raw.record by station and "
             "observation time; AWC's decoded JSON and the raw METAR text kept, the station's display name "
             "dropped. AWC keeps 30 days; IEM has the archive.",
}


def query_url(hours):
    west, south, east, north = RING
    q = {"bbox": f"{south:.2f},{west:.2f},{north:.2f},{east:.2f}",   # AWC's order: lat0,lon0,lat1,lon1
         "format": "json", "hours": hours}
    return API + "?" + urllib.parse.urlencode(q, safe=",")


def lookback_hours(last_good, now):
    """Hours to ask for: since the last good fetch plus LATE_HOURS, whole hours, MIN_HOURS..MAX_HOURS.
    MAX_HOURS when nothing has been fetched yet."""
    if last_good is None:
        return MAX_HOURS
    gap = max(0.0, (now - last_good).total_seconds() / 3600)
    return max(MIN_HOURS, min(MAX_HOURS, math.ceil(gap + LATE_HOURS)))


def last_good_fetch(conn):
    return conn.execute("select max(started_at) from ops.fetch where source = %s and ok",
                        (SOURCE["name"],)).fetchone()[0]


def decode(body):
    """AWC's answer as a list of reports. HTTP 204 (no data) has an empty body."""
    if not body.strip():
        return []
    data = json.loads(body)
    if not isinstance(data, list):
        raise RuntimeError(f"AWC answered with something other than a list: {str(data)[:300]}")
    return data


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def in_ring(lon, lat):
    west, south, east, north = RING
    return west <= lon <= east and south <= lat <= north


def observed_at(row):
    return datetime.fromtimestamp(int(row["obsTime"]), tz=timezone.utc)


def source_id(row):
    """Station and observation time to the minute, as METARs give it: "KBOI 2026-10-07T13:53Z"."""
    return f"{row['icaoId']} {observed_at(row):%Y-%m-%dT%H:%MZ}"


def parse(rows):
    """-> ([(source_id, payload, geometry)], counts). Reports outside the ring, or without a
    station, an observation time, raw text or a position, are left out and counted."""
    records, counts = [], {"outside the ring": 0, "unusable": 0}
    for row in rows:
        if not (isinstance(row, dict) and isinstance(row.get("icaoId"), str) and STATION.match(row["icaoId"])
                and _number(row.get("obsTime")) and 0 < row["obsTime"] < LATEST_OBS
                and isinstance(row.get("rawOb"), str) and row["rawOb"].strip()
                and _number(row.get("lat")) and _number(row.get("lon"))):
            counts["unusable"] += 1
            continue
        if not in_ring(row["lon"], row["lat"]):
            counts["outside the ring"] += 1
            continue
        payload = {k: v for k, v in row.items() if k not in DROP}
        records.append((source_id(row), payload, {"type": "Point", "coordinates": [row["lon"], row["lat"]]}))
    return records, counts


def store(conn, fetch_id, seen_at, records):
    """Version the reports (not a snapshot: nothing is marked removed). Returns (new, unchanged)."""
    new, unchanged, _ = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at, complete=False)
    return new, unchanged


def run(conn):
    db.ensure_source(conn, SOURCE)
    hours = lookback_hours(last_good_fetch(conn), db.now())
    with db.Fetch(conn, SOURCE["name"]) as f:
        try:
            f.http_status, body, f.robots = http.get(query_url(hours), timeout=60, compressed=True)
        except urllib.error.HTTPError as err:      # logged with its status: 429 is AWC's rate limit
            f.http_status = err.code
            raise
        f.bytes = len(body)
        rows = decode(body)
        records, counts = parse(rows)
        f.records = len({sid for sid, _, _ in records})
        if not records:
            raise RuntimeError(f"no reports from any ring airport in the last {hours} h "
                               f"(HTTP {f.http_status}, {len(rows)} rows)")
        new, unchanged = store(conn, f.id, f.started_at, records)
    return {"hours asked": hours, "reports": f.records, "record versions new": new, "unchanged": unchanged,
            "stations": len({p["icaoId"] for _, p, _ in records}),
            "specials": sum(1 for _, p, _ in records if p.get("metarType") == "SPECI"),
            **counts, "at AWC's cap": len(rows) >= MAX_ENTRIES}
