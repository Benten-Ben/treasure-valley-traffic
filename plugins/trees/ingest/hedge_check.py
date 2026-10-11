"""The hedge check (plan C14, docs/19 §19.8): do the shrubs find OpenStreetMap's hedges?
`python3 -m ingest shrubs-hedge-check [--hedges FILE | --extract PBF] [--json OUT]`.

OSM's hedges are a check on the shrub build, never drawn and never a source of shrubs. A hedge should come out of the
build as a row of bushes; one taller than 2.4 m comes out as trees. For each hedge inside a built shrub area
(trees.shrub_area), along its line (an area hedge: its outline), in metres on UTM 11N:

    shrub_cover   the share of its length within NEAR_M of a shrub's crown (half its width)
    tree_cover    the same for trees' crowns (trees.tree, where trees are built)
    either_cover  under either
    shrubs        shrubs within NEAR_M of their crown's edge: bushes and sages, and their median height

and a verdict: "shrubs" (shrub_cover 0.5 or more), "trees" (tree_cover 0.5 or more), "shrubs and trees" (either 0.5
or more), "partly" (either 0.2 or more) or "not found".

Where the hedges come from, the first that applies:
- --hedges FILE: a GeoJSON FeatureCollection or GeoJSON sequence of OSM hedges (ways as lines, area hedges as
  polygons; the id from @id, id or osm_id), e.g. from `osmium export`;
- --extract PBF: the held OpenStreetMap extract, filtered by osmium (barrier=hedge ways and areas) here;
- fences.fence's rows of type 'hedge', once the fences plugin (P10) is built.

Nothing is written to the database: the report is printed, and with --json saved (OSM-derived, ODbL: keep it in the
archive, not the repository). Standard library plus psycopg (and osmium-tool for --extract, as in the ingest image)."""

import argparse
import json
import os
import subprocess
import sys
import tempfile

NEAR_M = 1.0
VERDICTS = ("shrubs", "trees", "shrubs and trees", "partly", "not found")
UTM = 32611


def verdict(shrub_cover, tree_cover, either_cover):
    if shrub_cover >= 0.5:
        return "shrubs"
    if tree_cover >= 0.5:
        return "trees"
    if either_cover >= 0.5:
        return "shrubs and trees"
    if either_cover >= 0.2:
        return "partly"
    return "not found"


def _hedge_id(props, n):
    for k in ("@id", "id", "osm_id", "fence_id"):
        v = props.get(k)
        if v not in (None, ""):
            return str(v)
    return f"hedge-{n}"


def read_hedges(path):
    """[(id, GeoJSON geometry)] from a GeoJSON FeatureCollection, a single Feature or a GeoJSON sequence (one feature
    per line, RS characters allowed). Only lines and polygons are kept."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    stripped = text.lstrip("\x1e \t\r\n")
    feats = []
    if stripped.startswith("{"):
        try:
            doc = json.loads(stripped)
        except json.JSONDecodeError:
            doc = None
        if doc is not None:
            feats = doc.get("features", []) if doc.get("type") == "FeatureCollection" else [doc]
        else:
            feats = [json.loads(line.strip("\x1e \t\r")) for line in text.splitlines() if line.strip("\x1e \t\r")]
    out = []
    for n, feat in enumerate(feats, 1):
        g = feat.get("geometry") or {}
        if g.get("type") not in ("LineString", "MultiLineString", "Polygon", "MultiPolygon"):
            continue
        out.append((_hedge_id(feat.get("properties") or {}, n), g))
    return out


def hedges_from_extract(pbf, workdir):
    """Hedges from an OSM extract with osmium: barrier=hedge ways and areas, exported as a GeoJSON sequence."""
    filtered = os.path.join(workdir, "hedges.osm.pbf")
    seq = os.path.join(workdir, "hedges.geojsonseq")
    subprocess.run(["osmium", "tags-filter", "--overwrite", "-o", filtered, pbf, "w/barrier=hedge",
                    "a/barrier=hedge"], check=True)
    subprocess.run(["osmium", "export", "--overwrite", "-f", "geojsonseq", "-a", "type,id", "-o", seq,
                    "--geometry-types", "linestring,polygon", filtered], check=True)
    out = []
    for hid, g in read_hedges(seq):
        out.append((hid, g))
    return out


def hedges_from_fences(conn):
    if not conn.execute("select to_regclass('fences.fence') is not null").fetchone()[0]:
        return None
    rows = conn.execute("select fence_id, ST_AsGeoJSON(geom) from fences.fence where type = 'hedge'"
                        " and coalesce(active, true)").fetchall()
    return [(str(i), json.loads(g)) for i, g in rows]


CHECK_SQL = f"""
with h as (
  select h.hedge_id, a.area,
         ST_Intersection(ST_Transform(case when GeometryType(h.geom) in ('POLYGON', 'MULTIPOLYGON')
                                           then ST_Boundary(h.geom) else h.geom end, {UTM}),
                         ST_Transform(a.geom, {UTM})) as line
  from pg_temp.hedge h join trees.shrub_area a on ST_Intersects(h.geom, a.geom)
),
s as (
  select h.hedge_id, h.area,
         ST_Union(ST_Buffer(ST_Transform(s.geom, {UTM}), s.width_m / 2 + %(near)s, 8)) as crowns,
         count(*) as n, count(*) filter (where s.look = 'bush') as bushes,
         count(*) filter (where s.look = 'sage') as sages,
         percentile_cont(0.5) within group (order by s.height_m) as median_height_m
  from h join trees.shrub s
    on s.geom && ST_Transform(ST_Expand(h.line, 5 + %(near)s), 4326)
   and ST_DWithin(ST_Transform(s.geom, {UTM}), h.line, s.width_m / 2 + %(near)s)
  group by 1, 2
),
t as (
  select h.hedge_id, h.area, ST_Union(ST_Buffer(ST_Transform(t.geom, {UTM}), t.crown_radius_m + %(near)s, 8)) as crowns
  from h join trees.tree t
    on t.geom && ST_Transform(ST_Expand(h.line, 30 + %(near)s), 4326)
   and ST_DWithin(ST_Transform(t.geom, {UTM}), h.line, t.crown_radius_m + %(near)s)
  group by 1, 2
)
select h.hedge_id, h.area, ST_Length(h.line) as length_m,
       coalesce(ST_Length(ST_Intersection(h.line, s.crowns)), 0) as shrub_m,
       coalesce(ST_Length(ST_Intersection(h.line, t.crowns)), 0) as tree_m,
       coalesce(ST_Length(ST_Intersection(h.line, coalesce(ST_Union(s.crowns, t.crowns), s.crowns, t.crowns))), 0)
         as either_m,
       coalesce(s.n, 0), coalesce(s.bushes, 0), coalesce(s.sages, 0), s.median_height_m
