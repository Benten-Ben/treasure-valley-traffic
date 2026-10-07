"""IDFG's roadkill reports (wildlife-vehicle collisions) in the ring, versioned daily.

One point per carcass or salvage report, from Idaho Fish and Game's public
Roadkill Observations layer (gisportal-idfg.idaho.gov, ArcGIS Server 11.5,
MapServer layer 1; no key, robots.txt 404). The ring held 9,268 reports on
Oct 7, 2026, observed from 1970 on, with new ones almost every day. They come
through four channels (`source`): IDFG Roadkill & Salvage Reports (8,911 of
them), IDFG Survey 123 (317), ITD Survey 123 (31) and Big Game Mortality
Reports (9). docs/sources/wildlife.md ("IDFG roadkill observations") has the
verification.

Why poll it now (Wave A, docs/17 §17.4). IDFG rebuilds the layer in full:
the ring's reports on Oct 7 had OBJECTIDs spread over 149,961,448 to
150,031,872, one span the size of the whole statewide table (about 70,400),
with the highest held by reports made in 2017, while the layer already held
reports made that day. Corrections and removals (IDFG warns of duplicate
reports) leave no trace unless we keep the versions.

A run reads the ring with the shared ArcGIS reader: the IDs, then the
reports in one range query (three requests with robots.txt, about 5 MB
before gzip). Each report is kept in raw.record with complete=False: reports
are occurrences, so a report IDFG drops just stops being seen (its last_seen
stays behind) and nothing is marked removed.

Identity. OBJECTIDs change with every rebuild, and GlobalIDs probably do too
(not proven). So a report's ID is our own: a hash of what identifies it (its
channel, its observed and reported times, and its reported latitude and
longitude to 6 decimals), with "#2", "#3" for reports alike in all of those
(two animals in one report). A change to any other field adds a version of
the report. A change to one of these adds a new report, and the old one stops
being seen.

Privacy (docs/17 Q21). Fields are kept by allow-list (KEEP). Dropped at
ingest: IDFG's free-text `note` (it may hold personal details), `path`
(undocumented; it may point to a photo, which we never fetch), the
OBJECTID and GlobalID, and any field the layer adds later, until someone
reviews it and adds it to KEEP. The run lists such new fields by name. The
layer has no reporter name, email or phone field (checked Oct 7, 2026).

Dates. `observed` and `reported` are kept as served, in epoch milliseconds.
The service's time reference is Mountain Standard Time without daylight
saving: date-only reports come back at 07:00 UTC (midnight MST), while the
two Survey 123 channels carry a time of day (348 reports in the ring). Its
statistics answers return the stored values unconverted (midnight UTC);
that's where the catalog's "dates at 00:00 UTC" came from. local_date() gives
the calendar date in MST. Dates before 1977 (the service's stated start) are
suspect; the run counts them.

Refused, so that the fetch fails, nothing is stored, and the source retries
after retry_after:
- an answer with no reports;
- an answer with fewer than MIN_SHARE of the reports the last run saw (read
  during IDFG's rebuild, or a cut layer);
- an answer where most reports are new and most of the last run's are gone.
  That means dates or coordinates are served differently, and IDs made from
  them would duplicate every report.
"""

import hashlib
import json
import time
from datetime import datetime, timedelta, timezone

from ingest import arcgis, db, http

LAYER = "https://gisportal-idfg.idaho.gov/hosting/rest/services/Roadkill/Roadkill_Observations/MapServer/1"
HOST = "gisportal-idfg.idaho.gov"
RING = (-117.30, 42.90, -115.60, 44.30)       # west, south, east, north: the ring (docs/17 Q19)
VALLEY = (-117.05, 43.00, -115.95, 43.85)     # the valley box, counted in the run's stats
BATCH = 10000        # IDs per range query: the ring's ~9,300 reports in one answer (the layer allows 100,000)
PAUSE_S = 2.0        # between requests, on top of PACE_S below
MIN_SHARE = 0.9      # an answer with fewer than this share of the last run's reports is refused
MST = timedelta(hours=-7)                     # the service's dateFieldsTimeReference (no daylight saving)
SUSPECT_BEFORE_MS = 220924800000              # 1977-01-01T00:00Z: the service says its data starts in 1977

# IDFG's own IIS server also holds its access-site and fishing layers: give it gentle pacing
# (docs/sources/wildlife.md, correction 5). The longest setting for the host wins.
http.PACE_S[HOST] = max(http.PACE_S.get(HOST, 0), 5)

SOURCE = {
    "name": "idfg_roadkill",
    "title": "IDFG roadkill reports (wildlife-vehicle collisions) in the ring",
    "url": LAYER,
    "access": "open",
    "schedule": "1 day",
    "retry_after": "1 hour",
    "license": "none stated (disclaimer only)",
    "credit": "Idaho Department of Fish and Game",
    "notes": "Roadkill_Observations MapServer/1, cut to the ring; every report each day, versioned in "
             "raw.record under our own ID (OBJECTIDs change at each rebuild). note and path dropped at ingest. "
             "Internal, or aggregates only (docs/17 Q17); courtesy note to IDFG due.",
}

# The fields kept, as the layer names them (Oct 7, 2026). Anything else is left out.
KEEP = ("species", "source", "observed", "reported", "salvaged", "sex", "lifeStage", "lifeState", "disposition",
        "decomposition", "latitude", "longitude", "highway", "milepost", "county", "region", "gmu")
DATES = ("observed", "reported")
COORDS = ("latitude", "longitude")
# Known fields left out on purpose (lower case); any other field left out is reported as new.
LEFT_OUT = {"objectid", "globalid", "shape", "note", "path"}


