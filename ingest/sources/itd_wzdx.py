"""ITD's work zones, from the WZDx feed on 511 Idaho (owner OK, Oct 6, 2026).

Published for public use and open to republish, crediting ITD (WZDx asks
public feeds to be CC0; Idaho's states no license). The feed is rebuilt on
every request, with a new ETag and header time each time, so "changed since?"
never helps: `python3 -m ingest stream itd_wzdx` fetches it every 5 minutes
(gzip, about 124 KB) and compares the work zones themselves. When they changed:

1. the feed is archived as published (TVT_ARCHIVE/wzdx/<UTC date>/wzdx-<HHMMSS>Z.json.gz);
2. every work zone's version goes to raw.record (new versions added, ones gone
   from the feed get removed_at);
3. evt.event gets one cleaned row per work zone, with `observed` running from
   first seen until it leaves the feed.

Unchanged polls only move raw.record's last_seen. What the feed is like, and
why each fix below exists: docs/08 §8.8.

Fixes on load (listed per row in attributes.fixes):
- an overnight occurrence whose end is a day before its start gets a day added
  (24 on Oct 6, e.g. W Chinden Blvd 10 PM-6 AM);
- a reduced speed sent as "NaN" is dropped; the rest are stored in mph
  (the feed converts round mph to km/h: 72.42 = 45 mph);
- an empty work_zone_type is dropped.
Times and places are as planned (every "verified" flag is false), and worker
presence is a planning field, not live; both are kept as published.
"""

import gzip
import hashlib
import json
import math
import os
import sys
import time
import traceback
from datetime import datetime, timedelta, timezone

from .. import db, events, http

URL = "https://511.idaho.gov/api/wzdx"
POLL_S = 300

SOURCE = {
    "name": "itd_wzdx",
    "title": "ITD work zones (WZDx feed on 511 Idaho)",
    "url": URL,
    "access": "open",
    "schedule": None,          # a stream: `python3 -m ingest stream itd_wzdx`
    "license": "public use; WZDx asks for CC0 (none stated in the feed)",
    "credit": "Idaho Transportation Department (511 Idaho)",
    "notes": "Polled every 5 min; changed snapshots archived; versions in raw.record; cleaned rows in evt.event.",
}

KIND = {"work-zone": "work_zone", "detour": "detour"}
KPH_PER_MPH = 1.609344


