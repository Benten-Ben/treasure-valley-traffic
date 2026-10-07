"""Shared by the lands plugin's closure and order sources: one ArcGIS layer each, cut to the ring.

These layers hold only what is in force now (or soon): an order that ends or
is rescinded simply disappears. So history exists only if we poll
(docs/17 §17.4, Wave A). Each source reads one layer through the shared
ArcGIS reader (ingest/arcgis.py), query only, and keeps:

- raw.record: one record per order or closure, versioned. Its payload holds
  every field the features agree on once, and each feature's own fields
  (with its geometry fingerprint) under "_parts", so the record is lossless
  and doesn't change when the layer renumbers its object IDs. Object IDs,
  derived shape lengths and areas, and staff user names are left out.
- evt.event: one cleaned row per record (same source_id), with `declared`
  from the order's dates and `observed` from our polls (ingest/events.py).

**The ring.** The regional ring, adopted for lands on Oct 7 (docs/17 Q19;
docs/DECISIONS.md), as the lands and trails catalogs use it (W -117.30,
S 42.90, E -115.60, N 44.30). The layer is queried with that envelope;
anything that comes back from outside it (the reader's by-ID fallback) is
dropped here, and a feature whose geometry can't be read is kept and
counted. A record's polygons are stored as their union, made valid in
PostGIS, since an order's polygons can overlap.

**Reading only when the layer changed.** Each run first reads the layer's
metadata (one small request) and compares its `editingInfo.dataLastEditDate`
with our last full read. The layer is read in full only when it was edited
since shortly before that read, when it doesn't say, or when the last full
read is a day old. A skipped run is logged with no record count.

**Dates.** The agencies publish dates without times: USFS as 12:00 UTC, IDPR
as text ("8/13/2026", "12/31/2026 unless rescinded", "Indefinite"). They're
read as local days (America/Boise), the end date included, so `declared`
runs from the start date's midnight to the midnight after the end date.
Text without a leading date leaves that end open; nothing is guessed.

**Snapshot guard.** A read that would end more than half of the active
events is refused (logged as failed) unless the previous read saw the same
count and was refused too: a real drop (fire closures lifted at the end of
the season) is accepted an hour late, while a layer caught half-rebuilt or
emptied is not taken as the truth. An empty ring is fine when nothing is
active.
"""

import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from ingest import arcgis, db, events, http

RING = (-117.30, 42.90, -115.60, 44.30)       # west, south, east, north
TZ = ZoneInfo("America/Boise")
PRECISION = 6                                 # decimal places of degrees in answers: about 0.1 m
MAX_FEATURES = 2000                           # far more than a ring holds; more fails the read
FULL_READ_EVERY = timedelta(hours=24)
EDIT_SKEW = timedelta(minutes=10)             # their clock against ours
SNAPSHOT_MIN_SHARE = 0.5

HOST = "services1.arcgis.com"
http.PACE_S[HOST] = max(http.PACE_S.get(HOST, 0), 2.0)   # at least 2 s between requests to the host

# Never versioned: object IDs (renumbered when a layer is rebuilt), shape lengths and areas
# (derived from the geometry, which is fingerprinted), and staff user names.
DROP = {"objectid", "fid", "shape__area", "shape__length", "st_area(shape)", "st_perimeter(shape)",
        "shape_area", "shape_length", "creator", "editor", "created_user", "last_edited_user"}

FOREST_ORDER = re.compile(r"\b0\d{3}-\d{2}-\d{2,3}\b")      # USFS order numbers: 0402-03-140
CLOSURE = re.compile(r"\bclos(?:ure|ures|ed)\b|\bpublic use exclusion\b", re.IGNORECASE)
DAY_US = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?!\d)")
DAY_ISO = re.compile(r"^\s*(\d{4})-(\d{2})-(\d{2})(?!\d)")


def _get(url):
    return http.get(url, timeout=180, compressed=True)


# --- the layer's metadata and the edit gate ---------------------------------------

def _info(body, layer):
    info = json.loads(body)
    if not isinstance(info, dict) or "error" in info:
        raise RuntimeError(f"ArcGIS error from {layer}: {info.get('error') if isinstance(info, dict) else info}")
    return info


def layer_info(layer, label):
    """The layer's metadata (?f=json). Returns (info, bytes, http status, robots decision)."""
    status, body, decision, info = arcgis.get_with_retries(layer + "?f=json", label, _get,
                                                           parse=lambda b: _info(b, layer))
    return info, len(body), status, decision


