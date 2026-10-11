"""Export the water network: `python3 -m ingest water-export` (plan P4-data; C5, C6, C17; basemap/ground/README.md).

Writes $TVT_ARCHIVE/water/export/<build>/ through the ground's export contract (basemap/ground/manifest.py), with
manifest.json last, from the newest water-build, read in one snapshot. As a run of the build `water-export`
(ingest/builds.py), which marks the base bake (`landscape-bake`) out of date.

| Layer | File | Base | What |
|---|---|---|---|
| `reaches` | reaches.fgb | yes | every drawn line, EPSG:32611: `id` (water.reach.id, stable across builds: the canal season's feature-state), `kind`, `name` ('' for none), `width_m`, `intermittent`, `piped`, `nhd_only`, `canal` (water.canal.id, 0 for none), `minzoom` (the bake's directive) |
| `bodies` | bodies.fgb | yes | every drawn area: `id`, `kind`, `name` ('' for none), `intermittent`, `nhd_only`, `minzoom` |
| `mask` | mask.fgb | no | the ground's confident water (inputs.USES `water/mask`): every body but wetlands, and the reaches OSM draws or both sources agree on, buffered to their widths, with piped water and intermittent channels left out; `kind` |

Only what the map draws goes into the base: cards read the rest (sources, evidence, canals, gauges, IDWR's side
tables) from the plugin's own API. The base never reads IDWR (the bake refuses any input from an `idwr_*` source),
and the mask's geometry is OSM's and NHD's, all of it republishable (the ground's C17 rule).

Licences: the reaches and bodies carry OSM's geometry and NHD's facts, and on some canals HydroShare's names or its
type (a lateral, drain or field supply), which set their kinds and widths: ODbL, republish yes, credited "©
OpenStreetMap contributors; USGS National Hydrography Dataset; Tatum, Bittmann, Stone and Kaiser (2022), HydroShare
(CC BY 4.0; modified)". The mask buffers the reaches to those widths, so it lists the same inputs. HydroShare is an
input of the reaches and the mask only when the build took a name or a kind from it. Widths are estimates ⚠️
(rules.py). Each input's sha256 is the download's (the file at its url); the prepared GeoPackage loaded from it is
named in its note.

Standard library plus psycopg, basemap/ground (the export contract) and basemap/landscape's plan (the bake's rules
for a base layer), both of which the ingest image carries (ingest/Dockerfile).
"""

import argparse
import json
import os
import re
import shutil
import sys

from basemap.ground import inputs as GI
from basemap.ground import manifest as M
from basemap.landscape import plan as bake_plan

from .sources import hydroshare_canals, nhd_hr, osm_waterways

BUILD = "water-export"
THEN = ("landscape-bake",)
COMMAND = "python3 -m ingest water-export"
MIN_FEATURES = {"reaches": 1000, "bodies": 1000}     # far fewer would be a broken build, not the valley

# No column may be NULL: PostGIS 3.6.4's ST_AsFlatGeobuf writes the next column's value under a NULL column's index
# (GDAL then reads the canal id as the name, or fails on the feature), so names are '' when there's none and the canal
# 0. ROWS_* are the rows, so a test can check them.
REACHES_ROWS = """
  select id, kind, coalesce(name, '') as name, width_m::float8 as width_m, intermittent, piped,
         geometry_from = 'nhd' as nhd_only, coalesce(canal_id, 0) as canal, minzoom::int as minzoom,
         ST_Transform(geom, 32611) as geom
  from water.reach where build_id = %(build)s order by id"""
BODIES_ROWS = """
  select id, kind, coalesce(name, '') as name, intermittent, geometry_from = 'nhd' as nhd_only,
         minzoom::int as minzoom, ST_Multi(ST_Transform(geom, 32611)) as geom
  from water.body where build_id = %(build)s and not ST_IsEmpty(geom) order by id"""
