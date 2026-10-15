"""Load a shrubs build into the database (docs/19 §19.8): `python3 -m ingest shrubs-load --build DIR`.

DIR is what plugins/trees/build/build_shrubs.py wrote: build.json (with the area's outline, its inputs and their
licence) and shrubs.geojson. In one transaction the build is recorded in trees.shrub_build and the area's shrubs in
trees.shrub are replaced by the build's. Shrubs have no history of their own: a rebuild replaces them, and
trees.shrub_build keeps each build's inputs, licence, settings and counts. The shrubs are published, so a build whose
republish isn't yes isn't loaded (the build itself refuses such inputs). Standard library plus psycopg."""

import argparse
import io
import json
import math
import os
import sys

LOOKS = ("bush", "sage")
REPUBLISH = ("yes", "aggregates", "internal", "no")    # plugin.json's, loosest to strictest
BAND_M = (0.3, 2.4)
COLUMNS = ("shrub_id", "area", "look", "geom", "ground_m", "height_m", "width_m", "lidar", "fit", "build_id")


def read_build(folder):
    """(build, shrubs) from a build folder, checked: an area and its outline, every shrub with a known look, a point,
    a height in the shrub band and a width, and no id twice."""
    with open(os.path.join(folder, "build.json")) as f:
        build = json.load(f)
    for k in ("build_id", "area", "started_at", "geom", "license", "republish", "credit", "inputs"):
        if not build.get(k):
            raise ValueError(f"build.json has no {k}")
    for k in ("license", "credit"):
        if not isinstance(build[k], str) or not build[k].strip():
            raise ValueError(f"build.json's {k} must be a non-empty string")
    if build["republish"] not in REPUBLISH:
        raise ValueError(f"build.json's republish {build['republish']!r} isn't one of {', '.join(REPUBLISH)}")
    if build["republish"] != "yes":
        raise ValueError(f"the build's republish is {build['republish']!r}: the shrubs are published, so it isn't "
                         "loaded")
    g = build["geom"]
    if g.get("type") not in ("Polygon", "MultiPolygon") or not g.get("coordinates"):
        raise ValueError("build.json's geom must be the area's outline (a Polygon or MultiPolygon)")
    with open(os.path.join(folder, "shrubs.geojson")) as f:
        fc = json.load(f)
    shrubs = []
    for feat in fc.get("features", []):
        p = dict(feat.get("properties") or {})
        geom = feat.get("geometry") or {}
        sid = p.get("id")
        if not sid or not isinstance(sid, str):
            raise ValueError("a shrub has no id")
        if geom.get("type") != "Point":
            raise ValueError(f"shrub {sid}: not a point")
        lon, lat = (float(v) for v in geom["coordinates"][:2])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90) or not (math.isfinite(lon) and math.isfinite(lat)):
            raise ValueError(f"shrub {sid}: not a WGS84 point")
        if p.get("look") not in LOOKS:
            raise ValueError(f"shrub {sid}: look {p.get('look')!r} unknown")
        hgt, w = p.get("height_m"), p.get("width_m")
        if not isinstance(hgt, (int, float)) or not BAND_M[0] <= hgt <= BAND_M[1]:
            raise ValueError(f"shrub {sid}: height {hgt!r} outside {BAND_M[0]}-{BAND_M[1]} m")
        if not isinstance(w, (int, float)) or not w > 0:
            raise ValueError(f"shrub {sid}: no width")
        p["lon"], p["lat"] = lon, lat
        shrubs.append(p)
    ids = [s["id"] for s in shrubs]
    if len(ids) != len(set(ids)):
        raise ValueError("shrub ids repeat")
    return build, shrubs


def _copy_text(v):
    """A value in COPY's text format."""
    if v is None:
        return "\\N"
    s = str(v)
    return s.replace("\\", "\\\\").replace("\t", "\\t").replace("\n", "\\n").replace("\r", "\\r")


def rows(build, shrubs):
    """The trees.shrub rows, as COPY text lines (geom as EWKT)."""
    lidar = (build.get("params") or {}).get("lidar")
    for s in shrubs:
        vals = (s["id"], build["area"], s["look"], f"SRID=4326;POINT({s['lon']!r} {s['lat']!r})", s.get("ground_m"),
                s["height_m"], s["width_m"], lidar, json.dumps(s.get("fit") or {}, separators=(",", ":")),
                build["build_id"])
        yield "\t".join(_copy_text(v) for v in vals) + "\n"


def load(conn, build, shrubs):
    """Record the build and replace its area's shrubs. Doesn't commit."""
    b = build
    conn.execute(
        """insert into trees.shrub_build (build_id, area, started_at, finished_at, geom, inputs, license, republish,
             credit, params, counts)
           values (%s, %s, %s, %s, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326)), %s, %s, %s, %s, %s, %s)
           on conflict (build_id) do update set area = excluded.area, started_at = excluded.started_at,
             finished_at = excluded.finished_at, geom = excluded.geom, inputs = excluded.inputs,
             license = excluded.license, republish = excluded.republish, credit = excluded.credit,
             params = excluded.params, counts = excluded.counts, loaded_at = now()""",
        (b["build_id"], b["area"], b["started_at"], b.get("finished_at"), json.dumps(b["geom"]),
         json.dumps(b["inputs"]), b["license"], b["republish"], b["credit"],
         json.dumps(b.get("params") or {}), json.dumps(b.get("counts") or {})))
    removed = conn.execute("delete from trees.shrub where area = %s", (b["area"],)).rowcount
    with conn.cursor() as cur:
        with cur.copy(f"copy trees.shrub ({', '.join(COLUMNS)}) from stdin") as cp:
            buf = io.StringIO()
            for i, line in enumerate(rows(b, shrubs), 1):
                buf.write(line)
                if i % 5000 == 0:
                    cp.write(buf.getvalue())
                    buf = io.StringIO()
            if buf.tell():
                cp.write(buf.getvalue())
    looks = {k: sum(1 for s in shrubs if s["look"] == k) for k in LOOKS}
    return {"area": b["area"], "build": b["build_id"], "shrubs": len(shrubs), **looks, "replaced": removed}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest shrubs-load", description=__doc__.split("\n")[0])
    ap.add_argument("--build", required=True, help="a build folder written by plugins/trees/build/build_shrubs.py")
    ap.add_argument("--dry-run", action="store_true", help="check the build and print what would load; write nothing")
    args = ap.parse_args(argv)
    build, shrubs = read_build(args.build)
    if args.dry_run:
        print(f"shrubs-load (dry run): {build['area']} {build['build_id']}: {len(shrubs)} shrubs")
        return 0
    from ingest import db
    with db.connect() as conn:
        stats = load(conn, build, shrubs)
        conn.commit()
    print("shrubs-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
