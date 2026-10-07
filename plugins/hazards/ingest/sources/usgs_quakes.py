"""USGS earthquakes in the ring, from the GeoJSON summary feeds (docs/sources/hazards.md,
"USGS earthquake feeds and FDSN event service (ComCat)").

The "all earthquakes, past week" feed (about 1.4 MB, some 2,000 events worldwide; the
feeds are rebuilt every minute), read hourly, so an event's revisions over its first
week (automatic to reviewed, magnitude, felt reports) are all seen. The ring is quiet:
13 events of M2.5+ since 1970, none this week (Oct 7, 2026), so every magnitude is kept.

- raw.record only (quakes are occurrences): one record per event, keyed by USGS's event
  ID. Each revision is a version. The payload is the feed's properties without the
  links and title (`url`, `detail` and `title` derive from the ID and magnitude) and
  empty fields, plus the depth in km. The point is stored in 2D (raw.record.geom has
  no Z). When USGS changes an event's preferred ID, the event keeps the ID we first
  stored it under (any of its `ids`). complete=False.

Did You Feel It? reports are USGS's aggregates: link out, never collect. Public domain;
credit the USGS. earthquake.usgs.gov answers robots.txt with 404: no rules.
"""

import json

from ingest import db, http
from .. import common

URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/all_week.geojson"
DROP = {"url", "detail", "title"}

SOURCE = {
    "name": "usgs_quakes",
    "title": "USGS earthquakes (past-week summary feed, the ring)",
    "url": URL,
    "access": "open",
    "schedule": "1 hour",
    "license": "public domain",
    "credit": "U.S. Geological Survey, Earthquake Hazards Program",
    "notes": "All-magnitude past-week GeoJSON feed, hourly; events in the ring only, one raw.record per event "
             "with every revision as a version (complete=False).",
}


def ids_of(props):
    return [i for i in (props.get("ids") or "").split(",") if i]


def parse(feed, box=common.RING):
    """-> {event id: (payload, 2D point, [all its ids])} for events inside the box."""
    out = {}
    for f in feed.get("features") or []:
        coords = (f.get("geometry") or {}).get("coordinates") or []
        if len(coords) < 2 or not common.in_ring(coords[0], coords[1], box) or not f.get("id"):
            continue
        props = f.get("properties") or {}
        payload = {"id": f["id"], **common.clean_attributes(props, DROP)}
        if len(coords) > 2 and coords[2] is not None:
            payload["depth_km"] = coords[2]
        point = {"type": "Point", "coordinates": [float(coords[0]), float(coords[1])]}
        out[f["id"]] = (payload, point, [f["id"]] + [i for i in ids_of(props) if i != f["id"]])
    return out


def resolve(parsed, known):
    """Key each event by an ID we already hold for it (any of its ids), else its own."""
    return {next((i for i in ids if i in known), eid): (p, g) for eid, (p, g, ids) in parsed.items()}


def store(conn, fetch_id, seen_at, parsed):
    every = sorted({i for _, _, ids in parsed.values() for i in ids})
    known = {r[0] for r in conn.execute("""select distinct source_id from raw.record
                                           where source = %s and source_id = any(%s)""",
                                        (SOURCE["name"], every)).fetchall()} if every else set()
    records = resolve(parsed, known)
    new, same, _ = db.upsert_records(conn, SOURCE["name"], ((k, p, g) for k, (p, g) in records.items()),
                                     fetch_id, seen_at, complete=False)
    return {"quakes in the ring": len(records), "versions new": new, "unchanged": same}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        f.http_status, body, f.robots = http.get(URL, timeout=120, compressed=True)
        f.bytes = len(body)
        feed = json.loads(body)
        if not isinstance(feed.get("features"), list):
            raise RuntimeError("the USGS feed has no feature list")
        parsed = parse(feed)
        f.records = len(parsed)
        stats = store(conn, f.id, f.started_at, parsed)
    return stats
