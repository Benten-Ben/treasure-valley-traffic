"""Valley Regional Transit's static GTFS: routes, stops, route shapes and trips.

VRT publishes it "for public use" under CC BY 3.0 (credit Valley Regional
Transit). The zip is archived as published (when TVT_ARCHIVE is set), then
loaded into core.transit_*. Rows missing from a newer feed are marked
inactive rather than deleted.

Route colors: VRT's own GTFS colors are four shared tier colors, so routes
can't be told apart by them. Each route gets one of our eight map colors
instead, chosen so routes that share streets differ. The palette is the
validated categorical palette; eight hues can't all be told apart at once,
so the route number always travels with the color. The downtown core is left
out, and so are the other hubs (Towne Square), since every route serving a
hub meets there anyway. A route keeps its color for good, so colors don't
shift when routes come and go.

Note (Oct 2026): the live feed's trip IDs don't match this file's (the file
seems to predate the Oct 1, 2026 service change), so the realtime recorder
also reads the route number from the live trip ID (vrt_realtime.py).
"""

import csv
import hashlib
import io
import os
import zipfile
from collections import Counter, defaultdict

from .. import db, http

URL = "https://www.valleyregionaltransit.org/GTFS/vrt_transit1.zip"

SOURCE = {
    "name": "vrt_gtfs",
    "title": "Valley Regional Transit GTFS (static schedule)",
    "url": URL,
    "access": "open",
    "schedule": "1 day",
    "license": "CC BY 3.0",
    "credit": "Valley Regional Transit",
    "notes": "Routes, stops, shapes and trips; the zip is archived as published.",
}

# The validated categorical palette (8 hues, fixed order), on the cream map.
ROUTE_PALETTE = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
INK = "#2b2a33"
NEAR_M = 40            # routes within this distance of each other run "together"...
SHARED_MIN_M = 300     # ...for at least this long, outside the hubs
HUB_ROUTES = 6         # a stop served by this many routes is a hub (Main Street Station, Towne Square)...
HUB_RADIUS_M = 900     # ...and everything within this distance of it is left out: all its routes meet there


def _table(zf, name):
    if name not in zf.namelist():
        return []
    with zf.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))


def _int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parse_feed(data):
    """The parts of a GTFS zip we keep: routes, stops (with the routes serving
    each), shapes (with their route and direction), trips, and the version."""
    zf = zipfile.ZipFile(io.BytesIO(data))
    info = (_table(zf, "feed_info.txt") or [{}])[0]
    version = info.get("feed_version") or hashlib.sha256(data).hexdigest()[:12]

    routes = []
    for r in _table(zf, "routes.txt"):
        routes.append({"route_id": r["route_id"], "short_name": r.get("route_short_name") or r["route_id"],
                       "long_name": r.get("route_long_name") or None,
                       "gtfs_color": ("#" + r["route_color"].lower()) if r.get("route_color") else None,
                       "sort_order": _int(r.get("route_sort_order"))})

    trips = []
    for t in _table(zf, "trips.txt"):
        trips.append({"trip_id": t["trip_id"], "route_id": t["route_id"], "service_id": t["service_id"],
                      "headsign": t.get("trip_headsign") or None, "direction_id": _int(t.get("direction_id")),
                      "block_id": t.get("block_id") or None, "shape_id": t.get("shape_id") or None})
    trip_route = {t["trip_id"]: t["route_id"] for t in trips}

    stop_routes = defaultdict(set)
    if "stop_times.txt" in zf.namelist():
        with zf.open("stop_times.txt") as f:
            for st in csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")):
                route = trip_route.get(st["trip_id"])
                if route:
                    stop_routes[st["stop_id"]].add(route)
    stops = []
    for s in _table(zf, "stops.txt"):
        if s.get("stop_lat") and s.get("stop_lon"):
            stops.append({"stop_id": s["stop_id"], "name": s.get("stop_name") or None,
                          "lon": float(s["stop_lon"]), "lat": float(s["stop_lat"]),
                          "route_ids": sorted(stop_routes.get(s["stop_id"], ()))})

    shape_trip = {}
    for t in trips:
        if t["shape_id"]:
            shape_trip.setdefault(t["shape_id"], t)
    points = defaultdict(list)
    for p in _table(zf, "shapes.txt"):
        points[p["shape_id"]].append((int(p["shape_pt_sequence"]), float(p["shape_pt_lon"]), float(p["shape_pt_lat"])))
    shapes = []
    for sid, pts in points.items():
        if len(pts) < 2:
            continue
        pts.sort()
        t = shape_trip.get(sid, {})
        shapes.append({"shape_id": sid, "route_id": t.get("route_id"), "direction_id": t.get("direction_id"),
                       "coords": [(x, y) for _, x, y in pts]})
    return {"version": version, "routes": routes, "stops": stops, "shapes": shapes, "trips": trips}