def parse_time(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None


def content_digest(feed):
    """Digest of the road events only: the header's times change on every request."""
    return hashlib.sha256(json.dumps(feed.get("features", []), sort_keys=True,
                                     separators=(",", ":")).encode()).digest()


def clean(feature):
    """One WZDx road event -> a dict for evt.event. Never raises on odd values."""
    p = feature.get("properties") or {}
    core = p.get("core_details") or {}
    fixes = []

    start, end = parse_time(p.get("start_date")), parse_time(p.get("end_date"))
    if start and end and end < start:
        if end + timedelta(days=1) >= start:
            end += timedelta(days=1)
            fixes.append("end_date_moved_a_day")
        else:
            end = None
            fixes.append("end_before_start")

    speed = p.get("reduced_speed_limit_kph")
    mph = None
    if speed is not None:
        if isinstance(speed, (int, float)) and not isinstance(speed, bool) and math.isfinite(speed):
            mph = round(speed / KPH_PER_MPH)
        else:
            fixes.append("speed_not_a_number")

    wz_type = p.get("work_zone_type")
    if wz_type == "":
        wz_type = None
        fixes.append("work_zone_type_empty")

    related = {}
    for r in core.get("related_road_events") or []:
        related.setdefault(r.get("type"), []).append(r.get("id"))
    parent = p.get("road_event_id")

    attributes = {
        "road_names": core.get("road_names") or [],
        "direction": core.get("direction"),
        "vehicle_impact": p.get("vehicle_impact"),
        "work_zone_type": wz_type,
        "lanes": [{k: lane.get(k) for k in ("order", "type", "status", "restrictions") if lane.get(k) is not None}
                  for lane in p.get("lanes") or []],
        "reduced_speed_mph": mph,
        "restrictions": p.get("restrictions") or [],
        "types_of_work": p.get("types_of_work") or [],
        "worker_presence": p.get("worker_presence"),       # a planning field in Idaho's feed, not live
        "beginning_cross_street": p.get("beginning_cross_street") or None,
        "ending_cross_street": p.get("ending_cross_street") or None,
        "beginning_milepost": p.get("beginning_milepost"),
        "ending_milepost": p.get("ending_milepost"),
        "location_method": p.get("location_method"),
        "location_verified": bool(p.get("is_start_position_verified") and p.get("is_end_position_verified")),
        "times_verified": bool(p.get("is_start_date_verified") and p.get("is_end_date_verified")),
        "parent_event": parent if parent and parent != feature.get("id") else None,
        "related": related,
        "data_source_id": core.get("data_source_id"),
        "source_updated": core.get("update_date"),
        "fixes": fixes,
    }
    row = {
        "source_id": str(feature.get("id")),
        "kind": KIND.get(core.get("event_type"), core.get("event_type") or "unknown"),
        "geom": feature.get("geometry"),
        "start": start,
        "end": end,
        "description": (core.get("description") or "").strip() or None,
        "attributes": attributes,
    }
    row["content_hash"] = hashlib.sha256(json.dumps(
        {**row, "start": p.get("start_date"), "end": end.isoformat() if end else None},
        sort_keys=True, separators=(",", ":"), default=str).encode()).digest()
    return row


def store(conn, feed, seen_at, fetch_id=None):
    """Write one changed snapshot. Returns counts of new, changed, unchanged and gone work zones."""
    features = [f for f in feed.get("features", []) if f.get("id") is not None]
    new_v, _, removed_v = db.upsert_records(
        conn, SOURCE["name"], ((str(f["id"]), f, f.get("geometry")) for f in features), fetch_id, seen_at)
    counts = events.upsert(conn, SOURCE["name"], (clean(f) for f in features), seen_at)
    counts["versions_added"], counts["versions_removed"] = new_v, removed_v
    return counts


def heartbeat(conn, seen_at):
    """An unchanged poll: the current versions were seen again."""
    return conn.execute("update raw.record set last_seen = %s where source = %s and removed_at is null",
                        (seen_at, SOURCE["name"])).rowcount


def archive_path(root, when):
    return os.path.join(root, "wzdx", when.strftime("%Y-%m-%d"), when.strftime("wzdx-%H%M%SZ.json.gz"))


def archive_time(path):
    """The UTC time a snapshot was fetched, from <date>/wzdx-<HHMMSS>Z.json.gz."""
    day = os.path.basename(os.path.dirname(path))
    return datetime.strptime(day + os.path.basename(path), "%Y-%m-%dwzdx-%H%M%SZ.json.gz").replace(tzinfo=timezone.utc)


def latest_archived_digest(root):
    """Content digest of the newest archived snapshot (so a restart doesn't archive an unchanged feed again)."""
    base = os.path.join(root, "wzdx")
    days = sorted(d for d in os.listdir(base) if not d.startswith(".")) if os.path.isdir(base) else []
    for day in reversed(days):
        files = sorted(f for f in os.listdir(os.path.join(base, day)) if f.endswith(".json.gz"))
        if files:
            try:
                with gzip.open(os.path.join(base, day, files[-1])) as fh:
                    return content_digest(json.load(fh))
            except (OSError, ValueError):
                return None
    return None


def write_archive(root, data, when):
    path = archive_path(root, when)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with gzip.open(tmp, "wb") as f:
        f.write(data)
    os.replace(tmp, path)
    return path


def stream(every=POLL_S):
    """Poll forever. Never raises: network and database errors are logged and the
    loop carries on (changed snapshots are archived before the database write)."""
    root = os.environ.get("TVT_ARCHIVE")
    if not root:
        sys.exit("set TVT_ARCHIVE: changed snapshots are archived there")
    print(f"itd_wzdx: polling every {every} s, archiving changes to {root}/wzdx", flush=True)
    last = conn = None                        # digest of the last snapshot stored
    archived = latest_archived_digest(root)   # ... and archived
    polls = changed = failures = 0
    totals = {"new": 0, "changed": 0, "gone": 0}
    in_feed = None
    report_at = time.time() + 3600
    robots_at = time.time() + 86400
    while True:
        started = time.time()
        seen_at = db.now()
        try:
            status, data, decision = http.get(URL, timeout=60, compressed=True)
            feed = json.loads(data)
        except Exception as err:
            failures += 1
            print(f"itd_wzdx: fetch failed: {err}", flush=True)
            feed = None
        if feed is not None:
            polls += 1
            digest = content_digest(feed)
            in_feed = len(feed.get("features", []))
            if digest != archived:
                write_archive(root, data, seen_at)
                archived = digest
            try:
                if conn is None:
                    conn = db.connect()
                    db.ensure_source(conn, SOURCE)
                    conn.commit()
                with db.Fetch(conn, SOURCE["name"]) as f:
                    f.http_status, f.robots, f.bytes, f.records = status, decision, len(data), in_feed
                    if digest != last:
                        counts = store(conn, feed, seen_at, f.id)
                        changed += 1
                        for k in totals:
                            totals[k] += counts[k]
                        if last is None or counts["new"] or counts["changed"] or counts["gone"]:
                            print("itd_wzdx: " + ", ".join(f"{k} {v}" for k, v in counts.items()), flush=True)
                    else:
                        heartbeat(conn, seen_at)
                last = digest
            except Exception:
                print(f"itd_wzdx: database write failed (snapshot archived; backfill later):\n"
                      f"{traceback.format_exc()}", flush=True)
                try:
                    conn and conn.close()
                except Exception:
                    pass
                conn = None
        if time.time() >= report_at:
            print(f"itd_wzdx: last hour: {polls} polls, {failures} failed, {changed} changed snapshots "
                  f"({totals['new']} new, {totals['changed']} changed, {totals['gone']} gone); "
                  f"{in_feed} work zones in the feed", flush=True)
            polls = changed = failures = 0
            totals = {"new": 0, "changed": 0, "gone": 0}
            report_at = time.time() + 3600
        if time.time() >= robots_at:
            http.forget_robots()
            robots_at = time.time() + 86400
        time.sleep(max(1.0, every - (time.time() - started)))


def backfill(conn, root):
    """Load archived snapshots newer than what the database has, oldest first
    (for after a database outage). Safe to run more than once."""
    db.ensure_source(conn, SOURCE)
    latest = conn.execute("select max(last_seen) from raw.record where source = %s",
                          (SOURCE["name"],)).fetchone()[0]
    files = sorted(os.path.join(d, f) for d, _, fs in os.walk(root) for f in fs
                   if f.startswith("wzdx-") and f.endswith(".json.gz"))
    loaded = 0
    for path in files:
        when = archive_time(path)
        if latest and when <= latest:
            continue
        with gzip.open(path) as fh:
            store(conn, json.load(fh), when)
        conn.commit()
        loaded += 1
    return {"files": len(files), "loaded": loaded}
