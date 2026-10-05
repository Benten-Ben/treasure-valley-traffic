"""Valley Regional Transit GTFS (static) and GTFS-realtime vehicle positions.

VRT publishes these "for public use" (valleyregionaltransit.org/about-us/resources).
Logged bus positions act as probe vehicles: consecutive points give speeds and
delay along signalized arterials served by transit.
"""

import csv
import io
import zipfile

from ..http import get
from ..store import point

STATIC_URL = "https://www.valleyregionaltransit.org/GTFS/vrt_transit1.zip"
POSITIONS_URL = ("https://s3.amazonaws.com/etatransit.gtfs/"
                 "valleyregionaltransit.etaspot.net/position_updates.pb")


def _table(zf, name):
    with zf.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding="utf-8-sig")))


def static(store):
    zf = zipfile.ZipFile(io.BytesIO(get(STATIC_URL, timeout=180)))
    routes = {r["route_id"]: r for r in _table(zf, "routes.txt")}
    stops = [(s["stop_id"], point(float(s["stop_lon"]), float(s["stop_lat"])),
              {"name": s.get("stop_name")}) for s in _table(zf, "stops.txt")
             if s.get("stop_lat") and s.get("stop_lon")]
    n = store.upsert_features("vrt_static", "transit_stop", stops)

    shape_route = {}
    for t in _table(zf, "trips.txt"):
        if t.get("shape_id"):
            shape_route.setdefault(t["shape_id"], t["route_id"])
    pts = {}
    for row in _table(zf, "shapes.txt"):
        pts.setdefault(row["shape_id"], []).append(
            (int(row["shape_pt_sequence"]), float(row["shape_pt_lon"]), float(row["shape_pt_lat"])))
    shapes = []
    for sid, seq in pts.items():
        seq.sort()
        r = routes.get(shape_route.get(sid), {})
        shapes.append((sid, {"type": "LineString",
                             "coordinates": [[round(x, 6), round(y, 6)] for _, x, y in seq]},
                       {"route_id": r.get("route_id"), "route": r.get("route_short_name"),
                        "name": r.get("route_long_name"),
                        "color": "#" + (r.get("route_color") or "3366cc")}))
    return n + store.upsert_features("vrt_static", "transit_shape", shapes)


def parse_positions(data):
    """Decode a GTFS-realtime feed into position rows."""
    try:
        from google.transit import gtfs_realtime_pb2
    except ImportError as err:
        raise RuntimeError("pip install gtfs-realtime-bindings") from err
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(data)
    rows = []
    for ent in feed.entity:
        if not ent.HasField("vehicle"):
            continue
        v = ent.vehicle
        if not v.HasField("position"):
            continue
        p = v.position
        rows.append((
            v.timestamp or feed.header.timestamp,
            v.vehicle.id or ent.id, v.trip.route_id or None, v.trip.trip_id or None,
            p.latitude, p.longitude,
            p.bearing if p.HasField("bearing") else None,
            p.speed if p.HasField("speed") else None))
    return rows


def positions(store):
    return store.add_positions(parse_positions(get(POSITIONS_URL, timeout=30)))
