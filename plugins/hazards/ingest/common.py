"""Pieces the hazards sources share: the ring, one-request ArcGIS reads, Esri polygons as
GeoJSON, the snapshot guard for sources kept only in raw.record, and fire lifecycles
built from incremental reads.

The ring is the regional ring every catalog in docs/sources/ uses (proposed in
docs/DECISIONS.md, "How far the study area reaches"): west -117.30, south 42.90,
east -115.60, north 44.30, taking in Emmett, Mountain Home and Ontario.
"""

import hashlib
import json
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

from ingest import arcgis, db, events

RING = (-117.30, 42.90, -115.60, 44.30)     # west, south, east, north (degrees, WGS84)


def in_ring(lon, lat, box=RING):
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return False
    west, south, east, north = box
    return west <= lon <= east and south <= lat <= north


# --- times -------------------------------------------------------------------

def iso(t):
    """A datetime as UTC ISO text (what attributes hold), or None."""
    return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if t else None


def parse_time(s):
    """ISO text with an offset ('2026-10-07T12:00:00-04:00', '...Z') -> UTC datetime; blanks -> None."""
    s = arcgis.text(s)
    if not s:
        return None
    try:
        t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)


def declared(start, end):
    """(start, end) for evt.event's declared range. An end before the start is dropped
    (tstzrange would refuse it and fail the whole run); so is an end without a start."""
    if start is None or (end is not None and end < start):
        return start, None
    return start, end


# --- ArcGIS ------------------------------------------------------------------

def query_url(layer, where="1=1", box=RING, geometry=True, precision=None):
    q = {"where": where, "outFields": "*", "returnGeometry": "true" if geometry else "false",
         "outSR": "4326", "f": "json"}
    if box:
        q.update({"geometry": ",".join(str(v) for v in box), "geometryType": "esriGeometryEnvelope",
                  "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"})
    if geometry and precision is not None:
        q["geometryPrecision"] = precision
    return layer + "/query?" + urllib.parse.urlencode(q)


def _parse(body):
    data = json.loads(body)
    if "error" in data:
        raise RuntimeError(f"ArcGIS error: {data['error']}")
    if not isinstance(data.get("features"), list):
        raise RuntimeError("ArcGIS answer without a feature list")
    return data


def _cut(data):
    return bool(data.get("exceededTransferLimit") or (data.get("properties") or {}).get("exceededTransferLimit"))


def query_layer(layer, label, *, where="1=1", box=RING, geometry=True, precision=None, page_by_id=False,
                get=None, sleep=time.sleep):
    """Every feature matching `where` and touching `box`, in one request. Returns (features,
    bytes, http status, robots decision).

    The ring's answers are far below these servers' page sizes (2,000 and 4,000), and one
    request can't straddle a layer being rebuilt: NWS reloads its layer, renumbering
    objectid, every few minutes, and arcgis.fetch_layer's IDs-then-ranges read could
    fall between two loads. An answer cut at the page size fails the fetch, or, with
    page_by_id, is read again through arcgis.fetch_layer (for one-off bootstrap reads).
    Network errors and 5xx answers are retried with backoff (arcgis.get_with_retries)."""
    status, body, decision, data = arcgis.get_with_retries(query_url(layer, where, box, geometry, precision),
                                                           label, get, sleep=sleep, parse=_parse)
    if not _cut(data):
        return data["features"], len(body), status, decision
    if not page_by_id:
        raise RuntimeError(f"{label}: the answer was cut at the server's page size; not taken as whole")
    sleep(arcgis.PAUSE_S)
    features, n, status, decision = arcgis.fetch_layer(layer, label, where=where, box=box, precision=precision,
                                                       get=get, sleep=sleep)
    return features, len(body) + n, status, decision


def clean_attributes(attrs, drop=()):
    """A feature's attributes as versioned: hosting artefacts (`drop`) and empty values left
    out, so a republish or a null that stays null makes no new version."""
    return {k: v for k, v in (attrs or {}).items() if k not in drop and v is not None}


# --- polygons ------------------------------------------------------------------

def polygon_geojson(rings):
    """Esri polygon rings -> a GeoJSON Polygon or MultiPolygon (RFC 7946 winding), or None: the shared
    reader's converter (ingest/arcgis.esri_polygon), which keeps a fire in two pieces as two parts."""
    return arcgis.esri_polygon(rings)


def esri_polygon(geometry):
    return polygon_geojson((geometry or {}).get("rings"))


def merge_polygons(geoms):
    """Several (Multi)Polygons as one, parts deduplicated and in a stable order; None if none."""
    parts = {}
    for g in geoms:
        if not g:
            continue
        for part in ([g["coordinates"]] if g["type"] == "Polygon" else g["coordinates"]):
            parts.setdefault(json.dumps(part, separators=(",", ":")), part)
    ordered = [parts[k] for k in sorted(parts)]
    if not ordered:
        return None
    return {"type": "Polygon", "coordinates": ordered[0]} if len(ordered) == 1 else \
        {"type": "MultiPolygon", "coordinates": ordered}


# --- raw.record ------------------------------------------------------------------

