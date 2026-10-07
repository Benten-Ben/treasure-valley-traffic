"""What the water plugin's pollers share: the ring, times, and storing readings.

Readings (gauge and snow-station values, E. coli results, drought statistics)
are stored as raw.record versions with complete=False: nothing is ever retired
because a later answer no longer lists it. The pollers re-read a window (the
last two days, the last 30 days, the last four weeks) so late or revised values
are caught; store_readings() writes only the versions we don't hold yet, so a
re-read doesn't rewrite thousands of unchanged rows. Their last_seen therefore
stays at first_seen: for an observation, when we first saw it is what matters.
"""

from datetime import datetime, timezone

from ingest import db

# The regional ring, adopted for the new plugins on Oct 7 (docs/17 Q19; DECISIONS, "How far the study area reaches"):
# west, south, east, north in degrees. Gauges, snow stations and counties are cut to it.
RING = (-117.30, 42.90, -115.60, 44.30)


def in_ring(lon, lat, box=RING):
    try:
        lon, lat = float(lon), float(lat)
    except (TypeError, ValueError):
        return False
    return box[0] <= lon <= box[2] and box[1] <= lat <= box[3]


def point(lon, lat, places=6):
    """A GeoJSON point, or None for a missing or non-numeric position."""
    try:
        return {"type": "Point", "coordinates": [round(float(lon), places), round(float(lat), places)]}
    except (TypeError, ValueError):
        return None


def iso(dt):
    """A UTC datetime as '2026-10-07T12:45:00Z'."""
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_time(text):
    """An ISO 8601 time with Z or an offset -> aware UTC datetime; None if blank or unreadable."""
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def store_readings(conn, source, records, fetch_id, seen_at):
    """Store readings, skipping the versions already held. records: (source_id, payload,
    GeoJSON or None). Returns (new versions, already held)."""
    records = [(str(i), p, g) for i, p, g in records]
    if not records:
        return 0, 0
    held = {(sid, bytes(h)) for sid, h in conn.execute(
        "select source_id, version_hash from raw.record where source = %s and source_id = any(%s)",
        (source, sorted({r[0] for r in records}))).fetchall()}
    fresh = {}
    for r in records:
        key = (r[0], db.version_hash(r[1]))
        if key not in held:
            fresh.setdefault(key, r)
    new, _, _ = db.upsert_records(conn, source, fresh.values(), fetch_id, seen_at, complete=False)
    return new, len(records) - len(fresh)


def check_raw_snapshot(conn, source, n, label):
    """db.check_snapshot for a source whose full snapshot lives only in raw.record: refuse
    one with less than half of the records the last snapshot left current, or none at all."""
    current = conn.execute("select count(*) from raw.record where source = %s and removed_at is null",
                           (source,)).fetchone()[0]
    if n == 0 or n < db.SNAPSHOT_MIN_SHARE * current:
        raise RuntimeError(f"{label}: only {n} records against {current} current; not taken as a full snapshot")