def route_order(routes):
    """Display order: the feed's sort order, else numeric route numbers, then the rest."""
    def key(r):
        n = r["short_name"]
        return (r.get("sort_order") if r.get("sort_order") is not None else 10_000,
                0 if n.isdigit() else 1, int(n) if n.isdigit() else 0, n)
    return [r["route_id"] for r in sorted(routes, key=key)]


def assign_colors(order, neighbors, existing, palette=ROUTE_PALETTE, max_steps=200_000):
    """Colors for routes that don't have one yet; existing colors are kept.

    First an exact search for a coloring where no two neighbors (routes
    sharing streets) match, trying the least-used colors first so the palette
    is spread evenly. If none exists (or the search runs long), each new
    route takes the color least used by its neighbors instead."""
    fixed = {r: c for r, c in existing.items() if c}
    todo = [r for r in order if r not in fixed]
    found = _search(todo, neighbors, dict(fixed), palette, [max_steps])
    if found is not None:
        return found
    colors = dict(fixed)
    for r in sorted(todo, key=lambda r: (-len(neighbors.get(r, ())), order.index(r))):
        near = Counter(colors[n] for n in neighbors.get(r, ()) if n in colors)
        overall = Counter(colors.values())
        colors[r] = min(palette, key=lambda c: (near[c], overall[c], palette.index(c)))
    return colors


def _search(todo, neighbors, colors, palette, budget):
    """Backtracking with DSATUR order: color next the route whose neighbors
    already use the most distinct colors. Returns colors, or None."""
    if not todo:
        return colors
    def saturation(r):
        return len({colors[n] for n in neighbors.get(r, ()) if n in colors})
    r = max(todo, key=lambda r: (saturation(r), len(neighbors.get(r, ()))))
    taken = {colors[n] for n in neighbors.get(r, ()) if n in colors}
    overall = Counter(colors.values())
    for c in sorted(palette, key=lambda c: (overall[c], palette.index(c))):
        if c in taken:
            continue
        budget[0] -= 1
        if budget[0] < 0:
            return None
        colors[r] = c
        found = _search([x for x in todo if x != r], neighbors, colors, palette, budget)
        if found is not None:
            return found
        del colors[r]
    return None


def _luminance(hex_color):
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    la, lb = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def badge_text_color(color):
    """White or ink, whichever reads better on the route color."""
    return "#ffffff" if contrast(color, "#ffffff") >= contrast(color, INK) else INK


def archive_zip(data, version):
    base = os.environ.get("TVT_ARCHIVE")
    if not base:
        return None
    folder = os.path.join(base, "vrt-gtfs")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"{version}-{hashlib.sha256(data).hexdigest()[:8]}.zip")
    if not os.path.exists(path):
        with open(path + ".part", "wb") as f:
            f.write(data)
        os.replace(path + ".part", path)
    return path


def neighbors_from_db(conn):
    """Pairs of routes that run together outside the hubs, from the active shapes."""
    rows = conn.execute(
        """with core_area as (
             select st_union(st_buffer(st_transform(geom, 26911), %(core)s)) as c
             from core.transit_stop where active and cardinality(route_ids) >= %(hub)s),
           r as (
             select route_id, st_transform(st_union(geom), 26911) as g
             from core.transit_shape where active and route_id is not null group by route_id),
           rc as (
             select route_id, coalesce(st_difference(g, (select c from core_area)), g) as g from r)
           select a.route_id, b.route_id,
                  st_length(st_intersection(a.g, st_buffer(b.g, %(near)s))) as shared_m
           from rc a join rc b on a.route_id <> b.route_id and st_dwithin(a.g, b.g, %(near)s)""",
        {"core": HUB_RADIUS_M, "hub": HUB_ROUTES, "near": NEAR_M}).fetchall()
    out = defaultdict(set)
    for a, b, shared in rows:
        if shared >= SHARED_MIN_M:
            out[a].add(b)
            out[b].add(a)
    return out