def check_snapshot(conn, source, n, label, share=db.SNAPSHOT_MIN_SHARE):
    """db.check_snapshot for a source kept only in raw.record: refuse a snapshot with fewer
    than `share` of the records current now (an emptied or cut-off layer looks like that).
    The fetch is logged as failed and nothing is retired."""
    current = conn.execute("""select count(distinct source_id) from raw.record
                              where source = %s and removed_at is null""", (source,)).fetchone()[0]
    if n == 0 or n < share * current:
        raise RuntimeError(f"{label}: only {n} records against {current} current; not taken as a full snapshot")


def latest(conn, source, ids=None, current_only=False):
    """{source_id: (payload, GeoJSON geometry or None)}: each record's newest version
    (optionally only those not removed), for all records or the given IDs."""
    if ids is not None and not ids:
        return {}
    sql = """select distinct on (source_id) source_id, payload, ST_AsGeoJSON(geom)::json
             from raw.record where source = %s"""
    params = [source]
    if ids is not None:
        sql += " and source_id = any(%s)"
        params.append(list(ids))
    if current_only:
        sql += " and removed_at is null"
    sql += " order by source_id, last_seen desc, first_seen desc"
    return {sid: (payload, geom) for sid, payload, geom in conn.execute(sql, params).fetchall()}


def heartbeat(conn, source, seen_at):
    """An unchanged snapshot: the current versions were seen again."""
    return conn.execute("update raw.record set last_seen = %s where source = %s and removed_at is null",
                        (seen_at, source)).rowcount


# --- evt.event -----------------------------------------------------------------

def event_hash(row):
    """evt.event's content hash for a row, with the geometry as arcgis.geom_digest's
    fingerprint (about a metre), so a geometry read back from the database hashes the same."""
    body = {k: v for k, v in row.items() if k not in ("source_id", "geom", "content_hash")}
    body["_geom"] = arcgis.geom_digest(row.get("geom"))
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).digest()


# --- fires -----------------------------------------------------------------------

# NIFC's fall-off rules for its _Current views: a fire under 10 acres drops after 3 days
# without an update, 10-100 acres after 8, larger ones after 14 (docs/sources/hazards.md,
# WFIGS "Updates"). We apply them to staleness only, never to containment.
QUIET_DAYS = ((10, 3), (100, 8), (None, 14))

# NWCG fire size classes (acres).
SIZE_CLASSES = ((0.25, "A"), (10, "B"), (100, "C"), (300, "D"), (1000, "E"), (5000, "F"), (None, "G"))


def quiet_days(acres):
    a = acres or 0
    for limit, days in QUIET_DAYS:
        if limit is None or a < limit:
            return days


def size_class(acres):
    if acres is None:
        return None
    for limit, cls in SIZE_CLASSES:
        if limit is None or acres < limit:
            return cls


def fire_open(out, valid, modified, acres, at):
    """A fire's lifecycle stays open until it's declared out (or withdrawn as invalid), or its
    record goes quiet for longer than NIFC's fall-off window for its size. Containment
    never closes it: that's why we poll (a contained fire leaves WFIGS's _Current views)."""
    if out is not None or not valid or modified is None:
        return False
    return at - modified <= timedelta(days=quiet_days(acres))


def plan_lifecycles(known, rows):
    """What to write to evt.event for fires read incrementally.

    known: {source_id: (active, content_hash)} from evt.event; rows: {source_id: (row, open)}
    for every active event and every record read this run. events.upsert takes a whole
    snapshot and marks missing events gone, so it's called twice: first with every row
    that stays or changes (closing ones carry their final state, such as the out time),
    then with the open rows only, which closes the rest. Returns (first, second), or None
    when nothing would change. A fire first seen already over gets no event (raw.record
    keeps it); a closed one comes back only if it's open again or its record changed."""
    first, second, change = [], [], False
    for sid, (row, is_open) in rows.items():
        state = known.get(sid)
        if state is None:
            if not is_open:
                continue
            change = True
        else:
            active, h = state
            same = h == row["content_hash"]
            if not active and not is_open and same:
                continue
            if not active or not is_open or not same:
                change = True
        first.append(row)
        if is_open:
            second.append(row)
    if any(active and sid not in rows for sid, (active, _) in known.items()):
        change = True
    return (first, second) if change else None


def update_lifecycles(conn, source, fetched, seen_at, row_of):
    """Write fire lifecycles to evt.event. fetched: {source_id: (payload, geometry)} read this
    run; row_of(source_id, payload, geometry, at) -> (event row, open?). Active events not
    read this run are rebuilt from their newest raw.record version (so they can go quiet)."""
    known = {sid: (active, bytes(h)) for sid, active, h in conn.execute(
        """select source_id, active, content_hash from evt.event
           where source = %s and (active or source_id = any(%s))""", (source, list(fetched))).fetchall()}
    others = [sid for sid, (active, _) in known.items() if active and sid not in fetched]
    records = {**latest(conn, source, others), **fetched}
    rows = {sid: row_of(sid, payload, geom, seen_at) for sid, (payload, geom) in records.items()}
    plan = plan_lifecycles(known, rows)
    if plan is None:
        return {"events new": 0, "events changed": 0, "events closed": 0}
    first, second = plan
    a = events.upsert(conn, source, first, seen_at)
    b = events.upsert(conn, source, second, seen_at)
    return {"events new": a["new"], "events changed": a["changed"], "events closed": a["gone"] + b["gone"]}