from h left join s using (hedge_id, area) left join t using (hedge_id, area)
where ST_Length(h.line) > 0
order by h.area, h.hedge_id
"""


def check(conn, hedges, near_m=NEAR_M):
    """Per hedge inside a built shrub area: its length, covers and verdict. Uses a temporary table; writes nothing."""
    conn.execute("create temporary table if not exists hedge (hedge_id text, geom geometry(Geometry, 4326))"
                 " on commit drop")
    conn.execute("truncate pg_temp.hedge")
    with conn.cursor() as cur:
        cur.executemany("insert into pg_temp.hedge values (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326))",
                        [(hid, json.dumps(g)) for hid, g in hedges])
    rows = conn.execute(CHECK_SQL, {"near": near_m}).fetchall()
    out = []
    for hid, area, length, shrub_m, tree_m, either_m, n, bushes, sages, med in rows:
        sc, tc, ec = shrub_m / length, tree_m / length, either_m / length
        out.append({"hedge": hid, "area": area, "length_m": round(length, 1), "shrub_cover": round(sc, 2),
                    "tree_cover": round(tc, 2), "either_cover": round(ec, 2), "shrubs": n, "bushes": bushes,
                    "sages": sages, "median_height_m": None if med is None else round(med, 2),
                    "verdict": verdict(sc, tc, ec)})
    return out


def summary(results, total_hedges, source, near_m=NEAR_M):
    by = {v: {"hedges": 0, "length_m": 0.0} for v in VERDICTS}
    for r in results:
        by[r["verdict"]]["hedges"] += 1
        by[r["verdict"]]["length_m"] = round(by[r["verdict"]]["length_m"] + r["length_m"], 1)
    near = sum(r["shrubs"] for r in results)
    return {"source": source, "near_m": near_m, "hedges_read": total_hedges, "hedges_in_shrub_areas": len(results),
            "length_m": round(sum(r["length_m"] for r in results), 1), "by_verdict": by,
            "shrubs_along_hedges": near,
            "bush_share": round(sum(r["bushes"] for r in results) / near, 2) if near else None}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest shrubs-hedge-check", description=__doc__.split("\n")[0])
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--hedges", help="a GeoJSON (or GeoJSON sequence) of OSM hedges")
    src.add_argument("--extract", help="an OSM extract (.osm.pbf) to take barrier=hedge from, with osmium")
    ap.add_argument("--near-m", type=float, default=NEAR_M, help="how far from a crown's edge still counts (m)")
    ap.add_argument("--json", help="also write the report here (OSM-derived: keep it out of the repository)")
    args = ap.parse_args(argv)
    from ingest import db
    with db.connect() as conn:
        if not conn.execute("select to_regclass('trees.shrub_area') is not null").fetchone()[0]:
            raise SystemExit("trees.shrub_area is missing: apply the trees plugin's migration 0002")
        if args.hedges:
            hedges, source = read_hedges(args.hedges), os.path.basename(args.hedges)
        elif args.extract:
            with tempfile.TemporaryDirectory() as d:
                hedges = hedges_from_extract(args.extract, d)
            source = f"{os.path.basename(args.extract)} (barrier=hedge)"
        else:
            hedges, source = hedges_from_fences(conn), "fences.fence (type hedge)"
            if hedges is None:
                raise SystemExit("no hedges: fences.fence isn't there yet; pass --hedges FILE or --extract PBF")
        results = check(conn, hedges, args.near_m)
        conn.rollback()
    report = {"summary": summary(results, len(hedges), source, args.near_m), "hedges": results}
    s = report["summary"]
    print(f"hedge check ({source}): {s['hedges_in_shrub_areas']} of {s['hedges_read']} hedges are in built shrub areas,"
          f" {s['length_m']} m")
    for v in VERDICTS:
        b = s["by_verdict"][v]
        if b["hedges"]:
            print(f"  {v:17} {b['hedges']:4} hedges  {b['length_m']:8.1f} m")
    if s["shrubs_along_hedges"]:
        print(f"  shrubs along them: {s['shrubs_along_hedges']} (bushes {s['bush_share']:.0%})")
    for r in results:
        print(f"  {r['area']:9} {r['hedge']:16} {r['length_m']:7.1f} m  shrubs {r['shrub_cover']:.2f}"
              f"  trees {r['tree_cover']:.2f}  {r['shrubs']:3} shrubs  {r['verdict']}")
    if args.json:
        with open(args.json, "w") as f:
            json.dump(report, f, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