def store(conn, feed):
    v = feed["version"]
    for r in feed["routes"]:
        conn.execute(
            """insert into core.transit_route (route_id, short_name, long_name, gtfs_color, sort_order, active, feed_version, updated_at)
               values (%(route_id)s, %(short_name)s, %(long_name)s, %(gtfs_color)s, %(sort_order)s, true, %(v)s, now())
               on conflict (route_id) do update set short_name = excluded.short_name, long_name = excluded.long_name,
                 gtfs_color = excluded.gtfs_color, sort_order = excluded.sort_order, active = true,
                 feed_version = excluded.feed_version, updated_at = now()""", {**r, "v": v})
    conn.execute("update core.transit_route set active = false where feed_version <> %s", (v,))

    for s in feed["stops"]:
        conn.execute(
            """insert into core.transit_stop (stop_id, name, geom, route_ids, active, feed_version, updated_at)
               values (%(stop_id)s, %(name)s, st_setsrid(st_makepoint(%(lon)s, %(lat)s), 4326), %(route_ids)s, true, %(v)s, now())
               on conflict (stop_id) do update set name = excluded.name, geom = excluded.geom,
                 route_ids = excluded.route_ids, active = true, feed_version = excluded.feed_version, updated_at = now()""",
            {**s, "v": v})
    conn.execute("update core.transit_stop set active = false where feed_version <> %s", (v,))

    for sh in feed["shapes"]:
        wkt = "LINESTRING(" + ",".join(f"{x} {y}" for x, y in sh["coords"]) + ")"
        conn.execute(
            """insert into core.transit_shape (shape_id, route_id, direction_id, geom, active, feed_version, updated_at)
               values (%(shape_id)s, %(route_id)s, %(direction_id)s, st_geomfromtext(%(wkt)s, 4326), true, %(v)s, now())
               on conflict (shape_id) do update set route_id = excluded.route_id, direction_id = excluded.direction_id,
                 geom = excluded.geom, active = true, feed_version = excluded.feed_version, updated_at = now()""",
            {**sh, "wkt": wkt, "v": v})
    conn.execute("update core.transit_shape set active = false where feed_version <> %s", (v,))

    conn.execute("delete from core.transit_trip")
    with conn.cursor() as cur:
        cur.executemany(
            """insert into core.transit_trip (trip_id, route_id, service_id, headsign, direction_id, block_id, shape_id, feed_version)
               values (%(trip_id)s, %(route_id)s, %(service_id)s, %(headsign)s, %(direction_id)s, %(block_id)s, %(shape_id)s, %(v)s)""",
            [{**t, "v": v} for t in feed["trips"]])

    existing = dict(conn.execute("select route_id, color from core.transit_route").fetchall())
    colors = assign_colors(route_order(feed["routes"]), neighbors_from_db(conn), existing)
    for route_id, color in colors.items():
        conn.execute("update core.transit_route set color = %s, text_color = %s where route_id = %s",
                     (color, badge_text_color(color), route_id))
    return {"routes": len(feed["routes"]), "stops": len(feed["stops"]), "shapes": len(feed["shapes"]),
            "trips": len(feed["trips"]), "new colors": len(set(colors) - {r for r, c in existing.items() if c})}


def run(conn):
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:
        status, data, decision = http.get(URL, timeout=180)
        f.http_status, f.robots, f.bytes = status, decision, len(data)
        feed = parse_feed(data)
        archive_zip(data, feed["version"])
        stats = store(conn, feed)
        f.records = stats["routes"] + stats["stops"] + stats["shapes"] + stats["trips"]
    stats["version"] = feed["version"]
    return stats
