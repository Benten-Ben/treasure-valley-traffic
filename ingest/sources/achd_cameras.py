"""ACHD's traffic camera list (GIS layer 26): one point per camera, on its corner pole.

Automated access is allowed (the GIS host has no robots.txt). Quirks:
- 4 cameras are listed twice (same camID, separate records);
- labels sometimes carry stray spaces;
- camtimestamp is one layer-wide value that changes on every refresh, so it's
  left out of the stored record (it would make every fetch a "new version").
"""

from .. import db, http

URL = ("https://gis.achdidaho.org/server/rest/services/Traffic/Traffic_Cameras/MapServer/26/query"
       "?where=1%3D1&outFields=*&returnGeometry=true&outSR=4326&f=geojson")

SOURCE = {
    "name": "achd_cameras",
    "title": "ACHD traffic camera list (GIS layer 26)",
    "url": "https://gis.achdidaho.org/server/rest/services/Traffic/Traffic_Cameras/MapServer/26",
    "access": "open",
    "schedule": "1 day",
    "license": "none stated",
    "credit": "Ada County Highway District",
    "notes": "camtimestamp is layer-wide and excluded from versioning",
}

VOLATILE = {"camtimestamp"}


def parse(geojson):
    """-> (records, cameras).

    records: (source_id, payload, geometry) per GIS record, keyed by GlobalID.
    cameras: {camID: {"name", "geometry", "source_ids"}} with duplicates merged.
    """
    records, cameras = [], {}
    for f in geojson["features"]:
        props = {k: v for k, v in f["properties"].items() if k not in VOLATILE}
        source_id = props.get("GlobalID") or str(props.get("OBJECTID"))
        geom = f.get("geometry")
        records.append((source_id, props, geom))
        cam_id = props.get("camID")
        if cam_id is None:
            continue
        cam = cameras.setdefault(int(cam_id), {"name": None, "geometry": None, "source_ids": []})
        cam["source_ids"].append(source_id)
        if geom and not cam["geometry"]:
            cam["geometry"] = geom
        if props.get("label") and not cam["name"]:
            cam["name"] = " ".join(str(props["label"]).split())
    return records, cameras


def store(conn, fetch_id, seen_at, records, cameras):
    import json
    new, unchanged, removed = db.upsert_records(conn, SOURCE["name"], records, fetch_id, seen_at)
    for cam_id, c in cameras.items():
        camera_id = conn.execute(
            """insert into core.camera (name, pole_geom, achd_cam_id, active, first_seen, last_seen)
               values (%s, case when %s::text is null then null else ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326) end,
                       %s, true, %s, %s)
               on conflict (achd_cam_id) do update set name = excluded.name, pole_geom = excluded.pole_geom,
                 active = true, last_seen = excluded.last_seen
               returning id""",
            (c["name"] or f"ACHD camera {cam_id}",
             json.dumps(c["geometry"]) if c["geometry"] else None,
             json.dumps(c["geometry"]) if c["geometry"] else None,
             cam_id, seen_at, seen_at)).fetchone()[0]
        for sid in c["source_ids"]:
            conn.execute(
                """insert into core.source_link (source, source_id, entity, entity_id, method, confidence)
                   values (%s, %s, 'camera', %s, 'achd_cam_id', 1)
                   on conflict (source, source_id, entity) do update set entity_id = excluded.entity_id,
                     linked_at = now()""",
                (SOURCE["name"], sid, camera_id))
    retired = conn.execute(
        "update core.camera set active = false where active and achd_cam_id is not null and not (achd_cam_id = any(%s))",
        (list(cameras),)).rowcount
    return {"record versions new": new, "unchanged": unchanged, "removed": removed,
            "cameras": len(cameras), "retired": retired}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        f.http_status, data, f.robots, f.bytes = http.get_json(URL)
        records, cameras = parse(data)
        f.records = len(records)
        stats = store(conn, f.id, f.started_at, records, cameras)
    return stats
