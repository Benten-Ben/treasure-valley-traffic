"""Export OpenStreetMap's paved paths: `python3 -m ingest trails-export` (plan P6-app; C9, C17, C18; basemap/ground/README.md).

Writes $TVT_ARCHIVE/trails/export/<build>/ through the ground's export contract (basemap/ground/manifest.py), with
manifest.json last, from trails.osm_path and trails.osm_area, read in one snapshot. As a run of the build
`trails-export` (ingest/builds.py), which marks the base bake (`landscape-bake`) out of date.

| Layer | File | Base | What |
|---|---|---|---|
| `paved_paths` | paved_paths.fgb | yes | every active, public, paved way, EPSG:32611: `id` (the OSM way id), `kind`, `material` (asphalt, concrete, paving_stones, or paved when the tag names no other), `w` (the tagged width in metres, else the estimate by kind and surface ⚠️) |
| `paved_areas` | paved_areas.fgb | yes | the pedestrian and footway areas tagged paved, or not tagged at all (a tag we cannot place, such as woodchips, is left out): `id` (2 x the OSM id, +1 for a relation), `kind`, `material` (as the paths', `unknown` when the area names no surface) |

Both layers are baked from z15 (`minzoom` 15, an integer for the manifest; the Trails layer's style shows them from
z15.5, which is the app's concern). Left out: ways closed to the public (`no_access`, plan C18: access=private or no
unless foot, bicycle or horse is opened), informal ways (the Trails layer's own rules hide them near closures, which the base may not read), sidewalks and crossings (paving's), and anything not paved (C9: unpaved
ways are never in the base; they come from the plugin's own tiles).

Inputs: trails/osm_paths only (ODbL, republish yes, credited "© OpenStreetMap contributors"), the licence and
republish the plugin.json records for it. Never trails_match, Ridge to Rivers' trails or the City's layers: the bake
refuses those (basemap/landscape/plan.py NEVER), and nothing here reads their tables.

No column may be NULL: PostGIS's ST_AsFlatGeobuf writes the next column's value under a NULL column's index, so
every column is coalesced (as water's export does).

Standard library plus psycopg, basemap/ground (the export contract) and basemap/landscape's plan (the bake's rules
for a base layer), both of which the ingest image carries (ingest/Dockerfile).
"""

import argparse
import json
import os
import shutil
import sys

from basemap.ground import manifest as M
from basemap.landscape import plan as bake_plan
from ingest import osm_extract

from .sources import osm_paths

BUILD = "trails-export"
THEN = ("landscape-bake",)
COMMAND = "python3 -m ingest trails-export"
MIN_FEATURES = {"paved_paths": 1000}     # far fewer would be a broken load, not the valley
MINZOOM = 15

MATERIAL = """case
    when lower(btrim(surface_tag)) in ('asphalt', 'chipseal') then 'asphalt'
    when left(lower(btrim(surface_tag)), 8) = 'concrete' then 'concrete'
    when lower(btrim(surface_tag)) in ('paving_stones', 'bricks', 'sett') then 'paving_stones'
    else 'paved' end"""
AREA_MATERIAL = MATERIAL.replace("else 'paved' end", "when surface_tag is null then 'unknown'\n    else 'paved' end")

# ROWS_* are the rows, so a test can check them.
PATHS_ROWS = f"""
  select osm_id as id, kind, {MATERIAL} as material,
         round((case when width_m > 0 then width_m else width_est_m end)::numeric, 2)::float8 as w,
         ST_Transform(geom, 32611) as geom
  from trails.osm_path
  where active and surface = 'paved' and not no_access
    and not informal                         -- the Trails layer draws these, under its own rules
    and coalesce(tags->>'footway', '') not in ('sidewalk', 'crossing', 'access_aisle', 'traffic_island')
  order by osm_id"""
AREAS_ROWS = f"""
  select * from (
    select (osm_id * 2 + (osm_type = 'r')::int) as id, kind, {AREA_MATERIAL} as material,
           ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(geom, 32611)), 3)) as geom,
           osm_type, osm_id
    from trails.osm_area
    where active and not no_access and not ST_IsEmpty(geom)
      and (surface = 'paved' or (surface = 'unknown' and surface_tag is null))) a
  where not ST_IsEmpty(geom)
  order by osm_type, osm_id"""
PATHS_SQL = f"select ST_AsFlatGeobuf(q, true, 'geom') from ({PATHS_ROWS}) q"
AREAS_SQL = f"select ST_AsFlatGeobuf(q, true, 'geom') from (select id, kind, material, geom from ({AREAS_ROWS}) r) q"


class ExportError(ValueError):
    pass


