"""Road-weather camera stations from 511 Idaho's statewide camera list (docs/14 §14.6, "Road weather").

ITD's road-weather stations (RWIS) carry 2 to 4 cameras each, one per
direction: 385 views at 130 stations statewide in the one-off copy of 511's
camera list (Oct 5, 2026). The `regional` capture service records them every
10 minutes, with 4 Oregon DOT views in the regional ring (docs/11). This
source loads their names, positions and views so the map can draw them:

- every site whose `source` is RWIS, statewide, as a camera with provider
  'ITD RWIS';
- every ODOT site inside the regional ring as provider 'ODOT';
- each of a site's images as a core.camera_view (its 511 image id, its order,
  a direction label when the list gives one, and Disabled when 511 marks the
  image disabled or blocked).

Other sites (ACHD's, ITD's traffic cameras) are left to their own sources.
Stations are matched to cameras by the list's site id (core.source_link), and
views by image id, so loading the same file again changes nothing. A station
that's gone from a newer list is retired (active = false); one view gone from
a site is marked Removed.

Fields read: `id` (the site), `source`, `location`, `roadway`,
`latLng.geography.wellKnownText`, and per image `id`, `sortOrder` and, when
present, `description`, `disabled` and `blocked`.

The file is a third-party copy, so it's kept with the project's private
files, not in the repository: set TVT_PRIVATE_DATA to the folder holding it.
Tests use a synthetic fixture (made-up names, ids and positions). This
source is one-off: run it by hand
(`python3 -m ingest run idaho511_rwis_sites_oneoff`); the database refuses a
schedule for it. The official 511 API's camera list can replace it later.
"""

import json
import os
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from ingest import db

FILE_NAME = "511-camera-sites-statewide-2026-10-05.json"

SOURCE = {
    "name": "idaho511_rwis_sites_oneoff",
    "title": "511 Idaho road-weather camera stations (one-off list check, Oct 5, 2026)",
    "url": f"{FILE_NAME} (private reference file)",
    "access": "one_off",
    "license": "none stated",
    "credit": "Idaho Transportation Department (511 Idaho)",
    "notes": "ITD RWIS stations statewide and Oregon DOT cameras in the regional ring; views by 511 image id. "
             "Replace with the official 511 API cameras endpoint when it's wired in.",
}

# The regional ring (DECISIONS, Oct 5-7; the same box as plugins/conditions' idaho511_api.RING):
# west, south, east, north.
RING = (-117.30, 42.90, -115.60, 44.30)
PROVIDERS = {"RWIS": "ITD RWIS", "ODOT": "ODOT"}
TZ = ZoneInfo("America/Boise")
WKT_POINT = re.compile(r"^\s*POINT\s*Z?\s*\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)", re.I)
BLANK = {"", "unknown", "none", "n/a"}


def path():
    folder = os.environ.get("TVT_PRIVATE_DATA")
    if not folder:
        raise SystemExit(f"{FILE_NAME} is a private reference file, not in the repository: "
                         "set TVT_PRIVATE_DATA to the folder that holds it")
    file = os.path.join(folder, FILE_NAME)
    if not os.path.exists(file):
        raise SystemExit(f"{FILE_NAME} isn't in TVT_PRIVATE_DATA ({folder}): it's kept with the private files")
    return file


def taken_at(file_name):
    """When the list was taken, from the date in its file name (local midnight). Loading the same
    file again then writes the same times, so it changes nothing."""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", os.path.basename(file_name))
    if not m:
        raise ValueError(f"no date in {file_name}")
    return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=TZ)


def sites_of(data):
    """The camera sites: the list itself, or the table's rows ({"data": [...]})."""
    if isinstance(data, dict):
        for key in ("data", "items", "sites"):
            if isinstance(data.get(key), list):
                return data[key]
        raise ValueError("unexpected camera list format: no list of sites")
    if not isinstance(data, list):
        raise ValueError("unexpected camera list format")
    return data


def point(site):
    """(lon, lat) from latLng.geography.wellKnownText, or None."""
    wkt = (((site.get("latLng") or {}).get("geography") or {}).get("wellKnownText")) or ""
    m = WKT_POINT.match(wkt)
    if not m:
        return None
    lon, lat = float(m[1]), float(m[2])
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        return None
    return lon, lat


def in_ring(lon, lat):
    return RING[0] <= lon <= RING[2] and RING[1] <= lat <= RING[3]


def provider_of(site, at):
    """'ITD RWIS' for road-weather sites anywhere, 'ODOT' inside the ring; None for the rest."""
    src = str(site.get("source") or "").strip().upper()
    if src == "RWIS":
        return PROVIDERS["RWIS"]
    if src == "ODOT" and at and in_ring(*at):
        return PROVIDERS["ODOT"]
    return None


def text(v):
    s = " ".join(str(v or "").split())
    return None if s.lower() in BLANK else s


def flag(v):
    return v is True or str(v).strip().lower() == "true"


def site_key(site, images):
    """The list's site id, or (without one) the site's image ids."""
    if site.get("id") not in (None, ""):
        return str(site["id"])
    return "images:" + "-".join(str(i["image_id"]) for i in sorted(images, key=lambda i: i["image_id"]))


def views(site):
    """The site's images in 511's order: image id, order, direction label, status."""
    out = []
    for img in site.get("images") or []:
        try:
            image_id = int(img["id"])
        except (KeyError, TypeError, ValueError):
            continue
        out.append({
            "image_id": image_id,
            "sort_order": int(img.get("sortOrder") or 0),
            "direction": text(img.get("description")),
            "status": "Disabled" if flag(img.get("disabled")) or flag(img.get("blocked")) else "Enabled",
        })
    out.sort(key=lambda v: (v["sort_order"], v["image_id"]))
    return out


