"""511 Idaho camera views, from the dated reference file of the Oct 5, 2026 one-off check.

Each view is one 511 image stream (/map/Cctv/<image_id>). Views of ACHD
cameras are linked to our cameras by location (nearest within 200 m), since
511's site numbers differ from ACHD's camera numbers.

The file is a third-party copy, so it's kept with the project's private
files, not in the repository: set TVT_PRIVATE_DATA to the folder holding it.

This source is one-off (never scheduled; the database refuses a schedule for
it). Once the 511 developer key arrives, the official API's cameras endpoint
replaces it.
"""

import csv
import os

from ingest import db

FILE_NAME = "511-camera-views-2026-10-05.csv"

SOURCE = {
    "name": "idaho511_views_oneoff",
    "title": "511 Idaho camera views (one-off list check, Oct 5, 2026)",
    "url": f"{FILE_NAME} (private reference file)",
    "access": "one_off",
    "license": "none stated",
    "credit": "Idaho Transportation Department (511 Idaho)",
    "notes": "Replace with the official 511 API cameras endpoint when the key arrives.",
}
MAX_LINK_M = 200


def path():
    folder = os.environ.get("TVT_PRIVATE_DATA")
    if not folder:
        raise SystemExit(f"{FILE_NAME} is a private reference file, not in the repository: "
                         "set TVT_PRIVATE_DATA to the folder that holds it")
    return os.path.join(folder, FILE_NAME)


def read(file=None):
    with open(file or path(), newline="") as f:
        return [r for r in csv.DictReader(f) if r["source"] == "ACHD"]


def store(conn, fetch_id, seen_at, rows):
    records = [(r["image_id"], r, {"type": "Point", "coordinates": [float(r["lon"]), float(r["lat"])]})
               for r in rows]
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at)
    linked = unlinked = 0
    for r in rows:
        near = conn.execute(
            """select id, ST_Distance(pole_geom::geography, ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography)
               from core.camera where active and pole_geom is not null
               order by pole_geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326) limit 1""",
            (float(r["lon"]), float(r["lat"]), float(r["lon"]), float(r["lat"]))).fetchone()
        if not near or near[1] > MAX_LINK_M:
            unlinked += 1
            continue
        camera_id, dist = near
        disabled = r["image_disabled"] == "True" or r["image_blocked"] == "True"
        view_id = conn.execute(
            """insert into core.camera_view (camera_id, image_id, source, status, direction, description, sort_order)
               values (%s, %s, %s, %s, %s, %s, %s)
               on conflict (image_id) do update set camera_id = excluded.camera_id, status = excluded.status,
                 direction = excluded.direction, description = excluded.description, sort_order = excluded.sort_order
               returning id""",
            (camera_id, int(r["image_id"]), SOURCE["name"], "Disabled" if disabled else "Enabled",
             None if r["direction"] in ("", "Unknown") else r["direction"], r["location"],
             int(r["image_sort"] or 0))).fetchone()[0]
        conn.execute(
            """insert into core.source_link (source, source_id, entity, entity_id, method, distance_m, confidence)
               values (%s, %s, 'camera_view', %s, 'nearest_200m', %s, %s)
               on conflict (source, source_id, entity) do update set entity_id = excluded.entity_id,
                 distance_m = excluded.distance_m, confidence = excluded.confidence, linked_at = now()""",
            (SOURCE["name"], r["image_id"], view_id, dist, max(0.0, 1 - dist / MAX_LINK_M)))
        linked += 1
    return {"record versions new": new, "unchanged": unchanged, "views linked": linked,
            "views without a camera within 200 m": unlinked}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        rows = read()
        f.records, f.robots = len(rows), "one_off"
        stats = store(conn, f.id, f.started_at, rows)
    return stats
