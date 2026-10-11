"""Load a prepared soil survey into the soils schema: `python3 -m ingest soils-load --from DIR`.

DIR is what plugins/soils/build/prepare.py wrote (package.py describes it). Standard library plus psycopg:

    python3 -m ingest soils-load --from $TVT_ARCHIVE/soils/prepared/<stamp>            # every changed survey area
    python3 -m ingest soils-load --from DIR --areas ID001,ID665 [--force] [--dry-run]

Whole survey areas at a time, in one transaction: an area whose saverest (when NRCS established its version) is what
the database already has is skipped unless --force; any other area's rows are replaced. For each area it loads its
boundary, map units, components, horizons and polygons, then works out in PostGIS each polygon's area (on the
ellipsoid) and area inside the box, its simplified geometry (geom_lo, 5 m in UTM 11N, for z12-13) and its label point
(the centre of the largest circle inside it); each map unit's area in the box, polygon count and generalised geometry
for the valley zooms (geom_z8 at 100 m, geom_z10 at 25 m, collapsed parts dropped); the boundary's simplified copy
(20 m); and the ground types' counts, areas, fragment cover and dry albedo. A new ground type gets the next integer
key (gid); a type already there keeps its own. Ground types no map unit uses any more are removed. The run is recorded in soils.build (its inputs' sha256 and
its counts) and logged in ops.fetch under the source `ssurgo`, and it gives the Soils layer's tiles a new version
(core.layer_version, 'soils.units') in the same transaction as its data.

The data is downloaded by hand each October with the owner's OK (an Oct 8 rule); nothing here makes a request.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

from . import package
from .sources import ssurgo

TILE_LAYERS = ("soils.units",)       # the toggled layer whose tiles show these tables (/api/soils/tiles/units)
SIMPLIFY_M = 5.0                     # soils.polygon.geom_lo's tolerance, in metres (UTM 11N): z12-13
SIMPLIFY_Z8_M = 100.0                # soils.map_unit.geom_z8's: z8-9 (a pixel is about 110 m at z9, 512 px tiles)
SIMPLIFY_Z10_M = 25.0                # soils.map_unit.geom_z10's: z10-11 (about 28 m at z11)
SIMPLIFY_BOUNDS_M = 20.0             # soils.survey_area.geom_lo's: the survey bounds at z8-11
BOX_STEP_DEG = 0.001                 # the box's edges are densified so they follow their parallels on the ellipsoid

COPY_ROW_COLUMNS = ("id", "areasymbol", "mukey", "gj")


def build_id(now):
    return f"load-{now.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}"


def plan(pkg, current, areas=None, force=False):
    """(to load, skipped) survey-area symbols: those whose saverest differs from `current` ({symbol: iso}), all with
    force; only `areas` when given."""
    names = sorted(pkg.areas)
    if areas:
        unknown = sorted(set(areas) - set(names))
        if unknown:
            raise package.PackageError(f"the package has no survey area {', '.join(unknown)} (it has {', '.join(names)})")
        names = [n for n in names if n in areas]
    todo = [n for n in names if force or current.get(n) != pkg.areas[n]["saverest"]]
    return todo, [n for n in names if n not in todo]


def pending(conn, pkg, areas=None, force=False):
    """plan() against what the database holds."""
    current = {a: s.isoformat() for a, s in conn.execute("select areasymbol, saverest from soils.survey_area")}
    return plan(pkg, current, areas, force)


def nothing_to_do(skipped):
    return {"loaded": "nothing", "skipped": ", ".join(skipped) + " (same saverest as loaded; --force reloads)"}


def _insert(cur, table, rows, columns, json_columns=()):
    if not rows:
        return
    cols = ", ".join(columns)
    marks = ", ".join("%s::jsonb" if c in json_columns else "%s" for c in columns)
    cur.executemany(f"insert into {table} ({cols}) values ({marks})",
                    [tuple(json.dumps(r[c]) if c in json_columns else r[c] for c in columns) for r in rows])


MAP_UNIT_COLUMNS = (
    "mukey", "areasymbol", "musym", "muname", "mukind", "farmlndcl", "slopegraddcp", "aws025wta", "aws050wta",
    "aws0100wta", "drclassdcd", "hydgrpdcd", "flodfreqdcd", "pondfreqprs", "brockdepmin", "wtdepannmin", "iccdcd",
    "niccdcd", "hydclprs", "dom_cokey", "ground_type", "restr_kind", "restr_top_cm", "restr_hard", "c_restr", "pat",
    "c_drain", "c_aws", "c_farm", "farm_cond", "c_hsg", "hsg_dual")
COMPONENT_COLUMNS = (
    "cokey", "mukey", "compname", "compkind", "comppct_r", "majcomp", "slope_l", "slope_r", "slope_h", "drainagecl",
    "hydgrp", "hydricrating", "irrcapcl", "irrcapscl", "nirrcapcl", "nirrcapscl", "taxclname", "taxorder", "earthcov",
    "landform", "pm_kind", "ffd_r", "albedodry_r", "elev_r", "map_r", "surf_frag_cover_pct", "eco_id", "eco_name",
    "restrictions", "crop_yields")
HORIZON_COLUMNS = (
    "chkey", "cokey", "hzname", "top_cm", "bottom_cm", "texture", "texcl", "sand", "silt", "clay", "om", "ph", "caco3",
    "gypsum", "ec", "sar", "awc", "ksat", "kwfact", "frag_gt10", "frag_3to10")
# Ground types (package.derive's id, series, texture, texcl, modifier, misc). A type already there keeps its row and
# gid; only a new one takes the next gid. (An insert ... on conflict would draw a gid from the sequence for every type
# on every load, and they are never given back.)
UPSERT_GROUND_TYPE = """
with up as (update soils.ground_type set series = %(series)s, texture = %(texture)s, texcl = %(texcl)s,
                   modifier = %(modifier)s, misc = %(misc)s
            where id = %(id)s returning 1)
