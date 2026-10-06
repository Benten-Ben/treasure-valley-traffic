"""Valley Regional Transit GTFS-realtime: bus positions, trip updates and alerts.

Licensed CC BY 3.0 (credit Valley Regional Transit). The feeds are files on
S3 that refresh about every 30 s. This is a stream, not a scheduled source:
`python3 -m ingest stream vrt_realtime` polls every 30 s and, for each feed
whose bytes changed:

1. archives it as published (TVT_ARCHIVE/vrt-gtfs-rt/<UTC date>/<feed>-<HHMMSS>Z.pb),
   which is the record of truth (docs/12 decision 6);
2. for positions, writes one row per new GPS fix to obs.vehicle_position.

The archive is written before the database, so a database outage loses
nothing: `python3 -m ingest backfill vrt_realtime <archive dir>` reloads it.

After each batch of positions is committed, the playback matcher
(ingest/transit_progress.py) places the new fixes along their routes. It is
isolated so it can never cost a position: it runs only after the commit,
inside try/except with a rollback, with a 5 s budget and an advisory lock.

Routes: VRT's live trip IDs don't match its published schedule (Oct 2026), and
the feed leaves route_id empty. The route comes from, in order: the feed's
route_id; the schedule's trip; or the route number inside the live trip ID
(".._-_Regular_Service-Weekday-9-..."). Buses with plain numeric trip IDs
stay unassigned for now.
"""

import hashlib
import os
import re
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone

from .. import db, http

BASE = "https://s3.amazonaws.com/etatransit.gtfs/valleyregionaltransit.etaspot.net/"
FEEDS = {"position_updates": BASE + "position_updates.pb",
         "trip_updates": BASE + "trip_updates.pb",
         "alerts": BASE + "alerts.pb"}

SOURCE = {
    "name": "vrt_realtime",
    "title": "Valley Regional Transit GTFS-realtime (positions, trip updates, alerts)",
    "url": BASE,
    "access": "open",
    "schedule": None,          # a stream: `python3 -m ingest stream vrt_realtime`
    "license": "CC BY 3.0",
    "credit": "Valley Regional Transit",
    "notes": "Polled every 30 s; each changed feed archived as published, positions parsed.",
}

DAY = r"(?:Weekday|Saturday|Sunday|Mo|Tu|We|Th|Fr|Sa|Su)"
TRIP_ROUTE = re.compile(rf"-{DAY}-([A-Za-z0-9]+)-")


def _pb():
    from google.transit import gtfs_realtime_pb2
    return gtfs_realtime_pb2


def resolve_route(trip_id, feed_route_id, lookup):
    """route_id for a live position, or None. lookup: {"trips": {trip_id: route_id},
    "short": {short_name: route_id}}."""
    if feed_route_id:
        return feed_route_id
    if trip_id and trip_id in lookup["trips"]:
        return lookup["trips"][trip_id]
    m = TRIP_ROUTE.search(trip_id or "")
    return lookup["short"].get(m.group(1)) if m else None


def _ts(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc) if epoch else None


def parse_positions(data, lookup):
    """-> (feed time, [row dict]) from a VehiclePositions feed."""
    feed = _pb().FeedMessage()
    feed.ParseFromString(data)
    feed_ts = _ts(feed.header.timestamp)
    rows = []
    for e in feed.entity:
        if not e.HasField("vehicle"):
            continue
        v = e.vehicle
        if not v.HasField("position"):
            continue
        p = v.position
        vehicle_id = v.vehicle.id or v.vehicle.label or e.id
        ts = _ts(v.timestamp) or feed_ts
        if not vehicle_id or ts is None:
            continue
        rows.append({
            "ts": ts, "vehicle_id": vehicle_id, "vehicle_label": v.vehicle.label or None,
            "trip_id": v.trip.trip_id or None,
            "route_id": resolve_route(v.trip.trip_id, v.trip.route_id, lookup),
            "lon": p.longitude, "lat": p.latitude,
            "bearing": p.bearing if p.HasField("bearing") else None,
            "speed_ms": p.speed if p.HasField("speed") else None,
            "stop_id": v.stop_id or None,
            "stop_sequence": v.current_stop_sequence if v.HasField("current_stop_sequence") else None,
            "status": v.current_status if v.HasField("current_status") else None,
            "feed_ts": feed_ts,
        })
    return feed_ts, rows


def load_lookup(conn):
    return {"trips": dict(conn.execute("select trip_id, route_id from core.transit_trip").fetchall()),
            "short": dict(conn.execute("select short_name, route_id from core.transit_route where active").fetchall())}


def store_positions(conn, rows):
    """Insert new fixes; a fix already stored (same bus, same time) is skipped. Returns rows inserted."""
    if not rows:
        return 0
    with conn.cursor() as cur:
        cur.executemany(
            """insert into obs.vehicle_position (ts, vehicle_id, vehicle_label, trip_id, route_id, geom, bearing,
                 speed_ms, stop_id, stop_sequence, status, feed_ts)
               values (%(ts)s, %(vehicle_id)s, %(vehicle_label)s, %(trip_id)s, %(route_id)s,
                 st_setsrid(st_makepoint(%(lon)s, %(lat)s), 4326), %(bearing)s, %(speed_ms)s, %(stop_id)s,
                 %(stop_sequence)s, %(status)s, %(feed_ts)s)
               on conflict (vehicle_id, ts) do nothing""", rows)
        return max(cur.rowcount, 0)


