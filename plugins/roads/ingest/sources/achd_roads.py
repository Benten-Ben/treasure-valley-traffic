"""ACHD's road centerlines (Ada County): posted speed, class, one-way, level, community.

Open GIS layer (the host has no robots.txt), about 38,700 segments, read in
pages of 2,000 with a pause between requests. Each segment is keyed by
ACHD's PermID, which survives edits (OBJECTID doesn't). A run that changes
the segments rematches every source matched to them (the lane inventories
and OpenStreetMap; segment_match.py), in the same run; any other run
rematches those whose matches are out of date (a rematch that failed). One
matcher failing doesn't stop the others or the run.

Field notes, checked Oct 5, 2026:
- PostSpeed is set on every segment; most local streets read 20 mph, likely a
  residential default rather than surveyed signs.
- OneWay: B both ways, F one way in the line's drawn direction, T against it.
- FromElev/ToElev: 10 at grade, 20 elevated (bridges, overpasses).
"""

import json
import time
import urllib.error

from ingest import db, http
from .. import segment_match

LAYER = "https://gis.achdidaho.org/server/rest/services/Maintenance/Road_Centerline/MapServer/7"
FIELDS = ["OBJECTID", "PermID", "StrtConcat", "StName", "FuncClass", "PostSpeed", "EmergSpeed", "OneWay",
          "Private", "FromElev", "ToElev", "L_CommName", "R_CommName",
          "L_AddFrom", "L_AddTo", "R_AddFrom", "R_AddTo"]
PAGE = 2000
PAUSE_S = 1.0

SOURCE = {
    "name": "achd_roads",
    "title": "ACHD road centerlines (posted speed, class, one-way)",
    "url": LAYER,
    "access": "open",
    "schedule": "7 days",
    "license": "none stated",
    "credit": "Ada County Highway District",
    "notes": "Ada County only. PostSpeed on every segment; locals mostly 20 mph (likely a default).",
}

ONE_WAY = {"B": "both", "F": "forward", "T": "backward"}


def page_url(offset):
    q = {"where": "1=1", "outFields": ",".join(FIELDS), "returnGeometry": "true", "outSR": "4326",
         "orderByFields": "OBJECTID", "resultOffset": offset, "resultRecordCount": PAGE, "f": "geojson"}
    return LAYER + "/query?" + "&".join(f"{k}={v}" for k, v in q.items())


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _text(v):
    v = " ".join(str(v).split()) if v is not None else ""
    return v or None


def segment(props):
    """Our row for one ACHD record."""
    return {
        "perm_id": _int(props.get("PermID")),
        "name": _text(props.get("StrtConcat")) or _text(props.get("StName")),
        "functional_class": (_text(props.get("FuncClass")) or "").title() or None,   # a few read "LOCAL"
        "posted_speed_mph": _int(props.get("PostSpeed")) or None,
        "emergency_speed_mph": _int(props.get("EmergSpeed")) or None,
        "one_way": ONE_WAY.get(_text(props.get("OneWay")) or "B", "both"),
        "private": {"Y": True, "N": False}.get(_text(props.get("Private")) or ""),
        "from_level": _int(props.get("FromElev")),
        "to_level": _int(props.get("ToElev")),
        "community": _text(props.get("L_CommName")) or _text(props.get("R_CommName")),
    }


RETRY_WAITS_S = (5, 15, 45)


def _get_with_retries(url):
    """Network errors, server errors and an unreadable robots.txt are retried with
    backoff. A real robots.txt disallow and other HTTP errors are not."""
    for wait in RETRY_WAITS_S + (None,):
        try:
            return http.get(url, timeout=120)
        except (http.RobotsUnavailable, OSError) as err:
            if wait is None or (isinstance(err, urllib.error.HTTPError) and err.code < 500):
                raise
            print(f"achd_roads: {err}; retrying in {wait} s", flush=True)
            time.sleep(wait)


def fetch_all(fetch):
    """All features, page by page. Returns (features, bytes, robots decision)."""
    features, nbytes, decision, offset = [], 0, None, 0
    while True:
        status, body, decision = _get_with_retries(page_url(offset))
        nbytes += len(body)
        page = json.loads(body)
        if "error" in page:
            raise RuntimeError(f"ACHD GIS error: {page['error']}")
        batch = page.get("features", [])
        features += batch
        fetch.http_status = status
        if len(batch) < PAGE and not page.get("exceededTransferLimit") and not page.get("properties", {}).get("exceededTransferLimit"):
            break
        offset += len(batch)
        if not batch:
            break
        time.sleep(PAUSE_S)
    return features, nbytes, decision


def store(conn, fetch_id, seen_at, features):
    by_perm, duplicates = {}, 0
    for f in features:
        props, geom = f.get("properties") or {}, f.get("geometry")
        perm = _int(props.get("PermID"))
        if perm is None or not geom:
            continue
        if perm in by_perm:
            duplicates += 1
            continue
        by_perm[perm] = (props, geom)
    records = [(perm, props, geom) for perm, (props, geom) in by_perm.items()]
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at)
    for perm, (props, geom) in by_perm.items():
        row = segment(props)
        seg_id = conn.execute(
            """insert into core.road_segment (achd_perm_id, name, functional_class, posted_speed_mph, emergency_speed_mph,
                 one_way, private, from_level, to_level, community, geom, active, first_seen, last_seen)
               values (%(perm_id)s, %(name)s, %(functional_class)s, %(posted_speed_mph)s, %(emergency_speed_mph)s,
                 %(one_way)s, %(private)s, %(from_level)s, %(to_level)s, %(community)s,
                 ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%(geom)s), 4326)), true, %(seen)s, %(seen)s)
               on conflict (achd_perm_id) do update set name = excluded.name,
                 functional_class = excluded.functional_class, posted_speed_mph = excluded.posted_speed_mph,
                 emergency_speed_mph = excluded.emergency_speed_mph, one_way = excluded.one_way,
                 private = excluded.private, from_level = excluded.from_level, to_level = excluded.to_level,
                 community = excluded.community, geom = excluded.geom, active = true, last_seen = excluded.last_seen
               returning id""",
            {**row, "geom": json.dumps(geom), "seen": seen_at}).fetchone()[0]
        conn.execute(
            """insert into core.source_link (source, source_id, entity, entity_id, method, confidence)
               values (%s, %s, 'road_segment', %s, 'achd_perm_id', 1)
               on conflict (source, source_id, entity) do update set entity_id = excluded.entity_id""",
            (SOURCE["name"], str(perm), seg_id))
    retired = conn.execute("update core.road_segment set active = false where active and last_seen < %s",
                           (seen_at,)).rowcount
    return {"record versions new": new, "unchanged": unchanged, "removed": removed,
            "segments": len(by_perm), "duplicate PermIDs skipped": duplicates, "retired": retired}


def changed(stats):
    """Whether a run changed ACHD's segments (new versions, removals or retirements)."""
    return any(stats.get(k) for k in ("record versions new", "removed", "retired"))


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        features, f.bytes, f.robots = fetch_all(f)
        stats = store(conn, f.id, f.started_at, features)
        f.records = stats["segments"]
    # Changed segments: every source matched to them is rematched (owner, Oct 6); otherwise any
    # whose matches are out of date (an earlier rematch that failed). Each is committed in turn;
    # one that fails is logged and the rest still run.
    for name, s in segment_match.rematch_all(conn, only_stale=not changed(stats)).items():
        stats[f"{name} rematched"] = s.get("failed") or s.get("matched lines", s.get("ways matched"))
    return stats