def edited_at(info):
    """When the layer's data was last edited, from its editingInfo; None if it doesn't say."""
    e = info.get("editingInfo") or {}
    return arcgis.esri_date(e.get("dataLastEditDate") or e.get("lastEditDate"))


def missing_fields(info, required):
    """Required fields the layer no longer has (compared without case)."""
    have = {(f.get("name") or "").lower() for f in info.get("fields") or []}
    return [f for f in required if f.lower() not in have]


def needs_read(edited, last, now, every=FULL_READ_EVERY, skew=EDIT_SKEW):
    """Read the layer in full? Yes when we never have (last is None), when the last full read
    is `every` old, when the layer doesn't say when it was edited, or when it was edited since
    shortly before the last full read."""
    if last is None or edited is None or now - last >= every:
        return True
    return edited >= last - skew


def last_read(conn, source):
    """When the source last read its layer in full: its latest good fetch with a record count."""
    return conn.execute("""select max(started_at) from ops.fetch
                           where source = %s and ok and records is not null""", (source,)).fetchone()[0]


# --- geometry -------------------------------------------------------------------

def esri_polygon(g):
    """An Esri JSON polygon as GeoJSON (Polygon, or MultiPolygon with several outer rings), or None:
    the shared reader's converter (ingest/arcgis.esri_polygon; it started here, Oct 7)."""
    return arcgis.esri_polygon((g or {}).get("rings"))


def geojson(g):
    """Esri JSON geometry -> GeoJSON: polygons as above, lines and points by the shared reader."""
    if not g:
        return None
    if "rings" in g:
        return esri_polygon(g)
    try:
        return arcgis.esri_geometry(g)
    except ValueError:
        return None


def combine(geoms):
    """One geometry for a record built from several features (in the order given)."""
    geoms = [g for g in geoms if g]
    if not geoms:
        return None
    if len(geoms) == 1:
        return geoms[0]
    types = {g["type"] for g in geoms}
    for single, multi in (("Polygon", "MultiPolygon"), ("LineString", "MultiLineString"), ("Point", "MultiPoint")):
        if types <= {single, multi}:
            return {"type": multi, "coordinates": [c for g in geoms
                                                   for c in (g["coordinates"] if g["type"] == multi else [g["coordinates"]])]}
    return {"type": "GeometryCollection", "geometries": geoms}


def union(conn, geoms):
    """One valid MultiPolygon for a record's polygons: their union, from PostGIS (each part
    made valid first, outer rings counter-clockwise). An order's polygons can overlap, and a
    MultiPolygon of overlapping parts is invalid: on Oct 7, Deer Point's two polygons (361 and
    201 acres) cover 451 acres together, and Crooked Fire's two 11,017 acres. A valid single
    polygon keeps its shape. None if nothing is left."""
    row = conn.execute("""select ST_AsGeoJSON(ST_Multi(ST_ForcePolygonCCW(ST_CollectionExtract(
                                     ST_Union(ST_MakeValid(ST_GeomFromGeoJSON(g)) order by i), 3))))
                          from unnest(%s::text[]) with ordinality as t(g, i)""",
                       ([json.dumps(g) for g in geoms],)).fetchone()
    out = json.loads(row[0]) if row and row[0] else None
    return out if out and out.get("coordinates") else None


def bbox(geom):
    """(west, south, east, north) of a GeoJSON geometry, or None."""
    xs, ys = [], []

    def walk(c):
        if isinstance(c, (list, tuple)) and c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        elif isinstance(c, (list, tuple)):
            for x in c:
                walk(x)

    if geom and geom.get("type") == "GeometryCollection":
        for g in geom.get("geometries") or []:
            b = bbox(g)
            if b:
                xs.extend((b[0], b[2]))
                ys.extend((b[1], b[3]))
    elif geom:
        walk(geom.get("coordinates"))
    return (min(xs), min(ys), max(xs), max(ys)) if xs else None


def in_ring(geom, ring=RING):
    """The geometry's box touches the ring (the server already tested the geometry itself)."""
    b = bbox(geom)
    return b is not None and b[0] <= ring[2] and b[2] >= ring[0] and b[1] <= ring[3] and b[3] >= ring[1]


# --- fields -----------------------------------------------------------------------