REACHES_SQL = f"select ST_AsFlatGeobuf(q, true, 'geom') from ({REACHES_ROWS}) q"
BODIES_SQL = f"select ST_AsFlatGeobuf(q, true, 'geom') from ({BODIES_ROWS}) q"
MASK_SQL = """
select ST_AsFlatGeobuf(q, true, 'geom') from (
  select kind, geom from (
    select kind, ST_Multi(ST_CollectionExtract(ST_MakeValid(ST_Transform(geom, 32611)), 3)) geom
    from water.body where build_id = %(build)s and kind <> 'wetland'
    union all
    select kind, ST_Multi(ST_Buffer(ST_Transform(geom, 32611), width_m / 2.0, 'endcap=flat join=round')) geom
    from water.reach
    where build_id = %(build)s and not piped and not intermittent and (geometry_from = 'osm' or confirmed)) m
  where not ST_IsEmpty(geom)) q"""


class ExportError(ValueError):
    pass


def _hash(h):
    return isinstance(h, str) and re.fullmatch(r"[0-9a-f]{64}", h) is not None


def _download(entry, note):
    """The manifest's sha256 (the download's: what the input's url serves) and a note naming the prepared file that
    was loaded from it, from a load's entry in water.build.inputs."""
    entry = entry or {}
    out = {"sha256": entry["download_sha256"]} if _hash(entry.get("download_sha256")) else {}
    if entry.get("file") and _hash(entry.get("sha256")):
        note += f"; loaded from {entry['file']} (sha256 {entry['sha256']}), prepared from "
        note += f"{entry.get('download') or 'the download'}"
    return {**out, "note": note}


def input_entries(build_inputs):
    """The manifest's inputs, from the build's (water.build.inputs)."""
    osm = build_inputs.get("osm_waterways") or {}
    nhd = build_inputs.get("nhd_hr") or {}
    hs = build_inputs.get("hydroshare_canals") or {}
    extract = f"extract {osm.get('extract') or '?'} (md5 {osm.get('md5') or '?'})"
    return [{"name": "osm", "licence": "ODbL-1.0", "republish": "yes", "credit": osm_waterways.SOURCE["credit"],
             "source": "water/osm_waterways", "version": extract,
             "note": "the valley cut of the Idaho extract; the box's Oregon slice has no OpenStreetMap data"},
            {"name": "nhd", "licence": "public-domain", "republish": "yes", "credit": nhd_hr.SOURCE["credit"],
             "source": "water/nhd_hr", "url": nhd_hr.URL, "version": "HU4 1705, published 2023-12-09",
             **_download(nhd, "NAD83 read as WGS 84 (the ground's datum policy)")},
            {"name": "hydroshare", "licence": "CC-BY-4.0", "republish": "yes",
             "credit": hydroshare_canals.SOURCE["credit"], "source": "water/hydroshare_canals",
             "url": hydroshare_canals.URL, "doi": hydroshare_canals.DOI,
             **_download(hs, "canal names where OpenStreetMap and NHD have none, and the kinds of unnamed canals")}]