def parse(data):
    """The stations this source loads, and how many sites it left to other sources.

    Each station: key, provider, name, roadway, (lon, lat), views and the raw site."""
    stations, skipped = [], 0
    for site in sites_of(data):
        if not isinstance(site, dict):
            skipped += 1
            continue
        at = point(site)
        provider = provider_of(site, at)
        imgs = views(site)
        if not provider or not at or not imgs:
            skipped += 1
            continue
        name = text(site.get("location")) or text(site.get("roadway")) or f"{provider} station"
        stations.append({"key": site_key(site, imgs), "provider": provider, "name": name,
                         "roadway": text(site.get("roadway")), "at": at, "views": imgs, "site": site})
    keys = [s["key"] for s in stations]
    if len(keys) != len(set(keys)):
        raise ValueError("the camera list repeats a site id")
    return stations, skipped


def read(file=None):
    with open(file or path(), encoding="utf-8") as f:
        return json.load(f)


def store(conn, fetch_id, seen_at, stations):
    """Write the stations and their views. Changes only what differs, so a second load of the
    same list changes nothing."""
    name = SOURCE["name"]
    ours = "id in (select entity_id from core.source_link where source = %s and entity = 'camera')"
    db.check_snapshot(conn, "core.camera", ours, (name,), len(stations), name)
    records = [(s["key"], s["site"], {"type": "Point", "coordinates": list(s["at"])}) for s in stations]
    new_versions, unchanged, removed = db.upsert_records(conn, name, records, fetch_id, seen_at)

    st = {"new": 0, "changed": 0, "retired": 0}
    vw = {"new": 0, "changed": 0, "removed": 0}
    keep_cameras, keep_images = [], []
    for s in stations:
        lon, lat = s["at"]
        row = conn.execute(
            "select entity_id from core.source_link where source = %s and source_id = %s and entity = 'camera'",
            (name, s["key"])).fetchone()
        if row is None:
            camera_id = conn.execute(
                """insert into core.camera (name, pole_geom, provider, active, first_seen, last_seen)
                   values (%s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, true, %s, %s) returning id""",
                (s["name"], lon, lat, s["provider"], seen_at, seen_at)).fetchone()[0]
            conn.execute(
                """insert into core.source_link (source, source_id, entity, entity_id, method, confidence)
                   values (%s, %s, 'camera', %s, 'site_id', 1)""",
                (name, s["key"], camera_id))
            st["new"] += 1
        else:
            camera_id = row[0]
            # Only a station that differs is written (a newer list moves last_seen on).
            st["changed"] += conn.execute(
                """update core.camera set name = %(name)s, pole_geom = ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326),
                     provider = %(provider)s, active = true, last_seen = greatest(last_seen, %(seen)s)
                   where id = %(id)s
                     and ((name, provider, active) is distinct from (%(name)s, %(provider)s, true)
                          or pole_geom is null
                          or not ST_Equals(pole_geom, ST_SetSRID(ST_MakePoint(%(lon)s, %(lat)s), 4326))
                          or last_seen < %(seen)s)""",
                {"id": camera_id, "name": s["name"], "provider": s["provider"], "lon": lon, "lat": lat,
                 "seen": seen_at}).rowcount
        keep_cameras.append(camera_id)
        for v in s["views"]:
            keep_images.append(v["image_id"])
            got = conn.execute(
                """insert into core.camera_view (camera_id, image_id, source, status, direction, description, sort_order)
                   values (%s, %s, %s, %s, %s, %s, %s)
                   on conflict (image_id) do update set camera_id = excluded.camera_id, source = excluded.source,
                     status = excluded.status, direction = excluded.direction, sort_order = excluded.sort_order
                   where (core.camera_view.camera_id, core.camera_view.source, core.camera_view.status,
                          core.camera_view.direction, core.camera_view.sort_order)
                     is distinct from (excluded.camera_id, excluded.source, excluded.status,
                                       excluded.direction, excluded.sort_order)
                   returning (xmax = 0)""",
                (camera_id, v["image_id"], name, v["status"], v["direction"], None, v["sort_order"])).fetchone()
            if got is not None:
                vw["new" if got[0] else "changed"] += 1
    # Views 511 no longer lists at these stations, and stations gone from the list.
    vw["removed"] = conn.execute(
        """update core.camera_view set status = 'Removed'
           where source = %s and status is distinct from 'Removed' and not (image_id = any(%s))""",
        (name, keep_images)).rowcount
    st["retired"] = conn.execute(
        f"update core.camera set active = false where active and {ours} and not (id = any(%s))",
        (name, keep_cameras)).rowcount
    by_provider = {}
    for s in stations:
        by_provider[s["provider"]] = by_provider.get(s["provider"], 0) + 1
    return {"record versions new": new_versions, "unchanged": unchanged, "removed": removed,
            "stations": len(stations), **{f"stations {k}": v for k, v in st.items()},
            "views": len(keep_images), **{f"views {k}": v for k, v in vw.items()},
            **{f"provider {p}": n for p, n in sorted(by_provider.items())}}


def run(conn):
    db.ensure_source(conn, SOURCE)
    file = path()
    with db.Fetch(conn, SOURCE["name"]) as f:
        stations, skipped = parse(read(file))
        f.records, f.robots = len(stations), "one_off"
        stats = store(conn, f.id, taken_at(file), stations)
    return {**stats, "sites left to other sources": skipped}