def clean(attrs):
    """The fields worth versioning (see DROP), as published."""
    return {k: v for k, v in (attrs or {}).items() if k.lower() not in DROP}


def merge(parts):
    """One lossless, compact payload from (attributes, geometry) pairs: the fields every part
    agrees on once, and each part's other fields with its geometry fingerprint under "_parts"
    (sorted, so the layer's feature order doesn't matter)."""
    attrs = [clean(a) for a, _ in parts]
    keys = sorted(set().union(*attrs)) if attrs else []
    shared = {k: attrs[0][k] for k in keys if all(k in a and a[k] == attrs[0][k] for a in attrs)}
    own = [{**{k: v for k, v in a.items() if k not in shared}, "_geom": arcgis.geom_digest(g)}
           for a, (_, g) in zip(attrs, parts)]
    own.sort(key=lambda p: json.dumps(p, sort_keys=True, default=str))
    return {**shared, "_parts": own}


def pick(payload, key):
    """A field's value: shared, else the first part that has one."""
    if key in payload:
        return payload[key]
    return next((p[key] for p in payload.get("_parts") or [] if p.get(key) not in (None, "")), None)


def per_part(payload, *keys):
    """[{key: value}] for each part, shared values filled in."""
    return [{k: payload[k] if k in payload else p.get(k) for k in keys} for p in payload.get("_parts") or [{}]]


def total(payload, key):
    """The sum of a numeric field over the parts (acres, miles)."""
    nums = [arcgis.number(r[key]) for r in per_part(payload, key)]
    nums = [n for n in nums if n is not None]
    return round(sum(nums), 2) if nums else None


def text_span(payload, start_keys, end_keys):
    """(first start day, last end day) over the parts, from text date fields; each list of keys
    is tried in order. The end stays open when any part has no readable end."""
    rows = per_part(payload, *start_keys, *end_keys)
    starts = [next((d for d in (text_day(r[k]) for k in start_keys) if d), None) for r in rows]
    ends = [next((d for d in (text_day(r[k]) for k in end_keys) if d), None) for r in rows]
    return min((d for d in starts if d), default=None), (None if None in ends else max(ends))


def latest_edit(payload, key="EditDate"):
    edits = [arcgis.esri_date(r[key]) for r in per_part(payload, key)]
    edits = [e for e in edits if e]
    return max(edits).isoformat() if edits else None


def sentence(*parts):
    """Non-empty texts joined as sentences (a name cut off at its field's length may end in "(")."""
    texts = [t.rstrip(" .(,;:-") for t in (arcgis.text(p) for p in parts) if t]
    texts = [t for t in texts if t]
    return ". ".join(texts) + "." if texts else None


def kind_of(*texts):
    """'closure' when the order or area is closed to entry or use, else 'restriction'."""
    return "closure" if any(t and CLOSURE.search(str(t)) for t in texts) else "restriction"


def order_numbers(*texts):
    """USFS order numbers mentioned in the texts, once each, in order (for linking sources later)."""
    out = []
    for t in texts:
        for m in FOREST_ORDER.findall(str(t or "")):
            if m not in out:
                out.append(m)
    return out


def utc_day(ms):
    """A date-only Esri date (USFS writes them at 12:00 UTC) as its calendar date."""
    d = arcgis.esri_date(ms)
    return d.date() if d else None


def text_day(v):
    """A date at the start of a text field ("8/13/2026", "12/31/2026 unless rescinded",
    "2026-09-19"); None for anything else ("Indefinite", "Until Amended", "")."""
    s = arcgis.text(v)
    if not s:
        return None
    m = DAY_US.match(s)
    try:
        if m:
            year = int(m.group(3))
            return date(year + 2000 if year < 100 else year, int(m.group(1)), int(m.group(2)))
        m = DAY_ISO.match(s)
        if m:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None
    return None


def midnight(day):
    return datetime(day.year, day.month, day.day, tzinfo=TZ).astimezone(timezone.utc)


def declared(start_day, end_day, rescinded=None):
    """(start, end, fixes) for evt.event from local days, the end day included. A rescind
    date earlier than the end ends it at that day's start."""
    fixes = []
    start = midnight(start_day) if start_day else None
    end = midnight(end_day + timedelta(days=1)) if end_day else None
    if rescinded and (end is None or midnight(rescinded) < end):
        end = midnight(rescinded)
        fixes.append("ended_by_rescind_date")
    if start and end and end <= start:
        end = None
        fixes.append("end_before_start")
    return start, end, fixes


