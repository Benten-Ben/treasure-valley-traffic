"""Writing one source's signal devices into core.signal_device (migration 0011).

Shared by the COMPASS and ACHD signal ingestors. Each device is upserted by
(source, source_id); its intersection_id and distance_m belong to the
intersection build and are left alone here. Devices missing from a complete
snapshot are marked inactive, never deleted.
"""

import json
from collections import Counter

KINDS = {"signal_intersection", "signal_pole", "ped_hybrid", "rrfb", "ped_conventional",
         "warning_beacon", "school_flasher", "fire_signal"}

MIN_SHARE = 0.5      # a snapshot with less than half of what's active now is refused


def check_snapshot(conn, table, where, params, n, label):
    """Refuse a snapshot that would retire most of what we hold (an emptied or cut-off layer
    looks like that); the fetch is logged as failed and nothing is retired."""
    active = conn.execute(f"select count(*) from {table} where active and {where}", params).fetchone()[0]
    if n == 0 or n < MIN_SHARE * active:
        raise RuntimeError(f"{label}: only {n} records against {active} active; not taken as a full snapshot")


def check(conn, source, n):
    check_snapshot(conn, "core.signal_device", "source = %s", (source,), n, source)


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
