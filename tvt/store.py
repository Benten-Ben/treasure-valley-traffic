"""SQLite store for ingested data.

Tables:
  fetches            one row per ingest attempt (source, time, ok, records, error)
  features           things that exist: cameras, signals, count stations, crashes...
                     keyed (source, fid); last_seen tells you if it is still current
  events             things that start and end: work zones, roadwork, incidents,
                     message-sign text; first_seen/last_seen/active track lifetime
  observations       numeric time series (source, entity, ts, metric, value)
  vehicle_positions  transit vehicle GPS points (GTFS-realtime)

Geometry is stored as GeoJSON text, properties as JSON text.
"""

import json
import os
import sqlite3
from datetime import datetime, timezone

SCHEMA = """
CREATE TABLE IF NOT EXISTS fetches (
  id INTEGER PRIMARY KEY, source TEXT, started TEXT, ok INTEGER,
  records INTEGER, error TEXT, duration_s REAL);
CREATE TABLE IF NOT EXISTS features (
  source TEXT, fid TEXT, kind TEXT, geometry TEXT, props TEXT,
  first_seen TEXT, last_seen TEXT, PRIMARY KEY (source, fid));
CREATE TABLE IF NOT EXISTS events (
  source TEXT, eid TEXT, kind TEXT, geometry TEXT, props TEXT,
  first_seen TEXT, last_seen TEXT, active INTEGER, PRIMARY KEY (source, eid));
CREATE TABLE IF NOT EXISTS observations (
  source TEXT, entity TEXT, ts TEXT, metric TEXT, value REAL,
  PRIMARY KEY (source, entity, ts, metric));
CREATE TABLE IF NOT EXISTS vehicle_positions (
  ts INTEGER, vehicle TEXT, route TEXT, trip TEXT, lat REAL, lon REAL,
  bearing REAL, speed REAL, PRIMARY KEY (vehicle, ts));
CREATE INDEX IF NOT EXISTS features_kind ON features (kind);
CREATE INDEX IF NOT EXISTS vp_ts ON vehicle_positions (ts);
"""


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def point(lon, lat):
    return {"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}


class Store:
    def __init__(self, path):
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def close(self):
        self.db.close()

    # --- bookkeeping -------------------------------------------------------
    def log_fetch(self, source, started, ok, records, error, duration):
        self.db.execute(
            "INSERT INTO fetches (source, started, ok, records, error, duration_s) "
            "VALUES (?,?,?,?,?,?)", (source, started, int(ok), records, error, duration))
        self.db.commit()

    def last_fetch(self, source, ok_only=False):
        sql = "SELECT started, ok, records, error FROM fetches WHERE source=?"
        if ok_only:
            sql += " AND ok=1"
        return self.db.execute(sql + " ORDER BY id DESC LIMIT 1", (source,)).fetchone()

    # --- features ----------------------------------------------------------
    def upsert_features(self, source, kind, items, seen=None):
        """items: iterable of (fid, geometry_dict_or_None, props_dict)."""
        seen = seen or now_iso()
        rows = [(source, str(fid), kind, json.dumps(geom) if geom else None,
                 json.dumps(props), seen, seen) for fid, geom, props in items]
        self.db.executemany(
            "INSERT INTO features (source, fid, kind, geometry, props, first_seen, last_seen) "
            "VALUES (?,?,?,?,?,?,?) ON CONFLICT (source, fid) DO UPDATE SET "
            "kind=excluded.kind, geometry=excluded.geometry, props=excluded.props, "
            "last_seen=excluded.last_seen", rows)
        self.db.commit()
        return len(rows)

    def current_features(self, source=None, kind=None):
        """Features seen in the latest successful load of their source+kind."""
        sql = ("SELECT f.source, f.fid, f.kind, f.geometry, f.props FROM features f "
               "JOIN (SELECT source, kind, MAX(last_seen) AS ls FROM features "
               "GROUP BY source, kind) m ON f.source=m.source AND f.kind=m.kind "
               "AND f.last_seen=m.ls WHERE 1=1")
        args = []
        if source:
            sql += " AND f.source=?"
            args.append(source)
        if kind:
            sql += " AND f.kind=?"
            args.append(kind)
        for src, fid, knd, geom, props in self.db.execute(sql, args):
            yield {"source": src, "fid": fid, "kind": knd,
                   "geometry": json.loads(geom) if geom else None,
                   "props": json.loads(props)}

    # --- events ------------------------------------------------------------
    def sync_events(self, source, kind, items, seen=None):
        """Upsert the currently active events; mark the rest of this kind inactive."""
        seen = seen or now_iso()
        ids = []
        for eid, geom, props in items:
            ids.append(str(eid))
            self.db.execute(
                "INSERT INTO events (source, eid, kind, geometry, props, first_seen, "
                "last_seen, active) VALUES (?,?,?,?,?,?,?,1) ON CONFLICT (source, eid) "
                "DO UPDATE SET geometry=excluded.geometry, props=excluded.props, "
                "last_seen=excluded.last_seen, active=1",
                (source, str(eid), kind, json.dumps(geom) if geom else None,
                 json.dumps(props), seen, seen))
        marks = ",".join("?" * len(ids))
        self.db.execute(
            f"UPDATE events SET active=0 WHERE source=? AND kind=? AND active=1"
            + (f" AND eid NOT IN ({marks})" if ids else ""), [source, kind, *ids])
        self.db.commit()
        return len(ids)

    def active_events(self, kind=None):
        sql = "SELECT source, eid, kind, geometry, props, first_seen FROM events WHERE active=1"
        args = []
        if kind:
            sql += " AND kind=?"
            args.append(kind)
        for src, eid, knd, geom, props, first in self.db.execute(sql, args):
            yield {"source": src, "eid": eid, "kind": knd, "first_seen": first,
                   "geometry": json.loads(geom) if geom else None,
                   "props": json.loads(props)}

    # --- time series -------------------------------------------------------
    def add_observations(self, source, rows):
        """rows: iterable of (entity, ts_iso, metric, value)."""
        rows = [(source, e, ts, m, v) for e, ts, m, v in rows if v is not None]
        self.db.executemany("INSERT OR REPLACE INTO observations VALUES (?,?,?,?,?)", rows)
        self.db.commit()
        return len(rows)

    def add_positions(self, rows):
        """rows: iterable of (ts_epoch, vehicle, route, trip, lat, lon, bearing, speed)."""
        rows = list(rows)
        self.db.executemany(
            "INSERT OR IGNORE INTO vehicle_positions VALUES (?,?,?,?,?,?,?,?)", rows)
        self.db.commit()
        return len(rows)