def export(conn, archive, build=None, min_features=None):
    """Write an export folder and its manifest from the newest water-build. Returns the Manifest. Reads in one
    snapshot (a read-only repeatable-read transaction of its own, or the caller's when one is open)."""
    from psycopg import pq
    own = conn.info.transaction_status == pq.TransactionStatus.IDLE
    if own:
        conn.execute("set transaction isolation level repeatable read, read only")
    row = conn.execute("""select id, inputs, counts, finished_at from water.build
                          where finished_at is not null order by id desc limit 1""").fetchone()
    if row is None:
        raise ExportError("no finished water-build (run python3 -m ingest water-build first)")
    build_id, build_inputs, counts, finished = row
    blobs = {}
    for name, sql in (("reaches", REACHES_SQL), ("bodies", BODIES_SQL), ("mask", MASK_SQL)):
        blobs[name] = conn.execute(sql, {"build": build_id}).fetchone()[0]
    named_by_hs = conn.execute("select count(*) from water.reach where build_id = %s and name_from = 'hydroshare'",
                               (build_id,)).fetchone()[0]
    if own:
        conn.rollback()
    for name, least in (MIN_FEATURES if min_features is None else min_features).items():
        n = counts.get(name)
        if n is not None and n < least:
            raise ExportError(f"build {build_id} has only {n} {name}; not exporting it")
    if not all(blobs.values()):
        raise ExportError(f"build {build_id}: an empty layer ({', '.join(k for k, v in blobs.items() if not v)})")

    # HydroShare is an input only when the reaches carry its names or kinds (CC BY: credited wherever they show), and
    # then of the mask too, whose widths follow them.
    hydroshare = bool(named_by_hs or (counts or {}).get("kinds_from_hydroshare"))
    inputs = [i for i in input_entries(build_inputs or {}) if i["name"] != "hydroshare" or hydroshare]
    base_inputs = [i["name"] for i in inputs]
    folder = M.export_dir(archive, "water", build or M.build_id())
    os.makedirs(folder)
    try:
        for name, blob in blobs.items():
            with open(os.path.join(folder, f"{name}.fgb"), "wb") as f:
                f.write(bytes(blob))
        layers = [
            {"name": "reaches", "file": "reaches.fgb", "format": "FlatGeobuf", "geometry": "LineString",
             "inputs": base_inputs, "base": True, "minzoom": 8, "maxzoom": 16,
             "title": "Rivers, creeks, canals, laterals, ditches and drains",
             "note": "id: water.reach.id (stable across builds); minzoom: each line's first zoom; nhd_only: in NHD "
                     "only (topo-era, drawn lighter); canal: water.canal.id, 0 for none; name: '' for none; width_m "
                     "estimated ⚠️ unless OSM tags it"},
            {"name": "bodies", "file": "bodies.fgb", "format": "FlatGeobuf", "geometry": "MultiPolygon",
             "inputs": ["osm", "nhd"], "base": True, "minzoom": 8, "maxzoom": 16,
             "title": "Rivers drawn as areas, lakes, reservoirs, ponds, basins, wetlands and pools",
             "note": "id: water.body.id (an OSM way's 2 x id, a relation's 2 x id + 1, NHD-only 2^51 + a hash); "
                     "name: '' for none; pools from z15, wetlands from z14"},
            {"name": "mask", "file": "mask.fgb", "format": "FlatGeobuf", "geometry": "MultiPolygon",
             "inputs": base_inputs, "base": False, "title": "Confident water, for the ground",
             "note": "every body but wetlands, and the reaches OSM draws or both sources agree on, buffered to "
                     "their widths (which follow their names and kinds); piped water and intermittent channels left "
                     "out"},
        ]
        m = M.write(folder, "water", inputs=inputs, layers=layers, command=COMMAND,
                    note=f"water-build {build_id} of {finished:%Y-%m-%d %H:%M} UTC: "
                         + ", ".join(f"{k} {v}" for k, v in counts.items() if k in ("reaches", "bodies", "canals")))
        choice = GI.resolve({"water": m}).choice("water/mask")
        if choice.fallback:
            raise ExportError(f"the ground wouldn't read water/mask: {choice.reason}")
        visibility = bake_plan.plugin_visibility()
        for lay in m.layers:
            if lay["base"]:
                bake_plan.check_base(lay, visibility, m.inputs)
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return m, build_id


def main(argv=None):
    ap = argparse.ArgumentParser(prog=COMMAND, description=__doc__.split("\n")[0])
    ap.parse_args(argv)
    archive = os.environ.get("TVT_ARCHIVE")
    if not archive or not os.path.isdir(archive):
        print("water-export: set TVT_ARCHIVE to the archive folder", file=sys.stderr)
        return 1
    from ingest import builds, db
    try:
        with db.connect() as conn:
            with builds.Run(conn, BUILD, then=THEN) as run:
                m, build_id = export(conn, archive)
                run.note = f"{m.folder} from water-build {build_id}"
    except (ExportError, M.ManifestError, GI.InputError, bake_plan.BakeError, OSError) as err:
        print(f"water-export: {err}", file=sys.stderr, flush=True)
        return 1
    print(f"water-export: {m.folder}: " + ", ".join(
        f"{lay.name} ({lay['bytes']:,} bytes, {lay['features']:,} features)" for lay in m.layers), flush=True)
    print(json.dumps({"licence": {lay.name: lay["licence"] for lay in m.layers},
                      "republish": {lay.name: lay["republish"] for lay in m.layers}}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
