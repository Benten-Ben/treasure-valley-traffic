"""Boise River Greenbelt closures and detours (City of Boise Parks and Recreation).

The City's Greenbelt_Closures_View: layer 0 Greenbelt_Construction (closed stretches,
lines) and layer 1 Greenbelt_Detour (detour routes, lines). On Oct 7, 2026 they held two
closures and one detour, all STATUS "Active". There are no start or end dates (only a
CONSTRUCTION_SEASON text), and the layer keeps only the current state, so lifecycles exist
only if we poll: first and last seen are ours. Catalogs: docs/sources/trails.md
("Greenbelt closures, detours and mile markers") and docs/sources/cycling.md ("City of
Boise Greenbelt closures").

Both layers are read every hour, whole (two small requests each). The catalogs suggest
gating on the layer's lastEditDate, but here its description (about 10 KB a layer) costs
more than the rows (2-6 KB), so reading is the cheaper check, and a STATUS flip shows
within the hour whatever the view reports. Each run:

1. every row's version goes to raw.record as '<layer>:<OBJECTID>' (the view has no
   GlobalID), one complete snapshot of both layers;
2. every row in effect is one evt.event row: kind closure (layer 0) or detour (layer 1).
   A row in effect is one whose STATUS (and, for detours, Project_Status) isn't one of
   ENDED; the City flips STATUS to "Inactive" by hand and may leave the row in the layer.
   A row that ends or leaves the layer closes its event's `observed`.

A layer this small may legitimately empty (closures end), so the snapshot guard applies
only once we hold GUARD_FLOOR rows or more; fetch_layer already fails a read that doesn't
come back whole, and a wrongly empty answer heals on the next poll (rows and events that
come back keep their first-seen times).
"""

import time

from ingest import arcgis, db, events

from .. import layers

SERVICE = ("https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/"
           "Greenbelt_Closures_View/FeatureServer")
LAYERS = (  # (layer id, our name for it, evt.event kind)
    (0, "construction", "closure"),
    (1, "detour", "detour"),
)
MAX_ROWS = 500           # per layer; more isn't the layer we know
PRECISION = 6
GUARD_FLOOR = 5          # the snapshot guard applies once we hold this many rows

SOURCE = {
    "name": "boise_greenbelt_closures",
    "title": "Boise River Greenbelt closures and detours (City of Boise)",
    "url": SERVICE,
    "access": "open",
    "schedule": "1 hour",
    "license": "none stated (City of Boise disclaimer only)",
    "credit": "City of Boise Parks and Recreation",
    "notes": "Layers 0 (construction closures) and 1 (detours) read hourly; versions in raw.record as "
             "<layer>:<OBJECTID>; rows in effect (STATUS not Inactive) in evt.event as closure or detour. "
             "No dates in the layer: first and last seen are ours. Courtesy note to the City due.",
}

# STATUS values meaning the row is no longer in effect. The layers' types are "Active" and
# "Inactive" (Oct 7, 2026); the rest guard against wording changes. Blank or unknown counts as
# in effect: the row is still published on the City's closures map.
ENDED = {"inactive", "complete", "completed", "done", "finished", "cancelled", "canceled", "open", "reopened"}

# Fields kept in the event's attributes (all of them stay in raw.record).
ATTRIBUTES = {"PROJECT": "project", "WORK_DESCRIPTION": "work", "CONSTRUCTION_SEASON": "season",
              "CONSTRUCTION_UPDATES": "updates", "RIVER_MILE": "river_mile", "GREENBELT_MILE": "greenbelt_mile",
              "STATUS": "status", "Project_Status": "project_status", "LOCATION": "location",
              "LATITUDE": "latitude", "LONGITUDE": "longitude"}


def layer_url(layer_id):
    return f"{SERVICE}/{layer_id}"


def in_effect(attrs):
    """False once STATUS (or a detour's Project_Status) says the row has ended."""
    for field in ("STATUS", "Project_Status"):
        if (arcgis.text(attrs.get(field)) or "").lower() in ENDED:
            return False
    return True


# Never stored: staff names, should the view carry editor tracking now or later, OBJECTID
# (it's in the key) and the derived length.
DROP = layers.STAFF_FIELDS | {"objectid", "shape__length"}


def payload(part, attrs, geom):
    """The record as versioned: the layer's name, every field but those in DROP, and a
    fingerprint of the line."""
    out = {"layer": part, **{k: v for k, v in attrs.items() if k.lower() not in DROP}}
    out["_geom"] = arcgis.geom_digest(geom)
    return out


def event_row(source_id, part, kind, attrs, geom):
    attributes = {"layer": part}
    for field, key in ATTRIBUTES.items():
        value = arcgis.text(attrs.get(field))
        if value is not None:
            attributes[key] = value
    return {
        "source_id": source_id,
        "kind": kind,
        "geom": geom,
        "start": None,                      # the layer has no dates
        "end": None,
        "severity": None,
        "description": arcgis.text(attrs.get("WORK_DESCRIPTION")) or arcgis.text(attrs.get("PROJECT")),
        "attributes": attributes,
    }


def parse(layers_read):
    """[(layer name, kind, Esri JSON features)] -> (records, event rows, stats)."""
    records, rows = {}, {}
    stats = {"outside the ring": 0, "without an id": 0, "inactive rows": 0}
    for part, kind, features in layers_read:
        for f in features:
            attrs = f.get("attributes") or {}
            oid = arcgis.object_id(attrs, "OBJECTID")
            if oid is None:
                stats["without an id"] += 1
                continue
            geom = arcgis.esri_geometry(f.get("geometry"))
            if not layers.in_ring(geom):
                stats["outside the ring"] += 1
                continue
            source_id = f"{part}:{oid}"
            records[source_id] = (source_id, payload(part, attrs, geom), geom)
            if in_effect(attrs):
                rows[source_id] = event_row(source_id, part, kind, attrs, geom)
            else:
                stats["inactive rows"] += 1
    return list(records.values()), list(rows.values()), stats


def store(conn, fetch_id, seen_at, records, rows):
    """Write one read of both layers: versions (complete snapshot) and the rows in effect."""
    layers.check_snapshot(conn, SOURCE["name"], len(records), SOURCE["name"], floor=GUARD_FLOOR)
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at, complete=True)
    counts = events.upsert(conn, SOURCE["name"], rows, seen_at)
    return {"rows": len(records), "versions new": new, "unchanged": unchanged, "removed": removed,
            "closures": sum(1 for r in rows if r["kind"] == "closure"),
            "detours": sum(1 for r in rows if r["kind"] == "detour"),
            "events new": counts["new"], "changed": counts["changed"], "ended": counts["gone"]}


def run(conn, get=layers.get, sleep=time.sleep):
    db.ensure_source(conn, SOURCE)
    name = SOURCE["name"]
    with db.Fetch(conn, name) as f:
        read, f.bytes = [], 0
        for layer_id, part, kind in LAYERS:
            features, nbytes, f.http_status, f.robots = arcgis.fetch_layer(
                layer_url(layer_id), f"{name} {part}", precision=PRECISION, max_features=MAX_ROWS, get=get, sleep=sleep)
            f.bytes += nbytes
            read.append((part, kind, features))
        records, rows, parse_stats = parse(read)
        f.records = len(records)
        stats = store(conn, f.id, f.started_at, records, rows)
    return {**stats, **{k: v for k, v in parse_stats.items() if v}}
