"""Boise Fire's Boise River hazards and access points (Float the Boise), with hazard lifecycles.

Boise Fire Department GIS's "Boise River Hazards and Access" view
(services1.arcgis.com, Boise_River_Hazards_and_Access_-_VIEW FeatureServer
layer 10; robots.txt 403, so no rules): 119 points from Barber Park to Ann
Morrison Park on Oct 7, 2026: temporary, permanent and extreme hazards,
rapids, put-ins and take-outs, each with a status. It holds only the current
state, so when a hazard was reported and remediated exists only if we poll.
docs/sources/trails.md, "Boise River hazards and access".

Every hour, the whole layer through the shared ArcGIS reader (two small
requests):

- raw.record, as a full snapshot (complete=True; a snapshot with less than
  half of the points we hold is refused): one record per point by OBJECTID,
  every field as published except the editors' user names (Creator, Editor)
  and the "Internal Comments" field, which names people; plus `_geom`, a
  fingerprint of the point, so a moved point is a new version.
- evt.event: one row per hazard (temporary, permanent or extreme) whose
  status is active or potential, from first seen until it's remediated,
  made inactive or deleted. Rapids, put-ins and take-outs are places, not
  events. `declared` starts at the point's CreationDate.

Type and Status are stored as one-letter codes (T, P, E, R, I, O; A, R, I,
P), but some rows hold the word ("Remediated") and a few hold nothing; both
are normalized for the events and kept as published in the records.
Safety-critical: shown in the agencies' words, never as "safe".
"""

from ingest import arcgis, db, events

from ..common import check_raw_snapshot, in_ring, iso

LAYER = ("https://services1.arcgis.com/WHM6qC35aMtyAAlN/arcgis/rest/services/"
         "Boise_River_Hazards_and_Access_-_VIEW/FeatureServer/10")
DROP = {"objectid", "creator", "editor", "comments"}       # the key; staff user names; internal comments
TYPES = {"t": "temporary", "temporary hazard": "temporary", "p": "permanent", "permanent hazard": "permanent",
         "e": "extreme", "extreme hazard": "extreme", "r": "rapid", "rapid": "rapid",
         "i": "put_in", "put-in": "put_in", "o": "take_out", "take-out": "take_out"}
STATUSES = {"a": "active", "active": "active", "r": "remediated", "remediated": "remediated",
            "i": "inactive", "inactive": "inactive", "p": "potential", "potential": "potential"}
HAZARDS = ("extreme", "permanent", "temporary")
LIVE = ("active", "potential")

SOURCE = {
    "name": "boise_river_hazards",
    "title": "Boise River hazards, rapids, put-ins and take-outs (Boise Fire, Float the Boise)",
    "url": LAYER,
    "access": "open",
    "schedule": "1 hour",
    "license": "none stated (City of Boise / Boise Fire layer)",
    "credit": "Boise Fire Department and City of Boise (Float the Boise)",
    "notes": "Full snapshot each run into raw.record (Creator, Editor and Internal Comments left out); active "
             "and potential hazards as evt.event lifecycles. Internal use with credit until the City answers a "
             "courtesy note.",
}


def _norm(v, table):
    t = (arcgis.text(v) or "").lower()
    return table.get(t)


def hazard_type(p):
    return _norm(p.get("Type"), TYPES)


def status(p):
    return _norm(p.get("Status"), STATUSES)


def parse(features):
    """{OBJECTID: (payload, point)} for the points inside the ring (or without a position)."""
    out = {}
    for f in features:
        attrs = f.get("attributes") or {}
        oid = arcgis.object_id(attrs, "OBJECTID")
        geom = arcgis.point_geojson(f.get("geometry"))
        if oid is None or (geom and not in_ring(*geom["coordinates"])):
            continue
        payload = {k: v for k, v in attrs.items() if k.lower() not in DROP}
        payload["_geom"] = arcgis.geom_digest(geom)
        out[oid] = (payload, geom)
    return out


def hazard_rows(parsed):
    """evt.event rows: the hazards whose status is active or potential."""
    rows = []
    for oid, (p, geom) in sorted(parsed.items()):
        kind, state = hazard_type(p), status(p)
        if kind not in HAZARDS or state not in LIVE:
            continue
        name, text = arcgis.text(p.get("Name")), arcgis.text(p.get("Descriptions"))
        edited = arcgis.esri_date(p.get("EditDate"))
        rows.append({"source_id": str(oid), "kind": "river_hazard", "geom": geom,
                     "start": arcgis.esri_date(p.get("CreationDate")), "end": None, "severity": kind,
                     "description": ": ".join(x for x in (name, text) if x) or None,
                     "attributes": {"type": kind, "status": state, "name": name,
                                    "mile_marker": arcgis.text(p.get("Marker")),
                                    "edited": iso(edited) if edited else None}})
    return rows


def store(conn, fetch_id, seen_at, parsed):
    check_raw_snapshot(conn, SOURCE["name"], len(parsed), SOURCE["name"])
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], [(oid, p, g) for oid, (p, g) in parsed.items()],
                                                fetch_id, seen_at, complete=True)
    rows = hazard_rows(parsed)
    counts = events.upsert(conn, SOURCE["name"], rows, seen_at)
    return {"points": len(parsed), "versions new": new, "unchanged": unchanged, "removed": removed,
            "live hazards": len(rows), **{f"hazards {k}": v for k, v in counts.items()}}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.http_status, f.robots = arcgis.fetch_layer(LAYER, SOURCE["name"], max_features=5000)
        parsed = parse(features)
        f.records = len(parsed)
        stats = store(conn, f.id, f.started_at, parsed)
    return stats
