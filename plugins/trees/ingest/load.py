"""Load a trees build into the database (docs/19 §19.5): `python3 -m ingest trees-load --build DIR`.

DIR is what plugins/trees/build/build.py wrote: build.json, trees.geojson and log.jsonl. In one transaction the build is
recorded, the area's trees are replaced by the build's, and its log events are added (events already there are kept, so
a tree's history survives rebuilds). Standard library plus psycopg.

The public tables hold only trees found in the lidar, so the loader takes a fixed set of fields and nothing else: a
build whose trees, fits or log events carry anything outside those sets (an old-format build, or one that let an
inventory's data in) is refused whole, before anything is written. An anchors.jsonl beside the build is not read here;
the private plugin that owns the inventory loads it."""

import argparse
import json
import os
import sys

KINDS = ("placed",)
TYPES = ("broadleaf", "conifer", "narrow")
# The fields a public tree, its fit and its log events may carry. Anything else stops the load.
TREE_FIELDS = {"id", "kind", "type", "ground_m", "height_m", "crown_radius_m", "crown_a", "crown_n", "lidar", "fit"}
FIT_FIELDS = {"width_vs_typical_sd", "crowded", "width_curve", "profile", "spring"}
EVENTS = {"placed": {"lidar", "height_m", "crown_width_m", "theta"}}


def unknown(label, got, allowed):
    extra = sorted(set(got) - allowed)
    if extra:
        raise ValueError(f"{label}: fields not allowed in the public trees tables: {', '.join(extra)}")


def read_build(folder):
    """(build, trees, log) from a build folder, checked: every tree has a known kind and type, a point and sizes."""
    build = json.load(open(os.path.join(folder, "build.json")))
    fc = json.load(open(os.path.join(folder, "trees.geojson")))
    trees = []
    for f in fc["features"]:
        p = dict(f["properties"])
        lon, lat = f["geometry"]["coordinates"][:2]
        unknown(f"tree {p.get('id')}", p, TREE_FIELDS)
        unknown(f"tree {p.get('id')}: fit", p.get("fit") or {}, FIT_FIELDS)
        if p.get("kind") not in KINDS or p.get("type") not in TYPES:
            raise ValueError(f"tree {p.get('id')}: kind {p.get('kind')!r} or type {p.get('type')!r} unknown")
        if not (p.get("height_m") or 0) > 0 or not (p.get("crown_radius_m") or 0) > 0:
            raise ValueError(f"tree {p.get('id')}: no height or crown")
        p["lon"], p["lat"] = float(lon), float(lat)
        trees.append(p)
    ids = [t["id"] for t in trees]
    if len(ids) != len(set(ids)):
        raise ValueError("tree ids repeat")
    log = []
    path = os.path.join(folder, "log.jsonl")
    if os.path.exists(path):
        with open(path) as fh:
            log = [json.loads(line) for line in fh if line.strip()]
        for e in log:
            who = f"log event {e.get('event')!r} of {e.get('tree_id')}"
            if e.get("event") not in EVENTS:
                raise ValueError(f"{who}: not an event of a tree found in the lidar")
            unknown(who, e, {"tree_id", "at", "event", "detail"})
            unknown(who, e.get("detail") or {}, EVENTS[e["event"]])
    return build, trees, log


def load(conn, build, trees, log):
    b = build
    conn.execute(
        """insert into trees.build (build_id, area, started_at, finished_at, params, counts)
           values (%s, %s, %s, %s, %s, %s)
           on conflict (build_id) do update set finished_at = excluded.finished_at, params = excluded.params,
             counts = excluded.counts, loaded_at = now()""",
        (b["build_id"], b["area"], b["started_at"], b.get("finished_at"), json.dumps(b.get("params", {})),
         json.dumps(b.get("counts", {}))))
    removed = conn.execute("delete from trees.tree where area = %s", (b["area"],)).rowcount
    with conn.cursor() as cur:
        cur.executemany(
            """insert into trees.tree (tree_id, area, kind, type, geom, ground_m, height_m, crown_radius_m, crown_a,
                 crown_n, lidar, fit, build_id)
               values (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326), %s, %s, %s, %s, %s, %s, %s, %s)""",
            [(t["id"], b["area"], t["kind"], t["type"], t["lon"], t["lat"], t.get("ground_m"), t["height_m"],
              t["crown_radius_m"], t.get("crown_a"), t.get("crown_n"), t.get("lidar"),
              json.dumps(t.get("fit") or {}), b["build_id"]) for t in trees])
        cur.executemany(
            """insert into trees.tree_log (tree_id, at, event, detail, build_id) values (%s, %s, %s, %s, %s)
               on conflict (tree_id, at, event) do nothing""",
            [(e["tree_id"], e["at"], e["event"], json.dumps(e.get("detail") or {}), b["build_id"]) for e in log])
    return {"area": b["area"], "build": b["build_id"], "trees": len(trees), "replaced": removed, "log events": len(log)}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest trees-load", description=__doc__.split("\n")[0])
    ap.add_argument("--build", required=True, help="a build folder written by plugins/trees/build/build.py")
    ap.add_argument("--dry-run", action="store_true", help="check the build and print what would load; write nothing")
    args = ap.parse_args(argv)
    build, trees, log = read_build(args.build)
    if args.dry_run:
        print(f"trees-load (dry run): {build['area']} {build['build_id']}: {len(trees)} trees, {len(log)} log events")
        return 0
    from ingest import db
    with db.connect() as conn:
        stats = load(conn, build, trees, log)
        conn.commit()
    print("trees-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
