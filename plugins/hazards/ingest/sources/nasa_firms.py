"""NASA FIRMS active-fire detections in the ring, from the keyless 24-hour CSV files
(docs/sources/hazards.md, "NASA FIRMS active fire detections").

FIRMS rewrites its contiguous-US-and-Hawaii files every hour, each holding the last 24
hours. Without a MAP_KEY (an owner action) there's no ring-only or back-dated pull, so
a detection we don't read within a day is gone from the keyless files. Every hour we
read four files (about 200 KB each; Oct 7, 2026, all four paths confirmed):
VIIRS 375 m on NOAA-20, NOAA-21 and Suomi NPP, and MODIS 1 km (Terra and Aqua).

- raw.record only (detections are occurrences): one record per detection, keyed by
  sensor, satellite, acquisition date and time, and the published latitude and longitude,
  so the hourly rewrites only move last_seen. Every column is kept, numbers typed,
  plus the acquisition time as UTC ISO text. complete=False.
- A file that fails (a 404 when a satellite is retired, or a page that isn't a FIRMS
  CSV) is reported in the stats and the others are stored; if all fail, the fetch fails.

Points are pixel centres; scan and track are the pixel's size in km. Draw them as
footprints, never as pins on houses, and never build structure-fire alerts. Static
industrial heat sources and field burns show up too. NASA open data; credit NASA FIRMS.
robots.txt allows /data/ with Crawl-delay 1 (honored by ingest/http.py; we also pause
2 s between files).
"""

import csv
import io
import time

from ingest import arcgis, db, http
from .. import common

BASE = "https://firms.modaps.eosdis.nasa.gov/data/active_fire"
FILES = (  # (sensor, path under BASE)
    ("viirs_noaa20", "noaa-20-viirs-c2/csv/J1_VIIRS_C2_USA_contiguous_and_Hawaii_24h.csv"),
    ("viirs_noaa21", "noaa-21-viirs-c2/csv/J2_VIIRS_C2_USA_contiguous_and_Hawaii_24h.csv"),
    ("viirs_snpp", "suomi-npp-viirs-c2/csv/SUOMI_VIIRS_C2_USA_contiguous_and_Hawaii_24h.csv"),
    ("modis", "modis-c6.1/csv/MODIS_C6_1_USA_contiguous_and_Hawaii_24h.csv"),
)
PAUSE_S = 2.0
TEXT = {"acq_date", "acq_time", "satellite", "version", "daynight", "instrument", "type"}
HEADER = {"latitude", "longitude", "acq_date", "acq_time", "satellite"}   # every FIRMS CSV starts with these

SOURCE = {
    "name": "nasa_firms",
    "title": "NASA FIRMS active-fire detections, VIIRS and MODIS (the ring)",
    "url": "https://firms.modaps.eosdis.nasa.gov/active_fire/",
    "access": "open",
    "schedule": "1 hour",
    "license": "NASA open data",
    "credit": "NASA FIRMS (LANCE/ESDIS)",
    "notes": "Keyless 24 h CONUS CSVs for VIIRS NOAA-20, NOAA-21, S-NPP and MODIS, hourly; ring rows only, "
             "one raw.record per detection (complete=False). Draw as pixel footprints, never pins on houses.",
}


def value(column, v):
    """A cell typed: numbers as numbers (MODIS confidence is 0-100), words as text
    (VIIRS confidence is low, nominal or high); dates, times and codes stay text."""
    if column in TEXT:
        return arcgis.text(v)
    n = arcgis.number(v)
    return n if n is not None else arcgis.text(v)


def acquired(row):
    """'2026-10-06' and '0930' -> '2026-10-06T09:30:00Z' (FIRMS times are UTC)."""
    d, t = arcgis.text(row.get("acq_date")), (arcgis.text(row.get("acq_time")) or "").zfill(4)
    if not d or not t.isdigit() or len(t) != 4:
        return None
    return f"{d}T{t[:2]}:{t[2:]}:00Z"


def parse(sensor, text, box=common.RING):
    """-> {source_id: (payload, point)} for the file's rows inside the box."""
    out = {}
    for row in csv.DictReader(io.StringIO(text)):
        lat, lon = row.get("latitude"), row.get("longitude")
        if not common.in_ring(lon, lat, box):
            continue
        sid = ":".join([sensor, arcgis.text(row.get("satellite")) or "", arcgis.text(row.get("acq_date")) or "",
                        (arcgis.text(row.get("acq_time")) or "").zfill(4), lat.strip(), lon.strip()])
        payload = {"sensor": sensor, **{k: value(k, v) for k, v in row.items() if k and value(k, v) is not None}}
        payload["acquired"] = acquired(row)
        out[sid] = (payload, {"type": "Point", "coordinates": [float(lon), float(lat)]})
    return out


def is_firms_csv(text):
    """The answer starts with a FIRMS header (not a maintenance or error page served with 200)."""
    first = text.lstrip("\ufeff").split("\n", 1)[0]
    return HEADER <= {c.strip() for c in first.split(",")}


def fetch(get=None, sleep=time.sleep):
    """Read every file. Returns (parsed, failed {sensor: error}, bytes, last status, robots decision).
    An answer that isn't a FIRMS CSV counts as a failed file, so it can't pass as "no detections"."""
    get = get or (lambda url: http.get(url, timeout=120, compressed=True))
    parsed, failed, nbytes, status, decision = {}, {}, 0, None, None
    for i, (sensor, path) in enumerate(FILES):
        if i:
            sleep(PAUSE_S)
        try:
            status, body, decision = get(f"{BASE}/{path}")
        except (OSError, http.RobotsDisallowed) as err:
            failed[sensor] = f"{type(err).__name__}: {err}"[:200]
            continue
        nbytes += len(body)
        text = body.decode("utf-8", "replace")
        if not is_firms_csv(text):
            failed[sensor] = "not a FIRMS CSV (no latitude, longitude, acq_date header)"
            continue
        parsed.update(parse(sensor, text))
    if len(failed) == len(FILES):
        raise RuntimeError("every FIRMS file failed: " + "; ".join(f"{k}: {v}" for k, v in failed.items()))
    return parsed, failed, nbytes, status, decision


def store(conn, fetch_id, seen_at, parsed):
    new, same, _ = db.upsert_records(conn, SOURCE["name"], ((k, p, g) for k, (p, g) in parsed.items()),
                                     fetch_id, seen_at, complete=False)
    return {"detections in the ring": len(parsed), "new": new, "seen again": same}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        parsed, failed, f.bytes, f.http_status, f.robots = fetch()
        f.records = len(parsed)
        stats = store(conn, f.id, f.started_at, parsed)
        if failed:
            stats["files failed"] = "; ".join(f"{k} ({v})" for k, v in failed.items())
    return stats
