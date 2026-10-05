"""Combine ingested layers into a per-intersection view and GeoJSON exports.

Signalized intersections come from clustering ACHD's traffic-signal points
and OpenStreetMap signal nodes (whichever are present; several points make up
one intersection). Each intersection then gets what's nearby: the closest
ACHD camera, the highest ITD AADT on an adjacent non-interstate segment,
crashes in the last few years, rail crossings (preemption candidates), active work zones,
and bus stops.

Output (all GeoJSON, plus summary.json) goes to an output directory that any
front end can read.
"""

import json
import os
import time
from datetime import datetime, timezone

from .geo import GridIndex, cluster_points, line_vertices, representative_point

CLUSTER_M = 60      # signal points within this distance form one intersection
CAMERA_M = 150
AADT_M = 60
CRASH_M = 60
RAIL_M = 300
WORKZONE_M = 300
STOP_M = 60
BUS_WINDOW_S = 300


def _fc(features):
    return {"type": "FeatureCollection", "features": features}


def _feature(geom, props):
    return {"type": "Feature", "geometry": geom, "properties": props}


def _points(rows):
    for r in rows:
        p = representative_point(r["geometry"])
        if p:
            yield p[0], p[1], r


def intersections(store):
    pts = [(lat, lon, r) for lat, lon, r in _points(store.current_features(kind="signal_asset"))
           if r["props"].get("signal_type") == "traffic"]
    pts += list(_points(store.current_features(kind="signal_node")))
    out = []
    for i, members in enumerate(cluster_points(pts, CLUSTER_M)):
        lat = sum(m[0] for m in members) / len(members)
        lon = sum(m[1] for m in members) / len(members)
        streets = sorted({s for m in members for s in m[2]["props"].get("streets", [])})
        out.append({"id": i, "lat": lat, "lon": lon, "streets": streets,
                    "sources": sorted({m[2]["source"] for m in members})})
    return out


def _index(rows, cell=200):
    idx = GridIndex(cell)
    for lat, lon, r in _points(rows):
        idx.add(lat, lon, r)
    return idx


def build(store, out_dir):
    t0 = time.time()
    os.makedirs(out_dir, exist_ok=True)
    cams = list(store.current_features(kind="camera"))
    cam_idx = _index(cams)
    crash_idx = _index(store.current_features(kind="crash"), cell=100)
    rail = list(store.current_features(kind="rail_crossing"))
    rail_idx = _index(rail)
    stop_idx = _index(store.current_features(kind="transit_stop"), cell=100)
    aadt = list(store.current_features(kind="aadt_segment"))
    aadt_idx = GridIndex(100)
    for seg in aadt:
        if "AIN" in (seg["props"].get("route_id") or ""):  # skip interstate mainlines
            continue
        for lat, lon in line_vertices(seg["geometry"]):
            aadt_idx.add(lat, lon, seg)
    work = [e for e in store.active_events() if e["kind"] in ("work_zone", "roadwork", "incident")]
    work_idx = GridIndex(300)
    for e in work:
        for lat, lon in line_vertices(e["geometry"]) or [representative_point(e["geometry"])]:
            if lat is not None:
                work_idx.add(lat, lon, e["eid"])

    feats = []
    for x in intersections(store):
        lat, lon = x["lat"], x["lon"]
        cam = cam_idx.near(lat, lon, CAMERA_M)
        crashes = [c["props"] for _, c in crash_idx.near(lat, lon, CRASH_M)]
        near_aadt = [s["props"]["aadt"] for _, s in aadt_idx.near(lat, lon, AADT_M)
                     if s["props"].get("aadt")]
        rail_near = rail_idx.near(lat, lon, RAIL_M)
        name = " & ".join(x["streets"]) or (cam[0][1]["props"]["label"] if cam else "")
        feats.append(_feature({"type": "Point", "coordinates": [round(lon, 6), round(lat, 6)]}, {
            "id": x["id"], "name": name, "sources": x["sources"],
            "camera_id": cam[0][1]["fid"] if cam else None,
            "camera_label": cam[0][1]["props"]["label"] if cam else None,
            "camera_image": cam[0][1]["props"]["image_url"] if cam else None,
            "aadt_max_adjacent": max(near_aadt) if near_aadt else None,
            "crashes": len(crashes),
            "crashes_injury": sum(1 for c in crashes if (c.get("injuries") or 0) > 0),
            "crashes_fatal": sum(1 for c in crashes if (c.get("fatalities") or 0) > 0),
            "rail_crossing_m": round(rail_near[0][0]) if rail_near else None,
            "active_work_nearby": len({eid for _, eid in work_idx.near(lat, lon, WORKZONE_M)}),
            "bus_stops_nearby": len(stop_idx.near(lat, lon, STOP_M)),
        }))
    layers = {"intersections": feats}

    layers["cameras"] = [_feature(c["geometry"], {"id": c["fid"], **c["props"]}) for c in cams]
    layers["aadt"] = [_feature(s["geometry"], s["props"]) for s in aadt]
    layers["rail_crossings"] = [_feature(r["geometry"], {"id": r["fid"], **r["props"]}) for r in rail]
    layers["transit_routes"] = [_feature(s["geometry"], s["props"])
                                for s in store.current_features(kind="transit_shape")]
    layers["work"] = [_feature(e["geometry"], {"id": e["eid"], "kind": e["kind"],
                                               "since": e["first_seen"], **e["props"]})
                      for e in store.active_events() if e["kind"] != "message_sign"]
    layers["message_signs"] = [_feature(e["geometry"], {"since": e["first_seen"], **e["props"]})
                               for e in store.active_events("message_sign")]
    cutoff = int(time.time()) - BUS_WINDOW_S
    layers["buses"] = [_feature({"type": "Point", "coordinates": [lon, lat]},
                                {"vehicle": v, "route": r, "ts": ts})
                       for v, r, ts, lat, lon in store.db.execute(
                           "SELECT vehicle, route, MAX(ts), lat, lon FROM vehicle_positions "
                           "WHERE ts >= ? GROUP BY vehicle", (cutoff,))]
    for name, fs in layers.items():
        with open(os.path.join(out_dir, f"{name}.geojson"), "w") as f:
            json.dump(_fc(fs), f)

    weather = dict(store.db.execute(
        "SELECT metric, value FROM observations WHERE source='weather_boi' AND ts="
        "(SELECT MAX(ts) FROM observations WHERE source='weather_boi')").fetchall())
    summary = {
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "layers": {k: len(v) for k, v in layers.items()},
        "weather_boi": weather,
        "last_fetch": {src: store.last_fetch(src, ok_only=True)[0]
                       for (src,) in store.db.execute("SELECT DISTINCT source FROM fetches")
                       if store.last_fetch(src, ok_only=True)},
    }
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"built {out_dir} in {time.time() - t0:.1f}s: "
          + ", ".join(f"{k} {v}" for k, v in summary["layers"].items()))
    return summary