def input_entry(version=None):
    """The manifest's one input: OpenStreetMap's paths, as plugin.json records the osm_paths source."""
    src = osm_paths.SOURCE
    entry = {"name": "osm", "licence": "ODbL-1.0", "republish": "yes", "credit": src["credit"],
             "source": "trails/osm_paths", "url": src["url"],
             "note": "the valley cut of the Idaho extract (trails.osm_path and trails.osm_area)"}
    if version:
        entry["version"] = version
    return entry


def export(conn, archive, build=None, min_features=None):
    """Write an export folder and its manifest from trails.osm_path and trails.osm_area. Returns (Manifest, version
    note). Reads in one snapshot (a read-only repeatable-read transaction of its own, or the caller's when one is
    open)."""
    from psycopg import pq
    own = conn.info.transaction_status == pq.TransactionStatus.IDLE
    if own:
        conn.execute("set transaction isolation level repeatable read, read only")
    blobs = {"paved_paths": conn.execute(PATHS_SQL).fetchone()[0],
             "paved_areas": conn.execute(AREAS_SQL).fetchone()[0]}
    counts = {"paved_paths": conn.execute(f"select count(*) from ({PATHS_ROWS}) q").fetchone()[0],
              "paved_areas": conn.execute(f"select count(*) from ({AREAS_ROWS}) q").fetchone()[0]}
    state = osm_extract.db_state(conn, "trails.osm_paths")
    if own:
        conn.rollback()
    for name, least in (MIN_FEATURES if min_features is None else min_features).items():
        if counts[name] < least:
            raise ExportError(f"only {counts[name]} {name} in trails.osm_path and trails.osm_area; not exporting")
    if not blobs["paved_paths"]:
        raise ExportError("no paved paths (load an OpenStreetMap extract first: python3 -m ingest osm-load)")
    if not counts["paved_areas"]:
        blobs.pop("paved_areas")                 # a base layer without features is not built; leave it out
    load = (f"extract {state.get('extract_file') or '?'} (md5 {state.get('md5') or '?'})" if state
            else "unknown extract")
    folder = M.export_dir(archive, "trails", build or M.build_id())
    os.makedirs(folder)
    try:
        for name, blob in blobs.items():
            with open(os.path.join(folder, f"{name}.fgb"), "wb") as f:
                f.write(bytes(blob))
        layers = [{"name": "paved_paths", "file": "paved_paths.fgb", "format": "FlatGeobuf", "geometry": "LineString",
                   "inputs": ["osm"], "base": True, "minzoom": MINZOOM, "maxzoom": 16,
                   "title": "Paved paths, footways, cycleways and steps",
                   "note": "id: the OSM way id; material: asphalt, concrete, paving_stones, or paved; w: the tagged "
                           "width in metres, else an estimate by kind and surface ⚠️; ways closed to the public, "
                           "sidewalks, crossings and unpaved ways left out"}]
        if "paved_areas" in blobs:
            layers.append({"name": "paved_areas", "file": "paved_areas.fgb", "format": "FlatGeobuf",
                           "geometry": "MultiPolygon", "inputs": ["osm"], "base": True, "minzoom": MINZOOM,
                           "maxzoom": 16, "title": "Pedestrian and footway areas",
                           "note": "id: 2 x the OSM id, +1 for a relation; areas whose surface tag is not paved and areas "
                                   "closed to the public left out; material unknown: no surface tagged"})
        m = M.write(folder, "trails", inputs=[input_entry(load)], layers=layers, command=COMMAND,
                    note=f"trails.osm_path and trails.osm_area ({load}): "
                         + ", ".join(f"{k} {v}" for k, v in counts.items()))
        visibility = bake_plan.plugin_visibility()
        for lay in m.layers:
            if lay["base"]:
                bake_plan.check_base(lay, visibility, m.inputs)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return m, load


def main(argv=None):
    ap = argparse.ArgumentParser(prog=COMMAND, description=__doc__.split("\n")[0])
    ap.parse_args(argv)
    archive = os.environ.get("TVT_ARCHIVE")
    if not archive or not os.path.isdir(archive):
        print("trails-export: set TVT_ARCHIVE to the archive folder", file=sys.stderr)
        return 1
    from ingest import builds, db
    try:
        with db.connect() as conn:
            with builds.Run(conn, BUILD, then=THEN) as run:
                m, load = export(conn, archive)
                run.note = f"{m.folder} from {load}"
    except (ExportError, M.ManifestError, bake_plan.BakeError, OSError) as err:
        print(f"trails-export: {err}", file=sys.stderr, flush=True)
        return 1
    print(f"trails-export: {m.folder}: " + ", ".join(
        f"{lay.name} ({lay['bytes']:,} bytes, {lay['features']:,} features)" for lay in m.layers), flush=True)
    print(json.dumps({"licence": {lay.name: lay["licence"] for lay in m.layers},
                      "republish": {lay.name: lay["republish"] for lay in m.layers}}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
