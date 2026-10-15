"""Developed land for the paving's materials (plan C11): load a build made in the worker image, and measure shares of
it in PostGIS. Standard library plus psycopg:

    python3 -m ingest roads-developed-load --build $TVT_ARCHIVE/roads/developed/<id>
    python3 -m ingest roads-developed-load --build DIR --dry-run

The worker step (plugins/roads/build/developed.py) traces USDA NASS's Cropland Data Layer's developed classes
(CLASSES: 122-124, low to high intensity) into polygons on NASS's grid (EPSG:5070), from farm's archived copy of the
CDL. The raster itself is never read here: rasters are decoded in the worker image (docs/17 §17.8 Q9). A load, in one
transaction:
  - checks build.json (written last): its format, the classes, the grid, and developed.jsonl.gz's sha256;
  - records the build in roads.developed_build, with the CDL's file, year, sha256, licence and credit, as the
    current one (earlier builds stay listed, not current);
  - replaces roads.developed_land with its polygons, each cut into parts of at most SUBDIVIDE vertices
    (ST_Subdivide), so an intersection only ever meets small polygons;
  - measures the paving again (osm_paving.remeasure): each service way's and lot's `developed` share, and its
    material where that rests on it. A change marks roads-build (M1).
A build that is already the current one is skipped (--force loads it again). The load is logged in ops.fetch under
the source cdl_developed (no request is made).

The osm_paving consumer measures what it loads against the current build (current(), measure()). With none loaded it
still loads: untagged service ways and lots are 'unknown' until a build is loaded, which measures them. So a missing
CDL never stops an OpenStreetMap load or leaves the partition's tables on two extracts.

Yearly: after farm-cdl-load takes a new CDL year (late February, with the owner's OK for each), run the worker step
on farm's folder again and load the new build; the paving follows it, and roads-build is marked if anything changed.

Licence: USDA NASS Cropland Data Layer, public domain ("public domain and free to redistribute"); credit "USDA NASS
Cropland Data Layer <year>". An export of the paving's materials or `developed` lists it as an input, with the
current build's year and the CDL's sha256 (roads.developed_build where current).
"""

import argparse
import gzip
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

FORMAT = "tvt-roads-developed/1"
CLASSES = (122, 123, 124)        # developed, low, medium and high intensity (121, open space, isn't)
SRID = 5070                      # NAD83 / Conus Albers: NASS's grid
LAND_FILE = "developed.jsonl.gz"
BUILD_FILE = "build.json"
LICENSE = "public domain"
REPUBLISH = "yes"
SUBDIVIDE = 256                  # at most this many vertices in a stored part
DIGITS = 3                       # shares are rounded: the same land and geometry give the same value
AREA_CHECK = 1e-4                # the stored area may differ from the build's cell count by this share at most

SOURCE = {
    "name": "cdl_developed",
    "title": "Developed land from USDA NASS's Cropland Data Layer (the paving's materials)",
    "url": "https://www.nass.usda.gov/Research_and_Science/Cropland/Release/index.php",
    "access": "one_off",
    "schedule": None,    # loaded by hand after a new CDL year (each yearly download needs the owner's OK)
    "license": LICENSE,
    "credit": "USDA NASS Cropland Data Layer",
    "notes": "The CDL's developed classes 122-124 traced into polygons in the worker image "
             "(plugins/roads/build/developed.py) from farm's archived copy, loaded with python3 -m ingest "
             "roads-developed-load into roads.developed_land. osm_paving reads them for its material defaults "
             "(plan C11). Never served as tiles.",
}


class BuildError(ValueError):
    pass


def credit(year):
    return f"{SOURCE['credit']} {year}"


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---- a build ---------------------------------------------------------------

def read_build(folder):
    """build.json, checked against this module and against developed.jsonl.gz. Raises BuildError."""
    path = os.path.join(folder, BUILD_FILE)
    if not os.path.isfile(path):
        raise BuildError(f"{folder}: no {BUILD_FILE} (not a build, or an unfinished one)")
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc.get("format") != FORMAT:
        raise BuildError(f"{path}: format {doc.get('format')!r}, not {FORMAT}")
    if tuple(doc.get("classes") or ()) != CLASSES:
        raise BuildError(f"{path}: classes {doc.get('classes')}, not {list(CLASSES)}")
    if doc.get("srid") != SRID:
        raise BuildError(f"{path}: srid {doc.get('srid')}, not {SRID}")
    if doc.get("build_id") != os.path.basename(os.path.normpath(folder)):
        raise BuildError(f"{path}: build_id {doc.get('build_id')!r} isn't its folder's name")
    cdl = doc.get("cdl") or {}
    for key in ("file", "year", "res_m", "sha256", "license", "credit"):
        if cdl.get(key) in (None, ""):
            raise BuildError(f"{path}: the CDL's {key} is missing")
    if cdl["license"] != LICENSE or cdl["credit"] != credit(cdl["year"]):
        raise BuildError(f"{path}: the CDL's licence or credit isn't {LICENSE!r}, {credit(cdl['year'])!r}")
    land = os.path.join(folder, LAND_FILE)
    want = (doc.get("files") or {}).get(LAND_FILE, {}).get("sha256")
    if not os.path.isfile(land) or sha256_of(land) != want:
        raise BuildError(f"{land}: missing, or not the file build.json describes (sha256)")
    if not doc.get("counts", {}).get("pieces"):
        raise BuildError(f"{path}: no pieces")
    return doc