def iso(day):
    return day.isoformat() if day else None


# --- snapshot, guard and store -----------------------------------------------------

def snapshot(features, key, counts=None):
    """{source_id: [(attributes, GeoJSON geometry)]} for the features in the ring, grouped by
    key(attributes). Each group's parts are in a stable order (geometry fingerprint, then fields).
    A feature whose geometry can't be read is kept (the server's box query matched it, and
    losing an order would be worse); counts, if given, gets how many were kept that way
    ("without a geometry") and how many were dropped as lying outside the ring."""
    groups = {}
    counts = {} if counts is None else counts
    for f in features:
        attrs = f.get("attributes") or {}
        geom = geojson(f.get("geometry"))
        if geom is None:
            counts["without a geometry"] = counts.get("without a geometry", 0) + 1
        elif not in_ring(geom):
            counts["outside the ring"] = counts.get("outside the ring", 0) + 1
            continue
        groups.setdefault(key(attrs), []).append((attrs, geom))
    for parts in groups.values():
        parts.sort(key=lambda p: (arcgis.geom_digest(p[1]) or "",
                                  json.dumps(clean(p[0]), sort_keys=True, default=str)))
    return groups


def check_drop(conn, source, fetch_id, n):
    """Refuse a read that would end more than half of the source's active events, unless the
    previous read (a fetch with a record count) saw the same count and was refused too.
    Returns a note when a drop is accepted that way, else None."""
    active = conn.execute("select count(*) from evt.event where source = %s and active",
                          (source,)).fetchone()[0]
    if n >= SNAPSHOT_MIN_SHARE * active:
        return None
    prev = conn.execute("""select ok, records from ops.fetch
                           where source = %s and id < %s and records is not null
                           order by id desc limit 1""", (source, fetch_id)).fetchone()
    if prev and not prev[0] and prev[1] == n:
        return f"a drop from {active} to {n} active, seen twice in a row: accepted"
    raise RuntimeError(f"{source}: only {n} records against {active} active; not taken as a full snapshot "
                       "(accepted if the next read sees the same)")


def store(conn, source, fetch_id, seen_at, groups, event):
    """Write one full snapshot: record versions (complete) and events. event(source_id, payload,
    geometry) builds the evt.event row. A record's polygons are stored as their union."""
    records, rows = [], []
    for sid, parts in groups.items():
        payload = merge(parts)
        geoms = [g for _, g in parts if g]
        if geoms and all(g["type"] in ("Polygon", "MultiPolygon") for g in geoms):
            geom = union(conn, geoms) or combine(geoms)
        else:
            geom = combine(geoms)
        records.append((sid, payload, geom))
        rows.append(event(sid, payload, geom))
    new, unchanged, removed = db.upsert_records(conn, source, records, fetch_id, seen_at, complete=True)
    counts = events.upsert(conn, source, rows, seen_at)
    return {"record versions new": new, "unchanged": unchanged, "removed": removed,
            **{f"events {k}": v for k, v in counts.items()}}


def run_layer(conn, source, layer, *, required, key, event, sleep=time.sleep):
    """One run of a closure source: the edit gate, then a full read of the ring if needed."""
    name = source["name"]
    db.ensure_source(conn, source)
    with db.Fetch(conn, name) as f:
        info, f.bytes, f.http_status, f.robots = layer_info(layer, name)
        if missing := missing_fields(info, required):
            raise RuntimeError(f"{name}: the layer no longer has {', '.join(missing)} (schema changed)")
        edited = edited_at(info)
        stats = {"layer edited": edited.isoformat() if edited else "unknown"}
        if not needs_read(edited, last_read(conn, name), f.started_at):
            stats["read"] = "skipped (unchanged since the last full read)"
            return stats
        features, nbytes, f.http_status, f.robots = arcgis.fetch_layer(
            layer, name, box=RING, precision=PRECISION, max_features=MAX_FEATURES, get=_get, sleep=sleep)
        f.bytes += nbytes
        dropped = {}
        groups = snapshot(features, key, dropped)
        f.records = len(groups)
        stats.update({"features": len(features), "records": len(groups), **dropped})
        if note := check_drop(conn, name, f.id, len(groups)):
            stats["guard"] = note
        stats.update(store(conn, name, f.id, f.started_at, groups, event))
    return stats
