"""evt.event: things with lifecycles (docs/12 §12.7), written from a source's full snapshots.

A row is one event as its source names it. `observed` runs from first seen
until the event leaves the source's snapshot; an event that comes back keeps
its first-seen time. Unchanged events write nothing.
"""

import hashlib
import json


def content_hash(row):
    """Of the cleaned content (everything except source_id), so unchanged polls write nothing."""
    body = {k: v for k, v in row.items() if k not in ("source_id", "content_hash")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()).digest()


def upsert(conn, source, rows, seen_at):
    """rows: dicts with source_id, kind, geom (GeoJSON or None), start, end (datetimes or None),
    severity, description, attributes. The rows are the source's whole snapshot: events
    missing from it are marked gone. Returns counts of new, changed, unchanged and gone."""
    counts = {"new": 0, "changed": 0, "unchanged": 0}
    ids = []
    for r in rows:
        ids.append(r["source_id"])
        state = conn.execute(
            """insert into evt.event (source, source_id, kind, geom, declared, observed, active,
                                      severity, description, attributes, content_hash, updated_at)
               values (%(source)s, %(source_id)s, %(kind)s,
                       case when %(geom)s::text is null then null
                            else ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326) end,
                       case when %(start)s::timestamptz is null then null
                            else tstzrange(%(start)s, %(end)s, '[)') end,
                       tstzrange(%(seen)s, null, '[)'), true,
                       %(severity)s, %(description)s, %(attributes)s, %(hash)s, %(seen)s)
               on conflict (source, source_id) do update set
                 kind = excluded.kind, geom = excluded.geom, declared = excluded.declared,
                 severity = excluded.severity, description = excluded.description,
                 attributes = excluded.attributes, content_hash = excluded.content_hash, active = true,
                 observed = case when evt.event.active then evt.event.observed
                                 else tstzrange(lower(evt.event.observed), null, '[)') end,
                 updated_at = case when evt.event.content_hash = excluded.content_hash and evt.event.active
                                   then evt.event.updated_at else excluded.updated_at end
               returning (xmax = 0), updated_at = %(seen)s""",
            {"source": source, "source_id": r["source_id"], "kind": r["kind"],
             "geom": json.dumps(r["geom"]) if r.get("geom") else None,
             "start": r.get("start"), "end": r.get("end"), "seen": seen_at,
             "severity": r.get("severity"), "description": r.get("description"),
             "attributes": json.dumps(r.get("attributes") or {}, default=str),
             "hash": r.get("content_hash") or content_hash(r)}).fetchone()
        counts["new" if state[0] else "changed" if state[1] else "unchanged"] += 1
    counts["gone"] = conn.execute(
        """update evt.event set active = false, observed = tstzrange(lower(observed), %s, '[)'), updated_at = %s
           where source = %s and active and not (source_id = any(%s))""",
        (seen_at, seen_at, source, ids)).rowcount
    return counts
