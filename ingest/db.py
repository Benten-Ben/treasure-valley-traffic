"""Database helpers shared by ingestors: sources, the fetch log, raw record versions."""

import hashlib
import json
import os
from datetime import datetime, timezone

import psycopg


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("set DATABASE_URL (see db/README.md)")
    return psycopg.connect(url)


def now():
    return datetime.now(timezone.utc)


def ensure_source(conn, s):
    """Create or update a source's registry row."""
    conn.execute(
        """insert into ops.source (name, title, url, access, schedule, license, credit, notes)
           values (%(name)s, %(title)s, %(url)s, %(access)s, %(schedule)s, %(license)s, %(credit)s, %(notes)s)
           on conflict (name) do update set title = excluded.title, url = excluded.url,
             access = excluded.access, schedule = excluded.schedule, license = excluded.license,
             credit = excluded.credit, notes = excluded.notes""",
        {"schedule": None, "license": None, "credit": None, "notes": None, **s})


class Fetch:
    """Logs one fetch in ops.fetch. Use as a context manager; set the attributes
    (http_status, robots, records, bytes) as they become known."""

    def __init__(self, conn, source):
        self.conn, self.source = conn, source
        self.http_status = self.robots = self.records = self.bytes = None
        self.started_at = now()
        self.id = None

    def __enter__(self):
        self.id = self.conn.execute(
            "insert into ops.fetch (source, started_at, ok) values (%s, %s, false) returning id",
            (self.source, self.started_at)).fetchone()[0]
        self.conn.commit()
        return self

    def __exit__(self, exc_type, exc, tb):
        if exc_type:
            self.conn.rollback()
        self.conn.execute(
            """update ops.fetch set finished_at = %s, ok = %s, http_status = %s, robots = %s,
                 records = %s, bytes = %s, error = %s where id = %s""",
            (now(), exc_type is None, self.http_status, self.robots, self.records, self.bytes,
             None if exc is None else f"{exc_type.__name__}: {exc}"[:1000], self.id))
        self.conn.commit()
        return False


SNAPSHOT_MIN_SHARE = 0.5      # a snapshot with less than half of what's active now is refused


def check_snapshot(conn, table, where, params, n, label):
    """Refuse a snapshot that would retire most of what we hold (an emptied or cut-off layer
    looks like that); the fetch is logged as failed and nothing is retired. Shared by the
    road, lane, signal and rail-crossing sources."""
    active = conn.execute(f"select count(*) from {table} where active and {where}", params).fetchone()[0]
    if n == 0 or n < SNAPSHOT_MIN_SHARE * active:
        raise RuntimeError(f"{label}: only {n} records against {active} active; not taken as a full snapshot")


def version_hash(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).digest()


def upsert_records(conn, source, records, fetch_id, seen_at, complete=True):
    """Store record versions. records: iterable of (source_id, payload dict, GeoJSON geometry or None).

    A new or changed record adds a version; an unchanged one only moves
    last_seen. With complete=True (a full snapshot), versions not seen in it
    get removed_at. Returns (new_versions, unchanged, removed).
    """
    new = unchanged = 0
    for source_id, payload, geom in records:
        h = version_hash(payload)
        row = conn.execute(
            """insert into raw.record (source, source_id, version_hash, payload, geom, first_seen, last_seen, first_fetch)
               values (%s, %s, %s, %s, case when %s::text is null then null
                                            else ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) end, %s, %s, %s)
               on conflict (source, source_id, version_hash)
               do update set last_seen = excluded.last_seen, removed_at = null
               returning (xmax = 0)""",
            (source, str(source_id), h, json.dumps(payload),
             json.dumps(geom) if geom else None, json.dumps(geom) if geom else None,
             seen_at, seen_at, fetch_id)).fetchone()
        if row[0]:
            new += 1
        else:
            unchanged += 1
    removed = 0
    if complete:
        removed = conn.execute(
            """update raw.record set removed_at = %s
               where source = %s and removed_at is null and last_seen < %s""",
            (seen_at, source, seen_at)).rowcount
    return new, unchanged, removed