insert into soils.ground_type (id, series, texture, texcl, modifier, misc)
select %(id)s, %(series)s, %(texture)s, %(texcl)s, %(modifier)s, %(misc)s where not exists (select 1 from up)"""


def load(conn, pkg, areas=None, force=False, now=None):
    """Load the package's changed survey areas (or `areas`). Doesn't commit. Returns the stats."""
    now = now or datetime.now(timezone.utc)
    todo, skipped = pending(conn, pkg, areas, force)
    if not todo:
        return nothing_to_do(skipped)
    d = package.derive(pkg, todo)
    mukeys = {m["mukey"] for m in d.map_units}
    bid = build_id(now)
    inputs = {name: info["sha256"] for name, info in sorted(pkg.meta["files"].items())}
    inputs.update({f"source:{k}": v for k, v in sorted((pkg.meta.get("inputs") or {}).items())})
    params = {"from": os.path.abspath(pkg.folder), "areas": todo, "force": force,
              "prepared_at": pkg.meta.get("made_at"), "simplify_m": SIMPLIFY_M, "simplify_z8_m": SIMPLIFY_Z8_M,
              "simplify_z10_m": SIMPLIFY_Z10_M, "simplify_bounds_m": SIMPLIFY_BOUNDS_M}
    box = package.BOX

    with conn.cursor() as cur:
        cur.execute(
            """insert into soils.build (build_id, kind, started_at, params, inputs, license, republish, credit)
               values (%s, 'load', %s, %s::jsonb, %s::jsonb, %s, 'yes', %s)""",
            (bid, now, json.dumps(params), json.dumps(inputs), ssurgo.SOURCE["license"], ssurgo.SOURCE["credit"]))
        cur.execute("delete from soils.survey_area where areasymbol = any(%s)", (todo,))     # cascades to its rows

        # Survey areas, with their boundary pieces (soilsa_a) joined into one valid MultiPolygon each.
        cur.execute("create temporary table if not exists soils_area_in (areasymbol text, gj text) on commit drop")
        cur.execute("truncate soils_area_in")
        with cur.copy("copy soils_area_in (areasymbol, gj) from stdin") as cp:
            for area, gj in pkg.survey_areas(set(todo)):
                cp.write_row((area, gj))
        cur.executemany(
            """insert into soils.survey_area (areasymbol, areaname, saverest, saversion, scale, source_url, build_id,
                                              geom)
               select %s, %s, %s, %s, %s, %s, %s,
                      ST_Multi(ST_CollectionExtract(ST_Union(
                        ST_MakeValid(ST_SetSRID(ST_GeomFromGeoJSON(gj), 4326))), 3))
               from soils_area_in where areasymbol = %s having count(*) > 0""",
            [(a, pkg.areas[a]["areaname"], pkg.areas[a]["saverest"], pkg.areas[a].get("saversion"),
              pkg.areas[a].get("scale"), pkg.areas[a].get("source_url"), bid, a) for a in todo])
        have = {r[0] for r in cur.execute("select areasymbol from soils.survey_area where areasymbol = any(%s)",
                                          (todo,))}
        if missing_areas := sorted(set(todo) - have):
            raise package.PackageError(f"{package.SURVEY_AREAS} has no boundary for {', '.join(missing_areas)}")
        cur.execute(
            """update soils.survey_area set geom_lo = ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(
                 ST_SimplifyPreserveTopology(ST_Transform(geom, 32611), %s), 4326)), 3))
               where areasymbol = any(%s)""", (SIMPLIFY_BOUNDS_M, todo))
        cur.executemany(UPSERT_GROUND_TYPE, list(d.ground_types.values()))
        _insert(cur, "soils.map_unit", d.map_units, MAP_UNIT_COLUMNS)
        _insert(cur, "soils.component", d.components, COMPONENT_COLUMNS, json_columns=("restrictions", "crop_yields"))
        _insert(cur, "soils.horizon", d.horizons, HORIZON_COLUMNS)

        # Polygons: GeoJSON through a staging table, made valid where they aren't.
        cur.execute("create temporary table if not exists soils_polygon_in (id text, areasymbol text, mukey text, "
                    "gj text) on commit drop")
        cur.execute("truncate soils_polygon_in")
        missing, n = set(), 0
        with cur.copy(f"copy soils_polygon_in ({', '.join(COPY_ROW_COLUMNS)}) from stdin") as cp:
            for pid, area, mukey, gj in pkg.polygons(set(todo)):
                if mukey not in mukeys:
                    missing.add(mukey)
                cp.write_row((pid, area, mukey, gj))
                n += 1
        if missing:
            raise package.PackageError(f"polygons of map units the package doesn't have: {', '.join(sorted(missing)[:5])}")
        repaired = cur.execute(
            """with g as (select id, areasymbol, mukey, ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(gj), 4326)) as geom
                          from soils_polygon_in),
                    v as (select *, ST_IsValid(geom) as ok from g),
                    ins as (insert into soils.polygon (id, areasymbol, mukey, geom)
                            select id, areasymbol, mukey,
                                   case when ok then geom else ST_Multi(ST_CollectionExtract(ST_MakeValid(geom), 3)) end
                            from v returning 1)
               select count(*) filter (where not ok) from v""").fetchone()[0]

        # Areas, the simplified geometry and label points, in metres where it matters.
        cur.execute(
            """with b as (select ST_Segmentize(ST_MakeEnvelope(%s, %s, %s, %s, 4326), %s) as box)
               update soils.polygon p set
                 area_m2 = ST_Area(p.geom::geography),
                 area_in_box_m2 = case when ST_CoveredBy(p.geom, b.box) then ST_Area(p.geom::geography)
                                       else ST_Area(ST_Intersection(p.geom, b.box)::geography) end,
                 geom_lo = ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(
                             ST_SimplifyPreserveTopology(ST_Transform(p.geom, 32611), %s), 4326)), 3)),
                 label_pt = coalesce(ST_Transform((ST_MaximumInscribedCircle(ST_Transform(p.geom, 32611))).center,
                                                  4326), ST_PointOnSurface(p.geom))
               from b where p.areasymbol = any(%s)""",
            (*box, BOX_STEP_DEG, SIMPLIFY_M, todo))
        # Each map unit's polygons generalised for the valley zooms: each simplified and made valid, then joined
        # into one MultiPolygon. ST_Simplify (not the topology-preserving kind) drops the parts that collapse, which
        # are under a pixel there.
        cur.execute(
            """with p as (
                 select mukey, area_in_box_m2,
                        ST_CollectionExtract(ST_MakeValid(ST_Simplify(ST_Transform(geom, 32611), %s)), 3) as z8,
                        ST_CollectionExtract(ST_MakeValid(ST_Simplify(ST_Transform(geom, 32611), %s)), 3) as z10
                 from soils.polygon where areasymbol = any(%s)
               ), s as (
                 select mukey, sum(area_in_box_m2) as m2, count(*) as n,
                        ST_UnaryUnion(ST_Collect(z8) filter (where not ST_IsEmpty(z8))) as z8,
                        ST_UnaryUnion(ST_Collect(z10) filter (where not ST_IsEmpty(z10))) as z10
                 from p group by mukey
               )
               update soils.map_unit m set area_in_box_ha = s.m2 / 1e4, n_polygons = s.n,
                 geom_z8 = ST_Multi(ST_Transform(ST_CollectionExtract(s.z8, 3), 4326)),
                 geom_z10 = ST_Multi(ST_Transform(ST_CollectionExtract(s.z10, 3), 4326))
               from s where m.mukey = s.mukey""", (SIMPLIFY_Z8_M, SIMPLIFY_Z10_M, todo))
        cur.execute(
            """update soils.map_unit set geom_z8 = case when not ST_IsEmpty(geom_z8) then geom_z8 end,
                                         geom_z10 = case when not ST_IsEmpty(geom_z10) then geom_z10 end
               where areasymbol = any(%s) and (ST_IsEmpty(geom_z8) or ST_IsEmpty(geom_z10))""", (todo,))
        cur.execute(
            """update soils.ground_type g set n_mapunits = s.n, area_ha = s.ha, frag_cover_pct = s.frag,
                 albedo_dry = s.albedo
               from (select m.ground_type, count(*) as n, sum(m.area_in_box_ha) as ha,
                            sum(c.surf_frag_cover_pct * m.area_in_box_ha)
                              / nullif(sum(m.area_in_box_ha) filter (where c.surf_frag_cover_pct is not null), 0)
                              as frag,
                            sum(c.albedodry_r * m.area_in_box_ha)
                              / nullif(sum(m.area_in_box_ha) filter (where c.albedodry_r is not null), 0) as albedo
                     from soils.map_unit m left join soils.component c on c.cokey = m.dom_cokey
                     where m.ground_type is not null group by 1) s
               where g.id = s.ground_type""")
        dropped = cur.execute(
            """delete from soils.ground_type g
               where not exists (select 1 from soils.map_unit m where m.ground_type = g.id)""").rowcount

        counts = dict(zip(
            ("survey_areas", "map_units", "components", "horizons", "polygons", "ground_types",
             "ground_types_ada_canyon", "ground_types_misc", "area_in_box_ha", "area_not_surveyed_ha",
             "empty_geom_lo", "map_units_without_z8"),
            cur.execute(
                """select (select count(*) from soils.survey_area), (select count(*) from soils.map_unit),
                          (select count(*) from soils.component), (select count(*) from soils.horizon),
                          (select count(*) from soils.polygon), (select count(*) from soils.ground_type),
                          (select count(distinct ground_type) from soils.map_unit
                           where areasymbol in ('ID001', 'ID665')),
                          (select count(*) from soils.ground_type where misc is not null),
                          (select round(sum(area_in_box_m2)::numeric / 1e4) from soils.polygon),
                          (select coalesce(round(sum(m.area_in_box_ha)::numeric), 0) from soils.map_unit m
                           join soils.ground_type g on g.id = m.ground_type where g.misc = 'nodata'),
                          (select count(*) from soils.polygon where geom_lo is null or ST_IsEmpty(geom_lo)),
                          (select count(*) from soils.map_unit where geom_z8 is null)""").fetchone()))
        counts["area_in_box_ha"] = float(counts["area_in_box_ha"] or 0)
        counts["area_not_surveyed_ha"] = float(counts["area_not_surveyed_ha"] or 0)
        counts.update(loaded=todo, skipped=skipped, polygons_loaded=n, polygons_repaired=repaired,
                      ground_types_dropped=dropped)
        cur.execute("update soils.build set finished_at = clock_timestamp(), counts = %s::jsonb where build_id = %s",
                    (json.dumps(counts), bid))

        version = None
        if cur.execute("select to_regclass('core.layer_version') is not null").fetchone()[0]:
            from ingest import layer_version
            for layer in TILE_LAYERS:
                version = layer_version.record(
                    conn, layer, license=ssurgo.SOURCE["license"], republish="yes", credit=ssurgo.SOURCE["credit"],
                    build=bid, features=counts["polygons"], note=f"soils-load {', '.join(todo)}")

    stats = {"build": bid, "loaded": ", ".join(todo), "map units": len(d.map_units),
             "components": len(d.components), "horizons": len(d.horizons), "polygons": n,
             "repaired": repaired, "ground types (all)": counts["ground_types"],
             "area in box (ha, all)": counts["area_in_box_ha"]}
    if skipped:
        stats["skipped"] = ", ".join(skipped)
    stats["tiles"] = f"{TILE_LAYERS[0]} {version}" if version else "no core.layer_version (migration 0020): no version"
    return stats


def run(conn, pkg, areas=None, force=False):
    """load() with the source registered and the load logged in ops.fetch; commits."""
    from ingest import db
    todo, skipped = pending(conn, pkg, areas, force)
    if not todo:
        return nothing_to_do(skipped)            # not logged: nothing was read
    db.ensure_source(conn, ssurgo.SOURCE)
    with db.Fetch(conn, ssurgo.SOURCE["name"]) as f:        # no request made: robots and status stay empty
        f.bytes = sum(os.path.getsize(pkg.path(name)) for name in pkg.meta["files"])
        stats = load(conn, pkg, areas=areas, force=force)
        f.records = stats.get("polygons", 0)
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m ingest soils-load", description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="folder", required=True,
                    help="a folder written by plugins/soils/build/prepare.py (prepare.json, polygons.geojsonl, tabular/)")
    ap.add_argument("--areas", help="only these survey areas, comma-separated (e.g. ID001,ID665)")
    ap.add_argument("--force", action="store_true", help="reload areas even when their saverest is already loaded")
    ap.add_argument("--dry-run", action="store_true", help="check and derive the package; write nothing")
    args = ap.parse_args(argv)
    areas = [a.strip().upper() for a in args.areas.split(",") if a.strip()] if args.areas else None
    try:
        pkg = package.read(args.folder)
        if args.dry_run:
            todo, _ = plan(pkg, {}, areas, force=True)
            d = package.derive(pkg, todo)
            polygons = sum(1 for _ in pkg.polygons(set(todo)))
            print(f"soils-load (dry run): {', '.join(todo)}: {len(d.map_units)} map units, {len(d.components)} "
                  f"components, {len(d.horizons)} horizons, {polygons} polygons, {len(d.ground_types)} ground types",
                  flush=True)
            return 0
        from ingest import db
        with db.connect() as conn:
            stats = run(conn, pkg, areas=areas, force=args.force)
            conn.commit()
            conn.execute("analyze soils.map_unit, soils.component, soils.horizon, soils.polygon, soils.ground_type")
            conn.commit()
    except package.PackageError as err:
        print(f"soils-load: {err}", file=sys.stderr, flush=True)
        return 1
    print("soils-load: " + ", ".join(f"{k} {v}" for k, v in stats.items()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
