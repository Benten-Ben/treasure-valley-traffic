"""Writing one source's signal devices into core.signal_device (migration 0011).

Shared by the COMPASS and ACHD signal ingestors. Each device is upserted by
(source, source_id); its intersection_id and distance_m belong to the
intersection build and are left alone here. Devices missing from a complete
snapshot are marked inactive, never deleted.
"""

import json
from collections import Counter

from ingest import db

KINDS = {"signal_intersection", "signal_pole", "ped_hybrid", "rrfb", "ped_conventional",
         "warning_beacon", "school_flasher", "fire_signal"}

def check(conn, source, n):
    """The snapshot guard (db.check_snapshot) for one source's signal devices."""
    db.check_snapshot(conn, "core.signal_device", "source = %s", (source,), n, source)


def store(conn, source, devices, seen_at):
    """devices: dicts with source_id, kind, name, geom (GeoJSON point) and attributes.
    Returns {"devices": n, "by kind": {...}, "retired": n}. Call check(conn, source, n) first,
    before versioning the snapshot."""
    for d in devices:
        if d["kind"] not in KINDS:
            raise ValueError(f"unknown signal device kind {d['kind']!r}")
        device_id = conn.execute(
            """insert into core.signal_device (source, source_id, kind, name, geom, attributes, active, first_seen, last_seen)
               values (%s, %s, %s, %s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), %s, true, %s, %s)
               on conflict (source, source_id) do update set kind = excluded.kind, name = excluded.name,
                 geom = excluded.geom, attributes = excluded.attributes, active = true, last_seen = excluded.last_seen
               returning id""",
            (source, d["source_id"], d["kind"], d.get("name"), json.dumps(d["geom"]),
             json.dumps(d.get("attributes") or {}), seen_at, seen_at)).fetchone()[0]
        conn.execute(
            """insert into core.source_link (source, source_id, entity, entity_id, method, confidence)
               values (%s, %s, 'signal_device', %s, 'source_id', 1)
               on conflict (source, source_id, entity) do update set entity_id = excluded.entity_id""",
            (source, d["source_id"], device_id))
    retired = conn.execute(
        "update core.signal_device set active = false where source = %s and active and last_seen < %s",
        (source, seen_at)).rowcount
    kinds = Counter(d["kind"] for d in devices)
    return {"devices": len(devices), "by kind": dict(sorted(kinds.items())), "retired": retired}