def match_progress(conn, rows, matcher=None):
    """Place a just-committed batch of fixes along their routes, for playback
    (ingest/transit_progress.py). Bus positions are the most valuable live data,
    so this runs only after they're committed, and nothing it does can undo
    them: any error is logged and rolled back, and the stream carries on.
    Returns the matcher's stats, or None if it failed."""
    try:
        if matcher is None:
            from .. import transit_progress     # imported here: it imports this module
            matcher = transit_progress.after_batch
        return matcher(conn, fresh={(r["vehicle_id"], r["ts"]) for r in rows})
    except Exception:
        print(f"vrt_realtime: playback matching failed (positions are stored):\n{traceback.format_exc()}",
              flush=True)
        try:
            conn.rollback()
        except Exception:
            pass
        return None


def record_positions(conn, data, lookup, status=None, decision=None, matcher=None):
    """Store one positions snapshot, then match it for playback. The positions are
    committed (db.Fetch commits on exit) before the matcher starts, and the matcher
    can't raise past match_progress. Returns (new fixes, matcher stats or None)."""
    with db.Fetch(conn, SOURCE["name"]) as f:
        f.http_status, f.robots, f.bytes = status, decision, len(data)
        _, rows = parse_positions(data, lookup)
        n = store_positions(conn, rows)
        f.records = n
    return n, match_progress(conn, rows, matcher)


def archive_path(root, feed, when):
    day = os.path.join(root, "vrt-gtfs-rt", when.strftime("%Y-%m-%d"))
    return os.path.join(day, f"{feed}-{when.strftime('%H%M%S')}Z.pb")


def write_archive(root, feed, data, when):
    path = archive_path(root, feed, when)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if not os.path.exists(path):
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return path


def stream(every=30):
    """Poll the feeds forever. Never raises: network and database errors are
    logged, and the loop carries on (the archive keeps what the database missed)."""
    root = os.environ.get("TVT_ARCHIVE")
    if not root:
        sys.exit("set TVT_ARCHIVE: the raw archive is the record of truth for this stream")
    print(f"vrt_realtime: polling every {every} s, archiving to {root}", flush=True)
    last, conn, lookup, lookup_at = {}, None, None, 0.0
    snapshots = inserted = 0
    placed = Counter()
    report_at = time.time() + 600
    match_at, matched = time.time() + 60, None
    while True:
        started = time.time()
        for feed, url in FEEDS.items():
            try:
                status, data, decision = http.get(url, timeout=20)
            except Exception as err:
                print(f"vrt_realtime: {feed} fetch failed: {err}", flush=True)
                continue
            digest = hashlib.sha256(data).digest()
            if last.get(feed) == digest:
                continue
            last[feed] = digest
            write_archive(root, feed, data, db.now())
            if feed != "position_updates":
                continue
            snapshots += 1
            try:
                if conn is None:
                    conn = db.connect()
                    db.ensure_source(conn, SOURCE)
                    conn.commit()
                if lookup is None or time.time() - lookup_at > 3600:
                    lookup, lookup_at = load_lookup(conn), time.time()
                n, progress = record_positions(conn, data, lookup, status, decision)
                inserted += n
                if progress:
                    for k, v in progress.items():
                        if k in ("rows", "deferred", "skipped (locked)"):
                            placed[k] += v
            except Exception:
                print(f"vrt_realtime: database write failed (archived; backfill later):\n{traceback.format_exc()}",
                      flush=True)
                try:
                    conn and conn.close()
                except Exception:
                    pass
                conn = None
        if conn is not None and time.time() >= match_at:
            try:
                from .. import transit_match       # imported here: it imports this module
                matched = transit_match.run(conn)
            except Exception:
                print(f"vrt_realtime: route matching failed:\n{traceback.format_exc()}", flush=True)
                try:
                    conn.rollback()
                except Exception:
                    pass
            match_at = time.time() + 300
        if time.time() >= report_at:
            print(f"vrt_realtime: last 10 min: {snapshots} position snapshots, {inserted} new fixes"
                  + (f"; route matching: " + ", ".join(f"{k} {v}" for k, v in matched.items()) if matched else "")
                  + (f"; playback progress: " + ", ".join(f"{k} {v}" for k, v in sorted(placed.items()))
                     if placed else ""),
                  flush=True)
            snapshots = inserted = 0
            placed = Counter()
            report_at = time.time() + 600
        time.sleep(max(1.0, every - (time.time() - started)))


def backfill(conn, root):
    """Load every archived positions file under root (oldest first). Fixes
    already stored are skipped, so it's safe to run more than once."""
    lookup = load_lookup(conn)
    files = sorted(os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs
                   if f.startswith("position_updates-") and f.endswith(".pb"))
    total = 0
    for i, path in enumerate(files, 1):
        with open(path, "rb") as fh:
            _, rows = parse_positions(fh.read(), lookup)
        total += store_positions(conn, rows)
        if i % 200 == 0:
            conn.commit()
            print(f"  {i}/{len(files)} files, {total} new fixes", flush=True)
    conn.commit()
    return {"files": len(files), "new fixes": total}