def _get(url):
    return http.get(url, timeout=180, compressed=True)


def fetch(get=None, sleep=time.sleep, stats=None):
    """Every report in the ring, as Esri JSON features. Returns (features, bytes, status, robots)."""
    return arcgis.fetch_layer(LAYER, SOURCE["name"], box=RING, batch=BATCH, pause_s=PAUSE_S, precision=6,
                              stats=stats, get=get or _get, sleep=sleep)


def value(name, v):
    """A kept field's value: dates as integer milliseconds, coordinates as floats, the rest as
    text with whitespace collapsed. Blanks are None."""
    if name in DATES:
        return arcgis.to_int(v)
    if name in COORDS:
        return arcgis.to_float(v)
    return arcgis.text(v)


def local_date(ms):
    """The calendar date of an epoch-milliseconds value in the service's time (MST)."""
    if ms is None:
        return None
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ms) + MST).date()


def has_time(ms):
    """Whether a value carries a time of day (not midnight MST)."""
    return ms is not None and (ms + MST // timedelta(milliseconds=1)) % 86400000 != 0


def inside(lon, lat, box):
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


def location(payload, geom):
    """(lon, lat): the reported coordinates, else the layer's point."""
    lat, lon = payload.get("latitude"), payload.get("longitude")
    if lat is None or lon is None:
        lon, lat = geom["coordinates"]
    return lon, lat


def report_key(payload, geom):
    """Our ID for a report: a hash of its channel, observed and reported times, and point."""
    lon, lat = location(payload, geom)
    ident = [payload.get("source"), payload.get("observed"), payload.get("reported"),
             round(lat, 6) + 0.0, round(lon, 6) + 0.0]
    return hashlib.sha256(json.dumps(ident, separators=(",", ":")).encode()).hexdigest()[:20]


def parse(features):
    """-> (records, info). records: [(our ID, payload, GeoJSON point)] for the reports in the ring;
    info: counts for the run's stats."""
    kept, outside, no_point, new_fields = [], 0, 0, set()
    for f in features:
        attrs = f.get("attributes") or {}
        new_fields |= {k for k in attrs if k not in KEEP and k.lower() not in LEFT_OUT}
        payload = {k: v for k in KEEP if (v := value(k, attrs.get(k))) is not None}
        geom = arcgis.point_geojson(f.get("geometry")) or arcgis.point_geojson(
            {"x": payload.get("longitude"), "y": payload.get("latitude")})
        if geom is None:
            no_point += 1
            continue
        if not inside(*geom["coordinates"], RING):
            outside += 1
            continue
        kept.append((payload, geom))
    groups = {}
    for payload, geom in kept:
        groups.setdefault(report_key(payload, geom), []).append((payload, geom))
    records = []
    for key, alike in groups.items():
        alike.sort(key=lambda pg: json.dumps(pg[0], sort_keys=True))
        for i, (payload, geom) in enumerate(alike, 1):
            records.append((key if i == 1 else f"{key}#{i}", payload, geom))
    observed = [p["observed"] for _, p, _ in records if p.get("observed") is not None]
    reported = [p["reported"] for _, p, _ in records if p.get("reported") is not None]
    info = {
        "reports in the ring": len(records),
        "in the valley box": sum(1 for _, _, g in records if inside(*g["coordinates"], VALLEY)),
        "outside the ring (cut)": outside,
        "without a point": no_point,
        "alike (numbered #2 on)": sum(len(a) - 1 for a in groups.values()),
        "with a time of day": sum(1 for _, p, _ in records if has_time(p.get("observed"))),
        "observed before 1977 (suspect)": sum(1 for ms in observed if ms < SUSPECT_BEFORE_MS),
        "newest observed": str(local_date(max(observed))) if observed else None,
        "newest reported": str(local_date(max(reported))) if reported else None,
        "new fields left out": ", ".join(sorted(new_fields)) or "none",
    }
    return records, info


def check(previous, current):
    """Refuse an answer that is empty, much smaller than the last run's, or keyed afresh.
    previous, current: the last run's IDs and this answer's."""
    previous, current = set(previous), set(current)
    if not current:
        raise RuntimeError(f"{SOURCE['name']}: no reports in the ring; not taken as an answer")
    if len(current) < MIN_SHARE * len(previous):
        raise RuntimeError(f"{SOURCE['name']}: only {len(current)} reports against {len(previous)} last run "
                           "(read during IDFG's rebuild, or a cut layer); nothing stored")
    if arcgis.is_republish(previous, current):
        raise RuntimeError(f"{SOURCE['name']}: {len(current - previous)} of {len(current)} reports are new and "
                           f"{len(previous - current)} of the last run's {len(previous)} are gone: dates or points "
                           "are served differently, so our IDs would duplicate every report; nothing stored")


def last_run_ids(conn):
    """Our IDs for the reports the last stored run saw."""
    return {r[0] for r in conn.execute(
        """select source_id from raw.record where source = %(s)s
           and last_seen = (select max(last_seen) from raw.record where source = %(s)s)""",
        {"s": SOURCE["name"]}).fetchall()}


def store(conn, fetch_id, seen_at, records):
    previous = last_run_ids(conn)
    current = {sid for sid, _, _ in records}
    check(previous, current)
    new, unchanged, _ = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at, complete=False)
    return {"record versions new": new, "unchanged": unchanged,
            "last run's reports not seen": len(previous - current)}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.http_status, f.robots = fetch()
        records, info = parse(features)
        f.records = len(records)
        stats = store(conn, f.id, f.started_at, records)
    return {**stats, **info}