def pieces(folder):
    """(n, GeoJSON text) for each piece in a build's developed.jsonl.gz."""
    with gzip.open(os.path.join(folder, LAND_FILE), "rt", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                p = json.loads(line)
                if p.get("geom", {}).get("type") != "Polygon":
                    raise BuildError(f"{LAND_FILE}: piece {p.get('n')} isn't a Polygon")
                yield p["n"], json.dumps(p["geom"], separators=(",", ":"))


# ---- the current build -----------------------------------------------------

def ready(conn):
    return conn.execute("select to_regclass('roads.developed_build') is not null").fetchone()[0]


def current(conn):
    """The current build's row (a dict), or None when none is loaded."""
    if not ready(conn):
        return None
    with conn.cursor() as cur:
        cur.execute("""select id, cdl_file, cdl_year, cdl_res_m, cdl_sha256, license, credit, pieces, parts, area_km2,
                              loaded_at
                         from roads.developed_build where current""")
        row = cur.fetchone()
        return dict(zip([d.name for d in cur.description], row)) if row else None


def describe(build):
    """One line on the land a load measured against, for its counts."""
    if build is None:
        return ("none loaded (python3 -m ingest roads-developed-load): untagged service ways and lots are unknown "
                "until one is")
    return (f"{build['id']}: {build['credit']} ({build['cdl_file']}, {build['license']}, "
            f"sha256 {build['cdl_sha256']})")


# ---- measuring -------------------------------------------------------------

def measure(conn, items=None, query=None, params=(), area=False, land=True):
    """Each object's share of developed land: {(t, id): share}, or with area {(t, id): (share, area_m2)}.

    items: [(t, id, GeoJSON text in EPSG:4326)]; or query: SQL giving (t, id, geom in EPSG:4326), with params.
    Lines are measured by length and areas by area, on NASS's grid (EPSG:5070, an equal-area projection; OSM's
    WGS 84 taken as NAD83's, the null shift). share: 0-1, rounded to DIGITS; None when the object has no length
    or area, or when land is False (nothing to measure against). area_m2: its area on the ellipsoid (geography),
    to 0.1 m2. Uses a temporary table; doesn't commit."""
    conn.execute("drop table if exists pg_temp.roads_measure")
    conn.execute("create temp table roads_measure (t char(1), id bigint, gj text, g geometry, a geometry) "
                 "on commit drop")
    if items is not None:
        with conn.cursor() as cur:
            with cur.copy("copy roads_measure (t, id, gj) from stdin") as cp:
                for item in items:
                    cp.write_row(item)
        conn.execute("update roads_measure set g = ST_SetSRID(ST_GeomFromGeoJSON(gj), 4326), gj = null")
    else:
        conn.execute(f"insert into roads_measure (t, id, g) select q.t, q.id, q.geom from ({query}) q", params)
    conn.execute(f"update roads_measure set a = ST_Transform(g, {SRID})")
    size = "ST_Area" if area else "ST_Length"
    developed = (f"""(select coalesce(sum({size}(ST_Intersection(m.a, d.geom))), 0)
                        from roads.developed_land d where ST_Intersects(d.geom, m.a))""" if land else "null")
    m2 = "round(ST_Area(m.g::geography)::numeric, 1)::float8" if area else "null"
    out = {}
    for t, i, total, dev, m in conn.execute(
            f"select m.t, m.id, {size}(m.a), {developed}, {m2} from roads_measure m").fetchall():
        share = round(min(1.0, dev / total), DIGITS) if dev is not None and total else None
        out[(t, i)] = (share, m) if area else share
    conn.execute("drop table pg_temp.roads_measure")
    return out


# ---- a load ----------------------------------------------------------------

def load(conn, folder, doc=None, force=False, now=None):
    """Load a build as the current developed land and measure the paving again. Doesn't commit. Returns stats."""
    doc = doc or read_build(folder)
    now = now or datetime.now(timezone.utc)
    cdl = doc["cdl"]
    was = current(conn)
    if was and was["id"] == doc["build_id"] and was["cdl_sha256"] == cdl["sha256"] and not force:
        return {"skipped": f"{doc['build_id']} is already the current build (--force loads it again)"}
    conn.execute("drop table if exists pg_temp.developed_stage")
    conn.execute("create temp table developed_stage (n int, gj text) on commit drop")
    with conn.cursor() as cur:
        with cur.copy("copy developed_stage (n, gj) from stdin") as cp:
            for row in pieces(folder):
                cp.write_row(row)
    n = conn.execute("select count(*) from developed_stage").fetchone()[0]
    if n != doc["counts"]["pieces"]:
        raise BuildError(f"{LAND_FILE}: {n} pieces, but build.json says {doc['counts']['pieces']}")
    conn.execute("update roads.developed_build set current = false where current")
    conn.execute(
        """insert into roads.developed_build (id, cdl_file, cdl_year, cdl_res_m, cdl_sha256, classes, srid, license,
             credit, republish, pieces, parts, area_km2, made_at, loaded_at, current)
           values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0, 0, %s, %s, true)
           on conflict (id) do update set cdl_file = excluded.cdl_file, cdl_year = excluded.cdl_year,
             cdl_res_m = excluded.cdl_res_m, cdl_sha256 = excluded.cdl_sha256, classes = excluded.classes,
             srid = excluded.srid, license = excluded.license, credit = excluded.credit,
             republish = excluded.republish, pieces = excluded.pieces, made_at = excluded.made_at,
             loaded_at = excluded.loaded_at, current = true""",
        (doc["build_id"], cdl["file"], cdl["year"], cdl["res_m"], cdl["sha256"], list(CLASSES), SRID, cdl["license"],
         cdl["credit"], REPUBLISH, n, doc["finished_at"], now))
    conn.execute("delete from roads.developed_land")
    conn.execute(
        f"""insert into roads.developed_land (id, piece, geom)
            select row_number() over (order by s.n, p.path), s.n, p.geom
              from developed_stage s
              cross join lateral ST_Subdivide(ST_SetSRID(ST_GeomFromGeoJSON(s.gj), {SRID}), {SUBDIVIDE}) as sub
              cross join lateral ST_Dump(sub) as p
             where ST_GeometryType(p.geom) = 'ST_Polygon'""")
    conn.execute("drop table pg_temp.developed_stage")
    parts, km2 = conn.execute("select count(*), coalesce(sum(ST_Area(geom)), 0) / 1e6 from roads.developed_land"
                              ).fetchone()
    want = doc["counts"]["area_km2"]
    if abs(km2 - want) > AREA_CHECK * want + 1e-6:
        raise BuildError(f"{LAND_FILE}: {km2:.3f} km2 stored, but build.json counts {want} km2 of cells")
    conn.execute("update roads.developed_build set parts = %s, area_km2 = %s where id = %s",
                 (parts, round(km2, 3), doc["build_id"]))
    conn.execute("analyze roads.developed_land")
    stats = {"build": doc["build_id"], "cdl": f"{cdl['file']} ({cdl['year']}, sha256 {cdl['sha256']})",
             "pieces": n, "parts": parts, "area_km2": round(km2, 3),
             "replaced": was["id"] if was else "none"}
    from .sources import osm_paving
    stats.update(osm_paving.remeasure(conn, by=SOURCE["name"], reason=f"developed land {doc['build_id']} "
                                                                      f"(CDL {cdl['year']})"))
    return stats


def run(conn, folder, force=False):
    """load() with the source registered and the load logged in ops.fetch; commits."""
    from ingest import db
    doc = read_build(folder)
    db.ensure_source(conn, SOURCE)
    with db.Fetch(conn, SOURCE["name"]) as f:      # no request made: robots and status stay empty
        f.bytes = os.path.getsize(os.path.join(folder, LAND_FILE))
        stats = load(conn, folder, doc, force=force)
        f.records = stats.get("pieces", 0)
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest roads-developed-load", description=__doc__.split("\n")[0])
    ap.add_argument("--build", required=True, help="a folder written by plugins/roads/build/developed.py")
    ap.add_argument("--dry-run", action="store_true", help="check the build; write nothing")
    ap.add_argument("--force", action="store_true", help="load it even when it's already the current build")
    args = ap.parse_args(argv)
    try:
        doc = read_build(args.build)
        if args.dry_run:
            n = sum(1 for _ in pieces(args.build))
            print(f"roads-developed-load (dry run): {doc['build_id']}: {n} pieces, {doc['counts']['area_km2']} km2, "
                  f"from {doc['cdl']['file']} ({doc['cdl']['credit']})", flush=True)
            return 0
        from ingest import db
        with db.connect() as conn:
            stats = run(conn, args.build, force=args.force)
    except (BuildError, OSError, ValueError) as err:
        print(f"roads-developed-load: {err}", file=sys.stderr, flush=True)
        return 1
    print("roads-developed-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
